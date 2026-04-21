"""
LightGBM residual value model wrapper.

This module mirrors the shape of the existing curve-model wrapper so the
runtime integration can reuse similar concepts in later stages.
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from lightgbm import LGBMRegressor
except ImportError as exc:  # pragma: no cover - environment dependent
    raise ImportError(
        "lightgbm is required for LightGBMResidualModel. "
        "Install it with `pip install lightgbm`."
    ) from exc


logger = logging.getLogger(__name__)


@dataclass
class LightGBMResidualModel:
    """Serialized LightGBM residual-rate model plus runtime metadata."""

    estimator: LGBMRegressor
    group_name: str
    group_kind: str  # brand_series | car_type
    feature_names: List[str]
    categorical_features: List[str]
    category_levels: Dict[str, List[str]]
    monotone_constraints: List[int]
    r2: float
    rmse: float
    sample_count: int
    train_metrics: Dict[str, float] = field(default_factory=dict)
    clip_range: Tuple[float, float] = (0.0, 1.0)
    abnormal_prediction_ratio: float = 0.0
    model_type: str = "LightGBM"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def _build_input_frame(self, features: Dict[str, Any]) -> pd.DataFrame:
        missing = [name for name in self.feature_names if name not in features]
        if missing:
            raise ValueError(f"缺少预测所需特征: {missing}")

        frame = pd.DataFrame([{name: features.get(name) for name in self.feature_names}])

        for name in self.feature_names:
            if name in self.categorical_features:
                categories = self.category_levels.get(name, [])
                frame[name] = pd.Categorical(frame[name].astype(str), categories=categories)
            else:
                frame[name] = pd.to_numeric(frame[name], errors="coerce")

        if frame[self.feature_names].isna().all(axis=None):
            raise ValueError("输入特征全部为空，无法完成预测")

        return frame

    def predict(self, features: Dict[str, Any]) -> float:
        """
        Predict residual rate for a single vehicle sample.

        Args:
            features: Feature payload keyed by training feature names.

        Returns:
            Residual rate clipped into the configured range.
        """
        frame = self._build_input_frame(features)
        raw_value = float(self.estimator.predict(frame)[0])
        low, high = self.clip_range

        if not np.isfinite(raw_value):
            logger.warning("[%s] LightGBM produced non-finite residual %.4f", self.group_name, raw_value)
            raw_value = low

        return float(np.clip(raw_value, low, high))

    def predict_contributions(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return per-feature contribution details for a single sample.

        Uses LightGBM's `pred_contrib=True` output. The last term is the bias
        (expected value), while previous terms align with `feature_names`.
        """
        frame = self._build_input_frame(features)
        contrib_matrix = np.asarray(self.estimator.predict(frame, pred_contrib=True))
        if contrib_matrix.ndim != 2 or contrib_matrix.shape[1] != len(self.feature_names) + 1:
            raise ValueError("LightGBM 特征贡献输出格式异常")

        contrib_row = contrib_matrix[0]
        feature_contribs = contrib_row[:-1]
        bias = float(contrib_row[-1])
        new_price = float(features.get("新车的价格", 0) or 0)

        items: List[Dict[str, Any]] = []
        for name, contrib in zip(self.feature_names, feature_contribs):
            contribution_residual_rate = float(contrib)
            items.append({
                "name": name,
                "value": features.get(name),
                "contribution_residual_rate": contribution_residual_rate,
                "contribution_price": float(contribution_residual_rate * new_price) if new_price > 0 else None,
            })

        items.sort(key=lambda item: abs(item["contribution_price"] or 0.0), reverse=True)
        return {
            "source": "lightgbm_pred_contrib",
            "bias_residual_rate": bias,
            "bias_price": float(bias * new_price) if new_price > 0 else None,
            "features": items,
        }

    def predict_price(self, features: Dict[str, Any], new_price: Optional[float] = None) -> float:
        """
        Predict used-car price in wan yuan.

        Args:
            features: Feature payload keyed by training feature names.
            new_price: Optional explicit new-car price. Falls back to payload.

        Returns:
            Predicted used-car price rounded to 2 decimals.
        """
        resolved_new_price = new_price if new_price is not None else features.get("新车的价格")
        resolved_new_price = float(resolved_new_price)
        if resolved_new_price <= 0:
            raise ValueError("新车价格必须大于0")

        residual_rate = self.predict(features)
        return round(residual_rate * resolved_new_price, 2)

    def save(self, filepath: str) -> None:
        """Serialize the full model object so runtime metadata travels with it."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as handle:
            pickle.dump(self, handle)
        logger.debug("LightGBM 模型已保存: %s", filepath)

    @classmethod
    def load(cls, filepath: str) -> "LightGBMResidualModel":
        """Load model and metadata from a single pickle file."""
        with open(filepath, "rb") as handle:
            model = pickle.load(handle)
        if not isinstance(model, cls):
            raise TypeError(f"{filepath} 不是有效的 LightGBMResidualModel 文件")
        return model

    def get_formula(self) -> str:
        """Keep the old interface shape while acknowledging tree models have no formula."""
        return "LightGBM tree ensemble model (no closed-form formula)"

    def __repr__(self) -> str:
        return (
            f"LightGBMResidualModel(group={self.group_name}, kind={self.group_kind}, "
            f"R²={self.r2:.4f}, samples={self.sample_count})"
        )
