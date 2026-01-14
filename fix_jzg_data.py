
import pandas as pd
import json
import os
from pathlib import Path

# Paths to original files (as seen in jzg_hit_rate_analysis.py)
source_files = [
    r'd:\antigravity\price_evaluation\力洋\有辆成交20251219_result.csv',
    r'd:\antigravity\price_evaluation\力洋\有辆成交20251219_result_600.csv',
    r'd:\antigravity\price_evaluation\力洋\有辆成交20251219_result_1000.csv'
]

output_path = r'd:\antigravity\price_evaluation\车型库映射\doc\comparison_data\jzg_source_data.csv'

dfs = []
for f in source_files:
    if os.path.exists(f):
        print(f"Reading {f}...")
        try:
            # Read all columns to ensure we get '成交价格'
            df = pd.read_csv(f, on_bad_lines='skip')
            
            # Select relevant columns
            # Note: Checking column names first might be good, but assuming standard format due to previous scripts
            cols_to_keep = ['成交价格', 'jzg_result', 'vin', 'model_name'] # Keep some metadata if possible
            
            # Filter columns that actually exist
            existing_cols = [c for c in cols_to_keep if c in df.columns]
            
            # If '成交价格' matches 'actual_price' or similar, handle that (based on jzg_hit_rate_analysis it is '成交价格')
            
            if 'jzg_result' in df.columns:
                df_filtered = df[existing_cols].copy()
                dfs.append(df_filtered)
        except Exception as e:
            print(f"Error reading {f}: {e}")

if dfs:
    combined_df = pd.concat(dfs, ignore_index=True)
    print(f"Total rows read: {len(combined_df)}")
    
    # Filter for valid jzg_result (contains "Result")
    # Also ensure actual price is present
    
    def is_valid(row):
        try:
            # Check price
            price = row.get('成交价格')
            if pd.isna(price) or str(price).strip() == '':
                return False
            
            # Check JZG result
            res = row.get('jzg_result')
            if pd.isna(res) or str(res).strip() == '':
                return False
            if '"Result"' not in str(res): # Simple check
                return False
                
            return True
        except:
            return False

    valid_df = combined_df[combined_df.apply(is_valid, axis=1)]
    print(f"Valid rows (with Price and JZG Result): {len(valid_df)}")
    
    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    valid_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"Saved to {output_path}")
    
    # Verify
    print("\nFirst 3 rows:")
    print(valid_df[['成交价格']].head(3))
else:
    print("No data found!")
