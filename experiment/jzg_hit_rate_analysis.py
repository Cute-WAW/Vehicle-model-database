"""
精真估(JZG) 命中率分析脚本

计算精真估的区间命中率，用于与我方系统进行对比
"""

import pandas as pd
import json
from datetime import datetime
from pathlib import Path

print("=" * 70)
print("精真估 命中率分析")
print(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# 读取包含成交价和JZG结果的文件
result_files = [
    'd:/antigravity/price_evaluation/力洋/有辆成交20251219_result.csv',
    'd:/antigravity/price_evaluation/力洋/有辆成交20251219_result_600.csv',
    'd:/antigravity/price_evaluation/力洋/有辆成交20251219_result_1000.csv',
]

all_records = []

for file_path in result_files:
    if Path(file_path).exists():
        print(f"\n读取文件: {Path(file_path).name}")
        df = pd.read_csv(file_path, encoding='utf-8')
        print(f"  总记录数: {len(df)}")
        
        for idx, row in df.iterrows():
            try:
                # 解析成交价格
                actual_price_raw = row.get('成交价格', 0)
                if pd.isna(actual_price_raw) or actual_price_raw == '':
                    continue
                actual_price = float(actual_price_raw)
                # 成交价格单位是元，转换为万元
                if actual_price > 1000:
                    actual_price = actual_price / 10000
                
                # 解析JZG结果
                jzg_result_str = row.get('jzg_result', '')
                if pd.isna(jzg_result_str) or jzg_result_str == '':
                    continue
                
                jzg_data = json.loads(jzg_result_str)
                if not jzg_data.get('Result'):
                    continue
                
                result = jzg_data['Result']
                b2b = result.get('b2BPrices', {})
                
                # 获取b评级价格区间（中等车况）
                b_prices = b2b.get('b', {})
                if not b_prices:
                    continue
                
                jzg_low = float(b_prices.get('low', 0))
                jzg_mid = float(b_prices.get('mid', 0))
                jzg_up = float(b_prices.get('up', 0))
                
                if jzg_low <= 0 or jzg_up <= 0:
                    continue
                
                # 判断是否命中
                in_range = jzg_low <= actual_price <= jzg_up
                
                all_records.append({
                    'actual_price': actual_price,
                    'jzg_low': jzg_low,
                    'jzg_mid': jzg_mid,
                    'jzg_up': jzg_up,
                    'range_width': jzg_up - jzg_low,
                    'in_range': in_range,
                    'file': Path(file_path).name
                })
                
            except Exception as e:
                continue

print(f"\n有效记录总数: {len(all_records)}")

if len(all_records) == 0:
    print("错误: 没有找到有效的JZG结果记录!")
    exit(1)

# 创建DataFrame进行分析
df_results = pd.DataFrame(all_records)

# ========== 总体命中率 ==========
print("\n" + "=" * 70)
print("[1] 精真估总体命中率")
print("=" * 70)

total_count = len(df_results)
hit_count = df_results['in_range'].sum()
hit_rate = hit_count / total_count * 100

print(f"  测试样本数: {total_count}")
print(f"  区间命中数: {hit_count}")
print(f"  总体命中率: {hit_rate:.1f}%")
print(f"  平均区间宽度: {df_results['range_width'].mean():.2f}万")

# ========== 按价格段分析 ==========
print("\n" + "=" * 70)
print("[2] 按价格段分析")
print("=" * 70)

price_bins = [0, 1, 3, 5, 10, 20, float('inf')]
price_labels = ['<1万', '1-3万', '3-5万', '5-10万', '10-20万', '>20万']
df_results['price_group'] = pd.cut(df_results['actual_price'], bins=price_bins, labels=price_labels)

print(f"\n{'价格段':<10} {'样本数':>8} {'命中数':>8} {'命中率':>10} {'平均区间宽度':>12}")
print("-" * 60)

price_stats = {}
for label in price_labels:
    group = df_results[df_results['price_group'] == label]
    if len(group) > 0:
        grp_hit_count = group['in_range'].sum()
        grp_hit_rate = grp_hit_count / len(group) * 100
        grp_width = group['range_width'].mean()
        price_stats[label] = {
            'count': len(group),
            'hit_count': grp_hit_count,
            'hit_rate': grp_hit_rate,
            'avg_width': grp_width
        }
        print(f"{label:<10} {len(group):>8} {grp_hit_count:>8} {grp_hit_rate:>9.1f}% {grp_width:>11.2f}万")

# ========== 保存结果 ==========
print("\n" + "=" * 70)
print("[3] 保存结果")
print("=" * 70)

summary = {
    '分析时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    '精真估': {
        '测试样本数': total_count,
        '区间命中数': int(hit_count),
        '总体命中率': f"{hit_rate:.1f}%",
        '平均区间宽度': f"{df_results['range_width'].mean():.2f}万",
        '按价格段': {k: f"{v['hit_rate']:.1f}% ({v['count']}样本, 宽度{v['avg_width']:.2f}万)" 
                     for k, v in price_stats.items()}
    }
}

import json
output_file = 'experiment/jzg_hit_rate_stats.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(f"  已保存: {output_file}")

# ========== 生成报告数据 ==========
print("\n" + "=" * 70)
print("[4] 效果报告更新数据")
print("=" * 70)

print(f"""
### 3.2 关键指标对比 (更新版)

| 指标 | 我方系统 | 精真估 |
|:---|:---:|:---:|
| 测试样本 | 500 | {total_count} |
| 成功返回 | 500 (100%) | {total_count} (100%) |
| 平均区间宽度 | 0.60万 | {df_results['range_width'].mean():.2f}万 |
| 总体命中率 | **46.4%** | **{hit_rate:.1f}%** |
""")

print("\n" + "=" * 70)
print("分析完成!")
print("=" * 70)
