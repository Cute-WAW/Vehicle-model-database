# -*- coding: utf-8 -*-
"""
Local offline comparison between curve and LightGBM predictors.

Unlike the older evaluation scripts, this one does not call a remote HTTP API.
It executes the current local prediction chain twice with different
`model_strategy_config` settings so the comparison is reproducible inside the
repo workspace.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from residual_predictor_step5 import ResidualPredictor  # noqa: E402


DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "youxinpai_vehicles-2026年1-3月份.csv"
DEFAULT_RESULTS_PATH = PROJECT_ROOT / "experiment" / "curve_vs_lightgbm_results.csv"
DEFAULT_SUMMARY_PATH = PROJECT_ROOT / "experiment" / "curve_vs_lightgbm_summary.json"
DEFAULT_BUCKET_PATH = PROJECT_ROOT / "experiment" / "curve_vs_lightgbm_bucket_stats.csv"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "doc" / "价格预测" / "阶段五-新旧模型对比报告.md"


def parse_grade(rating_code: str) -> str:
    try:
        score = int(str(rating_code)[:2])
        if score >= 80:
            return "优"
        if score >= 60:
            return "中"
        return "差"
    except Exception:
        return "中"


def parse_price(price_str: str) -> Optional[float]:
    try:
        return float(str(price_str).replace("万元", "").replace("万", "").strip())
    except Exception:
        return None


def parse_mileage(mileage_str: str) -> Optional[float]:
    try:
        km = float(str(mileage_str).replace("公里", "").strip())
        return round(km / 10000, 4)
    except Exception:
        return None


def parse_date_to_months(date_str: str) -> Optional[int]:
    try:
        date_str = str(date_str).strip()
        year = int(date_str[:4])
        month = int(date_str[5:7])
        return year * 12 + month
    except Exception:
        return None


def parse_vehicle_name(name: str) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    parts = str(name).split("/")
    if len(parts) >= 2:
        brand = parts[0].strip()
        series = parts[1].strip()
        brand_series = f"{brand}-{series}"
        full_name = " ".join(parts).strip()
        return brand, series, brand_series, full_name
    return None, None, None, str(name)


def price_segment(price: Optional[float]) -> str:
    if price is None:
        return "未知"
    if price < 1:
        return "<1万"
    if price < 3:
        return "1-3万"
    if price < 5:
        return "3-5万"
    if price < 10:
        return "5-10万"
    if price < 20:
        return "10-20万"
    return ">20万"


def age_segment(years: float) -> str:
    if years < 3:
        return "0-3年"
    if years < 5:
        return "3-5年"
    if years < 8:
        return "5-8年"
    if years < 10:
        return "8-10年"
    return ">10年"


def is_nev(vehicle_name: str) -> bool:
    vehicle_name = str(vehicle_name).upper()
    keywords = ["电", "混动", "DM-I", "EV", "PHEV", "增程", "蔚来", "小鹏", "理想", "特斯拉", "MODEL", "ID."]
    return any(k in vehicle_name for k in keywords)


def mileage_bucket(mileage: float, threshold: float) -> str:
    return "高里程" if mileage >= threshold else "低里程"


def price_extreme_bucket(price: float) -> str:
    if price < 1:
        return "极端低价"
    if price >= 10:
        return "极端高价"
    return "中间价"


def compute_r2(actual: pd.Series, predicted: pd.Series) -> Optional[float]:
    if len(actual) < 2 or actual.nunique() < 2:
        return None
    denominator = ((actual - actual.mean()) ** 2).sum()
    if denominator <= 1e-12:
        return None
    numerator = ((predicted - actual) ** 2).sum()
    return round(1 - numerator / denominator, 4)


def prepare_dataset(data_path: Path, sample_size: int, random_state: int) -> pd.DataFrame:
    df = pd.read_csv(data_path, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()

    df["actual_price"] = df["成交价格"].apply(parse_price)
    df["mileage_wan"] = df["行驶里程"].apply(parse_mileage)
    df["trade_months"] = df["成交时间"].apply(parse_date_to_months)
    df["reg_months"] = df["上牌时间"].apply(parse_date_to_months)
    df["years"] = (df["trade_months"] - df["reg_months"]) / 12
    df["grade"] = df["车辆评级"].apply(parse_grade)

    parsed = df["车辆名称"].apply(parse_vehicle_name)
    df["brand"] = parsed.apply(lambda x: x[0])
    df["series"] = parsed.apply(lambda x: x[1])
    df["brand_series"] = parsed.apply(lambda x: x[2])
    df["vehicle_full_name"] = parsed.apply(lambda x: x[3])

    valid = df[
        df["actual_price"].notna()
        & df["mileage_wan"].notna()
        & df["years"].notna()
        & (df["years"] > 0)
        & (df["years"] < 30)
        & (df["actual_price"] > 0)
        & df["brand_series"].notna()
    ].copy()

    valid["price_seg"] = valid["actual_price"].apply(price_segment)
    valid["age_seg"] = valid["years"].apply(age_segment)
    valid["energy_type"] = valid["车辆名称"].apply(lambda x: "新能源" if is_nev(x) else "燃油")
    valid["price_extreme_bucket"] = valid["actual_price"].apply(price_extreme_bucket)

    mileage_threshold = float(valid["mileage_wan"].median())
    valid["mileage_bucket"] = valid["mileage_wan"].apply(lambda x: mileage_bucket(x, mileage_threshold))

    if sample_size > 0 and sample_size < len(valid):
        sampled_parts = []
        for seg, seg_df in valid.groupby("price_seg"):
            n = min(len(seg_df), max(1, round(sample_size * len(seg_df) / len(valid))))
            sampled_parts.append(seg_df.sample(n=n, random_state=random_state))
        sample = pd.concat(sampled_parts).sample(frac=1, random_state=random_state).head(sample_size)
        return sample.reset_index(drop=True)

    return valid.reset_index(drop=True)


def evaluate_family(
    sample_df: pd.DataFrame,
    model_family: str,
    allow_curve_fallback: bool,
    residual_data_csv: str,
) -> Tuple[pd.DataFrame, Dict]:
    predictor = ResidualPredictor(residual_data_csv=residual_data_csv)
    predictor.model_strategy_config = {
        "default_model_family": model_family,
        "allow_curve_fallback": allow_curve_fallback,
    }

    rows: List[Dict] = []
    for idx, row in sample_df.iterrows():
        result = predictor.predict(
            vehicle_full_name=row["vehicle_full_name"],
            brand_series=row["brand_series"],
            years=float(row["years"]),
            grade=row["grade"],
            city=str(row["车辆所在地"]),
            mileage=float(row["mileage_wan"]),
            new_price=None,
        )

        debug = result.debug.to_dict() if result.debug else {}
        grade_key = {"优": "a", "中": "b", "差": "c"}.get(row["grade"], "b")
        price_matrix = result.price_matrix or {}
        c2b = price_matrix.get("c2BPrices", {}).get(grade_key, {})
        b2b = price_matrix.get("b2BPrices", {}).get(grade_key, {})
        actual_price = float(row["actual_price"])
        predicted_price = result.predicted_price if result.success else None
        abs_error = abs(predicted_price - actual_price) if predicted_price is not None else None
        abs_pct_error = abs(predicted_price - actual_price) / actual_price * 100 if predicted_price not in (None, 0) else None

        rows.append({
            "sample_idx": idx + 1,
            "family": model_family,
            "allow_curve_fallback": allow_curve_fallback,
            "vehicle_name": row["车辆名称"],
            "brand": row["brand"],
            "series": row["series"],
            "brand_series": row["brand_series"],
            "grade": row["grade"],
            "years": round(float(row["years"]), 2),
            "mileage_wan": float(row["mileage_wan"]),
            "city": str(row["车辆所在地"]),
            "actual_price": actual_price,
            "price_seg": row["price_seg"],
            "age_seg": row["age_seg"],
            "energy_type": row["energy_type"],
            "mileage_bucket": row["mileage_bucket"],
            "price_extreme_bucket": row["price_extreme_bucket"],
            "success": result.success,
            "error_message": result.error_message,
            "new_price": result.new_price,
            "predicted_price": predicted_price,
            "residual_rate": result.residual_rate if result.success else None,
            "c2b_low": c2b.get("low"),
            "c2b_high": c2b.get("up"),
            "b2b_low": b2b.get("low"),
            "b2b_high": b2b.get("up"),
            "hit_c2b": c2b.get("low") is not None and c2b.get("up") is not None and c2b.get("low") <= actual_price <= c2b.get("up"),
            "hit_b2b": b2b.get("low") is not None and b2b.get("up") is not None and b2b.get("low") <= actual_price <= b2b.get("up"),
            "abs_error": abs_error,
            "abs_pct_error": abs_pct_error,
            "debug_model_used": debug.get("model_used", ""),
            "debug_model_name": debug.get("model_name", ""),
            "debug_model_type": debug.get("model_type", ""),
            "debug_model_family": debug.get("model_family", ""),
            "debug_final_model_family": debug.get("final_model_family", ""),
            "debug_requested_model_family": debug.get("requested_model_family", ""),
            "debug_fallback_triggered": debug.get("fallback_triggered", False),
            "debug_fallback_reason": debug.get("fallback_reason", ""),
        })

    result_df = pd.DataFrame(rows)
    summary = compute_family_summary(result_df)
    return result_df, summary


def compute_family_summary(result_df: pd.DataFrame) -> Dict:
    total = len(result_df)
    success_df = result_df[result_df["success"] == True].copy()
    success_count = len(success_df)
    summary = {
        "total_samples": total,
        "success_count": success_count,
        "success_rate": round(success_count / total * 100, 2) if total else 0.0,
        "fallback_count": int(success_df["debug_fallback_triggered"].sum()) if not success_df.empty else 0,
    }

    if success_df.empty:
        return summary

    err_df = success_df[success_df["abs_pct_error"].notna()].copy()
    summary.update({
        "c2b_hit_rate": round(success_df["hit_c2b"].mean() * 100, 2),
        "b2b_hit_rate": round(success_df["hit_b2b"].mean() * 100, 2),
        "mae": round(float(err_df["abs_error"].mean()), 3) if not err_df.empty else None,
        "mape": round(float(err_df["abs_pct_error"].mean()), 2) if not err_df.empty else None,
        "median_ape": round(float(err_df["abs_pct_error"].median()), 2) if not err_df.empty else None,
        "r2": compute_r2(err_df["actual_price"], err_df["predicted_price"]) if not err_df.empty else None,
        "avg_predicted_price": round(float(success_df["predicted_price"].mean()), 3),
    })
    return summary


def compute_bucket_stats(compare_df: pd.DataFrame) -> pd.DataFrame:
    bucket_columns = [
        ("age_seg", "车龄段"),
        ("brand_series", "品牌车系"),
        ("energy_type", "能源类型"),
        ("mileage_bucket", "里程桶"),
        ("price_extreme_bucket", "价格极端桶"),
    ]

    rows: List[Dict] = []
    for family, family_df in compare_df.groupby("family"):
        success_df = family_df[family_df["success"] == True].copy()
        for column, label in bucket_columns:
            grouped = success_df.groupby(column)
            for bucket_value, bucket_df in grouped:
                if bucket_df.empty:
                    continue
                rows.append({
                    "family": family,
                    "bucket_type": label,
                    "bucket_value": bucket_value,
                    "sample_count": len(bucket_df),
                    "success_rate": round(len(bucket_df) / len(family_df[family_df[column] == bucket_value]) * 100, 2)
                    if len(family_df[family_df[column] == bucket_value]) else 0.0,
                    "b2b_hit_rate": round(bucket_df["hit_b2b"].mean() * 100, 2),
                    "c2b_hit_rate": round(bucket_df["hit_c2b"].mean() * 100, 2),
                    "mape": round(float(bucket_df["abs_pct_error"].dropna().mean()), 2) if bucket_df["abs_pct_error"].notna().any() else None,
                    "r2": compute_r2(bucket_df["actual_price"], bucket_df["predicted_price"]),
                })
    return pd.DataFrame(rows)


def build_summary_json(
    sample_size: int,
    data_path: Path,
    curve_summary: Dict,
    lightgbm_summary: Dict,
    bucket_stats_path: Path,
) -> Dict:
    replacement_conditions = {
        "mape_not_worse": bool(
            curve_summary.get("mape") is not None
            and lightgbm_summary.get("mape") is not None
            and lightgbm_summary["mape"] <= curve_summary["mape"]
        ),
        "r2_not_worse": bool(
            curve_summary.get("r2") is not None
            and lightgbm_summary.get("r2") is not None
            and lightgbm_summary["r2"] >= curve_summary["r2"]
        ),
        "b2b_hit_rate_not_worse": bool(
            curve_summary.get("b2b_hit_rate") is not None
            and lightgbm_summary.get("b2b_hit_rate") is not None
            and lightgbm_summary["b2b_hit_rate"] >= curve_summary["b2b_hit_rate"]
        ),
        "success_rate_not_worse": bool(
            curve_summary.get("success_rate") is not None
            and lightgbm_summary.get("success_rate") is not None
            and lightgbm_summary["success_rate"] >= curve_summary["success_rate"]
        ),
    }
    return {
        "generated_at": datetime.now().isoformat(),
        "data_path": str(data_path),
        "sample_size": sample_size,
        "curve": curve_summary,
        "lightgbm": lightgbm_summary,
        "deltas": {
            "success_rate": round(lightgbm_summary.get("success_rate", 0) - curve_summary.get("success_rate", 0), 2),
            "b2b_hit_rate": round(lightgbm_summary.get("b2b_hit_rate", 0) - curve_summary.get("b2b_hit_rate", 0), 2),
            "mape": round((lightgbm_summary.get("mape") or 0) - (curve_summary.get("mape") or 0), 2),
            "r2": round((lightgbm_summary.get("r2") or 0) - (curve_summary.get("r2") or 0), 4),
        },
        "replacement_conditions": replacement_conditions,
        "lightgbm_ready_to_replace": all(replacement_conditions.values()),
        "bucket_stats_path": str(bucket_stats_path),
    }


def write_markdown_report(output_path: Path, summary: Dict) -> None:
    curve = summary["curve"]
    lightgbm = summary["lightgbm"]
    deltas = summary["deltas"]
    conditions = summary["replacement_conditions"]

    lines = [
        "# 阶段五：新旧模型对比报告",
        "",
        f"> 生成时间：{summary['generated_at']}",
        f"> 数据集：`{summary['data_path']}`",
        f"> 样本数：{summary['sample_size']}",
        "",
        "## 1. 总体结果",
        "",
        "| 指标 | curve | lightgbm | 差值(lightgbm-curve) |",
        "|:---|---:|---:|---:|",
        f"| 成功率 | {curve.get('success_rate', 0):.2f}% | {lightgbm.get('success_rate', 0):.2f}% | {deltas['success_rate']:.2f} |",
        f"| B2B 命中率 | {curve.get('b2b_hit_rate', 0):.2f}% | {lightgbm.get('b2b_hit_rate', 0):.2f}% | {deltas['b2b_hit_rate']:.2f} |",
        f"| C2B 命中率 | {curve.get('c2b_hit_rate', 0):.2f}% | {lightgbm.get('c2b_hit_rate', 0):.2f}% | {round((lightgbm.get('c2b_hit_rate',0)-curve.get('c2b_hit_rate',0)),2):.2f} |",
        f"| MAE(万元) | {curve.get('mae')} | {lightgbm.get('mae')} | {round((lightgbm.get('mae') or 0)-(curve.get('mae') or 0), 3):.3f} |",
        f"| MAPE(%) | {curve.get('mape')} | {lightgbm.get('mape')} | {deltas['mape']:.2f} |",
        f"| R² | {curve.get('r2')} | {lightgbm.get('r2')} | {deltas['r2']:.4f} |",
        "",
        "## 2. 替换条件判断",
        "",
        f"- `MAPE` 不劣于旧模型：{'是' if conditions['mape_not_worse'] else '否'}",
        f"- `R²` 不低于旧模型：{'是' if conditions['r2_not_worse'] else '否'}",
        f"- `B2B` 命中率不低于旧模型：{'是' if conditions['b2b_hit_rate_not_worse'] else '否'}",
        f"- 成功率不低于旧模型：{'是' if conditions['success_rate_not_worse'] else '否'}",
        "",
        f"**结论**：`LightGBM` {'达到' if summary['lightgbm_ready_to_replace'] else '未达到'} 当前替换条件。",
        "",
        "## 3. 说明",
        "",
        "- 本次对比在本地直接调用 `ResidualPredictor`，未走远端 HTTP 接口。",
        "- `curve` 评估使用默认模型家族。",
        "- `lightgbm` 评估关闭 `curve` 回退，以衡量新模型单独替换能力。",
        f"- 分桶统计详见：`{summary['bucket_stats_path']}`",
        "",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="本地 curve vs lightgbm 离线对比评估")
    parser.add_argument("--data", default=str(DEFAULT_DATA_PATH), help="评估数据文件路径")
    parser.add_argument("--sample-size", type=int, default=300, help="抽样数量，0 或负数表示全量")
    parser.add_argument("--random-state", type=int, default=42, help="随机种子")
    parser.add_argument("--results-output", default=str(DEFAULT_RESULTS_PATH), help="逐条对比结果输出路径")
    parser.add_argument("--summary-output", default=str(DEFAULT_SUMMARY_PATH), help="摘要 JSON 输出路径")
    parser.add_argument("--bucket-output", default=str(DEFAULT_BUCKET_PATH), help="分桶统计输出路径")
    parser.add_argument("--report-output", default=str(DEFAULT_REPORT_PATH), help="Markdown 报告输出路径")
    parser.add_argument("--residual-data-csv", default=str(PROJECT_ROOT / "output" / "merged_residual_value_data_with_dates.csv"), help="ResidualPredictor 使用的数据文件")
    args = parser.parse_args()

    data_path = Path(args.data)
    results_output = Path(args.results_output)
    summary_output = Path(args.summary_output)
    bucket_output = Path(args.bucket_output)
    report_output = Path(args.report_output)

    sample_df = prepare_dataset(data_path, args.sample_size, args.random_state)
    curve_df, curve_summary = evaluate_family(sample_df, "curve", True, args.residual_data_csv)
    lightgbm_df, lightgbm_summary = evaluate_family(sample_df, "lightgbm", False, args.residual_data_csv)

    compare_df = curve_df.merge(
        lightgbm_df,
        on=[
            "sample_idx",
            "vehicle_name",
            "brand",
            "series",
            "brand_series",
            "grade",
            "years",
            "mileage_wan",
            "city",
            "actual_price",
            "price_seg",
            "age_seg",
            "energy_type",
            "mileage_bucket",
            "price_extreme_bucket",
        ],
        suffixes=("_curve", "_lightgbm"),
    )

    bucket_stats = compute_bucket_stats(pd.concat([curve_df, lightgbm_df], ignore_index=True))
    summary = build_summary_json(len(sample_df), data_path, curve_summary, lightgbm_summary, bucket_output)

    results_output.parent.mkdir(parents=True, exist_ok=True)
    compare_df.to_csv(results_output, index=False, encoding="utf-8-sig")
    bucket_stats.to_csv(bucket_output, index=False, encoding="utf-8-sig")
    with open(summary_output, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    write_markdown_report(report_output, summary)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
