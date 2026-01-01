"""
Price Logic Step 6 - Price Explanation Module

Generates human-readable explanations for why a price range is recommended.
Uses template-based approach with dynamic data binding.

Usage:
    from price_logic_step6 import PriceExplainer
    
    explainer = PriceExplainer(prediction_result)
    report = explainer.generate_report()
    print(report.to_json())
"""

import json
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ConditionFactor:
    """车况因素影响"""
    name: str           # Factor identifier (e.g., "vehicle_age")
    label: str          # Display label (e.g., "车龄高")
    delta: float        # Price impact in wan yuan (e.g., -0.38)
    reason: str         # Explanation text
    value: Any = None   # Actual value (e.g., 10.9 years)
    benchmark: Any = None  # Benchmark value (e.g., 8.0 years average)
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'label': self.label,
            'delta': round(self.delta, 2),
            'reason': self.reason,
            'value': self.value,
            'benchmark': self.benchmark
        }


@dataclass
class SimilarVehicleInfo:
    """相似车辆信息"""
    name: str
    price: float        # Actual transaction price
    years: float        # Vehicle age
    mileage: float      # Mileage in wan km
    grade: str          # Vehicle condition grade
    score: float        # Similarity score
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'price': round(self.price, 2),
            'years': round(self.years, 1),
            'mileage': round(self.mileage, 1),
            'grade': self.grade,
            'score': round(self.score, 1)
        }


@dataclass
class PriceExplanationReport:
    """价格解释报告"""
    # Price range
    price_low: float
    price_high: float
    price_mid: float
    
    # Model prediction
    model_price: float
    model_type: str     # "brand_series" or "car_type"
    model_name: str
    model_r2: float
    
    # Condition factors
    factors: List[ConditionFactor] = field(default_factory=list)
    total_factor_delta: float = 0.0
    
    # Similar vehicles
    similar_vehicles: List[SimilarVehicleInfo] = field(default_factory=list)
    similar_avg_price: float = 0.0
    
    # Summary
    summary: str = ""
    confidence: str = "medium"  # low, medium, high
    
    def to_dict(self) -> Dict:
        return {
            'price_range': {
                'low': round(self.price_low, 2),
                'mid': round(self.price_mid, 2),
                'high': round(self.price_high, 2)
            },
            'model': {
                'predicted_price': round(self.model_price, 2),
                'type': self.model_type,
                'name': self.model_name,
                'r2': round(self.model_r2, 4)
            },
            'factors': [f.to_dict() for f in self.factors],
            'total_factor_delta': round(self.total_factor_delta, 2),
            'similar_vehicles': [v.to_dict() for v in self.similar_vehicles],
            'similar_avg_price': round(self.similar_avg_price, 2),
            'summary': self.summary,
            'confidence': self.confidence
        }
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class PriceExplainer:
    """
    价格解释器
    
    从 ResidualPredictor 的预测结果生成可解释的价格报告
    """
    
    # Default benchmarks (can be configured)
    DEFAULT_CONFIG = {
        'avg_mileage_per_year': 1.5,  # 万公里/年
        'age_penalty_per_year': 0.03,  # 超龄每年扣减比例
        'mileage_bonus_per_wan': 0.02,  # 里程少每万公里加成比例
        'transfer_penalty': 0.02,  # 每次过户扣减比例
        'condition_adjustments': {
            '优': 0.05,
            '中': 0.0,
            '差': -0.05
        },
        'popular_colors': ['白色', '黑色', '银色', '灰色'],
        'unpopular_color_penalty': 0.02
    }
    
    def __init__(self, prediction_result, config: Optional[Dict] = None):
        """
        初始化价格解释器
        
        Args:
            prediction_result: ResidualPredictionResult from ResidualPredictor.predict()
            config: Optional configuration overrides
        """
        self.result = prediction_result
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        
        # Extract debug info
        self.debug = prediction_result.debug if prediction_result.debug else None
        
    def analyze_age_factor(self, years: float, avg_years: float = 8.0) -> ConditionFactor:
        """分析车龄因素"""
        delta_years = years - avg_years
        
        if delta_years > 0:
            # Older than average
            penalty_rate = self.config['age_penalty_per_year']
            delta = -abs(delta_years * penalty_rate * self.result.predicted_price)
            label = "车龄高"
            reason = f"车龄{years:.1f}年，超出平均{avg_years:.1f}年约{delta_years:.1f}年"
        elif delta_years < -1:
            # Significantly newer
            delta = abs(delta_years * 0.02 * self.result.predicted_price)
            label = "车龄低"
            reason = f"车龄{years:.1f}年，低于平均{avg_years:.1f}年"
        else:
            delta = 0.0
            label = "车龄适中"
            reason = f"车龄{years:.1f}年，接近平均水平"
        
        return ConditionFactor(
            name="vehicle_age",
            label=label,
            delta=delta,
            reason=reason,
            value=years,
            benchmark=avg_years
        )
    
    def analyze_mileage_factor(self, mileage: float, years: float) -> ConditionFactor:
        """分析里程因素"""
        expected_mileage = years * self.config['avg_mileage_per_year']
        delta_mileage = mileage - expected_mileage
        
        if delta_mileage < -2:
            # Much lower mileage
            bonus_rate = self.config['mileage_bonus_per_wan']
            delta = abs(delta_mileage * bonus_rate * self.result.predicted_price)
            label = "里程少"
            reason = f"仅{mileage:.1f}万公里，远低于同龄车平均{expected_mileage:.1f}万公里"
        elif delta_mileage > 2:
            # Higher mileage
            delta = -abs(delta_mileage * 0.015 * self.result.predicted_price)
            label = "里程高"
            reason = f"行驶{mileage:.1f}万公里，高于同龄车平均{expected_mileage:.1f}万公里"
        else:
            delta = 0.0
            label = "里程正常"
            reason = f"行驶{mileage:.1f}万公里，符合同龄车平均水平"
        
        return ConditionFactor(
            name="mileage",
            label=label,
            delta=delta,
            reason=reason,
            value=mileage,
            benchmark=expected_mileage
        )
    
    def analyze_transfer_factor(self, transfer_count: int = 1) -> ConditionFactor:
        """分析过户次数因素"""
        avg_transfers = 1.2
        
        if transfer_count > avg_transfers + 0.5:
            penalty_rate = self.config['transfer_penalty']
            extra_transfers = transfer_count - 1
            delta = -extra_transfers * penalty_rate * self.result.predicted_price
            label = "过户多"
            reason = f"已过户{transfer_count}次，高于平均{avg_transfers:.1f}次"
        else:
            delta = 0.0
            label = "过户正常"
            reason = f"过户{transfer_count}次，属于正常范围"
        
        return ConditionFactor(
            name="transfer_count",
            label=label,
            delta=delta,
            reason=reason,
            value=transfer_count,
            benchmark=avg_transfers
        )
    
    def analyze_color_factor(self, color: str = "") -> ConditionFactor:
        """分析颜色因素"""
        popular_colors = self.config['popular_colors']
        
        if color and color not in popular_colors:
            penalty_rate = self.config['unpopular_color_penalty']
            delta = -penalty_rate * self.result.predicted_price
            label = "冷门色"
            reason = f"{color}为非主流颜色，市场接受度较低"
        else:
            delta = 0.0
            label = "热门色" if color else "颜色未知"
            reason = f"{color or '未知'}是市场热门颜色" if color else "颜色信息缺失"
        
        return ConditionFactor(
            name="color",
            label=label,
            delta=delta,
            reason=reason,
            value=color,
            benchmark=popular_colors
        )
    
    def analyze_condition_factor(self, grade: str = "中") -> ConditionFactor:
        """分析车况因素"""
        adjustments = self.config['condition_adjustments']
        adjustment = adjustments.get(grade, 0.0)
        
        if adjustment > 0:
            delta = adjustment * self.result.predicted_price
            label = "车况优秀"
            reason = "车况评级为优，整体状态良好"
        elif adjustment < 0:
            delta = adjustment * self.result.predicted_price
            label = "车况一般"
            reason = "车况评级为差，可能存在一定问题"
        else:
            delta = 0.0
            label = "车况中等"
            reason = "车况评级为中，属于正常水平"
        
        return ConditionFactor(
            name="condition",
            label=label,
            delta=delta,
            reason=reason,
            value=grade,
            benchmark="中"
        )
    
    def extract_similar_vehicles(self) -> List[SimilarVehicleInfo]:
        """从预测结果提取相似车辆信息"""
        similar_list = []
        
        if self.debug and self.debug.similar_vehicles:
            for sv in self.debug.similar_vehicles[:5]:  # Top 5
                similar_list.append(SimilarVehicleInfo(
                    name=sv.get('name', '未知'),
                    price=sv.get('price', 0.0),
                    years=sv.get('years', 0.0),
                    mileage=sv.get('mileage', 0.0),
                    grade=sv.get('grade', '中'),
                    score=sv.get('score', 0.0)
                ))
        
        return similar_list
    
    def generate_report(
        self,
        years: float = None,
        mileage: float = None,
        grade: str = None,
        color: str = "",
        transfer_count: int = 1
    ) -> PriceExplanationReport:
        """
        生成价格解释报告
        
        Args:
            years: 使用年限
            mileage: 行驶里程 (万公里)
            grade: 车况等级
            color: 车身颜色
            transfer_count: 过户次数
        
        Returns:
            PriceExplanationReport
        """
        # Use provided values or defaults
        years = years or 5.0
        mileage = mileage or 5.0
        grade = grade or "中"
        
        # Analyze each factor
        factors = [
            self.analyze_age_factor(years),
            self.analyze_mileage_factor(mileage, years),
            self.analyze_transfer_factor(transfer_count),
            self.analyze_color_factor(color),
            self.analyze_condition_factor(grade)
        ]
        
        # Filter out zero-impact factors for display
        significant_factors = [f for f in factors if abs(f.delta) > 0.01]
        
        # Calculate total delta
        total_delta = sum(f.delta for f in factors)
        
        # Extract similar vehicles
        similar_vehicles = self.extract_similar_vehicles()
        similar_avg = self.debug.similar_avg_price if self.debug else 0.0
        
        # Get model info
        model_type = self.debug.model_used if self.debug else "unknown"
        model_name = self.debug.model_name if self.debug else "unknown"
        model_r2 = self.debug.model_r2 if self.debug else 0.0
        model_price = self.debug.model_prediction if self.debug else self.result.predicted_price
        
        # Get price range from price_matrix
        price_matrix = self.result.price_matrix
        grade_map = {'优': 'a', '中': 'b', '差': 'c'}
        target_col = grade_map.get(grade, 'b')
        
        if price_matrix and 'b2BPrices' in price_matrix:
            b2b = price_matrix['b2BPrices'].get(target_col, {})
            price_low = float(b2b.get('low', self.result.predicted_price * 0.9))
            price_mid = float(b2b.get('mid', self.result.predicted_price))
            price_high = float(b2b.get('up', self.result.predicted_price * 1.1))
        else:
            price_mid = self.result.predicted_price
            price_low = price_mid * 0.9
            price_high = price_mid * 1.1
        
        # Determine confidence
        if model_r2 > 0.9 and len(similar_vehicles) >= 3:
            confidence = "high"
        elif model_r2 > 0.7 or len(similar_vehicles) >= 2:
            confidence = "medium"
        else:
            confidence = "low"
        
        # Generate summary
        factor_summary = "、".join([f.label for f in significant_factors]) if significant_factors else "无显著调整"
        summary = (
            f"基于{model_name}残值模型预测({model_price:.2f}万)，"
            f"考虑{factor_summary}等因素，"
            f"参考{len(similar_vehicles)}辆相似车成交价，"
            f"建议价格区间为{price_low:.2f}-{price_high:.2f}万元。"
        )
        
        return PriceExplanationReport(
            price_low=price_low,
            price_high=price_high,
            price_mid=price_mid,
            model_price=model_price,
            model_type=model_type,
            model_name=model_name,
            model_r2=model_r2,
            factors=significant_factors,
            total_factor_delta=total_delta,
            similar_vehicles=similar_vehicles,
            similar_avg_price=similar_avg,
            summary=summary,
            confidence=confidence
        )


# Convenience function
def explain_price(prediction_result, **kwargs) -> PriceExplanationReport:
    """
    快捷函数：生成价格解释报告
    
    Args:
        prediction_result: ResidualPredictionResult
        **kwargs: 传递给 generate_report() 的参数
    
    Returns:
        PriceExplanationReport
    """
    explainer = PriceExplainer(prediction_result)
    return explainer.generate_report(**kwargs)


if __name__ == "__main__":
    # Test with mock data
    print("Price Logic Step 6 - Test Mode")
    print("=" * 50)
    
    # Import ResidualPredictor for testing
    try:
        from residual_predictor_step5 import ResidualPredictor
        
        predictor = ResidualPredictor()
        result = predictor.predict(
            vehicle_full_name='丰田 凯美瑞 2015款 2.5G 豪华导航版',
            brand_series='丰田-凯美瑞',
            years=10.9,
            grade='中',
            city='北京',
            mileage=1.5,
            new_price=25.0
        )
        
        if result.success:
            report = explain_price(
                result,
                years=10.9,
                mileage=1.5,
                grade='中',
                color='蓝色',
                transfer_count=3
            )
            print(report.to_json())
        else:
            print(f"Prediction failed: {result.error_message}")
            
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
