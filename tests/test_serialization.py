from pathlib import Path
import tempfile

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from batch_model_trainer_step4 import ResidualValueModel  # noqa: E402
from lightgbm_residual_model import LightGBMResidualModel  # noqa: E402


def build_test_model() -> LightGBMResidualModel:
    feature_names = ["使用年限", "新车的价格", "行驶里程", "品牌车系", "车辆评级", "车辆大类", "车辆小类", "车辆属性", "城市"]
    categorical = ["品牌车系", "车辆评级", "车辆大类", "车辆小类", "车辆属性", "城市"]
    rows = []
    for idx in range(12):
        rows.append({
            "使用年限": 1.0 + idx * 0.5,
            "新车的价格": 10.0 + idx,
            "行驶里程": 1.0 + idx * 0.2,
            "品牌车系": "测试-车型A" if idx % 2 == 0 else "测试-车型B",
            "车辆评级": "中" if idx % 3 else "优",
            "车辆大类": "轿车",
            "车辆小类": "紧凑型车",
            "车辆属性": "合资",
            "城市": "北京" if idx % 2 == 0 else "上海",
            "残值率": max(0.1, 0.8 - idx * 0.03),
        })
    df = pd.DataFrame(rows)
    category_levels = {col: sorted(df[col].astype(str).unique().tolist()) for col in categorical}
    X = df[feature_names].copy()
    for col in categorical:
        X[col] = pd.Categorical(X[col].astype(str), categories=category_levels[col])

    estimator = LGBMRegressor(
        objective="regression",
        n_estimators=40,
        learning_rate=0.1,
        random_state=42,
        monotone_constraints=[-1, 0, 0, 0, 0, 0, 0, 0, 0],
        n_jobs=1,
        verbosity=-1,
    )
    estimator.fit(X, df["残值率"].to_numpy(), categorical_feature=categorical)

    return LightGBMResidualModel(
        estimator=estimator,
        group_name="测试-车型A",
        group_kind="brand_series",
        feature_names=feature_names,
        categorical_features=categorical,
        category_levels=category_levels,
        monotone_constraints=[-1, 0, 0, 0, 0, 0, 0, 0, 0],
        r2=0.8,
        rmse=0.05,
        sample_count=len(df),
        metadata={"target": "残值率"},
    )


def sample_features():
    return {
        "使用年限": 3.0,
        "新车的价格": 15.0,
        "行驶里程": 2.0,
        "品牌车系": "测试-车型A",
        "车辆评级": "中",
        "车辆大类": "轿车",
        "车辆小类": "紧凑型车",
        "车辆属性": "合资",
        "城市": "北京",
    }


def test_curve_model_serialization_roundtrip():
    model = ResidualValueModel(
        model_type="Power",
        params=np.array([0.9, -0.4]),
        r2=0.7,
        rmse=0.08,
        sample_count=88,
        group_name="测试-曲线模型",
    )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pkl") as handle:
        path = Path(handle.name)
    try:
        model.save(str(path))
        loaded = ResidualValueModel.load(str(path))
        assert loaded.group_name == model.group_name
        assert np.allclose(loaded.params, model.params)
        assert loaded.predict_price(5, 10.0) >= 0
    finally:
        if path.exists():
            path.unlink()


def test_lightgbm_model_serialization_contains_runtime_metadata():
    model = build_test_model()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pkl") as handle:
        path = Path(handle.name)
    try:
        model.save(str(path))
        loaded = LightGBMResidualModel.load(str(path))
        assert loaded.feature_names == model.feature_names
        assert loaded.categorical_features == model.categorical_features
        assert loaded.monotone_constraints == model.monotone_constraints
        assert loaded.clip_range == (0.0, 1.0)
        assert loaded.predict(sample_features()) >= 0
    finally:
        if path.exists():
            path.unlink()
