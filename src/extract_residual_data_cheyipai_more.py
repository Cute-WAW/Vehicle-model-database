
import sys
import os
from pathlib import Path
import csv
from datetime import datetime

# Add src to path to allow imports if needed, though we are in src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import utils from the original script
# We can import functions, but since we need to modify the parsing logic significantly for the date format,
# we might end up redefining most of it.
# However, we can reuse `clean_city_name`, `extract_brand_series_from_score`, `calculate_years`, `map_grade`, `calculate_adjusted_price`, `process_file`.

from extract_residual_data_step2 import (
    clean_city_name,
    extract_brand_series_from_score,
    calculate_years,
    map_grade,
    calculate_adjusted_price,
    process_file,
    parse_date_cyp
)

def parse_date_mon_yy(date_str: str) -> tuple:
    """解析日期格式: Mon-YY (e.g., Aug-24)"""
    try:
        date_str = date_str.strip()
        dt = datetime.strptime(date_str, "%b-%y")
        return dt.year, dt.month
    except Exception:
        return None, None

def parse_cheyipai_more_line(input_line: str, match_line: str, score_line: str = None) -> dict:
    """
    解析车易拍More数据
    字段索引: 0:品牌, 1:车型, 2:上牌时间(Mon-YY), 3:行驶里程, 4:颜色, 5:城市, 6:车况, 7:是否营运, 8:成交价格, 9:成交时间, 10:nan
    """
    try:
        # 解析输入行
        input_parts = input_line.split('|')
        if len(input_parts) < 2:
            return None
        
        # 提取车辆全称
        vehicle_full_name = input_parts[0].replace('【输入】', '').strip()
        
        # 提取CSV部分
        input_data = input_parts[1].strip().split(',')
        if len(input_data) < 10:
            return None
        
        # 1. 品牌车系
        if score_line:
            brand, series = extract_brand_series_from_score(score_line)
            if brand and series:
                brand_series = f"{brand}-{series}"
            else:
                brand_series = f"{input_data[0].strip()}-未知车系"
        else:
            brand_series = f"{input_data[0].strip()}-未知车系"

        # 日期与年限
        reg_date_str = input_data[2].strip()  # Aug-24
        
        # 成交时间
        if len(input_data) > 9:
            deal_date_str = input_data[9].strip() # 12月12日
        else:
            deal_date_str = "2025年1月1日" # Fallback
        
        # Parse Reg Date (Mon-YY)
        reg_year, reg_month = parse_date_mon_yy(reg_date_str)
        
        # 处理成交时间缺少年份的问题
        # 假设当前数据生成时间是2026年，成交时间如果是12月，可能是2025年。
        # 简单策略：如果成交时间不含年份，默认补全为2025年 (根据数据观察，Aug-24上牌，成交肯定在之后)
        # 实际上，reg_year是2024/2025. deal_date needs to be after reg_date.
        
        if "年" not in deal_date_str:
            # 临时策略: 默认为2025年
            deal_date_full = f"2025年{deal_date_str}"
        else:
            deal_date_full = deal_date_str
            
        eval_year, eval_month = parse_date_cyp(deal_date_full)
        
        # 如果解析出的成交时间早于上牌时间，尝试加一年 (e.g. 2026)
        if reg_year and eval_year:
             if eval_year < reg_year or (eval_year == reg_year and eval_month < reg_month):
                 eval_year += 1
                 deal_date_full = f"{eval_year}年{deal_date_str.replace('年', '').replace('月', '').replace('日', '')}" # Simplified reconstruction
                 # Re-parse to be safe or just use the incremented year
                 
        if not (reg_year and eval_year):
            return None
            
        # 计算使用年限
        years = calculate_years(eval_year, eval_month, reg_year, reg_month)
        if years is None:
            return None

        # 3. 价格 (单位: 万元)
        try:
            used_price = float(input_data[8].strip())
        except:
            return None
            
        # 4. 里程 (单位: 万公里)
        try:
            mileage = float(input_data[3].strip())
        except:
            mileage = None

        # 5. 评级 (65C -> C)
        grade_raw = input_data[6].strip()
        grade_char = grade_raw[-1] if grade_raw else 'C' # 默认C
        grade_label = map_grade(grade_char)
        
        # 6. 新车价格 (从匹配行)
        if '无匹配结果' in match_line:
            return None
        
        match_parts = match_line.split('|')
        if len(match_parts) < 2:
            return None
        
        match_data = match_parts[1].strip().split(',')
        # 新车价格是逗号分隔的第5项（索引4）
        if len(match_data) < 12:
            return None
            
        try:
            new_price = float(match_data[4].strip())
        except:
            return None
            
        # 7. 车况校正
        adjusted_price = calculate_adjusted_price(used_price, grade_label)
        
        # 8. 城市
        city = clean_city_name(input_data[5])

        return {
            '数据来源': '车易拍',
            '车辆全称': vehicle_full_name,
            '品牌车系': brand_series,
            '新车的价格': new_price,
            '二手车的成交价': used_price,
            '交易时间': deal_date_full,
            '车况校正价': adjusted_price,
            '使用年限': years,
            '车辆评级': grade_label,
            '车辆大类': match_data[7].strip(),
            '车辆小类': match_data[8].strip(),
            '车辆属性': match_data[11].strip(),
            '城市': city,
            '行驶里程': mileage
        }
    except Exception as e:
        # print(f"Error: {e}")
        return None

def main():
    script_dir = Path(__file__).parent.parent
    
    input_file = script_dir / 'output' / 'cheyipai_more_match_result_full.txt'
    output_file = script_dir / 'output' / 'cheyipai_more_residual_value.csv'
    
    print(f"处理文件: {input_file}")
    if not input_file.exists():
        print(f"文件不存在: {input_file}")
        return

    results = process_file(str(input_file), parse_cheyipai_more_line)
    print(f"提取有效记录: {len(results)} 条")
    
    print(f"输出文件: {output_file}")
    
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['数据来源', '车辆全称', '品牌车系', '新车的价格', '二手车的成交价', '交易时间', '车况校正价', '使用年限', '车辆评级', '车辆大类', '车辆小类', '车辆属性', '城市', '行驶里程'])
        
        for r in results:
             writer.writerow([
                r['数据来源'],
                r['车辆全称'],
                r['品牌车系'],
                r['新车的价格'],
                r['二手车的成交价'],
                r['交易时间'],
                r['车况校正价'],
                r['使用年限'],
                r['车辆评级'],
                r['车辆大类'],
                r['车辆小类'],
                r['车辆属性'],
                r['城市'],
                r['行驶里程']
            ])
            
    print("完成！")

if __name__ == "__main__":
    main()
