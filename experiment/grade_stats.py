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
        actual_price = float(row.get('二手车的成交价', 0))
        grade = str(row.get('车辆评级', '中'))
        if grade not in grade_stats:
            continue
        grade_map = {'优': 'a', '中': 'b', '差': 'c'}
        target_col = grade_map.get(grade, 'b')
        b2b_low = pred.price_matrix['b2BPrices'][target_col]['low']
        b2b_up = pred.price_matrix['b2BPrices'][target_col]['up']
        grade_stats[grade]['total'] += 1
        if b2b_low <= actual_price <= b2b_up:
            grade_stats[grade]['hit'] += 1
    except:
        continue

print('按评级命中率统计:')
for g in ['优', '中', '差']:
    s = grade_stats[g]
    rate = s['hit']/s['total']*100 if s['total'] > 0 else 0
    print(f"{g}: {s['hit']}/{s['total']} = {rate:.2f}%")
