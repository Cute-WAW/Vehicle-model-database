"""
残值预测参数优化程序

功能：
1. 从成交数据中随机抽取验证集
2. 网格搜索最优的 adjustment_factor 和 max_adjustment 参数
3. 输出参数优化过程和最优结果

使用方法：
    cd d:/antigravity/price_evaluation/车型库映射
    python src/tune_adjustment_params.py
"""

import random
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 切换到项目根目录
import os
os.chdir(Path(__file__).parent.parent)

from residual_predictor_step5 import ResidualPredictor, AdjustmentParams


@dataclass
class TuningResult:
    """调参结果"""
    adjustment_factor: float
    max_adjustment: float
    mae: float  # 平均绝对误差
    rmse: float  # 均方根误差
    mape: float  # 平均绝对百分比误差
    within_10pct: float  # 误差在10%以内的比例
    within_20pct: float  # 误差在20%以内的比例


def sample_validation_set(csv_path: str, n_samples: int = 200, seed: int = 42) -> pd.DataFrame:
    """
    从成交数据中随机抽取验证集
    
    Args:
        csv_path: CSV 文件路径
        n_samples: 抽取样本数
        seed: 随机种子
        
    Returns:
        验证集 DataFrame
    """
    random.seed(seed)
    np.random.seed(seed)
    
    df = pd.read_csv(csv_path)
    logger.info(f"原始数据: {len(df)} 条")
    
    # 随机抽取
    if len(df) > n_samples:
        indices = random.sample(range(len(df)), n_samples)
        df_sample = df.iloc[indices].copy()
    else:
        df_sample = df.copy()
    
    logger.info(f"验证集: {len(df_sample)} 条")
    return df_sample


def evaluate_params(
    predictor: ResidualPredictor,
    df_val: pd.DataFrame,
    adjustment_factor: float,
    max_adjustment: float
) -> TuningResult:
    """
    评估指定参数的预测效果
    
    Args:
        predictor: 预测器（需要临时修改参数）
        df_val: 验证集
        adjustment_factor: 调整系数
        max_adjustment: 最大调整幅度
        
    Returns:
        评估结果
    """
    # 临时修改参数
    original_factor = predictor.adjustment_params.adjustment_factor
    original_max = predictor.adjustment_params.max_adjustment
    
    predictor.adjustment_params.adjustment_factor = adjustment_factor
    predictor.adjustment_params.max_adjustment = max_adjustment
    
    errors = []
    pct_errors = []
    
    for _, row in df_val.iterrows():
        try:
            result = predictor.predict(
                vehicle_full_name=str(row.get('车辆全称', '')),
                brand_series=str(row.get('品牌车系', '')),
                years=float(row.get('使用年限', 0)),
                grade=str(row.get('车辆评级', '中')),
                city=str(row.get('城市', '')),
                mileage=float(row.get('行驶里程', 0)) if pd.notna(row.get('行驶里程')) else 0.0,
                new_price=float(row.get('新车的价格', 0))
            )
            
            if result.success and result.predicted_price > 0:
                actual_price = float(row.get('车况校正价', 0))
                predicted_price = result.predicted_price
                
                if actual_price > 0:
                    error = abs(predicted_price - actual_price)
                    pct_error = error / actual_price
                    errors.append(error)
                    pct_errors.append(pct_error)
        except Exception as e:
            pass
    
    # 恢复原始参数
    predictor.adjustment_params.adjustment_factor = original_factor
    predictor.adjustment_params.max_adjustment = original_max
    
    if not errors:
        return TuningResult(
            adjustment_factor=adjustment_factor,
            max_adjustment=max_adjustment,
            mae=float('inf'),
            rmse=float('inf'),
            mape=float('inf'),
            within_10pct=0.0,
            within_20pct=0.0
        )
    
    mae = np.mean(errors)
    rmse = np.sqrt(np.mean(np.array(errors) ** 2))
    mape = np.mean(pct_errors) * 100
    within_10pct = np.mean([1 if e < 0.10 else 0 for e in pct_errors]) * 100
    within_20pct = np.mean([1 if e < 0.20 else 0 for e in pct_errors]) * 100
    
    return TuningResult(
        adjustment_factor=adjustment_factor,
        max_adjustment=max_adjustment,
        mae=mae,
        rmse=rmse,
        mape=mape,
        within_10pct=within_10pct,
        within_20pct=within_20pct
    )


def grid_search(
    predictor: ResidualPredictor,
    df_val: pd.DataFrame,
    factor_range: List[float] = None,
    max_adj_range: List[float] = None
) -> Tuple[TuningResult, List[TuningResult]]:
    """
    网格搜索最优参数
    
    Args:
        predictor: 预测器
        df_val: 验证集
        factor_range: adjustment_factor 搜索范围
        max_adj_range: max_adjustment 搜索范围
        
    Returns:
        (最优结果, 所有结果列表)
    """
    if factor_range is None:
        factor_range = [0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0]
    if max_adj_range is None:
        max_adj_range = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    
    all_results = []
    total = len(factor_range) * len(max_adj_range)
    
    logger.info(f"开始网格搜索: {len(factor_range)} x {len(max_adj_range)} = {total} 组参数")
    
    for i, factor in enumerate(factor_range):
        for j, max_adj in enumerate(max_adj_range):
            result = evaluate_params(predictor, df_val, factor, max_adj)
            all_results.append(result)
            
            progress = (i * len(max_adj_range) + j + 1) / total * 100
            logger.info(f"[{progress:.0f}%] factor={factor:.1f}, max_adj={max_adj:.2f} -> MAPE={result.mape:.2f}%, 10%内={result.within_10pct:.1f}%")
    
    # 找到 MAPE 最低的结果
    best = min(all_results, key=lambda x: x.mape)
    
    return best, all_results


def print_results(best: TuningResult, all_results: List[TuningResult]):
    """打印结果"""
    print("\n" + "=" * 70)
    print("                    参数调优结果")
    print("=" * 70)
    
    print("\n📊 所有参数组合结果（按 MAPE 排序）:")
    print("-" * 70)
    print(f"{'factor':>8} {'max_adj':>8} {'MAE':>8} {'RMSE':>8} {'MAPE':>8} {'<10%':>8} {'<20%':>8}")
    print("-" * 70)
    
    sorted_results = sorted(all_results, key=lambda x: x.mape)
    for r in sorted_results[:15]:  # 只显示前15个
        print(f"{r.adjustment_factor:>8.1f} {r.max_adjustment:>8.2f} {r.mae:>8.2f} {r.rmse:>8.2f} {r.mape:>7.2f}% {r.within_10pct:>7.1f}% {r.within_20pct:>7.1f}%")
    
    print("\n" + "=" * 70)
    print("                    🏆 最优参数")
    print("=" * 70)
    print(f"""
  adjustment_factor = {best.adjustment_factor}
  max_adjustment    = {best.max_adjustment}
  
  评估指标:
    - MAE (平均绝对误差):     {best.mae:.2f} 万元
    - RMSE (均方根误差):      {best.rmse:.2f} 万元
    - MAPE (平均百分比误差):  {best.mape:.2f}%
    - 误差<10% 比例:          {best.within_10pct:.1f}%
    - 误差<20% 比例:          {best.within_20pct:.1f}%
""")
    print("=" * 70)


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                    残值预测 - 参数优化程序                            ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  当前价格微调逻辑（方案B：置信度动态调整法）:                          ║
║                                                                      ║
║    最终价格 = 模型预测价 × (1 + δ)                                    ║
║                                                                      ║
║    其中:                                                             ║
║      偏差 = (相近车辆均价 - 模型预测价) / 模型预测价                   ║
║      置信度 = 相近车辆平均匹配分数 / 160                               ║
║      δ = 偏差 × 置信度 × adjustment_factor                            ║
║      δ 被限制在 [-max_adjustment, +max_adjustment] 范围内              ║
║                                                                      ║
║  可调参数:                                                           ║
║    - adjustment_factor: 调整系数 (0~1)，越大则微调影响越大             ║
║    - max_adjustment: 最大调整幅度 (0~0.3)，限制极端调整                ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    
    # 加载验证集
    csv_path = 'output/residual_value_data.csv'
    df_val = sample_validation_set(csv_path, n_samples=200)
    
    # 初始化预测器
    logger.info("初始化预测器...")
    predictor = ResidualPredictor()
    
    # 网格搜索
    best, all_results = grid_search(predictor, df_val)
    
    # 打印结果
    print_results(best, all_results)
    
    # 保存结果到文件
    results_df = pd.DataFrame([
        {
            'adjustment_factor': r.adjustment_factor,
            'max_adjustment': r.max_adjustment,
            'MAE': r.mae,
            'RMSE': r.rmse,
            'MAPE': r.mape,
            'within_10pct': r.within_10pct,
            'within_20pct': r.within_20pct
        }
        for r in all_results
    ])
    results_df = results_df.sort_values('MAPE')
    results_df.to_csv('tests/tuning_results.csv', index=False)
    logger.info("调参结果已保存到 tests/tuning_results.csv")


if __name__ == '__main__':
    main()
