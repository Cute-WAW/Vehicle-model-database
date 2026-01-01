"""
实验七：自适应 B2B 区间范围 (Adaptive B2B Range)

假设：低价车（<1万）的 B2B 区间太窄，导致命中率低。
方案：对低价车扩大价格区间（使用更大的比例或设置最小绝对宽度）。

本脚本通过"后处理"方式模拟这一逻辑，不修改模型本身。
"""

import sys
from pathlib import Path
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir / 'src'))
import os
os.chdir(script_dir)

import pandas as pd
from residual_predictor_step5 import ResidualPredictor


def apply_adaptive_range(mid: float, low: float, up: float) -> tuple:
    """
    自适应区间扩展逻辑
    
    Args:
        mid: 预测中间价（万元）
        low: 原始下限
        up: 原始上限
    
    Returns:
        (new_low, new_up): 扩展后的区间
    """
    if mid < 1.0:
        # 预测价 < 1万：区间至少 ±15% 或 ±1500元
        min_half_width = max(mid * 0.15, 0.15)
    elif mid < 2.0:
        # 1-2万：区间至少 ±10% 或 ±1500元
        min_half_width = max(mid * 0.10, 0.15)
    elif mid < 3.0:
        # 2-3万：区间至少 ±8%
        min_half_width = mid * 0.08
    else:
        # >= 3万：保持原区间
        return low, up
    
    new_low = min(low, mid - min_half_width)
    new_up = max(up, mid + min_half_width)
    return new_low, new_up


def main():
    print("=" * 60)
    print("实验七：自适应 B2B 区间范围")
    print("=" * 60)
    
    # 加载数据
    df = pd.read_csv('output/residual_value_data_for_build_model.csv')
    df = df.sample(n=2000, random_state=42)
    
    predictor = ResidualPredictor(
        residual_data_csv=str(Path('output/residual_value_data_for_build_model.csv').absolute())
    )
    
    # 统计变量
    results = {
        'baseline': {'total': 0, 'hits': 0, 'by_price': {}},
        'adaptive': {'total': 0, 'hits': 0, 'by_price': {}}
    }
    price_buckets = ['<1万', '1-2万', '2-3万', '>=3万']
    for bucket in price_buckets:
        results['baseline']['by_price'][bucket] = {'total': 0, 'hits': 0}
        results['adaptive']['by_price'][bucket] = {'total': 0, 'hits': 0}
    
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
            
            grade = str(row.get('车辆评级', '中'))
            grade_map = {'优': 'a', '中': 'b', '差': 'c'}
            target_col = grade_map.get(grade, 'b')
            actual = float(row.get('二手车的成交价', 0))
            
            b2b_prices = pred.price_matrix['b2BPrices'][target_col]
            mid = float(b2b_prices['mid'])
            low = float(b2b_prices['low'])
            up = float(b2b_prices['up'])
            
            # 确定价格分桶
            if mid < 1.0:
                bucket = '<1万'
            elif mid < 2.0:
                bucket = '1-2万'
            elif mid < 3.0:
                bucket = '2-3万'
            else:
                bucket = '>=3万'
            
            # Baseline 命中判断
            results['baseline']['total'] += 1
            results['baseline']['by_price'][bucket]['total'] += 1
            if low <= actual <= up:
                results['baseline']['hits'] += 1
                results['baseline']['by_price'][bucket]['hits'] += 1
            
            # Adaptive 命中判断
            new_low, new_up = apply_adaptive_range(mid, low, up)
            results['adaptive']['total'] += 1
            results['adaptive']['by_price'][bucket]['total'] += 1
            if new_low <= actual <= new_up:
                results['adaptive']['hits'] += 1
                results['adaptive']['by_price'][bucket]['hits'] += 1
                
        except Exception as e:
            continue
    
    # 输出结果
    print("\n### 总体命中率对比")
    print(f"| 方案 | 命中数 | 总数 | 命中率 |")
    print(f"|------|--------|------|--------|")
    for name, data in results.items():
        rate = data['hits'] / data['total'] * 100 if data['total'] > 0 else 0
        print(f"| {name} | {data['hits']} | {data['total']} | {rate:.2f}% |")
    
    print("\n### 按价格分段命中率")
    print(f"| 价格段 | Baseline | Adaptive | 变化 |")
    print(f"|--------|----------|----------|------|")
    for bucket in price_buckets:
        b_data = results['baseline']['by_price'][bucket]
        a_data = results['adaptive']['by_price'][bucket]
        b_rate = b_data['hits'] / b_data['total'] * 100 if b_data['total'] > 0 else 0
        a_rate = a_data['hits'] / a_data['total'] * 100 if a_data['total'] > 0 else 0
        delta = a_rate - b_rate
        print(f"| {bucket} | {b_rate:.1f}% ({b_data['hits']}/{b_data['total']}) | {a_rate:.1f}% ({a_data['hits']}/{a_data['total']}) | {delta:+.1f}% |")
    
    print("\n### 自适应区间规则")
    print("- <1万: 区间至少 ±15% 或 ±1500元")
    print("- 1-2万: 区间至少 ±10% 或 ±1500元")
    print("- 2-3万: 区间至少 ±8%")
    print("- >=3万: 保持原区间")


if __name__ == '__main__':
    main()
