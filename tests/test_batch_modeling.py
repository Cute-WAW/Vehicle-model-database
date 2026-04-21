"""
Curve-model regression tests for the current codebase.

Run with:
    python -m pytest tests/test_batch_modeling.py -v
"""

from pathlib import Path
import tempfile

import numpy as np
import pytest

import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from batch_model_trainer_step4 import (  # noqa: E402
    BatchModelTrainer,
    ResidualValueModel,
    exponential_model,
    polynomial_model,
    power_model,
    safe_filename,
)
from price_predictor_step5 import PredictionResult, PricePredictor  # noqa: E402


PROJECT_ROOT = Path(__file__).parent.parent
CURVE_DATA_PATH = PROJECT_ROOT / "output" / "residual_value_data.csv"


class TestSafeFilename:
    def test_normal_name(self):
        assert safe_filename("本田-飞度") == "本田-飞度"

    def test_special_chars(self):
        assert safe_filename("A/B:C") == "A_B_C"
        assert safe_filename("test<>name") == "test__name"


class TestModelFunctions:
    def test_exponential_model(self):
        result = exponential_model(0, 1.0, -0.1)
        assert abs(result - 1.0) < 0.001
        assert exponential_model(10, 1.0, -0.1) < 1.0

    def test_polynomial_model(self):
        assert polynomial_model(2, 1, 0, 0) == 4.0

    def test_power_model(self):
        assert abs(power_model(4, 1.0, 0.5) - 2.0) < 0.001


class TestResidualValueModel:
    def setup_method(self):
        self.model = ResidualValueModel(
            model_type="Exponential",
            params=np.array([0.95, -0.08]),
            r2=0.85,
            rmse=0.05,
            sample_count=100,
            group_name="测试-车型",
        )

    def test_predict(self):
        rate = self.model.predict(5)
        assert 0 <= rate <= 1
        assert isinstance(rate, float)

    def test_predict_price(self):
        price = self.model.predict_price(5, 10.0)
        assert isinstance(price, float)
        assert 0 <= price <= 10.0

    def test_get_formula(self):
        formula = self.model.get_formula()
        assert "e^" in formula or "x²" in formula or "x^" in formula

    def test_save_and_load(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pkl") as handle:
            path = Path(handle.name)

        try:
            self.model.save(str(path))
            loaded = ResidualValueModel.load(str(path))
            assert loaded.model_type == self.model.model_type
            assert loaded.r2 == self.model.r2
            assert np.allclose(loaded.params, self.model.params)
        finally:
            if path.exists():
                path.unlink()


@pytest.mark.skipif(not CURVE_DATA_PATH.exists(), reason="缺少 curve 训练数据")
class TestBatchModelTrainer:
    def setup_method(self):
        self.trainer = BatchModelTrainer(str(CURVE_DATA_PATH), min_samples=100)

    def test_data_loading(self):
        df = self.trainer.df
        assert not df.empty
        assert "品牌车系" in df.columns
        assert "车辆大类" in df.columns
        assert "车辆小类" in df.columns

    def test_get_brand_series_groups(self):
        groups = self.trainer.get_brand_series_groups()
        assert len(groups) > 0
        assert all(len(df) >= 100 for df in groups.values())

    def test_get_car_type_groups(self):
        groups = self.trainer.get_car_type_groups()
        assert len(groups) > 0

    def test_train_for_group(self):
        groups = self.trainer.get_brand_series_groups()
        test_series = "大众-朗逸"
        if test_series not in groups:
            pytest.skip("缺少测试车系")
        model, clean_df = self.trainer.train_for_group(groups[test_series], test_series)
        assert model is not None
        assert model.r2 > 0
        assert model.sample_count > 0
        assert not clean_df.empty


class TestPricePredictor:
    def setup_method(self):
        self.predictor = PricePredictor()

    def test_list_available_models(self):
        assert isinstance(self.predictor.list_available_brand_series(), list)
        assert isinstance(self.predictor.list_available_car_types(), list)

    def test_predict_nonexistent_model(self):
        result = self.predictor.predict_by_brand_series("不存在的车型-XYZ", 5, 10.0)
        assert not result.success
        assert result.error_message

    def test_predict_invalid_year(self):
        result = self.predictor.predict_by_brand_series("本田-飞度", -1, 10.0)
        assert not result.success

    def test_predict_invalid_price(self):
        result = self.predictor.predict_by_brand_series("本田-飞度", 5, -10.0)
        assert not result.success

    def test_prediction_result(self):
        result = PredictionResult(
            success=True,
            predicted_price=5.5,
            residual_rate=0.55,
            model_type="Exponential",
            model_family="curve",
            r2=0.85,
        )
        assert result.success
        assert result.to_dict()["predicted_price"] == 5.5
        assert result.to_dict()["model_family"] == "curve"
