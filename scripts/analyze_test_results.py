import pandas as pd
import numpy as np

# 读取测试结果
df = pd.read_csv('output/patent_performance_test_report.csv')
success = df[df['成功']==True].copy()

print('='*60)
print('原始数据统计:')
print('='*60)
print(f'总样本数: {len(df)}')
print(f'成功预测数: {len(success)}')
print(f'覆盖率: {len(success)/len(df)*100:.2f}%')
print(f'MAPE: {success["误差率"].mean()*100:.2f}%')
print(f'中位数误差率: {success["误差率"].median()*100:.2f}%')
print()

# 过滤极端异常值(误差率>100%)
filtered = success[success['误差率'] <= 1.0].copy()

print('='*60)
print('过滤后数据统计 (误差率<=100%):')
print('='*60)
print(f'有效样本数: {len(filtered)}')
print(f'有效覆盖率: {len(filtered)/len(df)*100:.2f}%')
print(f'MAPE: {filtered["误差率"].mean()*100:.2f}%')
print(f'中位数误差率: {filtered["误差率"].median()*100:.2f}%')
print(f'P75误差率: {filtered["误差率"].quantile(0.75)*100:.2f}%')
print(f'P90误差率: {filtered["误差率"].quantile(0.90)*100:.2f}%')
print(f'P95误差率: {filtered["误差率"].quantile(0.95)*100:.2f}%')
print()

print('='*60)
print('响应时间统计:')
print('='*60)
print(f'平均响应时间: {filtered["响应时间ms"].mean():.2f}ms')
print(f'中位数响应时间: {filtered["响应时间ms"].median():.2f}ms')
print(f'P95响应时间: {filtered["响应时间ms"].quantile(0.95):.2f}ms')
print(f'P99响应时间: {filtered["响应时间ms"].quantile(0.99):.2f}ms')
print()

# 按价格区间分析
print('='*60)
print('按价格区间分析 (基于新车价格):')
print('='*60)

# 需要合并原始数据获取新车价格
test_data = pd.read_csv('output/residual_value_data.csv').sample(n=500, random_state=42)
filtered_with_price = filtered.merge(
    test_data[['车辆全称', '品牌车系', '新车的价格']],
    on=['车辆全称', '品牌车系'],
    how='left'
)

# 定义价格区间
filtered_with_price['价格区间'] = pd.cut(
    filtered_with_price['新车的价格'],
    bins=[0, 10, 20, 100],
    labels=['经济型(<10万)', '中档型(10-20万)', '豪华型(>20万)']
)

for category in ['经济型(<10万)', '中档型(10-20万)', '豪华型(>20万)']:
    subset = filtered_with_price[filtered_with_price['价格区间'] == category]
    if len(subset) > 0:
        print(f'\n{category}:')
        print(f'  样本数: {len(subset)}')
        print(f'  MAPE: {subset["误差率"].mean()*100:.2f}%')
        print(f'  中位数误差率: {subset["误差率"].median()*100:.2f}%')
        print(f'  平均响应时间: {subset["响应时间ms"].mean():.2f}ms')
