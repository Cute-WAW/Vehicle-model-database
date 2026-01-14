"""
精真估 vs 我方系统 对比分析脚本 v2

基于现有JZG API结果数据进行命中率对比分析
"""

import pandas as pd
import numpy as np
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# 添加src目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
os.chdir(Path(__file__).parent.parent)

from residual_predictor_step5 import ResidualPredictor

print("=" * 70)
print("精真估 vs 我方系统 命中率对比分析")
print(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# ========== 1. 分析精真估已有结果 ==========
print("\n[1] 分析精真估API已有结果...")


# Link fixed JZG source data
jzg_df = pd.read_csv('doc/comparison_data/jzg_source_data.csv', on_bad_lines='skip')
print(f"  JZG结果总数: {len(jzg_df)}")

# 解析JZG结果
jzg_results = []
for idx, row in jzg_df.iterrows():
    try:
        data = json.loads(row['jzg_result'])
        actual_price = float(row.get('成交价格', 0)) / 10000.0 # Convert Yuan to Wan
        
        if data.get('Result') and actual_price > 0:
            result = data['Result']
            b2b = result.get('b2BPrices', {})
            
            # 提取b评级价格区间 (中等车况)
            b_prices = b2b.get('b', {})
            if b_prices:
                low = float(b_prices.get('low', 0))
                up = float(b_prices.get('up', 0))
                mid = float(b_prices.get('mid', 0))
                
                jzg_results.append({
                    'actual': actual_price,
                    'jzg_low': low,
                    'jzg_mid': mid,
                    'jzg_up': up,
                    'in_range': low <= actual_price <= up,
                    'jzg_valid': True
                })
    except:
        pass

jzg_valid_count = len(jzg_results)
print(f"  有效JZG结果: {jzg_valid_count} ({jzg_valid_count/len(jzg_df)*100:.1f}%)")

# 计算JZG价格区间宽度统计
if jzg_results:
    jzg_df_valid = pd.DataFrame(jzg_results)
    jzg_df_valid['range_width'] = jzg_df_valid['jzg_up'] - jzg_df_valid['jzg_low']
    
    # JZG Hit Rate
    jzg_hit_rate_val = jzg_df_valid['in_range'].mean() * 100
    
    # Group by price
    # Group by price
    price_bins = [0, 1, 3, 5, 10, 20, float('inf')]
    price_labels = ['<1万', '1-3万', '3-5万', '5-10万', '10-20万', '>20万']
    jzg_df_valid['price_group'] = pd.cut(jzg_df_valid['actual'], bins=price_bins, labels=price_labels)
    
    jzg_price_stats = {}
    for label in price_labels:
        group = jzg_df_valid[jzg_df_valid['price_group'] == label]
        if len(group) > 0:
            jzg_price_stats[label] = {
                'rate': group['in_range'].mean() * 100,
                'count': len(group)
            }
    
    print(f"  JZG总体命中率: {jzg_hit_rate_val:.1f}%")
    print(f"  JZG平均价格区间宽度: {jzg_df_valid['range_width'].mean():.2f}万")
    print(f"  JZG区间宽度中位数: {jzg_df_valid['range_width'].median():.2f}万")
else:
    jzg_hit_rate_val = 0
    jzg_price_stats = {}

# ========== 2. 我方系统500样本分析 ==========
print("\n[2] 我方系统500样本分析...")

csv_path = 'output/residual_value_data_for_build_model.csv'
predictor = ResidualPredictor(residual_data_csv=csv_path)

full_df = pd.read_csv(csv_path, on_bad_lines='skip')
sample_df = full_df.sample(n=500, random_state=2024).reset_index(drop=True)
print(f"  抽样500条记录进行测试...")

our_results = []
for idx, row in sample_df.iterrows():
    try:
        result = predictor.predict(
            vehicle_full_name=str(row['车辆全称']),
            brand_series=str(row['品牌车系']),
            years=float(row['使用年限']),
            grade=str(row['车辆评级']),
            city=str(row['城市']),
            mileage=float(row['行驶里程']) if pd.notna(row['行驶里程']) else 0,
            new_price=float(row['新车的价格']) if pd.notna(row['新车的价格']) else None
        )
        
        if result.success and result.price_matrix:
            grade_map = {'优': 'a', '中': 'b', '差': 'c'}
            grade_key = grade_map.get(str(row['车辆评级']), 'b')
            b2b = result.price_matrix.get('b2BPrices', {}).get(grade_key, {})
            
            range_low = float(b2b.get('low', result.predicted_price * 0.9))
            range_high = float(b2b.get('up', result.predicted_price * 1.1))
            actual = float(row['二手车的成交价'])
            
            our_results.append({
                'actual': actual,
                'predicted': result.predicted_price,
                'low': range_low,
                'high': range_high,
                'in_range': range_low <= actual <= range_high,
                'grade': str(row['车辆评级']),
                'success': True
            })
    except Exception as e:
        pass
    
    if (idx + 1) % 100 == 0:
        print(f"  已处理 {idx + 1}/500...")

our_df = pd.DataFrame(our_results)
print(f"  成功预测: {len(our_df)}/500")

# ========== 3. 命中率对比分析 ==========
print("\n" + "=" * 70)
print("[3] 命中率对比分析")
print("=" * 70)

# 我方总体命中率
our_hit_rate = our_df['in_range'].mean() * 100
print(f"\n我方系统总体命中率: {our_hit_rate:.1f}%")

# 按价格段分析
# 按价格段分析
price_bins = [0, 1, 3, 5, 10, 20, float('inf')]
price_labels = ['<1万', '1-3万', '3-5万', '5-10万', '10-20万', '>20万']
our_df['price_group'] = pd.cut(our_df['actual'], bins=price_bins, labels=price_labels)
jzg_df_valid['price_group'] = pd.cut(jzg_df_valid['actual'], bins=price_bins, labels=price_labels)

print("\n按价格段命中率对比:")
print("-" * 50)
print(f"{'价格段':<10} {'我方命中率':<12} {'样本数':<10}")
print("-" * 50)

price_stats = {}
for label in price_labels:
    group = our_df[our_df['price_group'] == label]
    if len(group) > 0:
        hit_rate = group['in_range'].mean() * 100
        price_stats[label] = {
            'our_rate': hit_rate,
            'count': len(group)
        }
        print(f"{label:<10} {hit_rate:>8.1f}%    {len(group):>5}")

# ========== 4. 我方价格区间宽度分析 ==========
print("\n[4] 价格区间宽度对比:")
our_df['range_width'] = our_df['high'] - our_df['low']
print(f"  我方平均区间宽度: {our_df['range_width'].mean():.2f}万")
print(f"  我方区间宽度中位数: {our_df['range_width'].median():.2f}万")

if jzg_results:
    print(f"  JZG平均区间宽度: {jzg_df_valid['range_width'].mean():.2f}万")
    print(f"  JZG区间宽度中位数: {jzg_df_valid['range_width'].median():.2f}万")

# ========== 5. 保存结果 ==========
print("\n[5] 保存结果...")

summary = {
    '分析时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    '我方系统': {
        '样本数': 500,
        '成功预测': len(our_df),
        '总体命中率': f"{our_hit_rate:.1f}%",
        '按价格段': {k: f"{v['our_rate']:.1f}% ({v['count']}样本)" for k, v in price_stats.items()},
        '平均区间宽度': f"{our_df['range_width'].mean():.2f}万"
    },

    '精真估': {
        '有效结果数': jzg_valid_count,
        '总体命中率': f"{jzg_hit_rate_val:.1f}%" if jzg_results else "N/A",
        '按价格段': {k: f"{v['rate']:.1f}% ({v['count']}样本)" for k, v in jzg_price_stats.items()},
        '平均区间宽度': f"{jzg_df_valid['range_width'].mean():.2f}万" if jzg_results else "N/A"
    }
}

with open('experiment/jzg_vs_ours_comparison.json', 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print("  已保存: experiment/jzg_vs_ours_comparison.json")

# ========== 6. 生成报告数据 ==========
print("\n" + "=" * 70)
print("[6] 对比报告数据 (用于更新效果报告)")
print("=" * 70)

print("""
### 3.3 分价位对比命中率

| 价位段 | 我方命中率 | JZG命中率 | 我方样本 | JZG样本 |
|:---:|:---:|:---:|:---:|:---:|""")

for label in price_labels:
    our_rate = "N/A"
    our_count = 0
    if label in price_stats:
        our_rate = f"{price_stats[label]['our_rate']:.1f}%"
        our_count = price_stats[label]['count']
        
    jzg_rate = "N/A"
    jzg_count = 0
    if label in jzg_price_stats:
        jzg_rate = f"{jzg_price_stats[label]['rate']:.1f}%"
        jzg_count = jzg_price_stats[label]['count']
        
    print(f"| {label} | {our_rate} | {jzg_rate} | {our_count} | {jzg_count} |")

print(f"""
### 3.4 总体对比
| 指标 | 我方系统 | 精真估 |
|:---:|:---:|:---:|
| 总体命中率 | {our_hit_rate:.1f}% | {jzg_hit_rate_val:.1f}% |
| 平均区间宽度 | {our_df['range_width'].mean():.2f}万 | {jzg_df_valid['range_width'].mean():.2f}万 |
""")

print("\n" + "=" * 70)
print("对比分析完成!")
print("=" * 70)
