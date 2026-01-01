"""
二手车残值预测核心模块

功能：
1. 基于模型的残值预测（品牌车系优先，回退车辆类别）
2. 相近车辆检索
3. 成交价格微调（加权平均法）

使用方法：
    from residual_predictor import ResidualPredictor
    
    predictor = ResidualPredictor()
    result = predictor.predict(
        vehicle_full_name='起亚 K3 2013款 1.6 手自一体 GLS',
        brand_series='起亚-K3',
        years=11.67,
        grade='中',
        city='成都',
        mileage=19.95
    )
"""

import logging
import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from price_predictor_step5 import PricePredictor, PredictionResult
from residual_data_index_step5 import ResidualDataIndex, ResidualRecord, SimilarVehicle

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class AdjustmentParams:
    """调整参数"""
    method: str = "confidence_dynamic"  # 方案B：置信度动态调整
    adjustment_factor: float = 1.0  # 调整系数（最优值）
    max_adjustment: float = 0.30  # 最大调整幅度 30%（最优值）


@dataclass
class PredictionDebugInfo:
    """预测调试信息"""
    # 模型信息
    model_used: str = ""  # "brand_series" 或 "car_type"
    model_name: str = ""
    model_type: str = ""
    model_r2: float = 0.0
    model_prediction: float = 0.0
    
    # 相近车辆
    similar_vehicles: List[Dict] = field(default_factory=list)
    similar_avg_price: float = 0.0
    
    # 调整信息
    adjustment_method: str = ""
    adjustment_params: Dict = field(default_factory=dict)
    adjustment_delta: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'model_used': self.model_used,
            'model_name': self.model_name,
            'model_type': self.model_type,
            'model_r2': self.model_r2,
            'model_prediction': self.model_prediction,
            'similar_vehicles': self.similar_vehicles,
            'similar_avg_price': self.similar_avg_price,
            'adjustment_method': self.adjustment_method,
            'adjustment_params': self.adjustment_params,
            'adjustment_delta': self.adjustment_delta
        }



import sys
# 添加 C2B2C 模型路径
c2b2c_model_path = str(Path(__file__).parent / '..' / 'price_model' / 'c2b2c_model')
if c2b2c_model_path not in sys.path:
    sys.path.insert(0, c2b2c_model_path)

from predictor import C2B2CPricePredictor

@dataclass
class ResidualPredictionResult:
    """残值预测结果"""
    success: bool
    predicted_price: float = 0.0
    new_price: float = 0.0
    residual_rate: float = 0.0
    price_matrix: Dict = field(default_factory=dict)  # C2B2C 价格矩阵
    identical_records: List[Dict] = field(default_factory=list)
    debug: Optional[PredictionDebugInfo] = None
    error_message: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'success': self.success,
            'predicted_price': self.predicted_price,
            'new_price': self.new_price,
            'residual_rate': self.residual_rate,
            'price_matrix': self.price_matrix,
            'identical_records': self.identical_records,
            'debug': self.debug.to_dict() if self.debug else None,
            'error_message': self.error_message
        }


class ResidualPredictor:
    """二手车残值预测器"""
    
    def __init__(
        self,
        brand_series_model_dir: Optional[str] = None,
        car_types_model_dir: Optional[str] = None,
        residual_data_csv: Optional[str] = None,
        adjustment_params: Optional[AdjustmentParams] = None
    ):
        """
        初始化预测器
        
        Args:
            brand_series_model_dir: 品牌车系模型目录
            car_types_model_dir: 车辆类别模型目录
            residual_data_csv: 成交数据 CSV 路径
            adjustment_params: 调整参数
        """
        script_dir = Path(__file__).parent
        
        # 初始化价格预测器
        self.price_predictor = PricePredictor(
            brand_series_model_dir=brand_series_model_dir,
            car_types_model_dir=car_types_model_dir
        )
        
        # 初始化成交数据索引
        self.data_index = ResidualDataIndex()
        csv_path = residual_data_csv or str(script_dir / '..' / 'output' / 'residual_value_data.csv')
        index_cache_path = str(script_dir / '..' / 'index' / 'residual_data_index.pkl')
        if Path(csv_path).exists():
            self.data_index.build_from_csv(csv_path, index_path=index_cache_path)
        else:
            logger.warning(f"成交数据文件不存在: {csv_path}")
        
        # 调整参数
        self.adjustment_params = adjustment_params or AdjustmentParams()
        
        # 初始化 C2B2C 价格预测器
        try:
            # 使用正确的绝对路径
            c2b2c_model_dir = str(script_dir.parent / 'price_model' / 'c2b2c_model')
            self.c2b2c_predictor = C2B2CPricePredictor(model_dir=c2b2c_model_dir)
            logger.info(f"C2B2C 价格预测器初始化 (path={c2b2c_model_dir})...")
            if self.c2b2c_predictor.load():
                logger.info("C2B2C 价格预测器加载成功")
            else:
                logger.warning("C2B2C 价格预测器加载失败")
                self.c2b2c_predictor = None
        except Exception as e:
            logger.error(f"C2B2C 价格预测器初始化出错: {e}")
            self.c2b2c_predictor = None
        
        # 加载自适应区间配置
        self.adaptive_range_config = self._load_adaptive_range_config(script_dir)
    
    def predict(
        self,
        vehicle_full_name: str,
        brand_series: str,
        years: float,
        grade: str = "中",
        city: str = "",
        mileage: float = 0.0,
        new_price: Optional[float] = None,
        top_k_similar: int = 30
    ) -> ResidualPredictionResult:
        """
        预测二手车残值价格
        
        Args:
            vehicle_full_name: 车辆全称
            brand_series: 品牌-车系
            years: 使用年限
            grade: 车辆评级
            city: 城市
            mileage: 行驶里程
            new_price: 新车价格（如果不传则从数据中推断）
            top_k_similar: 检索的相近车辆数量
            
        Returns:
            预测结果
        """
        debug = PredictionDebugInfo()
        
        try:
            # ========== Step 1: 确定新车价格 ==========
            if new_price is None:
                new_price = self._infer_new_price(brand_series)
                if new_price is None:
                    return ResidualPredictionResult(
                        success=False,
                        error_message=f"无法确定新车价格，请提供 new_price 参数"
                    )
            
            # ========== Step 2: 模型预测 ==========
            model_result = self._predict_by_model(brand_series, vehicle_full_name, years, new_price)
            
            if not model_result['success']:
                return ResidualPredictionResult(
                    success=False,
                    error_message=model_result['error']
                )
            
            debug.model_used = model_result['model_used']
            debug.model_name = model_result['model_name']
            debug.model_type = model_result['model_type']
            debug.model_r2 = model_result['r2']
            debug.model_prediction = model_result['predicted_price']
            
            model_price = model_result['predicted_price']
            
            # ========== Step 3: 查找完全相同的记录 ==========
            identical = self.data_index.find_identical_records(
                vehicle_full_name, brand_series, years, grade, city, mileage
            )
            identical_records = [
                {
                    'vehicle_full_name': r.vehicle_full_name,
                    'used_price': r.used_price,
                    'adjusted_price': r.adjusted_price,
                    'years': r.years,
                    'city': r.city
                }
                for r in identical
            ]
            
            # ========== Step 4: 检索相近车辆 ==========
            similar = self.data_index.search_similar(
                vehicle_full_name, brand_series, years,
                grade=grade, city=city, mileage=mileage,
                exclude_identical=True, top_k=top_k_similar
            )
            
            debug.similar_vehicles = [
                {
                    'vehicle_full_name': s.record.vehicle_full_name,
                    'used_price': s.record.used_price,
                    'adjusted_price': s.record.adjusted_price,
                    'years': s.record.years,
                    'grade': s.record.grade,
                    'city': s.record.city,
                    'mileage': s.record.mileage,
                    'score': s.score,
                    'matched_features': s.matched_features
                }
                for s in similar
            ]
            
            # ========== Step 5: 成交价格微调 ==========
            # 使用相似车辆进行置信度动态调整（不使用完全相同记录，避免数据泄露）
            final_price = model_price
            adjustment_method = "model_only"
            
            # 置信度动态调整法：基于相似车辆（排除完全相同记录）
            if similar:
                # 方案B：置信度动态调整法
                # 对不同评级的成交价进行校正后再计算均价
                grade_adjustment = {
                    ('优', '中'): 1.05,
                    ('优', '差'): 1.10,
                    ('中', '优'): 0.952,
                    ('中', '差'): 1.05,
                    ('差', '优'): 0.909,
                    ('差', '中'): 0.952,
                }
                
                corrected_prices = []
                for s in similar:
                    original_price = s.record.adjusted_price
                    record_grade = s.record.grade
                    correction_factor = grade_adjustment.get((grade, record_grade), 1.0)
                    corrected_price = original_price * correction_factor
                    corrected_prices.append(corrected_price)
                
                similar_avg = sum(corrected_prices) / len(corrected_prices)
                debug.similar_avg_price = round(similar_avg, 2)
                
                # 计算偏差
                if model_price > 0:
                    deviation = (similar_avg - model_price) / model_price
                else:
                    deviation = 0
                
                # 计算置信度
                avg_score = sum(s.score for s in similar) / len(similar)
                max_possible_score = 160
                confidence = min(1.0, avg_score / max_possible_score)
                
                # 计算调整量 δ
                adjustment_factor = self.adjustment_params.adjustment_factor
                max_adjustment = self.adjustment_params.max_adjustment
                
                delta = deviation * confidence * adjustment_factor
                delta = max(-max_adjustment, min(max_adjustment, delta))
                
                adjusted_price = model_price * (1 + delta)
                
                adjustment_method = "confidence_dynamic"
                debug.adjustment_method = adjustment_method
                debug.adjustment_params = {
                    'deviation': round(deviation, 4),
                    'confidence': round(confidence, 4),
                    'adjustment_factor': adjustment_factor,
                    'max_adjustment': max_adjustment,
                    'delta': round(delta, 4),
                    'grade_correction_applied': True
                }
                debug.adjustment_delta = round(adjusted_price - model_price, 2)
                
                final_price = adjusted_price
            
            # 计算残值率
            residual_rate = final_price / new_price if new_price > 0 else 0

            
            # ========== Step 6: 计算 C2B2C 价格矩阵 ==========
            price_matrix = {}
            if self.c2b2c_predictor and self.c2b2c_predictor._loaded:
                try:
                    price_matrix = self.c2b2c_predictor.predict_numeric(final_price)
                    
                    # 先应用自适应区间扩展
                    price_matrix = self._apply_adaptive_range(price_matrix, final_price)
                    
                    # 检查完全相同记录是否在 B2B 预测区间内（使用扩展后的区间）
                    grade_map = {'优': 'a', '中': 'b', '差': 'c'}
                    target_col = grade_map.get(grade, 'b')
                    b2b_low = price_matrix['b2BPrices'][target_col]['low']
                    b2b_up = price_matrix['b2BPrices'][target_col]['up']
                    
                    for record in identical_records:
                        u_price = record['used_price']
                        if b2b_low <= u_price <= b2b_up:
                            record['in_range'] = True
                        else:
                            record['in_range'] = False
                        record['prediction_range'] = {'low': b2b_low, 'up': b2b_up}
                        
                except Exception as e:
                    logger.error(f"C2B2C 预测失败: {e}")

            
            return ResidualPredictionResult(
                success=True,
                predicted_price=round(final_price, 2),
                new_price=new_price,
                residual_rate=round(residual_rate, 4),
                price_matrix=price_matrix,
                identical_records=identical_records,
                debug=debug
            )
            
        except Exception as e:
            logger.exception("预测过程发生异常")
            return ResidualPredictionResult(
                success=False,
                error_message=str(e)
            )
    
    def _load_adaptive_range_config(self, script_dir: Path) -> Dict:
        """加载自适应区间配置"""
        config_path = script_dir.parent / 'config' / 'adaptive_range.yaml'
        default_config = {
            'enabled': False,
            'rules': {
                'low_price': {'threshold': 1.0, 'percentage': 0.20, 'absolute': 0.20},
                'mid_price': {'threshold': 2.0, 'percentage': 0.12, 'absolute': 0.15},
                'high_price': {'threshold': 3.0, 'percentage': 0.08, 'absolute': 0.0}
            }
        }
        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                logger.info(f"自适应区间配置已加载: {config_path}")
                return config
        except Exception as e:
            logger.warning(f"加载自适应区间配置失败: {e}，使用默认值")
        return default_config
    
    def _apply_adaptive_range(self, price_matrix: Dict, mid_price: float) -> Dict:
        """
        对 B2B 价格区间应用自适应扩展
        
        Args:
            price_matrix: 原始价格矩阵
            mid_price: 预测的中间价（万元）
        
        Returns:
            修改后的价格矩阵
        """
        if not self.adaptive_range_config.get('enabled', False):
            return price_matrix
        
        # Check if b2b adaptive range is enabled
        price_types = self.adaptive_range_config.get('price_types', {})
        if not price_types.get('b2b', True):
            return price_matrix
        
        if 'b2BPrices' not in price_matrix:
            return price_matrix
        
        rules = self.adaptive_range_config.get('rules', {})
        
        # 确定适用的规则
        if mid_price < rules.get('low_price', {}).get('threshold', 1.0):
            rule = rules.get('low_price', {})
        elif mid_price < rules.get('mid_price', {}).get('threshold', 2.0):
            rule = rules.get('mid_price', {})
        elif mid_price < rules.get('high_price', {}).get('threshold', 3.0):
            rule = rules.get('high_price', {})
        else:
            # >= 3万，不扩展
            return price_matrix
        
        pct = rule.get('percentage', 0)
        abs_val = rule.get('absolute', 0)
        min_half_width = max(mid_price * pct, abs_val)
        
        if min_half_width <= 0:
            return price_matrix
        
        # 对每个评级 (a/b/c) 扩展区间
        for condition in ['a', 'b', 'c']:
            if condition in price_matrix['b2BPrices']:
                orig_low = price_matrix['b2BPrices'][condition].get('low', mid_price)
                orig_up = price_matrix['b2BPrices'][condition].get('up', mid_price)
                cond_mid = price_matrix['b2BPrices'][condition].get('mid', mid_price)
                
                new_low = min(orig_low, cond_mid - min_half_width)
                new_up = max(orig_up, cond_mid + min_half_width)
                
                price_matrix['b2BPrices'][condition]['low'] = round(new_low, 2)
                price_matrix['b2BPrices'][condition]['up'] = round(new_up, 2)
        
        return price_matrix
    
    def _predict_by_model(
        self,
        brand_series: str,
        vehicle_full_name: str,
        years: float,
        new_price: float
    ) -> Dict[str, Any]:
        """
        使用模型预测
        
        优先使用品牌车系模型，如果不存在则使用车辆类别模型
        """
        # 尝试品牌车系模型
        result = self.price_predictor.predict_by_brand_series(brand_series, years, new_price)
        
        if result.success:
            return {
                'success': True,
                'model_used': 'brand_series',
                'model_name': brand_series,
                'model_type': result.model_type,
                'r2': result.r2,
                'predicted_price': result.predicted_price,
                'residual_rate': result.residual_rate
            }
        
        # 回退到车辆类别模型
        car_type = self.data_index.get_car_type_for_brand_series(brand_series)
        
        if car_type:
            result = self.price_predictor.predict_by_car_type(car_type, years, new_price)
            
            if result.success:
                return {
                    'success': True,
                    'model_used': 'car_type',
                    'model_name': car_type,
                    'model_type': result.model_type,
                    'r2': result.r2,
                    'predicted_price': result.predicted_price,
                    'residual_rate': result.residual_rate
                }
        
        return {
            'success': False,
            'error': f"无法找到适用的模型: 品牌车系={brand_series}, 车辆类别={car_type}"
        }
    
    def _infer_new_price(self, brand_series: str) -> Optional[float]:
        """
        从成交数据中推断新车价格
        
        Args:
            brand_series: 品牌-车系
            
        Returns:
            新车价格的中位数，如果找不到返回 None
        """
        records = self.data_index.get_records_by_brand_series(brand_series)
        if not records:
            return None
        
        prices = [r.new_price for r in records if r.new_price > 0]
        if not prices:
            return None
        
        # 返回中位数
        prices.sort()
        mid = len(prices) // 2
        return prices[mid]
    
    def get_available_brand_series(self) -> List[str]:
        """获取可用的品牌车系列表"""
        return self.price_predictor.list_available_brand_series()
    
    def get_available_car_types(self) -> List[str]:
        """获取可用的车辆类别列表"""
        return self.price_predictor.list_available_car_types()


if __name__ == '__main__':
    # 测试
    import os
    os.chdir(Path(__file__).parent.parent)
    
    predictor = ResidualPredictor()
    
    # 测试预测
    result = predictor.predict(
        vehicle_full_name='起亚 K3 2013款 1.6 手自一体 GLS',
        brand_series='起亚-K3',
        years=11.67,
        grade='中',
        city='成都',
        mileage=19.95
    )
    
    print(f"\n预测结果:")
    print(f"  成功: {result.success}")
    print(f"  预测价格: {result.predicted_price} 万")
    print(f"  新车价格: {result.new_price} 万")
    print(f"  残值率: {result.residual_rate:.1%}")
    
    if result.debug:
        print(f"\n调试信息:")
        print(f"  使用模型: {result.debug.model_used}")
        print(f"  模型名称: {result.debug.model_name}")
        print(f"  模型预测: {result.debug.model_prediction} 万")
        print(f"  模型R²: {result.debug.model_r2:.4f}")
        print(f"  相近车辆均价: {result.debug.similar_avg_price} 万")
        print(f"  调整方法: {result.debug.adjustment_method}")
        print(f"  调整量: {result.debug.adjustment_delta} 万")
        
        if result.debug.similar_vehicles:
            print(f"\n相近车辆:")
            for v in result.debug.similar_vehicles[:3]:
                print(f"    {v['vehicle_full_name'][:30]}... 成交价={v['adjusted_price']}万")
    
    if result.identical_records:
        print(f"\n完全相同记录:")
        for r in result.identical_records:
            print(f"    成交价={r['used_price']}万, 城市={r['city']}")
