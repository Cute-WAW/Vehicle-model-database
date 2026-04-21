from pathlib import Path

import pandas as pd
import pytest

import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from residual_predictor_step5 import ResidualPredictor  # noqa: E402


PROJECT_ROOT = Path(__file__).parent.parent
DATA_PATH = PROJECT_ROOT / "output" / "merged_residual_value_data_with_dates.csv"


@pytest.fixture(scope="module")
def sample_row():
    if not DATA_PATH.exists():
        pytest.skip("缺少阶段4/5预测数据")
    df = pd.read_csv(DATA_PATH, low_memory=False)
    rows = df[df["品牌车系"] == "日产-轩逸"]
    if rows.empty:
        pytest.skip("缺少 日产-轩逸 测试样本")
    return rows.iloc[0]


def build_predictor() -> ResidualPredictor:
    return ResidualPredictor(residual_data_csv=str(DATA_PATH))


def test_default_curve_mode(sample_row):
    predictor = build_predictor()
    result = predictor.predict(
        vehicle_full_name=str(sample_row["车辆全称"]),
        brand_series=str(sample_row["品牌车系"]),
        years=float(sample_row["使用年限"]),
        grade="中",
        city=str(sample_row["城市"]),
        mileage=float(sample_row["行驶里程"]),
        new_price=float(sample_row["新车的价格"]),
    )
    assert result.success
    assert result.debug is not None
    assert result.debug.final_model_family == "curve"
    assert result.debug.fallback_triggered is False


def test_lightgbm_mode(sample_row):
    predictor = build_predictor()
    predictor.model_strategy_config = {
        "default_model_family": "lightgbm",
        "allow_curve_fallback": True,
    }
    result = predictor.predict(
        vehicle_full_name=str(sample_row["车辆全称"]),
        brand_series=str(sample_row["品牌车系"]),
        years=float(sample_row["使用年限"]),
        grade="中",
        city=str(sample_row["城市"]),
        mileage=float(sample_row["行驶里程"]),
        new_price=float(sample_row["新车的价格"]),
    )
    assert result.success
    assert result.debug is not None
    assert result.debug.final_model_family == "lightgbm"
    assert result.debug.model_family == "lightgbm"


def test_lightgbm_to_curve_fallback(sample_row, tmp_path):
    predictor = build_predictor()
    predictor.model_strategy_config = {
        "default_model_family": "lightgbm",
        "allow_curve_fallback": True,
    }

    empty_brand = tmp_path / "lightgbm_brand_series"
    empty_car_type = tmp_path / "lightgbm_car_types"
    empty_brand.mkdir()
    empty_car_type.mkdir()

    predictor.price_predictor.lightgbm_brand_series_model_dir = empty_brand
    predictor.price_predictor.lightgbm_car_types_model_dir = empty_car_type
    predictor.price_predictor._lightgbm_brand_series_cache.clear()
    predictor.price_predictor._lightgbm_car_types_cache.clear()

    result = predictor.predict(
        vehicle_full_name=str(sample_row["车辆全称"]),
        brand_series=str(sample_row["品牌车系"]),
        years=float(sample_row["使用年限"]),
        grade="中",
        city=str(sample_row["城市"]),
        mileage=float(sample_row["行驶里程"]),
        new_price=float(sample_row["新车的价格"]),
    )

    assert result.success
    assert result.debug is not None
    assert result.debug.fallback_triggered is True
    assert result.debug.final_model_family == "curve"
    assert "lightgbm" in result.debug.fallback_reason.lower()
