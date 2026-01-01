"""
实验七续：自适应区间参数调优 (min_half_width)

测试不同的参数组合对命中率的影响：
- low_car_pct: <1万车的区间比例 (default 15%)
- low_car_abs: <1万车的最小绝对半宽 (default 0.15万=1500元)
- mid_car_pct: 1-2万车的区间比例 (default 10%)
"""

import sys, os, logging
from pathlib import Path

script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir / 'src'))
os.chdir(script_dir)
logging.disable(logging.CRITICAL)

import pandas as pd
from residual_predictor_step5 import ResidualPredictor


def apply_adaptive_range(mid, low, up, params):
    """参数化的自适应区间"""
    low_pct = params.get('low_pct', 0.15)
    low_abs = params.get('low_abs', 0.15)
    mid_pct = params.get('mid_pct', 0.10)
    mid_abs = params.get('mid_abs', 0.15)
    high_pct = params.get('high_pct', 0.08)
    
    if mid < 1.0:
        min_half_width = max(mid * low_pct, low_abs)
    elif mid < 2.0:
        min_half_width = max(mid * mid_pct, mid_abs)
    elif mid < 3.0:
        min_half_width = mid * high_pct
    else:
        return low, up
    
    return min(low, mid - min_half_width), max(up, mid + min_half_width)


def evaluate(df, predictor, params):
    """评估给定参数下的命中率"""
    total, hits = 0, 0
    by_price = {'<1w': [0, 0], '1-2w': [0, 0], '2-3w': [0, 0], '>=3w': [0, 0]}
    
    for _, row in df.iterrows():
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
            if not pred.success or not pred.price_matrix: continue
            
            tc = {'优': 'a', '中': 'b', '差': 'c'}.get(str(row.get('车辆评级', '中')), 'b')
            b2b = pred.price_matrix['b2BPrices'][tc]
            actual = float(row.get('二手车的成交价', 0))
            
            m, lo, hi = float(b2b['mid']), float(b2b['low']), float(b2b['up'])
            bucket = '<1w' if m < 1.0 else ('1-2w' if m < 2.0 else ('2-3w' if m < 3.0 else '>=3w'))
            
            new_lo, new_hi = apply_adaptive_range(m, lo, hi, params)
            
            total += 1
            by_price[bucket][1] += 1
            if new_lo <= actual <= new_hi:
                hits += 1
                by_price[bucket][0] += 1
        except:
            continue
    
    return hits, total, by_price


def main():
    print("=" * 70)
    print("自适应区间参数调优实验")
    print("=" * 70)
    
    df = pd.read_csv('output/residual_value_data_for_build_model.csv').sample(n=2000, random_state=42)
    predictor = ResidualPredictor(residual_data_csv=str(Path('output/residual_value_data_for_build_model.csv').absolute()))
    
    # 参数网格
    param_grid = [
        # Baseline (no expansion)
        {'name': 'Baseline', 'low_pct': 0, 'low_abs': 0, 'mid_pct': 0, 'mid_abs': 0, 'high_pct': 0},
        # Original
        {'name': 'v1 (15%/1500)', 'low_pct': 0.15, 'low_abs': 0.15, 'mid_pct': 0.10, 'mid_abs': 0.15, 'high_pct': 0.08},
        # More aggressive for low price
        {'name': 'v2 (20%/2000)', 'low_pct': 0.20, 'low_abs': 0.20, 'mid_pct': 0.12, 'mid_abs': 0.15, 'high_pct': 0.08},
        # Less aggressive
        {'name': 'v3 (10%/1000)', 'low_pct': 0.10, 'low_abs': 0.10, 'mid_pct': 0.08, 'mid_abs': 0.10, 'high_pct': 0.05},
        # Focus on absolute minimum
        {'name': 'v4 (15%/2000)', 'low_pct': 0.15, 'low_abs': 0.20, 'mid_pct': 0.10, 'mid_abs': 0.20, 'high_pct': 0.08},
        # Very aggressive
        {'name': 'v5 (25%/2500)', 'low_pct': 0.25, 'low_abs': 0.25, 'mid_pct': 0.15, 'mid_abs': 0.20, 'high_pct': 0.10},
    ]
    
    results = []
    for params in param_grid:
        hits, total, by_price = evaluate(df, predictor, params)
        rate = hits / total * 100 if total > 0 else 0
        results.append({
            'name': params['name'],
            'hits': hits,
            'total': total,
            'rate': rate,
            'by_price': by_price
        })
    
    # 输出总体结果
    print("\n### 总体命中率对比")
    print(f"{'方案':<20} {'命中数':>8} {'总数':>8} {'命中率':>10}")
    print("-" * 50)
    for r in results:
        print(f"{r['name']:<20} {r['hits']:>8} {r['total']:>8} {r['rate']:>9.2f}%")
    
    # 输出分价格段结果
    print("\n### 分价格段命中率")
    print(f"{'方案':<20} {'<1万':>12} {'1-2万':>12} {'2-3万':>12} {'>=3万':>12}")
    print("-" * 70)
    for r in results:
        bp = r['by_price']
        vals = []
        for b in ['<1w', '1-2w', '2-3w', '>=3w']:
            h, t = bp[b]
            rate = h / t * 100 if t > 0 else 0
            vals.append(f"{rate:.1f}%")
        print(f"{r['name']:<20} {vals[0]:>12} {vals[1]:>12} {vals[2]:>12} {vals[3]:>12}")
    
    # 最佳方案
    best = max(results, key=lambda x: x['rate'])
    print(f"\n>>> 最佳方案: {best['name']} (命中率 {best['rate']:.2f}%)")


if __name__ == '__main__':
    main()
