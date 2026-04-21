"""
Training utilities for LightGBM residual-rate models.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from lightgbm_residual_model import LightGBMResidualModel


logger = logging.getLogger(__name__)


def get_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute root-mean-squared error."""
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


@dataclass
class GroupTrainingResult:
    """Result bundle for one trained group."""

    model: Optional[LightGBMResidualModel]
    clean_df: pd.DataFrame
    abnormal_df: pd.DataFrame
    train_count: int = 0
    eval_count: int = 0


class LightGBMTrainer:
    """Shared trainer for brand-series and car-type LightGBM models."""

    NUMERIC_FEATURES = ["使用年限", "新车的价格", "行驶里程"]
    CATEGORICAL_FEATURES = ["品牌车系", "车辆评级", "车辆大类", "车辆小类", "车辆属性", "城市"]
    FEATURE_NAMES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    TARGET_COLUMN = "残值率"
    CLIP_RANGE = (0.0, 1.0)
    MONOTONE_CONSTRAINTS = [-1, 0, 0, 0, 0, 0, 0, 0, 0]

    def __init__(
        self,
        data_path: str,
        min_samples: int = 10,
        test_size: float = 0.2,
        random_state: int = 42,
    ):
        self.data_path = Path(data_path)
        self.min_samples = min_samples
        self.test_size = test_size
        self.random_state = random_state
        self._df: Optional[pd.DataFrame] = None
        self._prepared_df: Optional[pd.DataFrame] = None

    @property
    def df(self) -> pd.DataFrame:
        """Raw loaded dataframe."""
        if self._df is None:
            logger.info("加载 LightGBM 训练数据: %s", self.data_path)
            self._df = pd.read_csv(self.data_path, low_memory=False)
        return self._df

    @property
    def prepared_df(self) -> pd.DataFrame:
        """Clean dataframe ready for grouping and training."""
        if self._prepared_df is None:
            self._prepared_df = self._prepare_base_df(self.df)
            logger.info("LightGBM 训练数据清洗完成，共 %s 条记录", len(self._prepared_df))
        return self._prepared_df

    def _prepare_base_df(self, df: pd.DataFrame) -> pd.DataFrame:
        required = [
            "品牌车系",
            "新车的价格",
            "车况校正价",
            "使用年限",
            "车辆评级",
            "车辆大类",
            "车辆小类",
            "车辆属性",
            "城市",
            "行驶里程",
        ]
        missing = [name for name in required if name not in df.columns]
        if missing:
            raise ValueError(f"训练数据缺少必要字段: {missing}")

        prepared = df.copy()
        prepared["新车的价格"] = pd.to_numeric(prepared["新车的价格"], errors="coerce")
        prepared["车况校正价"] = pd.to_numeric(prepared["车况校正价"], errors="coerce")
        prepared["使用年限"] = pd.to_numeric(prepared["使用年限"], errors="coerce")
        prepared["行驶里程"] = pd.to_numeric(prepared["行驶里程"], errors="coerce")

        if self.TARGET_COLUMN not in prepared.columns:
            prepared[self.TARGET_COLUMN] = prepared["车况校正价"] / prepared["新车的价格"]
        else:
            prepared[self.TARGET_COLUMN] = pd.to_numeric(prepared[self.TARGET_COLUMN], errors="coerce")

        # Always rebuild the aggregated car-type field from the source columns.
        # Historical files may contain a partially-filled `车辆类别` column that only
        # covers a subset of rows, which would silently shrink car-type coverage.
        prepared["车辆类别"] = (
            prepared["车辆大类"].astype(str)
            + "-"
            + prepared["车辆小类"].astype(str)
            + "-"
            + prepared["车辆属性"].astype(str)
        )

        if "trade_date" in prepared.columns:
            prepared["_trade_date"] = pd.to_datetime(prepared["trade_date"], errors="coerce")
        elif "交易时间" in prepared.columns:
            prepared["_trade_date"] = pd.to_datetime(prepared["交易时间"], errors="coerce")
        else:
            prepared["_trade_date"] = pd.NaT

        for column in self.CATEGORICAL_FEATURES:
            prepared[column] = prepared[column].astype(str).str.strip()

        prepared = prepared.dropna(subset=self.FEATURE_NAMES + [self.TARGET_COLUMN]).copy()
        prepared = prepared[prepared["新车的价格"] > 0.1]
        prepared = prepared[prepared["使用年限"].between(0.5, 20.0)]
        prepared = prepared[prepared["行驶里程"] >= 0]
        prepared = prepared[prepared[self.TARGET_COLUMN].between(0.01, 1.5)]
        prepared = prepared.reset_index(drop=True)
        return prepared

    def _build_feature_frame(
        self,
        df: pd.DataFrame,
        category_levels: Optional[Dict[str, List[str]]] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
        features = df[self.FEATURE_NAMES].copy()
        resolved_levels = category_levels or {}

        for column in self.NUMERIC_FEATURES:
            features[column] = pd.to_numeric(features[column], errors="coerce").astype(float)

        for column in self.CATEGORICAL_FEATURES:
            if category_levels is None:
                levels = sorted(features[column].astype(str).dropna().unique().tolist())
                resolved_levels[column] = levels
            levels = resolved_levels.get(column, [])
            features[column] = pd.Categorical(features[column].astype(str), categories=levels)

        return features, resolved_levels

    def _split_group_df(self, group_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        n_samples = len(group_df)
        if n_samples < self.min_samples:
            raise ValueError(f"样本不足，至少需要 {self.min_samples} 条，当前 {n_samples} 条")

        dated = group_df[group_df["_trade_date"].notna()].sort_values("_trade_date")
        undated = group_df[group_df["_trade_date"].isna()]
        eval_size = max(1, int(round(len(group_df) * self.test_size)))

        if len(dated) >= max(self.min_samples, eval_size + 1):
            eval_df = dated.tail(eval_size).copy()
            train_df = pd.concat([dated.iloc[:-eval_size], undated], ignore_index=True)
            return train_df.reset_index(drop=True), eval_df.reset_index(drop=True)

        train_df, eval_df = train_test_split(
            group_df,
            test_size=self.test_size,
            random_state=self.random_state,
        )
        return train_df.reset_index(drop=True), eval_df.reset_index(drop=True)

    def _collect_abnormal_predictions(
        self,
        eval_df: pd.DataFrame,
        raw_pred: np.ndarray,
        clipped_pred: np.ndarray,
        group_name: str,
        group_kind: str,
    ) -> pd.DataFrame:
        abnormal_mask = (~np.isfinite(raw_pred)) | (raw_pred < self.CLIP_RANGE[0]) | (raw_pred > self.CLIP_RANGE[1])
        if not abnormal_mask.any():
            return pd.DataFrame()

        details = eval_df.loc[abnormal_mask, self.FEATURE_NAMES + [self.TARGET_COLUMN]].copy()
        details["group_name"] = group_name
        details["group_kind"] = group_kind
        details["raw_predicted_residual_rate"] = raw_pred[abnormal_mask]
        details["clipped_residual_rate"] = clipped_pred[abnormal_mask]
        details["actual_residual_rate"] = details[self.TARGET_COLUMN]
        details["abnormal_reason"] = np.where(
            ~np.isfinite(raw_pred[abnormal_mask]),
            "non_finite",
            np.where(raw_pred[abnormal_mask] < self.CLIP_RANGE[0], "below_zero", "above_one"),
        )
        return details.reset_index(drop=True)

    def train_for_group(self, group_df: pd.DataFrame, group_name: str, group_kind: str) -> GroupTrainingResult:
        clean_df = group_df.copy().reset_index(drop=True)
        if len(clean_df) < self.min_samples:
            logger.warning("[%s] 样本不足 (%s 条)，跳过建模", group_name, len(clean_df))
            return GroupTrainingResult(model=None, clean_df=clean_df, abnormal_df=pd.DataFrame())

        train_df, eval_df = self._split_group_df(clean_df)
        X_train, category_levels = self._build_feature_frame(train_df)
        X_eval, _ = self._build_feature_frame(eval_df, category_levels=category_levels)
        y_train = train_df[self.TARGET_COLUMN].to_numpy(dtype=float)
        y_eval = eval_df[self.TARGET_COLUMN].to_numpy(dtype=float)

        estimator = LGBMRegressor(
            objective="regression",
            n_estimators=200,
            learning_rate=0.05,
            num_leaves=31,
            min_child_samples=20,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=self.random_state,
            monotone_constraints=self.MONOTONE_CONSTRAINTS,
            n_jobs=1,
            verbosity=-1,
        )
        estimator.fit(X_train, y_train, categorical_feature=self.CATEGORICAL_FEATURES)

        raw_pred = np.asarray(estimator.predict(X_eval), dtype=float)
        clipped_pred = np.clip(np.where(np.isfinite(raw_pred), raw_pred, self.CLIP_RANGE[0]), *self.CLIP_RANGE)

        mae = float(mean_absolute_error(y_eval, clipped_pred))
        mape = float(np.mean(np.abs((clipped_pred - y_eval) / y_eval)) * 100)
        rmse = get_rmse(y_eval, clipped_pred)
        r2 = float(r2_score(y_eval, clipped_pred)) if len(np.unique(y_eval)) > 1 else 0.0

        abnormal_df = self._collect_abnormal_predictions(eval_df, raw_pred, clipped_pred, group_name, group_kind)
        abnormal_ratio = float(len(abnormal_df) / len(eval_df)) if len(eval_df) else 0.0

        model = LightGBMResidualModel(
            estimator=estimator,
            group_name=group_name,
            group_kind=group_kind,
            feature_names=list(self.FEATURE_NAMES),
            categorical_features=list(self.CATEGORICAL_FEATURES),
            category_levels=category_levels,
            monotone_constraints=list(self.MONOTONE_CONSTRAINTS),
            r2=r2,
            rmse=rmse,
            sample_count=len(clean_df),
            train_metrics={
                "mae": mae,
                "mape": mape,
                "r2": r2,
                "rmse": rmse,
                "train_count": float(len(train_df)),
                "eval_count": float(len(eval_df)),
            },
            clip_range=self.CLIP_RANGE,
            abnormal_prediction_ratio=abnormal_ratio,
            metadata={
                "target": self.TARGET_COLUMN,
                "numeric_features": list(self.NUMERIC_FEATURES),
                "categorical_features": list(self.CATEGORICAL_FEATURES),
            },
        )
        logger.info(
            "[%s] LightGBM 建模成功: R²=%.4f, RMSE=%.4f, 样本=%s",
            group_name,
            model.r2,
            model.rmse,
            model.sample_count,
        )
        return GroupTrainingResult(
            model=model,
            clean_df=clean_df,
            abnormal_df=abnormal_df,
            train_count=len(train_df),
            eval_count=len(eval_df),
        )

    def get_brand_series_groups(self, min_samples: int = 100) -> Dict[str, pd.DataFrame]:
        counts = self.prepared_df["品牌车系"].value_counts()
        valid = counts[counts >= min_samples].index.tolist()
        groups = {
            name: self.prepared_df[self.prepared_df["品牌车系"] == name].copy()
            for name in valid
        }
        logger.info("找到 %s 个品牌车系 LightGBM 分组（样本数≥%s）", len(groups), min_samples)
        return groups

    def get_car_type_groups(self) -> Dict[str, pd.DataFrame]:
        counts = self.prepared_df["车辆类别"].value_counts()
        valid = counts.index.tolist()
        groups = {
            name: self.prepared_df[self.prepared_df["车辆类别"] == name].copy()
            for name in valid
        }
        logger.info("找到 %s 个车辆类别 LightGBM 分组", len(groups))
        return groups
