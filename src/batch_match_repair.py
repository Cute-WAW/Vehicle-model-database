
import sys
from pathlib import Path

# 设置工作目录
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir))

import os
os.chdir(script_dir)

import pandas as pd
from datetime import datetime
from src.entity_extractor import EntityExtractor
from src.vehicle_index import VehicleIndex
from src.matching_engine import MatchingEngine

def load_index():
    """加载索引"""
    extractor = EntityExtractor("config/entity_rules.yaml")
    index = VehicleIndex(extractor)
    
    index_path = Path("index/vehicle_index.pkl")
    if index_path.exists():
        print("加载现有索引...")
        index.load(str(index_path))
    else:
        print("索引不存在，请先运行 rebuild_index.py")
        sys.exit(1)
    
    return extractor, index

def format_score_breakdown(result, entities):
    """格式化分数明细"""
    if not result.matches:
        return "无匹配结果"
    
    best = result.matches[0]
    breakdown = []
    
    # 总分
    breakdown.append(f"总分: {best.score:.2f}")
    
    # 匹配的实体
    if best.matched_entities:
        breakdown.append(f"匹配项: {', '.join(best.matched_entities)}")
    
    # 置信度
    breakdown.append(f"置信度: {best.confidence:.2f}")
    
    # 提取的实体信息
    extracted_info = []
    if entities.brand:
        extracted_info.append(f"品牌={entities.brand}")
    if entities.series:
        extracted_info.append(f"车系={entities.series}")
    if entities.year:
        extracted_info.append(f"年款={entities.year}")
    
    if extracted_info:
        breakdown.append(f"识别结果: [{', '.join(extracted_info)}]")
    
    return " | ".join(breakdown)

def batch_match_repair(input_file: str, output_file: str):
    """
    修复并重新匹配
    """
    # 加载索引
    extractor, index = load_index()
    engine = MatchingEngine(extractor, index)
    
    # 加载力洋车型库用于获取完整记录
    print("加载力洋车型库...")
    liyang_df = pd.read_csv("data/力洋车型库精简5.csv")
    liyang_dict = {}
    for _, row in liyang_df.iterrows():
        level_id = row.get('level_id', '')
        if level_id:
            liyang_dict[level_id] = ','.join(str(v) for v in row.values)
    
    # 读取输入数据
    print(f"\n读取输入数据: {input_file}")
    try:
        df = pd.read_csv(input_file)
    except UnicodeDecodeError:
        df = pd.read_csv(input_file, encoding='gbk')
    
    print(f"总记录数: {len(df)}")
    
    # 批量处理
    print(f"\n开始修复匹配...")
    start_time = datetime.now()
    
    match_count = 0
    no_match_count = 0
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"修复匹配结果 - 生成时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"输入文件: {input_file}\n")
        f.write("=" * 120 + "\n\n")
        
        for idx, row in df.iterrows():
            # 1. 获取品牌和车型
            brand_raw = str(row.get('品牌', '')).strip()
            model_raw = str(row.get('车型', '')).strip()
            
            # 2. 构造查询字符串
            # 将品牌中的 '-' 替换为空格，以便提取器能识别多个潜在品牌
            brand_clean = brand_raw.replace('-', ' ')
            
            # 组合查询：品牌 + 车型
            query = f"{brand_clean} {model_raw}"
            
            # 获取输入行的完整原始记录
            input_row_csv = ','.join(str(v) for v in row.values)
            
            # 进度提示
            if (idx + 1) % 100 == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                print(f"  已处理 {idx + 1}/{len(df)}... ({elapsed:.1f}s)")
            
            # 匹配
            result = engine.match(query, top_k=1)
            entities = extractor.extract(query)
            
            if result.matches:
                best = result.matches[0]
                match_count += 1
                
                info = best.vehicle_info
                matched_name = f"{info.get('brand', '')} {info.get('series', '')}  {info.get('year', '')}款 {info.get('sales_name', '')}"
                liyang_record = liyang_dict.get(best.level_id, '')
                
                f.write(f"【输入】{brand_raw} | {model_raw} | {input_row_csv}\n")
                f.write(f"【修正查询】{query}\n")
                f.write(f"【匹配】{matched_name.strip()} (level_id: {best.level_id}) | {liyang_record}\n")
                f.write(f"【得分】{format_score_breakdown(result, entities)}\n")
            else:
                no_match_count += 1
                f.write(f"【输入】{brand_raw} | {model_raw} | {input_row_csv}\n")
                f.write(f"【修正查询】{query}\n")
                f.write(f"【匹配】无匹配结果\n")
                f.write(f"【得分】识别结果: 品牌={entities.brand}, 车系={entities.series}, 年款={entities.year}\n")
            
            f.write("\n")
            f.write("\n")
    
    # 统计
    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    
    print("\n" + "=" * 60)
    print("修复匹配完成！")
    print("=" * 60)
    print(f"总处理数: {match_count + no_match_count}")
    print(f"匹配成功: {match_count} ({100*match_count/(match_count+no_match_count):.1f}%)")
    print(f"匹配失败: {no_match_count}")
    print(f"处理时间: {elapsed:.1f}秒")
    print(f"输出文件: {output_file}")

if __name__ == "__main__":
    input_csv = "output/unmatched_cheyipai_more.csv"
    output_txt = "output/cheyipai_more_match_result_repair.txt"
    
    batch_match_repair(input_csv, output_txt)
