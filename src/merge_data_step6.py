
import pandas as pd
import os
from pathlib import Path

def merge_datasets():
    # Define paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    # Use the newly generated file from step 2 which now contains ALL data
    original_data_path = project_root / 'output' / 'residual_value_data.csv'
    output_path = project_root / 'output' / 'merged_residual_value_data.csv'
    
    if not original_data_path.exists():
        print(f"Error: Data file not found at {original_data_path}")
        return None
        
    print(f"Reading data from: {original_data_path}")
    try:
        df_merged = pd.read_csv(original_data_path, encoding='utf-8-sig')
    except UnicodeDecodeError:
        print("utf-8-sig failed, trying gbk")
        df_merged = pd.read_csv(original_data_path, encoding='gbk')
        
    print(f"Data shape: {df_merged.shape}")
    
    # Fill '数据来源' if missing
    if '数据来源' in df_merged.columns:
        print("Value counts for '数据来源':")
        print(df_merged['数据来源'].value_counts(dropna=False))
        
        # If original data has NaN source, fill it with '有辆' (YouLiang) or 'original'
        df_merged['数据来源'] = df_merged['数据来源'].fillna('有辆')
    
    # Save merged file
    print(f"Saving merged data to: {output_path}")
    df_merged.to_csv(output_path, index=False, encoding='utf-8-sig')
    print("Merge completed successfully.")
    
    return str(output_path)

if __name__ == "__main__":
    merge_datasets()
