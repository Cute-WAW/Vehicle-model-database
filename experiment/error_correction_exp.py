"""
误差学习与校正实验 (Error Correction)

思路:
1. 使用基础模型进行预测，获取 predicted_price
2. 计算 误差比率 = actual_price / predicted_price
3. 训练一个"误差预测模型" (Random Forest)，根据特征预测这个比率
4. 校正: final_price = predicted_price * predicted_ratio
5. 验证: 校正后的价格是否能提高 B2B 区间命中率

特征:
- 使用年限 (years)
- 行驶里程 (mileage)
- 车辆评级 (grade)
- 新车价格 (new_price)
- 基础预测价 (predicted_price)
- (可选) 品牌车系 target encoding
"""

import sys
from pathlib import Path
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir / 'src'))
import os
os.chdir(script_dir)

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from residual_predictor_step5 import ResidualPredictor

def get_grade_code(grade):
    return {'优': 3, '中': 2, '差': 1}.get(grade, 2)

def run_iteration(seed):
    print(f"\n开始第 {seed} 轮测试 (Random Seed: {seed})...")
    # 加载数据
    df = pd.read_csv('output/residual_value_data_for_build_model.csv')
    df = df.sample(n=10000, random_state=seed)
    
    predictor = ResidualPredictor(residual_data_csv=str(Path('output/residual_value_data_for_build_model.csv').absolute()))
    
    dataset = []
    
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
            
            if not pred.success or pred.predicted_price <= 0:
                continue
                
            actual_price = float(row.get('二手车的成交价', 0))
            if actual_price <= 0:
                continue
            
            target_ratio = actual_price / pred.predicted_price
            
            feat = {
                'years': float(row.get('使用年限', 0)),
                'mileage': float(row.get('行驶里程', 0)) if pd.notna(row.get('行驶里程')) else 0,
                'grade_code': get_grade_code(str(row.get('车辆评级', '中'))),
                'new_price': float(row.get('新车的价格', 0)),
                'predicted_price': pred.predicted_price,
                'row_data': row,
                'price_matrix': pred.price_matrix,
                'target_ratio': target_ratio
            }
            dataset.append(feat)
            
        except Exception:
            continue
            
    data_df = pd.DataFrame(dataset)
    if len(data_df) == 0:
        return 0, 0, 0, 0
        
    feature_cols = ['years', 'mileage', 'grade_code', 'new_price', 'predicted_price']
    X = data_df[feature_cols]
    y = data_df['target_ratio']
    
    X_train, X_test, y_train, y_test, idx_train, idx_test = train_test_split(
        X, y, data_df.index, test_size=0.2, random_state=seed
    )
    
    error_model = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=seed)
    error_model.fit(X_train, y_train)
    
    test_data = data_df.loc[idx_test]
    predicted_ratios = error_model.predict(X_test)
    
    base_hits = 0
    corrected_hits = 0
    total = 0
    
    for i, (idx, row) in enumerate(test_data.iterrows()):
        original_row = row['row_data']
        price_matrix = row['price_matrix']
        base_pred_price = row['predicted_price']
        actual_price = original_row['二手车的成交价']
        
        if not price_matrix: continue
        
        grade = str(original_row.get('车辆评级', '中'))
        grade_map = {'优': 'a', '中': 'b', '差': 'c'}
        target_col = grade_map.get(grade, 'b')
        
        b2b_low = price_matrix['b2BPrices'][target_col]['low']
        b2b_up = price_matrix['b2BPrices'][target_col]['up']
        
        base_hit = b2b_low <= actual_price <= b2b_up
        
        ratio = np.clip(predicted_ratios[i], 0.7, 1.3)
        
        new_low = b2b_low * ratio
        new_up = b2b_up * ratio
        
        corrected_hit = new_low <= actual_price <= new_up
        
        total += 1
        if base_hit: base_hits += 1
        if corrected_hit: corrected_hits += 1
        
    return base_hits, corrected_hits, total

def main():
    seeds = [43, 44] # Additional seeds
    print(f"执行鲁棒性测试，Seeds: {seeds}")
    
    results = []
    
    for seed in seeds:
        base, corrected, total = run_iteration(seed)
        base_rate = base/total*100
        corr_rate = corrected/total*100
        imp = corr_rate - base_rate
        print(f"Seed {seed}: Base={base_rate:.2f}%, Corrected={corr_rate:.2f}%, Improvement={imp:+.2f}%")
        results.append((base_rate, corr_rate, imp))
        
    print("\n" + "="*50)
    print("汇总结果:")
    for i, seed in enumerate(seeds):
        r = results[i]
        print(f"Seed {seed}: {r[0]:.2f}% -> {r[1]:.2f}% ({r[2]:+.2f}%)")


if __name__ == '__main__':
    main()
