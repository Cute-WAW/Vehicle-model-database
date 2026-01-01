import sys
sys.path.insert(0, 'd:/antigravity/price_evaluation/车型库映射/src')
import os
os.chdir('d:/antigravity/price_evaluation/车型库映射')
import pandas as pd
from residual_predictor_step5 import ResidualPredictor

df = pd.read_csv('output/residual_value_data_for_build_model.csv')
df = df.sample(n=2000, random_state=42)

predictor = ResidualPredictor(residual_data_csv='output/residual_value_data_for_build_model.csv')

city_stats = {}
tier1 = ['北京', '上海', '广州', '深圳']

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
        city = str(row.get('城市', ''))
        city_type = '一线城市' if city in tier1 else '其他城市'
        if city_type not in city_stats:
            city_stats[city_type] = {'hit': 0, 'total': 0}
        grade = str(row.get('车辆评级', '中'))
        grade_map = {'优': 'a', '中': 'b', '差': 'c'}
        target_col = grade_map.get(grade, 'b')
        actual = float(row.get('二手车的成交价', 0))
        low = pred.price_matrix['b2BPrices'][target_col]['low']
        up = pred.price_matrix['b2BPrices'][target_col]['up']
        city_stats[city_type]['total'] += 1
        if low <= actual <= up:
            city_stats[city_type]['hit'] += 1
    except:
        pass

print('按城市类型命中率:')
for k, v in city_stats.items():
    pct = v['hit']/v['total']*100 if v['total'] > 0 else 0
    print(f"{k}: {v['hit']}/{v['total']} = {pct:.2f}%")
