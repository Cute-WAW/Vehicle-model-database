"""
效果报告分析脚本 v2

简化版本，直接输出统计结果
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

print("=" * 60)
print("二手车价格预测效果分析")
print(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# 初始化预测器
print("\n[1] 初始化预测器...")
csv_path = 'output/residual_value_data_for_build_model.csv'
predictor = ResidualPredictor(residual_data_csv=csv_path)

# 加载数据
print("\n[2] 加载并抽样数据...")
full_df = pd.read_csv(csv_path, on_bad_lines='skip')
print(f"  总记录数: {len(full_df)}")

# 抽取2000样本
sample_size = 2000
df = full_df.sample(n=min(sample_size, len(full_df)), random_state=42).reset_index(drop=True)
print(f"  抽样数量: {sample_size}")

# 运行预测
print("\n[3] 运行预测 (这可能需要几分钟)...")
results = []

for idx, row in df.iterrows():
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
            
            results.append({
                'vehicle': str(row['车辆全称'])[:40],
                'actual': actual,
                'predicted': result.predicted_price,
                'low': range_low,
                'high': range_high,
                'in_range': range_low <= actual <= range_high,
                'grade': str(row['车辆评级']),
                'years': float(row['使用年限']),
                'success': True
            })
        else:
            results.append({'success': False})
    except Exception as e:
        results.append({'success': False, 'error': str(e)})
    
    if (idx + 1) % 200 == 0:
        print(f"  已处理 {idx + 1}/{len(df)}...")

# 转换为DataFrame
results_df = pd.DataFrame(results)
success_df = results_df[results_df['success'] == True].copy()

print(f"\n  成功预测: {len(success_df)}/{len(df)}")

# ========== 总体命中率 ==========
print("\n" + "=" * 60)
print("[4] 总体命中率分析")
print("=" * 60)

hit_count = success_df['in_range'].sum()
total_count = len(success_df)
hit_rate = hit_count / total_count if total_count > 0 else 0

print(f"\n  样本总数: {len(df)}")
print(f"  成功预测: {total_count}")
print(f"  命中数量: {hit_count}")
print(f"  命中率: {hit_rate:.2%}")

# ========== 按价格段分析 ==========
print("\n" + "=" * 60)
print("[5] 按价格段分析")
print("=" * 60)

price_bins = [0, 1, 3, 5, 10, 20, float('inf')]
price_labels = ['<1万', '1-3万', '3-5万', '5-10万', '10-20万', '>20万']
success_df['price_group'] = pd.cut(success_df['actual'], bins=price_bins, labels=price_labels)

price_stats = success_df.groupby('price_group', observed=True).agg({
    'in_range': ['sum', 'count']
}).reset_index()
price_stats.columns = ['价格段', '命中数', '样本数']
price_stats['命中率'] = price_stats['命中数'] / price_stats['样本数'] * 100

print("\n价格段      命中数  样本数  命中率")
print("-" * 40)
for _, r in price_stats.iterrows():
    print(f"{r['价格段']:<10} {int(r['命中数']):>5}  {int(r['样本数']):>5}  {r['命中率']:.1f}%")

# ========== 按评级分析 ==========
print("\n" + "=" * 60)
print("[6] 按车辆评级分析")
print("=" * 60)

grade_stats = success_df.groupby('grade', observed=True).agg({
    'in_range': ['sum', 'count']
}).reset_index()
grade_stats.columns = ['评级', '命中数', '样本数']
grade_stats['命中率'] = grade_stats['命中数'] / grade_stats['样本数'] * 100

print("\n评级  命中数  样本数  命中率")
print("-" * 30)
for _, r in grade_stats.iterrows():
    print(f"{r['评级']:<5} {int(r['命中数']):>5}  {int(r['样本数']):>5}  {r['命中率']:.1f}%")

# ========== 按车龄分析 ==========
print("\n" + "=" * 60)
print("[7] 按车龄分析")
print("=" * 60)

year_bins = [0, 3, 5, 8, 10, float('inf')]
year_labels = ['0-3年', '3-5年', '5-8年', '8-10年', '>10年']
success_df['year_group'] = pd.cut(success_df['years'], bins=year_bins, labels=year_labels)

year_stats = success_df.groupby('year_group', observed=True).agg({
    'in_range': ['sum', 'count']
}).reset_index()
year_stats.columns = ['车龄', '命中数', '样本数']
year_stats['命中率'] = year_stats['命中数'] / year_stats['样本数'] * 100

print("\n车龄段    命中数  样本数  命中率")
print("-" * 35)
for _, r in year_stats.iterrows():
    print(f"{r['车龄']:<8} {int(r['命中数']):>5}  {int(r['样本数']):>5}  {r['命中率']:.1f}%")

# ========== 具体案例 ==========
print("\n" + "=" * 60)
print("[8] 具体案例分析")
print("=" * 60)

print("\n【命中案例 TOP 3】")
hit_cases = success_df[success_df['in_range'] == True].head(3)
for i, (_, row) in enumerate(hit_cases.iterrows(), 1):
    print(f"\n案例{i}: {row['vehicle']}")
    print(f"  预测价格: {row['predicted']:.2f}万")
    print(f"  建议区间: [{row['low']:.2f}, {row['high']:.2f}]万")
    print(f"  实际成交: {row['actual']:.2f}万 ✓ 命中")

print("\n【未命中案例 TOP 3】")
miss_cases = success_df[success_df['in_range'] == False].head(3)
for i, (_, row) in enumerate(miss_cases.iterrows(), 1):
    diff = row['actual'] - row['predicted']
    print(f"\n案例{i}: {row['vehicle']}")
    print(f"  预测价格: {row['predicted']:.2f}万")
    print(f"  建议区间: [{row['low']:.2f}, {row['high']:.2f}]万")
    print(f"  实际成交: {row['actual']:.2f}万 ✗ 偏差{diff:+.2f}万")

# ========== 保存结果 ==========
print("\n" + "=" * 60)
print("[9] 保存结果")
print("=" * 60)

# 保存详细结果
success_df.to_csv('experiment/hit_rate_2000_results.csv', index=False, encoding='utf-8-sig')
print("  已保存: experiment/hit_rate_2000_results.csv")

# 保存统计摘要
summary = {
    '分析时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    '样本数': len(df),
    '成功预测': total_count,
    '命中数': int(hit_count),
    '命中率': f"{hit_rate:.2%}",
    '按价格段': price_stats.to_dict('records'),
    '按评级': grade_stats.to_dict('records'),
    '按车龄': year_stats.to_dict('records')
}

with open('experiment/hit_rate_stats.json', 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
print("  已保存: experiment/hit_rate_stats.json")

print("\n" + "=" * 60)
print("分析完成!")
print("=" * 60)
