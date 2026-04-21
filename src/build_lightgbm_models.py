"""
Unified entrypoint for training LightGBM residual-value models.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from batch_model_trainer_step4 import safe_filename
from lightgbm_trainer import GroupTrainingResult, LightGBMTrainer
from model_paths import get_model_dirs


def resolve_default_data_path(project_root: Path) -> Path:
    """Use the stage-2 frozen training-data priority."""
    preferred = [
        project_root / "output" / "merged_residual_value_data_with_dates.csv",
        project_root / "output" / "merged_residual_value_data.csv",
    ]
    for path in preferred:
        if path.exists():
            return path
    return preferred[0]


def _save_reports(
    reports_dir: Path,
    summary_rows: List[Dict],
    abnormal_rows: List[pd.DataFrame],
    summary: Dict,
) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(reports_dir / "training_summary.csv", index=False, encoding="utf-8-sig")

    abnormal_df = pd.concat(abnormal_rows, ignore_index=True) if abnormal_rows else pd.DataFrame()
    abnormal_df.to_csv(reports_dir / "abnormal_predictions.csv", index=False, encoding="utf-8-sig")

    with open(reports_dir / "eval_summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)


def build_models_for_group_kind(
    trainer: LightGBMTrainer,
    groups: Dict[str, pd.DataFrame],
    output_dir: Path,
    group_kind: str,
    max_groups: int = 0,
) -> Tuple[List[Dict], List[pd.DataFrame]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_rows: List[Dict] = []
    abnormal_rows: List[pd.DataFrame] = []
    selected_groups = list(groups.items())
    if max_groups > 0:
        selected_groups = selected_groups[:max_groups]

    total = len(selected_groups)
    print(f"\n开始训练 {total} 个 {group_kind} LightGBM 模型...\n")

    for index, (group_name, group_df) in enumerate(selected_groups, 1):
        print(f"[{index}/{total}] 正在训练: {group_name} (样本数: {len(group_df)})")
        try:
            result: GroupTrainingResult = trainer.train_for_group(group_df, group_name, group_kind)
            if result.model is None:
                summary_rows.append({
                    "group_kind": group_kind,
                    "group_name": group_name,
                    "status": "failed",
                    "sample_count": len(group_df),
                    "train_count": 0,
                    "eval_count": 0,
                    "model_type": "LightGBM",
                    "r2": None,
                    "rmse": None,
                    "mae": None,
                    "mape": None,
                    "abnormal_prediction_ratio": None,
                    "file": "",
                })
                print("    ✗ 失败: 样本不足或模型未生成")
                continue

            filename = safe_filename(group_name) + ".pkl"
            model_path = output_dir / filename
            result.model.save(str(model_path))
            metrics = result.model.train_metrics
            summary_rows.append({
                "group_kind": group_kind,
                "group_name": group_name,
                "status": "success",
                "sample_count": result.model.sample_count,
                "train_count": result.train_count,
                "eval_count": result.eval_count,
                "model_type": result.model.model_type,
                "r2": result.model.r2,
                "rmse": result.model.rmse,
                "mae": metrics.get("mae"),
                "mape": metrics.get("mape"),
                "abnormal_prediction_ratio": result.model.abnormal_prediction_ratio,
                "file": filename,
            })
            if not result.abnormal_df.empty:
                abnormal_rows.append(result.abnormal_df)
            print(f"    ✓ 成功: LightGBM, R²={result.model.r2:.4f}, RMSE={result.model.rmse:.4f}")
        except Exception as exc:
            summary_rows.append({
                "group_kind": group_kind,
                "group_name": group_name,
                "status": "failed",
                "sample_count": len(group_df),
                "train_count": 0,
                "eval_count": 0,
                "model_type": "LightGBM",
                "r2": None,
                "rmse": None,
                "mae": None,
                "mape": None,
                "abnormal_prediction_ratio": None,
                "file": "",
                "error": str(exc),
            })
            print(f"    ✗ 异常: {exc}")

    return summary_rows, abnormal_rows


def build_lightgbm_models(
    data_path: Path,
    group_by: str = "both",
    min_brand_samples: int = 100,
    min_model_samples: int = 10,
    random_state: int = 42,
    test_size: float = 0.2,
    max_groups: int = 0,
) -> Dict:
    project_root = Path(__file__).resolve().parent.parent
    model_dirs = get_model_dirs(project_root)
    trainer = LightGBMTrainer(
        data_path=str(data_path),
        min_samples=min_model_samples,
        test_size=test_size,
        random_state=random_state,
    )

    summary_rows: List[Dict] = []
    abnormal_rows: List[pd.DataFrame] = []

    if group_by in {"brand_series", "both"}:
        brand_groups = trainer.get_brand_series_groups(min_samples=min_brand_samples)
        brand_rows, brand_abnormal = build_models_for_group_kind(
            trainer=trainer,
            groups=brand_groups,
            output_dir=model_dirs["lightgbm_brand_series"],
            group_kind="brand_series",
            max_groups=max_groups,
        )
        summary_rows.extend(brand_rows)
        abnormal_rows.extend(brand_abnormal)

    if group_by in {"car_type", "both"}:
        car_type_groups = trainer.get_car_type_groups()
        car_rows, car_abnormal = build_models_for_group_kind(
            trainer=trainer,
            groups=car_type_groups,
            output_dir=model_dirs["lightgbm_car_types"],
            group_kind="car_type",
            max_groups=max_groups,
        )
        summary_rows.extend(car_rows)
        abnormal_rows.extend(car_abnormal)

    success_rows = [row for row in summary_rows if row.get("status") == "success"]
    summary = {
        "data_path": str(data_path),
        "group_by": group_by,
        "generated_at": datetime.now().isoformat(),
        "total_models": len(summary_rows),
        "success_models": len(success_rows),
        "failed_models": len(summary_rows) - len(success_rows),
        "avg_r2": round(sum(row["r2"] for row in success_rows) / len(success_rows), 4) if success_rows else None,
        "avg_rmse": round(sum(row["rmse"] for row in success_rows) / len(success_rows), 4) if success_rows else None,
        "avg_mape": round(sum(row["mape"] for row in success_rows) / len(success_rows), 4) if success_rows else None,
        "model_dirs": {
            "brand_series": str(model_dirs["lightgbm_brand_series"]),
            "car_types": str(model_dirs["lightgbm_car_types"]),
            "reports": str(model_dirs["lightgbm_reports"]),
        },
    }
    _save_reports(model_dirs["lightgbm_reports"], summary_rows, abnormal_rows, summary)
    return summary


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="LightGBM 残值模型训练脚本")
    parser.add_argument("--file", default=str(resolve_default_data_path(project_root)), help="训练数据文件路径")
    parser.add_argument(
        "--group-by",
        choices=["brand_series", "car_type", "both"],
        default="both",
        help="训练分组类型",
    )
    parser.add_argument("--min-brand-samples", type=int, default=100, help="品牌车系建模最小样本数")
    parser.add_argument("--min-model-samples", type=int, default=10, help="单模型最小样本数")
    parser.add_argument("--test-size", type=float, default=0.2, help="验证集比例")
    parser.add_argument("--random-state", type=int, default=42, help="随机种子")
    parser.add_argument("--max-groups", type=int, default=0, help="最多训练多少个分组，0 表示不限制")
    args = parser.parse_args()

    data_path = Path(args.file)
    if not data_path.is_absolute():
        data_path = (project_root / data_path).resolve()

    if not data_path.exists():
        print(f"错误: 训练数据不存在: {data_path}")
        sys.exit(1)

    summary = build_lightgbm_models(
        data_path=data_path,
        group_by=args.group_by,
        min_brand_samples=args.min_brand_samples,
        min_model_samples=args.min_model_samples,
        random_state=args.random_state,
        test_size=args.test_size,
        max_groups=args.max_groups,
    )

    print("\n" + "=" * 60)
    print("LightGBM 训练完成")
    print("=" * 60)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
