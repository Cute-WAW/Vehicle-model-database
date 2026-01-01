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

# 按预测价格分组 (单位: 万元, 1万 = 10000元)
price_stats = {
    '<1万': {'hit': 0, 'total': 0},
    '>=1万': {'hit': 0, 'total': 0}
}

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
        
        predicted_price = pred.predicted_price  # 单位: 万元
        actual_price = float(row.get('二手车的成交价', 0))
        grade = str(row.get('车辆评级', '中'))
        
        grade_map = {'优': 'a', '中': 'b', '差': 'c'}
        target_col = grade_map.get(grade, 'b')
        b2b_low = pred.price_matrix['b2BPrices'][target_col]['low']
        b2b_up = pred.price_matrix['b2BPrices'][target_col]['up']
        
        hit = b2b_low <= actual_price <= b2b_up
        
        # 分组 (预测价格: 万元)
        if predicted_price < 1.0:  # < 1万
            key = '<1万'
        else:  # >= 1万
            key = '>=1万'
        
        price_stats[key]['total'] += 1
        if hit:
            price_stats[key]['hit'] += 1
    except:
        continue

print('按预测价格命中率统计:')
for k in ['<1万', '>=1万']:
    s = price_stats[k]
    rate = s['hit']/s['total']*100 if s['total'] > 0 else 0
    print(f"{k}: {s['hit']}/{s['total']} = {rate:.2f}%")
