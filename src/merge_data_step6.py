
import pandas as pd
import os
from pathlib import Path

def merge_datasets():
    # Define paths
    original_data_path = Path(r"D:\BaiduNetdiskDownload\residual_value_data_for_build_model.csv")
    new_data_path = Path(r"D:\BaiduNetdiskDownload\车型库映射\车型库映射\output\residual_value_data_for_build_model.csv")
    output_path = Path(r"D:\BaiduNetdiskDownload\车型库映射\车型库映射\output\merged_residual_value_data.csv")
    
    print(f"Reading original data from: {original_data_path}")
    try:
        df_original = pd.read_csv(original_data_path, encoding='utf-8-sig')
    except UnicodeDecodeError:
        print("utf-8-sig failed, trying gbk")
        df_original = pd.read_csv(original_data_path, encoding='gbk')
        
    print(f"Original data shape: {df_original.shape}")
    
    print(f"Reading new data from: {new_data_path}")
    try:
        df_new = pd.read_csv(new_data_path, encoding='utf-8-sig')
    except UnicodeDecodeError:
        print("utf-8-sig failed, trying gbk")
        df_new = pd.read_csv(new_data_path, encoding='gbk')
        
    print(f"New data shape: {df_new.shape}")
    
    # Identify common columns
    common_cols = list(set(df_original.columns) & set(df_new.columns))
    print(f"Common columns count: {len(common_cols)}")
    
    # We want to keep all columns from original data, and append new data
    # If new data has extra columns (like prediction results), we can keep them or drop them.
    # For model building, we mainly need the input features.
    # Let's align to the union of columns to preserve information
    
    df_merged = pd.concat([df_original, df_new], axis=0, ignore_index=True)
    
    print(f"Merged data shape: {df_merged.shape}")
    
    # Fill '数据来源' if missing (assuming original is '有辆' if not specified, but let's check)
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
