
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import shutil
import os

def parse_chinese_date(date_str):
    try:
        # Format: 2025年11月11日
        return datetime.strptime(date_str, '%Y年%m月%d日')
    except Exception as e:
        print(f"Error parsing date {date_str}: {e}")
        return None

def main():
    merged_path = 'output/merged_residual_value_data_with_dates.csv'
    new_data_path = 'output/cheyipai_more_residual_value.csv'
    backup_path = 'output/merged_residual_value_data_with_dates.csv.bak'

    # Backup original file
    if os.path.exists(merged_path):
        shutil.copy2(merged_path, backup_path)
        print(f"Backed up {merged_path} to {backup_path}")
    
    # Load existing data
    df_merged = pd.read_csv(merged_path)
    print(f"Loaded {len(df_merged)} records from {merged_path}")
    
    # Load new data
    df_new = pd.read_csv(new_data_path)
    print(f"Loaded {len(df_new)} records from {new_data_path}")
    
    # Process new data to match merged structure
    
    # 1. Handle dates
    # cheyipai has '交易时间' like '2025年11月11日'
    # merged has 'trade_date' like '2025-12-01'
    
    trade_dates = []
    reg_dates = []
    
    for idx, row in df_new.iterrows():
        trade_date_str = row.get('交易时间')
        years = row.get('使用年限')
        
        trade_date = parse_chinese_date(trade_date_str)
        
        if trade_date:
            trade_date_fmt = trade_date.strftime('%Y-%m-%d')
            
            # Estimate reg_date
            if pd.notna(years):
                days = int(years * 365)
                reg_date = trade_date - timedelta(days=days)
                # Use 1st day of the month for consistency with typical monthly data
                reg_date = reg_date.replace(day=1) 
                reg_date_fmt = reg_date.strftime('%Y-%m-%d')
            else:
                reg_date_fmt = None
        else:
            trade_date_fmt = None
            reg_date_fmt = None
            
        trade_dates.append(trade_date_fmt)
        reg_dates.append(reg_date_fmt)
        
    df_new['trade_date'] = trade_dates
    df_new['reg_date'] = reg_dates
    
    # 2. Calculate Residual Rate
    # 残值率 = 车况校正价 / 新车的价格
    df_new['残值率'] = df_new.apply(
        lambda row: row['车况校正价'] / row['新车的价格'] if row['新车的价格'] > 0 else 0, axis=1
    )
    
    # 3. Add other missing columns
    # Columns in merged but not in new: 
    # rounded_year, 预测值, 误差, 误差率, 误差等级, 最佳模型, 车辆类别
    
    # rounded_year can be calculated
    df_new['rounded_year'] = df_new['使用年限'].apply(lambda x: round(x * 2) / 2) # Round to nearest 0.5
    
    # 车辆类别: usually mapped from 车辆小类/大类. In merged data, let's see what it is.
    # From sample: 车辆小类='紧凑型车', 车辆大类='轿车' -> 车辆类别 seems to be missing in sample output provided by user?
    # Wait, in the Read output of merged file: "车辆类别" is the last column but the sample rows show empty values for it?
    # Row 2: ...,最佳模型,车辆类别,reg_date,trade_date
    # Row 2 values end with: ...,1.0,,,,,,,2024-07-01,2025-12-01
    # It seems "车辆类别" might be empty or specific. Let's just fill with empty for now or copy '车辆小类'.
    # Actually, looking at previous steps, 'car_types_models' use aggregated types.
    # Let's just leave it empty or map if simple.
    
    cols_to_add = ['预测值', '误差', '误差率', '误差等级', '最佳模型', '车辆类别']
    for col in cols_to_add:
        df_new[col] = np.nan
        
    # 4. Align columns
    # Ensure all columns from merged exist in new, and order them
    merged_cols = df_merged.columns.tolist()
    
    # Remove '交易时间' from new if it's not in merged (it's not)
    if '交易时间' in df_new.columns:
        df_new = df_new.drop(columns=['交易时间'])
        
    # Reindex to match merged columns
    # This will create NaN for missing columns and drop extra columns
    df_new_aligned = df_new.reindex(columns=merged_cols)
    
    # 5. Append
    df_final = pd.concat([df_merged, df_new_aligned], ignore_index=True)
    
    print(f"Merged total: {len(df_final)} records")
    
    # Save
    df_final.to_csv(merged_path, index=False)
    print(f"Saved to {merged_path}")

if __name__ == "__main__":
    main()
