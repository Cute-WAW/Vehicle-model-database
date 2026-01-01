"""简化版重叠分析（抑制日志输出）"""
import sys, os, logging
from pathlib import Path

# Setup
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir / 'src'))
os.chdir(script_dir)

# 抑制所有日志
logging.disable(logging.CRITICAL)

import pandas as pd
from residual_predictor_step5 import ResidualPredictor


def apply_adaptive_range(mid, low, up):
    if mid < 1.0:
        min_half_width = max(mid * 0.15, 0.15)
    elif mid < 2.0:
        min_half_width = max(mid * 0.10, 0.15)
    elif mid < 3.0:
        min_half_width = mid * 0.08
    else:
        return low, up
    return min(low, mid - min_half_width), max(up, mid + min_half_width)


def main():
    df = pd.read_csv('output/residual_value_data_for_build_model.csv').sample(n=2000, random_state=42)
    predictor = ResidualPredictor(residual_data_csv=str(Path('output/residual_value_data_for_build_model.csv').absolute()))
    
    buckets = ['<1w', '1-2w', '2-3w', '>=3w']
    stats = {b: {'n': 0, 'b_c2b': 0, 'a_c2b': 0, 'inv': 0, 'b_b2c': 0, 'a_b2c': 0} for b in buckets}
    
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
            b2b, c2b, b2c = pred.price_matrix['b2BPrices'][tc], pred.price_matrix['c2BPrices'][tc], pred.price_matrix['b2CPrices'][tc]
            
            mid, low, up = float(b2b['mid']), float(b2b['low']), float(b2b['up'])
            c2b_up, b2c_low = float(c2b['up']), float(b2c['low'])
            
            bucket = '<1w' if mid < 1.0 else ('1-2w' if mid < 2.0 else ('2-3w' if mid < 3.0 else '>=3w'))
            stats[bucket]['n'] += 1
            
            if low < c2b_up: stats[bucket]['b_c2b'] += 1
            if up > b2c_low: stats[bucket]['b_b2c'] += 1
            
            new_low, new_up = apply_adaptive_range(mid, low, up)
            if new_low < c2b_up: stats[bucket]['a_c2b'] += 1
            if new_up > b2c_low: stats[bucket]['a_b2c'] += 1
            if new_low < c2b_up and low >= c2b_up: stats[bucket]['inv'] += 1
        except: continue
    
    print("=" * 60)
    print("B2B.low < C2B.up (B2B下限侵入C2B收购价区间)")
    print("=" * 60)
    print(f"{'Bucket':<8} {'N':>5} {'Baseline':>10} {'Adaptive':>10} {'NewInvade':>10}")
    for b in buckets:
        s = stats[b]
        if s['n'] == 0: continue
        print(f"{b:<8} {s['n']:>5} {s['b_c2b']/s['n']*100:>9.1f}% {s['a_c2b']/s['n']*100:>9.1f}% {s['inv']/s['n']*100:>9.1f}%")
    
    print()
    print("=" * 60)
    print("B2B.up > B2C.low (B2B上限与B2C零售价重叠)")
    print("=" * 60)
    print(f"{'Bucket':<8} {'N':>5} {'Baseline':>10} {'Adaptive':>10}")
    for b in buckets:
        s = stats[b]
        if s['n'] == 0: continue
        print(f"{b:<8} {s['n']:>5} {s['b_b2c']/s['n']*100:>9.1f}% {s['a_b2c']/s['n']*100:>9.1f}%")


if __name__ == '__main__':
    main()
