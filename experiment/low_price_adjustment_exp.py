"""
低价车绝对值调整实验

对于预测价格 <1万 的车辆，测试按评级进行绝对值调整：
- 优: +X 万
- 中: 不调整
- 差: -Y 万
"""

import sys
from pathlib import Path
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir / 'src'))
import os
os.chdir(script_dir)

import pandas as pd
from residual_predictor_step5 import ResidualPredictor

df = pd.read_csv('output/residual_value_data_for_build_model.csv')
df = df.sample(n=2000, random_state=42)

predictor = ResidualPredictor(residual_data_csv=str(Path('output/residual_value_data_for_build_model.csv').absolute()))

# 测试不同的绝对值调整方案
# 格式: (优调整, 中调整, 差调整) 单位: 万元
adjustments = [
    (0, 0, 0),        # 基准 (无调整)
    (-0.05, 0, 0.05), # 优-500, 差+500
    (-0.10, 0, 0.10), # 优-1000, 差+1000
    (-0.15, 0, 0.15), # 优-1500, 差+1500
    (-0.20, 0, 0.20), # 优-2000, 差+2000
]

print("低价车 (<1万) 绝对值调整实验")
print("=" * 70)

for adj_you, adj_zhong, adj_cha in adjustments:
    stats = {'hit': 0, 'total': 0}
    grade_stats = {'优': {'hit': 0, 'total': 0}, '中': {'hit': 0, 'total': 0}, '差': {'hit': 0, 'total': 0}}
    
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
            
            predicted_price = pred.predicted_price
            
            # 只处理低价车
            if predicted_price >= 1.0:
                continue
            
            actual_price = float(row.get('二手车的成交价', 0))
            grade = str(row.get('车辆评级', '中'))
            
            # 根据评级选择调整值
            if grade == '优':
                adj = adj_you
            elif grade == '差':
                adj = adj_cha
            else:
                adj = adj_zhong
            
            # 调整后的预测价格
            adjusted_price = predicted_price + adj
            
            # 重新计算区间 (假设区间按比例调整)
            grade_map = {'优': 'a', '中': 'b', '差': 'c'}
            target_col = grade_map.get(grade, 'b')
            b2b_low = pred.price_matrix['b2BPrices'][target_col]['low'] + adj
            b2b_up = pred.price_matrix['b2BPrices'][target_col]['up'] + adj
            
            hit = b2b_low <= actual_price <= b2b_up
            
            stats['total'] += 1
            if hit:
                stats['hit'] += 1
            
            if grade in grade_stats:
                grade_stats[grade]['total'] += 1
                if hit:
                    grade_stats[grade]['hit'] += 1
        except:
            continue
    
    rate = stats['hit']/stats['total']*100 if stats['total'] > 0 else 0
    print(f"\n调整方案: 优{adj_you:+.2f}万, 中{adj_zhong:+.2f}万, 差{adj_cha:+.2f}万")
    print(f"  整体: {stats['hit']}/{stats['total']} = {rate:.2f}%")
    for g in ['优', '中', '差']:
        s = grade_stats[g]
        r = s['hit']/s['total']*100 if s['total'] > 0 else 0
        print(f"  {g}: {s['hit']}/{s['total']} = {r:.2f}%")
