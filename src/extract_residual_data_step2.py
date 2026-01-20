"""
残值率分析数据提取程序

从匹配结果文件中提取二手车残值率分析所需数据，输出CSV格式文件。
支持两种数据源：
- 有辆成交价格 (youliang_match_result.txt)
- 优信拍 (youxinpai_match_result.txt)

输出格式: 数据来源,品牌车系,新车的价格,二手车的成交价,使用年限,车辆评级,车辆大类,车辆小类,车辆属性
"""

import re
from pathlib import Path
from datetime import datetime



# 配置评估时间过滤阈值 (只输出该日期及之后的记录)
EVAL_THRESHOLD = datetime(2023, 1, 1)


def clean_city_name(city_str: str) -> str:
    """清洗城市名称，移除末尾的'市'"""
    if not city_str:
        return ""
    city = city_str.strip()
    if city.endswith("市") and len(city) > 1:
        return city[:-1]
    return city

def parse_date_yy(date_str: str) -> tuple:
    """解析有辆日期格式: YYYY-MM-DD"""
    try:
        parts = date_str.strip().split('-')
        return int(parts[0]), int(parts[1])
    except:
        return None, None


def parse_date_yxp(date_str: str) -> tuple:
    """解析优信拍日期格式: YYYY年MM月"""
    try:
        match = re.match(r'(\d{4})年(\d{1,2})月', date_str.strip())
        if match:
            return int(match.group(1)), int(match.group(2))
    except:
        pass
    return None, None


def parse_date_cyp(date_str: str) -> tuple:
    """解析车易拍日期格式: YYYY年M月D日"""
    try:
        # 移除可能存在的空格
        date_str = date_str.strip()
        match = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_str)
        if match:
            return int(match.group(1)), int(match.group(2))
    except:
        pass
    return None, None


def parse_cheyipai_line(input_line: str, match_line: str, score_line: str = None) -> dict:
    """
    解析车易拍格式数据
    字段索引: 0:品牌, 1:车型, 2:上牌时间, 3:行驶里程, 4:颜色, 5:城市, 6:车况, 7:是否营运, 8:成交价格, 9:成交时间
    """
    try:
        # 解析输入行
        input_parts = input_line.split('|')
        if len(input_parts) < 2:
            return None
        
        # 提取车辆全称
        # 格式: 【输入】日产 2016款 轩逸... | 日产,2016款...
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

        # 2. 日期与年限
        reg_date_str = input_data[2].strip()  # 2016年4月1日
        deal_date_str = input_data[9].strip() # 11月28日 (可能缺少年份)
        
        reg_year, reg_month = parse_date_cyp(reg_date_str)
        
        # 处理成交时间缺少年份的问题 (假设为2024年，或根据上下文推断)
        # 临时策略：如果成交时间不含年份，默认补全为2024年（基于之前观察）
        if "年" not in deal_date_str:
            deal_date_str = f"2024年{deal_date_str}"
            
        eval_year, eval_month = parse_date_cyp(deal_date_str)

        if not (reg_year and eval_year):
            # print(f"日期解析失败: reg={reg_date_str}, deal={deal_date_str}")
            return None
            
        # 计算使用年限
        years = calculate_years(eval_year, eval_month, reg_year, reg_month)
        if years is None:
            # print(f"年限计算失败: {eval_year}-{eval_month} vs {reg_year}-{reg_month}")
            return None

        # 3. 价格 (单位: 万元)
        try:
            used_price = float(input_data[8].strip())
        except:
            # print(f"价格解析失败: {input_data[8]}")
            return None
            
        # 4. 里程 (单位: 万公里)
        try:
            mileage = float(input_data[3].strip())
        except:
            mileage = None

        # 5. 评级 (80B -> B)
        # 车易拍评级格式如 "80B", "65D". 取最后一个字母
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
        print(f"Error in parse_cheyipai_line: {e}")
        return None


def calculate_years(eval_year, eval_month, reg_year, reg_month):
    """计算使用年限，精确到月"""
    if None in (eval_year, eval_month, reg_year, reg_month):
        return None
    years = eval_year - reg_year
    months = (eval_month - reg_month) / 12
    return round(years + months, 2)


def map_grade(grade: str) -> str:
    """映射车辆评级: A=优, B/C=中, D=差"""
    grade = grade.upper()
    if grade == 'A':
        return '优'
    elif grade in ('B', 'C'):
        return '中'
    elif grade == 'D':
        return '差'
    return '未知'


def extract_grade_from_code(code: str) -> str:
    """从优信拍评级码(如70BC)中提取中间字母"""
    # 格式: 数字+字母+字母, 取中间字母
    match = re.match(r'\d+([A-D])[A-D]', code.upper())
    if match:
        return match.group(1)
    return None


def extract_brand_series_from_score(score_line: str) -> tuple:
    """
    从【得分】行的识别结果中提取品牌和车系
    
    示例输入:
    【得分】总分: 250.00 | ... | 识别结果: [品牌=本田, 车系=飞度, ...]
    
    Returns:
        Tuple[str, str]: (品牌, 车系)，如果解析失败返回 (None, None)
    """
    try:
        # 匹配 识别结果: [...] 部分
        result_match = re.search(r'识别结果:\s*\[([^\]]+)\]', score_line)
        if not result_match:
            return (None, None)
        
        result_content = result_match.group(1)
        
        # 提取品牌
        brand_match = re.search(r'品牌=([^,\]]+)', result_content)
        brand = brand_match.group(1).strip() if brand_match else None
        
        # 提取车系
        series_match = re.search(r'车系=([^,\]]+)', result_content)
        series = series_match.group(1).strip() if series_match else None
        
        return (brand, series)
    except:
        return (None, None)


def calculate_adjusted_price(price: float, grade_label: str) -> float:
    """
    计算车况校正价 (还原为B级车况价格)
    
    规则:
    1. 优 (A):
       - 价格 >= 0.5万: price / 1.092887
       - 价格 < 0.5万:  price - 0.03
    2. 差 (D):
       - 价格 >= 0.5万: price / 0.875000
       - 价格 < 0.5万:  price + 0.04
    3. 其他 (中): 不调整
    """
    if price is None:
        return None
        
    if grade_label == '优':
        if price < 0.5:
            return round(price - 0.03, 2)
        else:
            return round(price / 1.092887, 2)
    elif grade_label == '差':
        if price < 0.5:
            return round(price + 0.04, 2)
        else:
            return round(price / 0.875000, 2)
    
    return price


def parse_youliang_line(input_line: str, match_line: str, score_line: str = None) -> dict:
    """
    解析有辆格式数据
    """
    try:
        # 解析输入行
        input_parts = input_line.split('|')
        if len(input_parts) < 2:
            return None
        
        # 提取车辆全称：【输入】后面的车辆描述部分
        # 格式: 【输入】起亚/K3/2013款 1.6 自动 GLS | ...
        vehicle_full_name = input_parts[0].replace('【输入】', '').strip()
        # 将 / 替换为空格，得到标准格式: "起亚 K3 2013款 1.6 自动 GLS"
        vehicle_full_name = vehicle_full_name.replace('/', ' ')
        
        input_data = input_parts[1].strip().split(',')
        if len(input_data) < 10:
            return None
        
        # 提取品牌车系 (第10、11项，索引9、10)
        # 优先从【得分】行的识别结果提取品牌车系
        if score_line:
            brand, series = extract_brand_series_from_score(score_line)
            if brand and series:
                brand_series = f"{brand}-{series}"
            else:
                # 回退到原始逻辑
                brand = input_data[9].strip()
                series = input_data[10].strip()
                brand_series = f"{brand}-{series}"
        else:
            brand = input_data[9].strip()
            series = input_data[10].strip()
            brand_series = f"{brand}-{series}"
        
        # 格式: 品牌 车系 年款 版本, 评级, 成交价, 成交时间, 上牌时间, 里程...
        reg_date = input_data[1].strip()  # 注册日期 2020-01-03
        eval_date = input_data[6].strip()  # 评估日期 2023-10-10
        grade = input_data[5].strip()  # 评级 B

        # 时间过滤: 有辆格式 YYYY-MM-DD
        try:
            eval_dt = datetime.strptime(eval_date, "%Y-%m-%d")
            if eval_dt < EVAL_THRESHOLD:
                return None
        except:
            return None
        
        # 解析日期
        reg_year, reg_month = parse_date_yy(reg_date)
        eval_year, eval_month = parse_date_yy(eval_date)
        
        # 计算使用年限
        years = calculate_years(eval_year, eval_month, reg_year, reg_month)
        if years is None:
            return None
        
        # 二手车成交价 (第8项，索引7) 单位元，需除以10000
        try:
            used_price = round(float(input_data[7].strip()) / 10000, 2)
        except:
            return None
        
        # 解析匹配行获取新车价格
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
            
            return None
            
        grade_label = map_grade(grade)
        adjusted_price = calculate_adjusted_price(used_price, grade_label)
        
        # 提取城市 (第13项，索引12)
        # 对应输入行: ...| 317580,...,成都市,否,否,否,...
        city = ""
        if len(input_data) > 12:
            city = clean_city_name(input_data[12])
        
        # 提取行驶里程 (第4项，索引3) 19.95
        try:
            mileage = float(input_data[3].strip())
        except:
            mileage = None

        return {
            '数据来源': '有辆',
            '车辆全称': vehicle_full_name,
            '品牌车系': brand_series,
            '新车的价格': new_price,
            '二手车的成交价': used_price,
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
        return None


def parse_youxinpai_line(input_line: str, match_line: str, score_line: str = None) -> dict:
    """
    解析优信拍格式数据
    """
    try:
        # 解析输入行
        input_parts = input_line.split('|')
        if len(input_parts) < 2:
            return None
        
        # 提取车辆全称：【输入】后面的车辆描述部分
        # 格式: 【输入】红旗/E-QM5/2022款 431km 自动 充电乐享版 | ...
        vehicle_full_name = input_parts[0].replace('【输入】', '').strip()
        # 将 / 替换为空格，得到标准格式
        vehicle_full_name = vehicle_full_name.replace('/', ' ')
        
        # 从【输入】后的文字中提取品牌车系
        # 优先从【得分】行的识别结果提取品牌车系
        if score_line:
            brand, series = extract_brand_series_from_score(score_line)
            if brand and series:
                brand_series = f"{brand}-{series}"
            else:
                # 回退到原始逻辑
                input_name = input_parts[0].replace('【输入】', '').strip()
                name_parts = input_name.split('/')
                if len(name_parts) < 2:
                    return None
                brand = name_parts[0].strip()
                series = name_parts[1].strip()
                brand_series = f"{brand}-{series}"
        else:
            input_name = input_parts[0].replace('【输入】', '').strip()
            name_parts = input_name.split('/')
            if len(name_parts) < 2:
                return None
            brand = name_parts[0].strip()
            series = name_parts[1].strip()
            brand_series = f"{brand}-{series}"
        
        # 解析逗号分隔的数据部分
        input_data = input_parts[1].strip().split(',')
        if len(input_data) < 5:
            return None
        
        # 评级码 (第2项，索引1)
        grade_code = input_data[1].strip()
        grade = extract_grade_from_code(grade_code)
        if not grade:
            return None
        
        # 二手车成交价 (第3项，索引2) 格式: 1.82万元
        price_str = input_data[2].strip().replace('万元', '')
        try:
            used_price = round(float(price_str), 2)
        except:
            return None
        
        # 日期: 评估日期(第4项) - 注册日期(第5项)
        eval_date_str = input_data[3].strip()  # 2025年12月
        reg_date_str = input_data[4].strip()   # 2017年12月
        
        # 行驶里程 (第6项，索引5) 122192公里
        mileage_str = input_data[5].strip().replace('公里', '')
        try:
            mileage = round(float(mileage_str) / 10000, 2)
        except:
            mileage = None

        eval_year, eval_month = parse_date_yxp(eval_date_str)
        reg_year, reg_month = parse_date_yxp(reg_date_str)

        # 时间过滤
        if eval_year and eval_month:
            # 优信拍只有年月，默认按当月1号与阈值比较
            eval_dt = datetime(eval_year, eval_month, 1)
            if eval_dt < EVAL_THRESHOLD:
                return None
        else:
            return None
        
        # 计算使用年限
        years = calculate_years(eval_year, eval_month, reg_year, reg_month)
        if years is None:
            return None
        
        # 解析匹配行获取新车价格
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
            
            return None
            
        grade_label = map_grade(grade)
        adjusted_price = calculate_adjusted_price(used_price, grade_label)
        
        # 提取城市 (第7项，索引6)
        # 对应输入行: ...| 宝骏/...,杭州,非营运,棕色
        city = ""
        if len(input_data) > 6:
            city = clean_city_name(input_data[6])
        
        return {
            '数据来源': '优信拍',
            '车辆全称': vehicle_full_name,
            '品牌车系': brand_series,
            '新车的价格': new_price,
            '二手车的成交价': used_price,
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
        return None


def process_file(file_path: str, parser_func) -> list:
    """处理匹配结果文件"""
    results = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if line.startswith('【输入】'):
            input_line = line
            match_line = ''
            score_line = ''
            
            # 查找下一行的匹配结果
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith('【匹配】'):
                    match_line = next_line
            
            # 查找【得分】行
            if i + 2 < len(lines):
                score_candidate = lines[i + 2].strip()
                if score_candidate.startswith('【得分】'):
                    score_line = score_candidate
            
            if match_line:
                result = parser_func(input_line, match_line, score_line)
                if result:
                    results.append(result)
            
            i += 3  # 跳过输入、匹配、得分三行
        else:
            i += 1
    
    return results


def main():
    """主函数"""
    script_dir = Path(__file__).parent.parent
    
    # 输入文件
    youliang_file = script_dir / 'output' / 'youliang_match_result.txt'
    youxinpai_file = script_dir / 'output' / 'youxinpai_match_result.txt'
    cheyipai_file = script_dir / 'output' / 'cheyipai_match_result.txt'
    
    # 输出文件
    output_file = script_dir / 'output' / 'residual_value_data.csv'
    
    all_results = []
    
    # 处理车易拍数据
    if cheyipai_file.exists():
        print(f"处理车易拍数据: {cheyipai_file}")
        results = process_file(str(cheyipai_file), parse_cheyipai_line)
        print(f"  提取有效记录: {len(results)} 条")
        all_results.extend(results)
    else:
        print(f"文件不存在: {cheyipai_file}")
    
    # 处理有辆数据
    if youliang_file.exists():
        print(f"处理有辆数据: {youliang_file}")
        results = process_file(str(youliang_file), parse_youliang_line)
        print(f"  提取有效记录: {len(results)} 条")
        all_results.extend(results)
    else:
        print(f"文件不存在: {youliang_file}")
    
    # 处理优信拍数据
    if youxinpai_file.exists():
        print(f"处理优信拍数据: {youxinpai_file}")
        results = process_file(str(youxinpai_file), parse_youxinpai_line)
        print(f"  提取有效记录: {len(results)} 条")
        all_results.extend(results)
    else:
        print(f"文件不存在: {youxinpai_file}")
    
    # 输出CSV
    print(f"\n总记录数: {len(all_results)}")
    print(f"输出文件: {output_file}")
    
    
    with open(output_file, 'w', encoding='utf-8') as f:
        # 写入表头
        f.write('数据来源,车辆全称,品牌车系,新车的价格,二手车的成交价,车况校正价,使用年限,车辆评级,车辆大类,车辆小类,车辆属性,城市,行驶里程\n')
        
        # 写入数据
        count_filtered_grade = 0
        count_filtered_years = 0
        
        for r in all_results:
            # 过滤 车辆评级 为未知的数据
            if r['车辆评级'] == '未知':
                count_filtered_grade += 1
                continue
            
            # 过滤 使用年限 不是数字的数据
            if not isinstance(r['使用年限'], (int, float)):
                count_filtered_years += 1
                continue
            
            f.write(f"{r['数据来源']},{r['车辆全称']},{r['品牌车系']},{r['新车的价格']},{r['二手车的成交价']},{r['车况校正价']},{r['使用年限']},{r['车辆评级']},{r['车辆大类']},{r['车辆小类']},{r['车辆属性']},{r['城市']},{r['行驶里程']}\n")
            
        print(f"过滤掉 '车辆评级=未知' 的数据: {count_filtered_grade} 条")
        print(f"过滤掉 '使用年限!=数字' 的数据: {count_filtered_years} 条")
    
    print("完成！")


if __name__ == '__main__':
    main()
