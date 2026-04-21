"""
价格预测查询接口

功能：
1. 加载品牌车系模型或车辆类别模型
2. 提供统一的价格预测API
3. 支持查询可用模型列表

使用方法：
    from price_predictor import PricePredictor
    
    predictor = PricePredictor()
    
    # 按品牌车系预测
    result = predictor.predict_by_brand_series('本田-飞度', year=5, new_price=10.0)
    
    # 按车辆类别预测
    result = predictor.predict_by_car_type('轿车-紧凑型车', year=5, new_price=10.0)
"""

from pathlib import Path
from typing import Optional, List, Dict, Union, Any
import logging

from batch_model_trainer_step4 import ResidualValueModel, safe_filename
from model_paths import get_model_dirs

logger = logging.getLogger(__name__)


class PredictionResult:
    """预测结果封装类"""
    
    def __init__(
        self,
        success: bool,
        predicted_price: Optional[float] = None,
        residual_rate: Optional[float] = None,
        model_type: Optional[str] = None,
        model_family: Optional[str] = None,
        feature_contributions: Optional[Dict[str, Any]] = None,
        explanation_source: Optional[str] = None,
        r2: Optional[float] = None,
        error_message: Optional[str] = None
    ):
        self.success = success
        self.predicted_price = predicted_price
        self.residual_rate = residual_rate
        self.model_type = model_type
        self.model_family = model_family
        self.feature_contributions = feature_contributions
        self.explanation_source = explanation_source
        self.r2 = r2
        self.error_message = error_message
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'success': self.success,
            'predicted_price': self.predicted_price,
            'residual_rate': self.residual_rate,
            'model_type': self.model_type,
            'model_family': self.model_family,
            'feature_contributions': self.feature_contributions,
            'explanation_source': self.explanation_source,
            'r2': self.r2,
            'error_message': self.error_message
        }
    
    def __repr__(self):
        if self.success:
            return f"PredictionResult(价格={self.predicted_price}万, 残值率={self.residual_rate:.1%})"
        return f"PredictionResult(失败: {self.error_message})"


class PricePredictor:
    """价格预测器"""
    
    # 车龄分段定义
    AGE_SEGMENTS = [
        (0.5, 5.0, 'young'),
        (5.0, 10.0, 'mid'),
        (10.0, 20.0, 'old'),
    ]
    
    def __init__(
        self,
        brand_series_model_dir: Optional[str] = None,
        car_types_model_dir: Optional[str] = None,
        segmented_model_dir: Optional[str] = None,
        lightgbm_brand_series_model_dir: Optional[str] = None,
        lightgbm_car_types_model_dir: Optional[str] = None,
    ):
        """
        初始化预测器
        
        Args:
            brand_series_model_dir: 品牌车系模型目录
            car_types_model_dir: 车辆类别模型目录
            segmented_model_dir: 分段模型目录 (方案三)
            lightgbm_brand_series_model_dir: LightGBM 品牌车系模型目录
            lightgbm_car_types_model_dir: LightGBM 车辆类别模型目录
        """
        script_dir = Path(__file__).parent
        model_dirs = get_model_dirs(script_dir.parent)
        
        self.brand_series_model_dir = Path(brand_series_model_dir) if brand_series_model_dir else \
            model_dirs['brand_series']
        
        self.car_types_model_dir = Path(car_types_model_dir) if car_types_model_dir else \
            model_dirs['car_types']
        
        self.segmented_model_dir = Path(segmented_model_dir) if segmented_model_dir else \
            model_dirs['segmented']

        self.lightgbm_brand_series_model_dir = (
            Path(lightgbm_brand_series_model_dir)
            if lightgbm_brand_series_model_dir
            else model_dirs['lightgbm_brand_series']
        )

        self.lightgbm_car_types_model_dir = (
            Path(lightgbm_car_types_model_dir)
            if lightgbm_car_types_model_dir
            else model_dirs['lightgbm_car_types']
        )
        
        # 模型缓存
        self._brand_series_cache: Dict[str, ResidualValueModel] = {}
        self._car_types_cache: Dict[str, ResidualValueModel] = {}
        self._segmented_cache: Dict[str, ResidualValueModel] = {}
        self._lightgbm_brand_series_cache: Dict[str, Any] = {}
        self._lightgbm_car_types_cache: Dict[str, Any] = {}
    
    def _get_age_segment(self, year: float) -> str:
        """根据车龄获取分段名称"""
        for low, high, seg_name in self.AGE_SEGMENTS:
            if low <= year < high:
                return seg_name
        return 'old'  # 默认老车
    
    def _load_segmented_model(self, brand_series: str, year: float) -> Optional[ResidualValueModel]:
        """加载分段模型"""
        seg_name = self._get_age_segment(year)
        cache_key = f"{brand_series}_{seg_name}"
        
        if cache_key in self._segmented_cache:
            return self._segmented_cache[cache_key]
        
        filename = safe_filename(brand_series) + f'_seg_{seg_name}.pkl'
        model_path = self.segmented_model_dir / filename
        
        if not model_path.exists():
            return None
        
        try:
            model = ResidualValueModel.load(str(model_path))
            self._segmented_cache[cache_key] = model
            return model
        except Exception as e:
            logger.warning(f"加载分段模型失败 ({cache_key}): {e}")
            return None
    
    def _load_brand_series_model(self, brand_series: str) -> Optional[ResidualValueModel]:
        """加载品牌车系模型"""
        if brand_series in self._brand_series_cache:
            return self._brand_series_cache[brand_series]
        
        filename = safe_filename(brand_series) + '.pkl'
        model_path = self.brand_series_model_dir / filename
        
        if not model_path.exists():
            logger.warning(f"品牌车系模型不存在: {brand_series}")
            return None
        
        try:
            model = ResidualValueModel.load(str(model_path))
            self._brand_series_cache[brand_series] = model
            return model
        except Exception as e:
            logger.error(f"加载模型失败 ({brand_series}): {e}")
            return None
    
    def _load_car_type_model(self, car_type: str) -> Optional[ResidualValueModel]:
        """加载车辆类别模型"""
        if car_type in self._car_types_cache:
            return self._car_types_cache[car_type]
        
        filename = safe_filename(car_type) + '.pkl'
        model_path = self.car_types_model_dir / filename
        
        if not model_path.exists():
            logger.warning(f"车辆类别模型不存在: {car_type}")
            return None
        
        try:
            model = ResidualValueModel.load(str(model_path))
            self._car_types_cache[car_type] = model
            return model
        except Exception as e:
            logger.error(f"加载模型失败 ({car_type}): {e}")
            return None

    def _load_lightgbm_model_class(self):
        """Lazy import to avoid hard failure before LightGBM is actually used."""
        try:
            from lightgbm_residual_model import LightGBMResidualModel
            return LightGBMResidualModel
        except Exception as e:
            logger.error(f"导入 LightGBMResidualModel 失败: {e}")
            return None

    def _load_lightgbm_brand_series_model(self, brand_series: str):
        """加载 LightGBM 品牌车系模型"""
        if brand_series in self._lightgbm_brand_series_cache:
            return self._lightgbm_brand_series_cache[brand_series]

        filename = safe_filename(brand_series) + '.pkl'
        model_path = self.lightgbm_brand_series_model_dir / filename
        if not model_path.exists():
            logger.warning(f"LightGBM 品牌车系模型不存在: {brand_series}")
            return None

        model_cls = self._load_lightgbm_model_class()
        if model_cls is None:
            return None

        try:
            model = model_cls.load(str(model_path))
            self._lightgbm_brand_series_cache[brand_series] = model
            return model
        except Exception as e:
            logger.error(f"加载 LightGBM 模型失败 ({brand_series}): {e}")
            return None

    def _load_lightgbm_car_type_model(self, car_type: str):
        """加载 LightGBM 车辆类别模型"""
        if car_type in self._lightgbm_car_types_cache:
            return self._lightgbm_car_types_cache[car_type]

        filename = safe_filename(car_type) + '.pkl'
        model_path = self.lightgbm_car_types_model_dir / filename
        if not model_path.exists():
            logger.warning(f"LightGBM 车辆类别模型不存在: {car_type}")
            return None

        model_cls = self._load_lightgbm_model_class()
        if model_cls is None:
            return None

        try:
            model = model_cls.load(str(model_path))
            self._lightgbm_car_types_cache[car_type] = model
            return model
        except Exception as e:
            logger.error(f"加载 LightGBM 模型失败 ({car_type}): {e}")
            return None

    def _build_lightgbm_features(
        self,
        brand_series: str,
        new_price: float,
        year: float,
        grade: str = "",
        city: str = "",
        mileage: float = 0.0,
        vehicle_type: str = "",
        vehicle_size: str = "",
        vehicle_attr: str = "",
    ) -> Dict[str, Any]:
        """构造 LightGBM 预测特征"""
        return {
            '使用年限': year,
            '新车的价格': new_price,
            '行驶里程': mileage,
            '品牌车系': brand_series,
            '车辆评级': grade or "中",
            '车辆大类': vehicle_type or "",
            '车辆小类': vehicle_size or "",
            '车辆属性': vehicle_attr or "",
            '城市': city or "",
        }

    def _predict_curve_by_brand_series(
        self,
        brand_series: str,
        year: float,
        new_price: float
    ) -> PredictionResult:
        """按旧 curve 模型预测品牌车系价格"""
        # 【方案三】优先尝试分段模型
        model = self._load_segmented_model(brand_series, year)
        model_source = "segmented"
        
        if model is None:
            # 回退到全量模型
            model = self._load_brand_series_model(brand_series)
            model_source = "full"
        
        if model is None:
            return PredictionResult(
                success=False,
                error_message=f"未找到品牌车系模型: {brand_series}"
            )
        
        rate = model.predict(year)
        price = model.predict_price(year, new_price)
        
        return PredictionResult(
            success=True,
            predicted_price=price,
            residual_rate=rate,
            model_type=f"{model.model_type}({model_source})",
            model_family="curve",
            explanation_source="heuristic_rules",
            r2=model.r2
        )

    def _predict_curve_by_car_type(
        self,
        car_type: str,
        year: float,
        new_price: float
    ) -> PredictionResult:
        """按旧 curve 模型预测车辆类别价格"""
        model = self._load_car_type_model(car_type)
        if model is None:
            return PredictionResult(
                success=False,
                error_message=f"未找到车辆类别模型: {car_type}"
            )
        
        rate = model.predict(year)
        price = model.predict_price(year, new_price)
        
        return PredictionResult(
            success=True,
            predicted_price=price,
            residual_rate=rate,
            model_type=model.model_type,
            model_family="curve",
            explanation_source="heuristic_rules",
            r2=model.r2
        )

    def _predict_lightgbm_by_brand_series(
        self,
        brand_series: str,
        year: float,
        new_price: float,
        *,
        grade: str = "",
        city: str = "",
        mileage: float = 0.0,
        vehicle_type: str = "",
        vehicle_size: str = "",
        vehicle_attr: str = "",
    ) -> PredictionResult:
        """按 LightGBM 品牌车系模型预测价格"""
        model = self._load_lightgbm_brand_series_model(brand_series)
        if model is None:
            return PredictionResult(
                success=False,
                error_message=f"未找到 LightGBM 品牌车系模型: {brand_series}"
            )

        features = self._build_lightgbm_features(
            brand_series=brand_series,
            new_price=new_price,
            year=year,
            grade=grade,
            city=city,
            mileage=mileage,
            vehicle_type=vehicle_type,
            vehicle_size=vehicle_size,
            vehicle_attr=vehicle_attr,
        )

        try:
            rate = model.predict(features)
            price = model.predict_price(features, new_price=new_price)
            contributions = model.predict_contributions(features)
        except Exception as e:
            return PredictionResult(success=False, error_message=f"LightGBM 品牌车系预测失败: {e}")

        return PredictionResult(
            success=True,
            predicted_price=price,
            residual_rate=rate,
            model_type=model.model_type,
            model_family="lightgbm",
            feature_contributions=contributions,
            explanation_source="lightgbm_pred_contrib",
            r2=model.r2,
        )

    def _predict_lightgbm_by_car_type(
        self,
        car_type: str,
        year: float,
        new_price: float,
        *,
        brand_series: Optional[str] = None,
        grade: str = "",
        city: str = "",
        mileage: float = 0.0,
        vehicle_type: str = "",
        vehicle_size: str = "",
        vehicle_attr: str = "",
    ) -> PredictionResult:
        """按 LightGBM 车辆类别模型预测价格"""
        model = self._load_lightgbm_car_type_model(car_type)
        if model is None:
            return PredictionResult(
                success=False,
                error_message=f"未找到 LightGBM 车辆类别模型: {car_type}"
            )

        if not brand_series:
            return PredictionResult(
                success=False,
                error_message="LightGBM 车辆类别预测缺少 brand_series 特征"
            )

        features = self._build_lightgbm_features(
            brand_series=brand_series,
            new_price=new_price,
            year=year,
            grade=grade,
            city=city,
            mileage=mileage,
            vehicle_type=vehicle_type,
            vehicle_size=vehicle_size,
            vehicle_attr=vehicle_attr,
        )

        try:
            rate = model.predict(features)
            price = model.predict_price(features, new_price=new_price)
            contributions = model.predict_contributions(features)
        except Exception as e:
            return PredictionResult(success=False, error_message=f"LightGBM 车辆类别预测失败: {e}")

        return PredictionResult(
            success=True,
            predicted_price=price,
            residual_rate=rate,
            model_type=model.model_type,
            model_family="lightgbm",
            feature_contributions=contributions,
            explanation_source="lightgbm_pred_contrib",
            r2=model.r2,
        )
    
    def predict_by_brand_series(
        self,
        brand_series: str,
        year: float,
        new_price: float,
        *,
        grade: str = "",
        city: str = "",
        mileage: float = 0.0,
        vehicle_type: str = "",
        vehicle_size: str = "",
        vehicle_attr: str = "",
        model_family: str = "curve",
    ) -> PredictionResult:
        """
        按品牌车系预测价格 (优先使用分段模型)
        
        Args:
            brand_series: 品牌-车系，如 "本田-飞度"
            year: 使用年限
            new_price: 新车价格（万元）
            
        Returns:
            预测结果
        """
        if year <= 0:
            return PredictionResult(success=False, error_message="使用年限必须大于0")
        
        if new_price <= 0:
            return PredictionResult(success=False, error_message="新车价格必须大于0")

        if model_family == "lightgbm":
            return self._predict_lightgbm_by_brand_series(
                brand_series,
                year,
                new_price,
                grade=grade,
                city=city,
                mileage=mileage,
                vehicle_type=vehicle_type,
                vehicle_size=vehicle_size,
                vehicle_attr=vehicle_attr,
            )

        return self._predict_curve_by_brand_series(brand_series, year, new_price)
    
    def predict_by_car_type(
        self,
        car_type: str,
        year: float,
        new_price: float,
        *,
        brand_series: Optional[str] = None,
        grade: str = "",
        city: str = "",
        mileage: float = 0.0,
        vehicle_type: str = "",
        vehicle_size: str = "",
        vehicle_attr: str = "",
        model_family: str = "curve",
    ) -> PredictionResult:
        """
        按车辆类别预测价格
        
        Args:
            car_type: 车辆类别，如 "轿车-紧凑型车"
            year: 使用年限
            new_price: 新车价格（万元）
            
        Returns:
            预测结果
        """
        if year <= 0:
            return PredictionResult(success=False, error_message="使用年限必须大于0")
        
        if new_price <= 0:
            return PredictionResult(success=False, error_message="新车价格必须大于0")

        if model_family == "lightgbm":
            return self._predict_lightgbm_by_car_type(
                car_type,
                year,
                new_price,
                brand_series=brand_series,
                grade=grade,
                city=city,
                mileage=mileage,
                vehicle_type=vehicle_type,
                vehicle_size=vehicle_size,
                vehicle_attr=vehicle_attr,
            )

        return self._predict_curve_by_car_type(car_type, year, new_price)
    
    def list_available_brand_series(self) -> List[str]:
        """
        获取可用的品牌车系列表
        
        Returns:
            品牌车系名称列表
        """
        if not self.brand_series_model_dir.exists():
            return []
        
        models = []
        for pkl_file in self.brand_series_model_dir.glob('*.pkl'):
            # 从文件名还原品牌车系名
            name = pkl_file.stem
            models.append(name)
        
        return sorted(models)
    
    def list_available_car_types(self) -> List[str]:
        """
        获取可用的车辆类别列表
        
        Returns:
            车辆类别名称列表
        """
        if not self.car_types_model_dir.exists():
            return []
        
        models = []
        for pkl_file in self.car_types_model_dir.glob('*.pkl'):
            name = pkl_file.stem
            models.append(name)
        
        return sorted(models)
    
    def get_brand_series_model_info(self, brand_series: str) -> Optional[Dict]:
        """
        获取品牌车系模型的详细信息
        
        Args:
            brand_series: 品牌-车系名称
            
        Returns:
            模型信息字典
        """
        model = self._load_brand_series_model(brand_series)
        if model is None:
            return None
        
        return {
            'name': model.group_name,
            'model_type': model.model_type,
            'formula': model.get_formula(),
            'r2': model.r2,
            'rmse': model.rmse,
            'sample_count': model.sample_count
        }
    
    def get_car_type_model_info(self, car_type: str) -> Optional[Dict]:
        """
        获取车辆类别模型的详细信息
        
        Args:
            car_type: 车辆类别名称
            
        Returns:
            模型信息字典
        """
        model = self._load_car_type_model(car_type)
        if model is None:
            return None
        
        return {
            'name': model.group_name,
            'model_type': model.model_type,
            'formula': model.get_formula(),
            'r2': model.r2,
            'rmse': model.rmse,
            'sample_count': model.sample_count
        }
    
    def predict_with_fallback(
        self,
        brand_series: Optional[str],
        car_type: Optional[str],
        year: float,
        new_price: float
    ) -> PredictionResult:
        """
        带回退的预测：优先使用品牌车系模型，失败时使用车辆类别模型
        
        Args:
            brand_series: 品牌-车系，可选
            car_type: 车辆类别，可选
            year: 使用年限
            new_price: 新车价格（万元）
            
        Returns:
            预测结果
        """
        # 首先尝试品牌车系
        if brand_series:
            result = self.predict_by_brand_series(brand_series, year, new_price)
            if result.success:
                return result
        
        # 回退到车辆类别
        if car_type:
            return self.predict_by_car_type(car_type, year, new_price)
        
        return PredictionResult(
            success=False,
            error_message="未提供有效的品牌车系或车辆类别"
        )


# ============= 命令行接口 =============

def main():
    """命令行测试入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='二手车价格预测工具')
    parser.add_argument('--brand_series', '-b', help='品牌-车系，如 "本田-飞度"')
    parser.add_argument('--car_type', '-t', help='车辆类别，如 "轿车-紧凑型车"')
    parser.add_argument('--year', '-y', type=float, help='使用年限')
    parser.add_argument('--new_price', '-p', type=float, help='新车价格（万元）')
    parser.add_argument('--list_models', '-l', action='store_true', help='列出可用模型')
    
    args = parser.parse_args()
    
    predictor = PricePredictor()
    
    if args.list_models:
        print("可用的品牌车系模型:")
        for name in predictor.list_available_brand_series()[:20]:
            print(f"  - {name}")
        print(f"  ... 共 {len(predictor.list_available_brand_series())} 个\n")
        
        print("可用的车辆类别模型:")
        for name in predictor.list_available_car_types():
            print(f"  - {name}")
        return
    
    if not args.year or not args.new_price:
        print("错误: 进行预测时，必须指定 --year 和 --new_price")
        return

    if args.brand_series:
        print(f"品牌车系预测: {args.brand_series}")
        result = predictor.predict_by_brand_series(args.brand_series, args.year, args.new_price)
    elif args.car_type:
        print(f"车辆类别预测: {args.car_type}")
        result = predictor.predict_by_car_type(args.car_type, args.year, args.new_price)
    else:
        print("错误: 请指定 --brand_series 或 --car_type")
        return
    
    print(f"\n输入参数:")
    print(f"  使用年限: {args.year} 年")
    print(f"  新车价格: {args.new_price} 万元")
    
    print(f"\n预测结果:")
    if result.success:
        print(f"  预测价格: {result.predicted_price} 万元")
        print(f"  残值率: {result.residual_rate:.1%}")
        print(f"  模型类型: {result.model_type}")
        print(f"  模型R²: {result.r2:.4f}")
    else:
        print(f"  预测失败: {result.error_message}")


if __name__ == '__main__':
    main()
