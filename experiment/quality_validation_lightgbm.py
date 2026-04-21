# -*- coding: utf-8 -*-
"""
Fine-grained quality validation for the LightGBM residual-value model.

Outputs:
    - experiment/lightgbm_quality_summary.json
    - experiment/lightgbm_quality_bucket_stats.csv
    - experiment/lightgbm_monotonicity_checks.csv
    - experiment/lightgbm_quality_cases.csv
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from residual_predictor_step5 import ResidualPredictor  # noqa: E402

# Reuse the stage-5 comparison data preparation and evaluation helpers.
from compare_curve_vs_lightgbm import (  # noqa: E402
    DEFAULT_DATA_PATH,
    prepare_dataset,
    evaluate_family,
    compute_r2,
)


DEFAULT_SUMMARY_PATH = PROJECT_ROOT / "experiment" / "lightgbm_quality_summary.json"
DEFAULT_BUCKET_PATH = PROJECT_ROOT / "experiment" / "lightgbm_quality_bucket_stats.csv"
DEFAULT_MONO_PATH = PROJECT_ROOT / "experiment" / "lightgbm_monotonicity_checks.csv"
DEFAULT_CASES_PATH = PROJECT_ROOT / "experiment" / "lightgbm_quality_cases.csv"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "doc" / "价格预测" / "阶段五-细粒度质量验证报告.md"

TOP_BRANDS = ["大众", "丰田", "本田", "日产", "比亚迪", "宝马", "奔驰"]


def summarize_bucket(df: pd.DataFrame, family: str, bucket_type: str, bucket_value: str) -> Dict:
    if df.empty:
        return {
            "family": family,
            "bucket_type": bucket_type,
            "bucket_value": bucket_value,
            "sample_count": 0,
            "success_rate": 0.0,
            "b2b_hit_rate": None,
            "c2b_hit_rate": None,
            "mae": None,
            "mape": None,
            "r2": None,
        }

    success_df = df[df["success"] == True].copy()
    err_df = success_df[success_df["abs_pct_error"].notna()].copy()
    return {
        "family": family,
        "bucket_type": bucket_type,
        "bucket_value": bucket_value,
        "sample_count": int(len(df)),
        "success_rate": round(len(success_df) / len(df) * 100, 2),
        "b2b_hit_rate": round(success_df["hit_b2b"].mean() * 100, 2) if not success_df.empty else None,
        "c2b_hit_rate": round(success_df["hit_c2b"].mean() * 100, 2) if not success_df.empty else None,
        "mae": round(float(err_df["abs_error"].mean()), 3) if not err_df.empty else None,
        "mape": round(float(err_df["abs_pct_error"].mean()), 2) if not err_df.empty else None,
        "r2": compute_r2(err_df["actual_price"], err_df["predicted_price"]) if not err_df.empty else None,
    }


def build_quality_buckets(compare_long_df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict] = []
    families = ["curve", "lightgbm"]

    # Old cars
    for family in families:
        family_df = compare_long_df[compare_long_df["family"] == family]
        rows.append(summarize_bucket(family_df[family_df["age_seg"] == ">10年"], family, "专题桶", "老车>10年"))

    # Energy buckets
    for family in families:
        family_df = compare_long_df[compare_long_df["family"] == family]
        for energy in ["新能源", "燃油"]:
            rows.append(summarize_bucket(family_df[family_df["energy_type"] == energy], family, "专题桶", f"能源-{energy}"))

    # Mileage buckets
    for family in families:
        family_df = compare_long_df[compare_long_df["family"] == family]
        for bucket in ["高里程", "低里程"]:
            rows.append(summarize_bucket(family_df[family_df["mileage_bucket"] == bucket], family, "专题桶", f"里程-{bucket}"))

    # Typical brands
    for family in families:
        family_df = compare_long_df[compare_long_df["family"] == family]
        for brand in TOP_BRANDS:
            brand_df = family_df[family_df["brand"] == brand]
            if len(brand_df) >= 5:
                rows.append(summarize_bucket(brand_df, family, "典型品牌", brand))

    return pd.DataFrame(rows)


def run_monotonicity_checks(
    source_df: pd.DataFrame,
    residual_data_csv: str,
    max_anchors: int = 40,
    years_from: int = 1,
    years_to: int = 15,
    increase_threshold: float = 0.005,
) -> pd.DataFrame:
    predictor = ResidualPredictor(residual_data_csv=residual_data_csv)
    predictor.model_strategy_config = {
        "default_model_family": "lightgbm",
        "allow_curve_fallback": False,
    }

    success_df = source_df[source_df["success"] == True].copy()
    anchors = success_df.drop_duplicates(subset=["brand_series", "grade", "city", "mileage_wan"]).head(max_anchors)
    rows: List[Dict] = []

    for _, anchor in anchors.iterrows():
        residual_rates: List[float] = []
        predicted_prices: List[float] = []
        fallback_flags: List[bool] = []
        requested_years = list(range(years_from, years_to + 1))

        for year in requested_years:
            result = predictor.predict(
                vehicle_full_name=anchor["vehicle_name"],
                brand_series=anchor["brand_series"],
                years=float(year),
                grade=anchor["grade"],
                city=anchor["city"],
                mileage=float(anchor["mileage_wan"]),
                new_price=float(anchor["new_price"]) if pd.notna(anchor["new_price"]) and anchor["new_price"] else None,
            )

            if result.success:
                residual_rates.append(float(result.residual_rate))
                predicted_prices.append(float(result.predicted_price))
                fallback_flags.append(bool(result.debug.fallback_triggered) if result.debug else False)
            else:
                residual_rates.append(np.nan)
                predicted_prices.append(np.nan)
                fallback_flags.append(False)

        increases = []
        for idx in range(len(residual_rates) - 1):
            current_rate = residual_rates[idx]
            next_rate = residual_rates[idx + 1]
            if np.isnan(current_rate) or np.isnan(next_rate):
                continue
            increases.append((requested_years[idx], requested_years[idx + 1], next_rate - current_rate))

        abnormal_steps = [item for item in increases if item[2] > increase_threshold]
        max_increase = max((item[2] for item in increases), default=0.0)
        rows.append({
            "vehicle_name": anchor["vehicle_name"],
            "brand": anchor["brand"],
            "brand_series": anchor["brand_series"],
            "grade": anchor["grade"],
            "city": anchor["city"],
            "mileage_wan": float(anchor["mileage_wan"]),
            "new_price": float(anchor["new_price"]) if pd.notna(anchor["new_price"]) and anchor["new_price"] else None,
            "checked_years": f"{years_from}-{years_to}",
            "valid_predictions": int(np.isfinite(np.array(residual_rates)).sum()),
            "abnormal_increase_steps": int(len(abnormal_steps)),
            "max_increase": round(float(max_increase), 6),
            "abnormal": len(abnormal_steps) > 0,
            "abnormal_step_detail": "; ".join(f"{a}->{b}:{delta:.4f}" for a, b, delta in abnormal_steps),
            "used_fallback": any(fallback_flags),
        })

    return pd.DataFrame(rows)


def build_case_samples(compare_df: pd.DataFrame) -> pd.DataFrame:
    merged = compare_df.copy()
    merged["mape_diff"] = merged["abs_pct_error_lightgbm"] - merged["abs_pct_error_curve"]
    merged["b2b_diff"] = merged["hit_b2b_lightgbm"].astype(int) - merged["hit_b2b_curve"].astype(int)

    cases = []
    best = merged.sort_values("mape_diff").head(5).copy()
    best["case_type"] = "lightgbm明显优于curve"
    cases.append(best)

    worst = merged.sort_values("mape_diff", ascending=False).head(5).copy()
    worst["case_type"] = "lightgbm明显劣于curve"
    cases.append(worst)

    old_car = merged[merged["age_seg"] == ">10年"].head(5).copy()
    old_car["case_type"] = "老车样本"
    cases.append(old_car)

    nev = merged[merged["energy_type"] == "新能源"].head(5).copy()
    nev["case_type"] = "新能源样本"
    cases.append(nev)

    fallback_like = merged[merged["debug_model_used_lightgbm"] == "car_type"].head(5).copy()
    fallback_like["case_type"] = "lightgbm车型类别兜底样本"
    cases.append(fallback_like)

    return pd.concat([df for df in cases if not df.empty], ignore_index=True)


def build_summary(
    quality_buckets: pd.DataFrame,
    monotonicity_df: pd.DataFrame,
    compare_summary: Dict,
) -> Dict:
    lightgbm_buckets = quality_buckets[quality_buckets["family"] == "lightgbm"].copy()
    curve_buckets = quality_buckets[quality_buckets["family"] == "curve"].copy()

    merged_buckets = lightgbm_buckets.merge(
        curve_buckets,
        on=["bucket_type", "bucket_value"],
        suffixes=("_lightgbm", "_curve"),
    )

    risk_rows = merged_buckets[
        (merged_buckets["sample_count_lightgbm"] >= 20)
        & (
            ((merged_buckets["mape_lightgbm"].fillna(-999) - merged_buckets["mape_curve"].fillna(-999)) > 3)
            | ((merged_buckets["b2b_hit_rate_curve"].fillna(-999) - merged_buckets["b2b_hit_rate_lightgbm"].fillna(-999)) > 5)
        )
    ].copy()

    abnormal_rate = round(float(monotonicity_df["abnormal"].mean() * 100), 2) if not monotonicity_df.empty else None
    summary = {
        "generated_at": datetime.now().isoformat(),
        "source_summary": compare_summary,
        "monotonicity": {
            "anchor_count": int(len(monotonicity_df)),
            "abnormal_anchor_count": int(monotonicity_df["abnormal"].sum()) if not monotonicity_df.empty else 0,
            "abnormal_anchor_rate": abnormal_rate,
            "acceptable": bool(abnormal_rate is not None and abnormal_rate <= 5.0),
        },
        "stability": {
            "risk_bucket_count": int(len(risk_rows)),
            "acceptable": bool(len(risk_rows) == 0),
            "risk_buckets": risk_rows[
                ["bucket_type", "bucket_value", "sample_count_lightgbm", "mape_curve", "mape_lightgbm", "b2b_hit_rate_curve", "b2b_hit_rate_lightgbm"]
            ].to_dict(orient="records"),
        },
    }
    summary["quality_ready"] = bool(summary["monotonicity"]["acceptable"] and summary["stability"]["acceptable"])
    return summary


def write_report(report_path: Path, summary: Dict, bucket_path: Path, mono_path: Path, cases_path: Path) -> None:
    mono = summary["monotonicity"]
    stability = summary["stability"]
    compare = summary["source_summary"]
    lines = [
        "# 阶段五：细粒度质量验证报告",
        "",
        f"> 生成时间：{summary['generated_at']}",
        f"> 对比摘要：`{bucket_path.parent / 'curve_vs_lightgbm_summary.json'}`",
        "",
        "## 1. 车龄单调性检查",
        "",
        f"- 锚点样本数：{mono['anchor_count']}",
        f"- 异常上涨锚点数：{mono['abnormal_anchor_count']}",
        f"- 异常上涨比例：{mono['abnormal_anchor_rate']}%",
        f"- 是否可接受：{'是' if mono['acceptable'] else '否'}",
        "",
        "## 2. 重点桶稳定性",
        "",
        f"- 风险桶数量：{stability['risk_bucket_count']}",
        f"- 是否可接受：{'是' if stability['acceptable'] else '否'}",
        "",
        "## 3. 总体判断",
        "",
        f"- `LightGBM` 替换条件：{'已达到' if compare['lightgbm_ready_to_replace'] else '未达到'}",
        f"- 细粒度质量验证：{'通过' if summary['quality_ready'] else '未完全通过'}",
        "",
        "## 4. 结果文件",
        "",
        f"- 分桶统计：`{bucket_path}`",
        f"- 单调性检查：`{mono_path}`",
        f"- 典型案例：`{cases_path}`",
        "",
    ]
    if stability["risk_buckets"]:
        lines.extend([
            "## 5. 风险桶",
            "",
        ])
        for row in stability["risk_buckets"]:
            lines.append(
                f"- {row['bucket_type']} / {row['bucket_value']}: "
                f"MAPE curve={row['mape_curve']}, lightgbm={row['mape_lightgbm']}; "
                f"B2B curve={row['b2b_hit_rate_curve']}, lightgbm={row['b2b_hit_rate_lightgbm']}"
            )
        lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="LightGBM 细粒度质量验证")
    parser.add_argument("--data", default=str(DEFAULT_DATA_PATH), help="评估数据文件路径")
    parser.add_argument("--sample-size", type=int, default=300, help="抽样数量")
    parser.add_argument("--random-state", type=int, default=42, help="随机种子")
    parser.add_argument("--residual-data-csv", default=str(PROJECT_ROOT / "output" / "merged_residual_value_data_with_dates.csv"), help="ResidualPredictor 使用的数据文件")
    parser.add_argument("--summary-output", default=str(DEFAULT_SUMMARY_PATH), help="质量摘要输出路径")
    parser.add_argument("--bucket-output", default=str(DEFAULT_BUCKET_PATH), help="质量分桶输出路径")
    parser.add_argument("--monotonicity-output", default=str(DEFAULT_MONO_PATH), help="单调性检查输出路径")
    parser.add_argument("--cases-output", default=str(DEFAULT_CASES_PATH), help="典型案例输出路径")
    parser.add_argument("--report-output", default=str(DEFAULT_REPORT_PATH), help="Markdown 报告输出路径")
    args = parser.parse_args()

    data_path = Path(args.data)
    sample_df = prepare_dataset(data_path, args.sample_size, args.random_state)
    curve_df, curve_summary = evaluate_family(sample_df, "curve", True, args.residual_data_csv)
    lightgbm_df, lightgbm_summary = evaluate_family(sample_df, "lightgbm", False, args.residual_data_csv)
    compare_summary = {
        "curve": curve_summary,
        "lightgbm": lightgbm_summary,
        "lightgbm_ready_to_replace": bool(
            lightgbm_summary.get("mape") is not None
            and curve_summary.get("mape") is not None
            and lightgbm_summary["mape"] <= curve_summary["mape"]
            and lightgbm_summary["r2"] >= curve_summary["r2"]
            and lightgbm_summary["b2b_hit_rate"] >= curve_summary["b2b_hit_rate"]
            and lightgbm_summary["success_rate"] >= curve_summary["success_rate"]
        ),
    }

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

    compare_long_df = pd.concat([curve_df, lightgbm_df], ignore_index=True)
    quality_buckets = build_quality_buckets(compare_long_df)
    monotonicity_df = run_monotonicity_checks(lightgbm_df, args.residual_data_csv)
    cases_df = build_case_samples(compare_df)
    summary = build_summary(quality_buckets, monotonicity_df, compare_summary)

    bucket_path = Path(args.bucket_output)
    mono_path = Path(args.monotonicity_output)
    cases_path = Path(args.cases_output)
    summary_path = Path(args.summary_output)
    report_path = Path(args.report_output)

    bucket_path.parent.mkdir(parents=True, exist_ok=True)
    quality_buckets.to_csv(bucket_path, index=False, encoding="utf-8-sig")
    monotonicity_df.to_csv(mono_path, index=False, encoding="utf-8-sig")
    cases_df.to_csv(cases_path, index=False, encoding="utf-8-sig")
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    write_report(report_path, summary, bucket_path, mono_path, cases_path)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
