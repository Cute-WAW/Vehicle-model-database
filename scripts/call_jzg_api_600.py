import requests
import json
import pandas as pd
import logging
import re
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('jzg_api_600.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 读取省市信息
def load_city_info(city_file):
    if not os.path.exists(city_file):
        logging.error(f"City info file not found: {city_file}")
        return {}
    city_data = pd.read_csv(city_file)
    city_dict = {}
    for _, row in city_data.iterrows():
        city_name = str(row['市名'])
        city_id = row['市编号']
        # 处理市名的特殊情况
        city_name_clean = city_name.replace('市', '').replace('自治州', '')
        city_dict[city_name_clean] = city_id
    return city_dict

def parse_match_result(file_path, start_idx=1000, limit=600):
    entries = []
    if not os.path.exists(file_path):
        logging.error(f"Match result file not found: {file_path}")
        return entries

    with open(file_path, 'r', encoding='utf-8') as f:
        current_entry = {}
        processed_count = 0
        for line in f:
            line = line.strip()
            if line.startswith('【输入】'):
                # 处理之前的内容（如果有）
                if 'level_id' in current_entry and 'input_data' in current_entry:
                    if processed_count >= start_idx:
                        entries.append(current_entry)
                        if len(entries) >= limit:
                            break
                    processed_count += 1
                
                # 开始解析新的记录
                current_entry = {}
                parts = line.split('|')
                if len(parts) < 2:
                    continue
                
                input_fields = parts[1].strip().split(',')
                # 映射：2009-02-16 为 buy_car_date (index 1)
                # 烟台市 为 location_city (index 12)
                # 8.18 为 mileage (last one)
                if len(input_fields) >= 14:
                    current_entry['buy_car_date'] = input_fields[1].strip()
                    current_entry['location_city'] = input_fields[12].strip()
                    current_entry['mileage_raw'] = input_fields[-1].strip()
                    current_entry['input_data'] = input_fields
                    current_entry['vin'] = input_fields[0].strip()
                
            elif line.startswith('【匹配】'):
                match = re.search(r'level_id: (\w+)', line)
                if match:
                    current_entry['level_id'] = match.group(1)
        
        # 别忘了最后一个
        if 'level_id' in current_entry and 'input_data' in current_entry:
            if processed_count >= start_idx and len(entries) < limit:
                entries.append(current_entry)
            
    return entries

def call_jzg_api(entry, city_info):
    location_city = entry.get('location_city')
    city_name_clean = str(location_city).replace('市', '').replace('自治州', '')
    city_id = city_info.get(city_name_clean)
    
    if city_id is None:
        logging.warning(f"City ID not found for {location_city}. Skipping...")
        return None

    # 里程处理
    try:
        mileage_val = float(entry.get('mileage_raw', 0))
        mileage_km = int(mileage_val * 10000)
    except ValueError:
        logging.error(f"Invalid mileage value: {entry.get('mileage_raw')}")
        return None

    params = {
        "jsonInput": json.dumps({
            "LevelId": str(entry['level_id']),
            "vin": entry['vin'],
            "Mileage": str(mileage_km),
            "BuyCarDate": str(entry['buy_car_date']),
            "CityId": str(city_id),
            "appkey": "369f06187fe8dfc1",
            "appsecret": "e25a2f71070a4cc8952a8eddfdb270ae"
        })
    }

    try:
        url = "https://interface.dat881.com/api/gz/getEstimateInfo"
        response = requests.post(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error(f"API call failed for VIN {entry['vin']}: {e}")
        return None

def main():
    city_file = "省市信息.csv"
    match_file = "data/youliang_match_result.txt"
    output_file = "有辆成交20251219_result_1000.csv"
    
    city_info = load_city_info(city_file)
    # 处理 1000-1600 条记录：跳过前 1000 条，取之后的 600 条
    entries = parse_match_result(match_file, start_idx=1000, limit=600)
    
    logging.info(f"Parsed {len(entries)} entries from {match_file} (range: 1000-1600)")
    
    results = []
    total_entries = len(entries)
    for i, entry in enumerate(entries):
        logging.info(f"Processing {i+1}/{total_entries}: VIN={entry['vin']}, City={entry['location_city']}")
        api_res = call_jzg_api(entry, city_info)
        
        input_data = entry['input_data']
        
        res_row = {
            "vehicle_id": input_data[0] if len(input_data) > 0 else "",
            "上牌日期": input_data[1] if len(input_data) > 1 else "",
            "车龄": input_data[2] if len(input_data) > 2 else "",
            "行驶里程": input_data[3] if len(input_data) > 3 else "",
            "车辆评分": input_data[4] if len(input_data) > 4 else "",
            "车辆评级": input_data[5] if len(input_data) > 5 else "",
            "成交日期": input_data[6] if len(input_data) > 6 else "",
            "成交价格": input_data[7] if len(input_data) > 7 else "",
            "业务类型": input_data[8] if len(input_data) > 8 else "",
            "品牌": input_data[9] if len(input_data) > 9 else "",
            "车系": input_data[10] if len(input_data) > 10 else "",
            "车型": input_data[11] if len(input_data) > 11 else "",
            "是否火烧": input_data[13] if len(input_data) > 13 else "",
            "是否水泡": input_data[14] if len(input_data) > 14 else "",
            "是否事故": input_data[15] if len(input_data) > 15 else "",
            "level_id": entry['level_id'],
            "力扬指导价格": input_data[17] if len(input_data) > 17 else "",
            "jzg_result": json.dumps(api_res, ensure_ascii=False) if api_res else ""
        }
        results.append(res_row)
        
    if results:
        df = pd.DataFrame(results)
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        logging.info(f"Saved {len(results)} results to {output_file}")


if __name__ == "__main__":
    main()
