"""
Optimization Analysis Script
Focuses on 3 specific segments:
1. New Cars (0-3 Years)
2. High-End Cars (>100k)
3. NEVs (New Energy Vehicles)
"""

import pandas as pd
import numpy as np
import sys
import os
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
os.chdir(Path(__file__).parent.parent)

from residual_predictor_step5 import ResidualPredictor

def is_nev(vehicle_name):
    """Simple keyword matching for NEV"""
    vehicle_name = str(vehicle_name).upper()
    keywords = ['电', '混动', 'DM-I', 'EV', 'PHEV', '增程', '蔚来', '小鹏', '理想', '特斯拉', 'MODEL', 'ID.']
    return any(k in vehicle_name for k in keywords)

def analyze_segment(df, segment_name):
    """Calculate metrics for a segment"""
    if len(df) == 0:
        print(f"\n[{segment_name}] No samples found.")
        return

    # Hit Rate
    hits = df['in_range'].sum()
    hit_rate = hits / len(df) * 100
    
    # Error Metrics
    # Error = Actual - Predicted
    # Bias = Mean Error (positive means we under-predict, negative means we over-predict)
    errors = df['actual'] - df['predicted']
    bias = errors.mean()
    mae = errors.abs().mean()
    mape = (errors.abs() / df['actual']).mean() * 100
    
    print(f"\n[{segment_name}]")
    print(f"  Samples: {len(df)}")
    print(f"  Hit Rate: {hit_rate:.1f}%")
    print(f"  Bias (Act-Pred): {bias:.2f}万 (Pos=Under, Neg=Over)")
    print(f"  MAE: {mae:.2f}万")
    print(f"  MAPE: {mape:.1f}%")
    
    # Price Ratio Analysis (Actual / Predicted)
    ratios = df['actual'] / df['predicted']
    print(f"  Avg Ratio (Act/Pred): {ratios.mean():.3f}")
    
    return hit_rate, bias, ratios.mean()

print("=" * 60)
print("Model Optimization Analysis")
print("=" * 60)

# Load Data
csv_path = 'output/residual_value_data_for_build_model.csv'
full_df = pd.read_csv(csv_path, on_bad_lines='skip')

# Sampling: use a larger set for stable metrics, or full set if feasible
# 3000 should be enough
sample_size = 3000
df_source = full_df.sample(n=min(sample_size, len(full_df)), random_state=42).reset_index(drop=True)
print(f"Dataset size: {len(df_source)}")

predictor = ResidualPredictor(residual_data_csv=csv_path)

results = []
print("Running predictions...")

for idx, row in df_source.iterrows():
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
                'vehicle': str(row['车辆全称']),
                'years': float(row['使用年限']),
                'actual': actual,
                'predicted': result.predicted_price,
                'low': range_low,
                'high': range_high,
                'in_range': range_low <= actual <= range_high,
                'is_nev': is_nev(row['车辆全称'])
            })
            
    except Exception:
        pass
    
    if (idx + 1) % 500 == 0:
        print(f"  Processed {idx + 1}...")

df = pd.DataFrame(results)

# 1. New Cars (0-3 Years)
df_new = df[df['years'] <= 3]
analyze_segment(df_new, "New Cars (0-3y)")

# 2. High-End Cars (>100k) - based on ACTUAL price for segmentation analysis
# (In practice we predict based on new price, but for analysis let's look at high value used ones)
df_high = df[df['actual'] >= 10] # 10万 = 100k RMB
analyze_segment(df_high, "High-End (>100k)")

# 3. NEVs
df_nev = df[df['is_nev'] == True]
analyze_segment(df_nev, "NEVs")

# Overall
analyze_segment(df, "Overall Baseline")
