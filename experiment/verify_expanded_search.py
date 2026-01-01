import sys
from pathlib import Path
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir / 'src'))
import os
os.chdir(script_dir)

import pandas as pd
from residual_predictor_step5 import ResidualPredictor

def main():
    print("开始验证扩大搜索范围后的命中率...")
    # 使用 2000 条样本
    df = pd.read_csv('output/residual_value_data_for_build_model.csv')
    df = df.sample(n=2000, random_state=42)
    
    predictor = ResidualPredictor(residual_data_csv=str(Path('output/residual_value_data_for_build_model.csv').absolute()))
    
    total = 0
    hits = 0
    model_stats = {}
    
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
            
            if not pred.success:
                if total < 5: print(f"Row {idx} failed: {pred.error_message}")
                continue
                
            if not pred.price_matrix:
                if total < 5: print(f"Row {idx} has no price matrix")
                continue
                
            # 统计不同模型的表现
            model_key = pred.debug.model_used if pred.debug else 'unknown' # 'brand_series' or 'car_type'
            if model_key not in model_stats:
                model_stats[model_key] = {'hit': 0, 'total': 0, 'adjusted': 0}
            
            model_stats[model_key]['total'] += 1
            # Check adjustment in debug info
            if pred.debug and pred.debug.adjustment_method != 'none' and pred.debug.adjustment_delta != 0:
                 model_stats[model_key]['adjusted'] += 1
            
            grade = str(row.get('车辆评级', '中'))
            grade_map = {'优': 'a', '中': 'b', '差': 'c'}
            target_col = grade_map.get(grade, 'b')
            actual = float(row.get('二手车的成交价', 0))
            
            low = pred.price_matrix['b2BPrices'][target_col]['low']
            up = pred.price_matrix['b2BPrices'][target_col]['up']
            
            total += 1
            if low <= actual <= up:
                hits += 1
                model_stats[model_key]['hit'] += 1
                
        except Exception as e:
            if total < 5:
                import traceback
                print(f"Error Row {idx}: {e}")
                traceback.print_exc()
            continue
            
    print("-" * 50)
    # Simplify f-string to avoid potential parsing errors
    hit_rate = hits/total*100 if total > 0 else 0
    print(f"总体命中率: {hits}/{total} = {hit_rate:.2f}%")
    print("-" * 50)
    for model, stats in model_stats.items():
        hit_rate = stats['hit']/stats['total']*100 if stats['total'] > 0 else 0
        adj_rate = stats['adjusted']/stats['total']*100 if stats['total'] > 0 else 0
        print(f"模型 {model}: {stats['hit']}/{stats['total']} = {hit_rate:.2f}% (微调覆盖率: {adj_rate:.2f}%)")

if __name__ == '__main__':
    main()
