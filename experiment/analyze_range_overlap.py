"""
分析 B2B 区间扩大后与 C2B/B2C 区间的重叠程度

正常价格层级: C2B < B2B < B2C
检查:
1. B2B.low 是否低于 C2B.up (C2B上限侵入B2B下限)
2. B2B.up 是否高于 B2C.low (B2B上限侵入B2C下限)
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
    """自适应区间扩展逻辑"""
    if mid < 1.0:
        min_half_width = max(mid * 0.15, 0.15)
    elif mid < 2.0:
        min_half_width = max(mid * 0.10, 0.15)
    elif mid < 3.0:
        min_half_width = mid * 0.08
    else:
        return low, up
    
    new_low = min(low, mid - min_half_width)
    new_up = max(up, mid + min_half_width)
    return new_low, new_up


def main():
    print("=" * 60)
    print("分析 B2B 区间扩大后与 C2B/B2C 的重叠情况")
    print("=" * 60)
    
    df = pd.read_csv('output/residual_value_data_for_build_model.csv')
    df = df.sample(n=2000, random_state=42)
    
    predictor = ResidualPredictor(
        residual_data_csv=str(Path('output/residual_value_data_for_build_model.csv').absolute())
    )
    
    # 统计
    price_buckets = ['<1万', '1-2万', '2-3万', '>=3万']
    stats = {bucket: {
        'total': 0,
        'baseline_c2b_overlap': 0,  # B2B.low < C2B.up (异常)
        'baseline_b2c_overlap': 0,  # B2B.up > B2C.low (可能正常)
        'adaptive_c2b_overlap': 0,
        'adaptive_b2c_overlap': 0,
        'adaptive_b2b_invades_c2b': 0,  # 扩大后 B2B.low 侵入 C2B 区间
    } for bucket in price_buckets}
    
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
            
            # 获取各类价格
            b2b = pred.price_matrix['b2BPrices'][target_col]
            c2b = pred.price_matrix['c2BPrices'][target_col]
            b2c = pred.price_matrix['b2CPrices'][target_col]
            
            b2b_mid = float(b2b['mid'])
            b2b_low = float(b2b['low'])
            b2b_up = float(b2b['up'])
            c2b_up = float(c2b['up'])
            b2c_low = float(b2c['low'])
            
            # 确定价格分桶
            if b2b_mid < 1.0:
                bucket = '<1万'
            elif b2b_mid < 2.0:
                bucket = '1-2万'
            elif b2b_mid < 3.0:
                bucket = '2-3万'
            else:
                bucket = '>=3万'
            
            stats[bucket]['total'] += 1
            
            # Baseline 重叠检查
            if b2b_low < c2b_up:
                stats[bucket]['baseline_c2b_overlap'] += 1
            if b2b_up > b2c_low:
                stats[bucket]['baseline_b2c_overlap'] += 1
            
            # Adaptive 区间
            new_b2b_low, new_b2b_up = apply_adaptive_range(b2b_mid, b2b_low, b2b_up)
            
            # Adaptive 重叠检查
            if new_b2b_low < c2b_up:
                stats[bucket]['adaptive_c2b_overlap'] += 1
            if new_b2b_up > b2c_low:
                stats[bucket]['adaptive_b2c_overlap'] += 1
            
            # 新增侵入（扩大后才出现的问题）
            if new_b2b_low < c2b_up and b2b_low >= c2b_up:
                stats[bucket]['adaptive_b2b_invades_c2b'] += 1
                
        except Exception as e:
            continue
    
    # 输出结果
    print("\n### B2B.low 与 C2B.up 重叠情况 (B2B.low < C2B.up)")
    print("| 价格段 | 样本数 | Baseline | Adaptive | 新增侵入 |")
    print("|--------|--------|----------|----------|----------|")
    for bucket in price_buckets:
        s = stats[bucket]
        if s['total'] == 0:
            continue
        b_rate = s['baseline_c2b_overlap'] / s['total'] * 100
        a_rate = s['adaptive_c2b_overlap'] / s['total'] * 100
        inv_rate = s['adaptive_b2b_invades_c2b'] / s['total'] * 100
        print(f"| {bucket} | {s['total']} | {b_rate:.1f}% | {a_rate:.1f}% | {inv_rate:.1f}% |")
    
    print("\n### B2B.up 与 B2C.low 重叠情况 (B2B.up > B2C.low)")
    print("| 价格段 | 样本数 | Baseline | Adaptive |")
    print("|--------|--------|----------|----------|")
    for bucket in price_buckets:
        s = stats[bucket]
        if s['total'] == 0:
            continue
        b_rate = s['baseline_b2c_overlap'] / s['total'] * 100
        a_rate = s['adaptive_b2c_overlap'] / s['total'] * 100
        print(f"| {bucket} | {s['total']} | {b_rate:.1f}% | {a_rate:.1f}% |")
    
    print("\n### 说明")
    print("- **B2B.low < C2B.up**: B2B下限侵入C2B区间，可能导致报价逻辑混乱。")
    print("- **B2B.up > B2C.low**: B2B上限与B2C下限重叠，通常是正常的（价格区间有交叉）。")
    print("- **新增侵入**: 扩大区间后新出现的 B2B 侵入 C2B 的情况。")


if __name__ == '__main__':
    main()
