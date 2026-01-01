"""
批量建模测试程序

测试内容：
1. 模型训练功能测试
2. 模型序列化测试（保存/加载）
3. 价格预测功能测试
4. 边界情况测试

使用方法：
    cd d:\antigravity\price_evaluation\车型库映射
    python -m pytest tests/test_batch_modeling.py -v
    
    # 或者直接运行
    python tests/test_batch_modeling.py
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pandas as pd
import numpy as np

from batch_model_trainer import (
    BatchModelTrainer,
    ResidualValueModel,
    exponential_model,
    polynomial_model,
    power_model,
    safe_filename,
    load_model
)
from price_predictor import PricePredictor, PredictionResult


class TestSafeFilename:
    """文件名安全转换测试"""
    
    def test_normal_name(self):
        """测试正常名称"""
        assert safe_filename('本田-飞度') == '本田-飞度'
    
    def test_special_chars(self):
        """测试特殊字符替换"""
        assert safe_filename('A/B:C') == 'A_B_C'
        assert safe_filename('test<>name') == 'test__name'


class TestModelFunctions:
    """模型函数测试"""
    
    def test_exponential_model(self):
        """测试指数模型"""
        # y = 1.0 * e^(-0.1 * x)
        result = exponential_model(0, 1.0, -0.1)
        assert abs(result - 1.0) < 0.001
        
        result = exponential_model(10, 1.0, -0.1)
        assert result < 1.0  # 应该衰减
    
    def test_polynomial_model(self):
        """测试多项式模型"""
        # y = 1*x^2 + 0*x + 0
        result = polynomial_model(2, 1, 0, 0)
        assert result == 4.0
    
    def test_power_model(self):
        """测试幂函数模型"""
        # y = 1.0 * x^0.5 = sqrt(x)
        result = power_model(4, 1.0, 0.5)
        assert abs(result - 2.0) < 0.001


class TestResidualValueModel:
    """残值率模型类测试"""
    
    def setup_method(self):
        """测试前设置"""
        self.model = ResidualValueModel(
            model_type='Exponential',
            params=np.array([0.95, -0.08]),
            r2=0.85,
            rmse=0.05,
            sample_count=100,
            group_name='测试-车型'
        )
    
    def test_predict(self):
        """测试预测功能"""
        rate = self.model.predict(5)
        assert 0 <= rate <= 1
        assert isinstance(rate, float)
    
    def test_predict_price(self):
        """测试价格预测"""
        price = self.model.predict_price(5, 10.0)
        assert isinstance(price, float)
        assert 0 <= price <= 10.0
    
    def test_get_formula(self):
        """测试公式输出"""
        formula = self.model.get_formula()
        assert 'e^' in formula or 'x²' in formula or 'x^' in formula
    
    def test_save_and_load(self):
        """测试保存和加载"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pkl') as f:
            temp_path = f.name
        
        try:
            self.model.save(temp_path)
            assert Path(temp_path).exists()
            
            loaded_model = ResidualValueModel.load(temp_path)
            assert loaded_model.model_type == self.model.model_type
            assert loaded_model.r2 == self.model.r2
            assert np.allclose(loaded_model.params, self.model.params)
        finally:
            if Path(temp_path).exists():
                os.remove(temp_path)


class TestBatchModelTrainer:
    """批量模型训练器测试"""
    
    def setup_method(self):
        """测试前设置"""
        self.data_path = Path(__file__).parent.parent / 'output' / 'residual_value_data.csv'
        if self.data_path.exists():
            self.trainer = BatchModelTrainer(str(self.data_path), min_samples=100)
        else:
            self.trainer = None
    
    def test_data_loading(self):
        """测试数据加载"""
        if self.trainer is None:
            print("跳过: 数据文件不存在")
            return
        
        df = self.trainer.df
        assert not df.empty
        assert '品牌车系' in df.columns
        assert '车辆大类' in df.columns
        assert '车辆小类' in df.columns
    
    def test_get_brand_series_groups(self):
        """测试品牌车系分组"""
        if self.trainer is None:
            print("跳过: 数据文件不存在")
            return
        
        groups = self.trainer.get_brand_series_groups()
        assert len(groups) > 0
        
        for name, df in groups.items():
            assert len(df) >= 100
    
    def test_get_car_type_groups(self):
        """测试车辆类别分组"""
        if self.trainer is None:
            print("跳过: 数据文件不存在")
            return
        
        groups = self.trainer.get_car_type_groups()
        assert len(groups) > 0
    
    def test_train_for_group(self):
        """测试单个分组训练"""
        if self.trainer is None:
            print("跳过: 数据文件不存在")
            return
        
        groups = self.trainer.get_brand_series_groups()
        
        # 选择一个样本量大的车系进行测试
        test_series = '大众-朗逸'
        if test_series in groups:
            model = self.trainer.train_for_group(groups[test_series], test_series)
            assert model is not None
            assert model.r2 > 0
            assert model.sample_count > 0


class TestPricePredictor:
    """价格预测器测试"""
    
    def setup_method(self):
        """测试前设置"""
        self.predictor = PricePredictor()
    
    def test_list_available_models(self):
        """测试列出可用模型"""
        brand_series = self.predictor.list_available_brand_series()
        car_types = self.predictor.list_available_car_types()
        
        # 即使没有模型也不应该报错
        assert isinstance(brand_series, list)
        assert isinstance(car_types, list)
    
    def test_predict_nonexistent_model(self):
        """测试预测不存在的模型"""
        result = self.predictor.predict_by_brand_series('不存在的车型-XYZ', 5, 10.0)
        assert not result.success
        assert result.error_message is not None
    
    def test_predict_invalid_year(self):
        """测试无效年限"""
        result = self.predictor.predict_by_brand_series('本田-飞度', -1, 10.0)
        assert not result.success
    
    def test_predict_invalid_price(self):
        """测试无效价格"""
        result = self.predictor.predict_by_brand_series('本田-飞度', 5, -10.0)
        assert not result.success
    
    def test_prediction_result(self):
        """测试预测结果类"""
        result = PredictionResult(
            success=True,
            predicted_price=5.5,
            residual_rate=0.55,
            model_type='Exponential',
            r2=0.85
        )
        
        assert result.success
        assert result.to_dict()['predicted_price'] == 5.5


class TestEndToEnd:
    """端到端测试"""
    
    def test_full_workflow(self):
        """测试完整工作流"""
        data_path = Path(__file__).parent.parent / 'output' / 'residual_value_data.csv'
        if not data_path.exists():
            print("跳过: 数据文件不存在")
            return
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp()
        model_dir = Path(temp_dir) / 'models'
        
        try:
            # 1. 初始化训练器
            trainer = BatchModelTrainer(str(data_path), min_samples=500)
            groups = trainer.get_brand_series_groups()
            
            if not groups:
                print("跳过: 没有足够样本的车系")
                return
            
            # 2. 训练并保存一个模型
            test_series = list(groups.keys())[0]
            model = trainer.train_for_group(groups[test_series], test_series)
            
            if model:
                model_path = model_dir / (safe_filename(test_series) + '.pkl')
                model.save(str(model_path))
                
                # 3. 使用预测器加载并预测
                predictor = PricePredictor(
                    brand_series_model_dir=str(model_dir)
                )
                
                result = predictor.predict_by_brand_series(test_series, 5, 15.0)
                assert result.success
                assert result.predicted_price > 0
                print(f"端到端测试成功: {test_series} -> {result.predicted_price}万")
        
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("批量建模测试程序")
    print("=" * 60)
    
    test_classes = [
        TestSafeFilename,
        TestModelFunctions,
        TestResidualValueModel,
        TestBatchModelTrainer,
        TestPricePredictor,
        TestEndToEnd
    ]
    
    total_tests = 0
    passed_tests = 0
    failed_tests = []
    
    for test_class in test_classes:
        print(f"\n--- {test_class.__name__} ---")
        instance = test_class()
        
        # 调用 setup_method 如果存在
        if hasattr(instance, 'setup_method'):
            try:
                instance.setup_method()
            except Exception as e:
                print(f"  setup_method 失败: {e}")
                continue
        
        for method_name in dir(instance):
            if method_name.startswith('test_'):
                total_tests += 1
                try:
                    getattr(instance, method_name)()
                    print(f"  ✓ {method_name}")
                    passed_tests += 1
                except AssertionError as e:
                    print(f"  ✗ {method_name}: {e}")
                    failed_tests.append(f"{test_class.__name__}.{method_name}")
                except Exception as e:
                    print(f"  ! {method_name}: {type(e).__name__}: {e}")
                    failed_tests.append(f"{test_class.__name__}.{method_name}")
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed_tests}/{total_tests} 通过")
    
    if failed_tests:
        print(f"\n失败的测试:")
        for t in failed_tests:
            print(f"  - {t}")
    
    return len(failed_tests) == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
