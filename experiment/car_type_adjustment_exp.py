"""
车辆大类模型微调比例实验

实验目的：测试不同的微调比例（adjustment_factor）对 car_type 模型命中率的影响
"""

import sys
from pathlib import Path

script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir / 'src'))

import os
os.chdir(script_dir)


import os
os.chdir(script_dir)

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional, Dict

from residual_predictor_step5 import ResidualPredictor, AdjustmentParams


def run_experiment(df, adjustment_factor: float, max_adjustment: float):
    """运行单次实验"""
    params = AdjustmentParams(
        adjustment_factor=adjustment_factor,
        max_adjustment=max_adjustment
    )
    
    predictor = ResidualPredictor(
        residual_data_csv=str(Path('output/residual_value_data_for_build_model.csv').absolute()),
        adjustment_params=params
    )
    
    # 仅统计 car_type 模型的结果
    car_type_hit = 0
    car_type_total = 0
    brand_series_hit = 0
    brand_series_total = 0
    
    for idx, row in df.iterrows():
        try:
            pred = predictor.predict(
                vehicle_full_name=str(row.get('车辆全称', '')),
                brand_series=str(row.get('品牌车系', '')),
                years=float(row.get('使用年限', 0)),
                grade=str(row.get('车辆评级', '中')),
                city=str(row.get('城市', '')),
                mileage=float(row.get('行驶里程', 0)) if pd.notna(row.get('行驶里程')) else 0,
                new_price=float(row.get('新车的价格', 0)) if row.get('新车的价格', 0) > 0 else None
            )
            
            if not pred.success or not pred.price_matrix:
                continue
            
            actual_price = float(row.get('二手车的成交价', 0))
            grade = str(row.get('车辆评级', '中'))
            model_used = pred.debug.model_used if pred.debug else 'unknown'
            
            grade_map = {'优': 'a', '中': 'b', '差': 'c'}
            target_col = grade_map.get(grade, 'b')
            
            b2b_low = pred.price_matrix['b2BPrices'][target_col]['low']
            b2b_up = pred.price_matrix['b2BPrices'][target_col]['up']
            
            hit = b2b_low <= actual_price <= b2b_up
            
            if model_used == 'car_type':
                car_type_total += 1
                if hit:
                    car_type_hit += 1
            elif model_used == 'brand_series':
                brand_series_total += 1
                if hit:
                    brand_series_hit += 1
                    
        except Exception:
            continue
    
    return {
        'car_type_hit': car_type_hit,
        'car_type_total': car_type_total,
        'car_type_rate': car_type_hit / car_type_total if car_type_total > 0 else 0,
        'brand_series_hit': brand_series_hit,
        'brand_series_total': brand_series_total,
        'brand_series_rate': brand_series_hit / brand_series_total if brand_series_total > 0 else 0,
    }


def main():
    # 加载数据
    print("加载数据...")
    df = pd.read_csv('output/residual_value_data_for_build_model.csv')
    df = df.sample(n=2000, random_state=42)
    print(f"采样: {len(df)} 条")
    
    # 测试不同的 adjustment_factor
    factors = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    max_adj = 0.30  # 保持 max_adjustment 固定
    
    print("\n开始实验...")
    print("=" * 70)
    results = []
    
    for factor in factors:
        print(f"测试 adjustment_factor = {factor}...")
        result = run_experiment(df, factor, max_adj)
        result['factor'] = factor
        results.append(result)
        print(f"  car_type: {result['car_type_hit']}/{result['car_type_total']} = {result['car_type_rate']:.2%}")
        print(f"  brand_series: {result['brand_series_hit']}/{result['brand_series_total']} = {result['brand_series_rate']:.2%}")
    
    print("\n" + "=" * 70)
    print("实验汇总")
    print("=" * 70)
    print(f"{'Factor':<10} {'car_type命中率':<18} {'brand_series命中率':<18}")
    print("-" * 50)
    for r in results:
        print(f"{r['factor']:<10} {r['car_type_rate']:.2%} ({r['car_type_hit']}/{r['car_type_total']})     {r['brand_series_rate']:.2%} ({r['brand_series_hit']}/{r['brand_series_total']})")


if __name__ == '__main__':
    main()
