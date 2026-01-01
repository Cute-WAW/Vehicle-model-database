"""
B2B 区间命中率统计脚本 (输出精确数字)
"""

import sys
from pathlib import Path

script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir / 'src'))

import os
os.chdir(script_dir)

import pandas as pd
from residual_predictor_step5 import ResidualPredictor


def main():
    data_path = 'output/residual_value_data_for_build_model.csv'
    print(f"加载数据: {data_path}")
    df = pd.read_csv(data_path)
    print(f"总记录数: {len(df)}")
    
    sample_size = 2000
    if len(df) > sample_size:
        df = df.sample(n=sample_size, random_state=42)
        print(f"采样后: {len(df)}")
    
    print("初始化预测器...")
    predictor = ResidualPredictor(residual_data_csv=str(Path(data_path).absolute()))
    
    same_grade_hit = 0
    b_grade_hit = 0
    total_valid = 0
    
    model_source_count = {}
    model_source_hit = {}
    
    print("开始评估...")
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
            
            model_used = 'unknown'
            if pred.debug and pred.debug.model_used:
                model_used = pred.debug.model_used
            
            if model_used not in model_source_count:
                model_source_count[model_used] = 0
                model_source_hit[model_used] = 0
            model_source_count[model_used] += 1
            
            grade_map = {'优': 'a', '中': 'b', '差': 'c'}
            target_col = grade_map.get(grade, 'b')
            
            same_low = pred.price_matrix['b2BPrices'][target_col]['low']
            same_up = pred.price_matrix['b2BPrices'][target_col]['up']
            b_low = pred.price_matrix['b2BPrices']['b']['low']
            b_up = pred.price_matrix['b2BPrices']['b']['up']
            
            total_valid += 1
            
            if same_low <= actual_price <= same_up:
                same_grade_hit += 1
                model_source_hit[model_used] += 1
            
            if b_low <= actual_price <= b_up:
                b_grade_hit += 1
                
        except Exception as e:
            continue
    
    print()
    print("=" * 60)
    print("B2B 区间命中率统计结果")
    print("=" * 60)
    print(f"有效样本数: {total_valid}")
    print(f"同等级命中: {same_grade_hit}/{total_valid} = {same_grade_hit/total_valid*100:.2f}%")
    print(f"B级命中: {b_grade_hit}/{total_valid} = {b_grade_hit/total_valid*100:.2f}%")
    print()
    print("按模型来源:")
    for src in model_source_count:
        cnt = model_source_count[src]
        hit = model_source_hit[src]
        print(f"  {src}: {cnt} 条, 命中 {hit}, 命中率 {hit/cnt*100:.2f}%")


if __name__ == '__main__':
    main()
