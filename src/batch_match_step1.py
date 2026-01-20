"""
批量匹配程序

将优信拍车辆数据匹配到力洋车型库，输出格式：
- 第一行：输入的车辆名称
- 第二行：匹配到的最高分车型
- 第三行：匹配分数及详细得分说明
- 空一行

使用前需要更新索引：
    python -c "from rebuild_index import rebuild; rebuild()"
"""

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




def rebuild_index():
    """重建索引（如果词表更新了需要重建）"""
    print("=" * 60)
    print("重建车型库索引...")
    print("=" * 60)
    
    extractor = EntityExtractor("config/entity_rules.yaml")
    index = VehicleIndex(extractor)
    
    # 加载车型库
    df = pd.read_csv("data/力洋车型库精简5.csv")
    print(f"加载车型库: {len(df)} 条记录")
    
    # 构建索引
    index.build(df)
    
    # 保存索引
    index.save("index/vehicle_index.pkl")
    print("索引已保存到 index/vehicle_index.pkl")
    
    return extractor, index


def load_or_rebuild_index():
    """加载索引，如果不存在则重建"""
    extractor = EntityExtractor("config/entity_rules.yaml")
    index = VehicleIndex(extractor)
    
    index_path = Path("index/vehicle_index.pkl")
    if index_path.exists():
        print("加载现有索引...")
        index.load(str(index_path))
    else:
        print("索引不存在，需要重建...")
        return rebuild_index()
    
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
    if entities.displacement:
        extracted_info.append(f"排量={entities.displacement}")
    if entities.transmission:
        extracted_info.append(f"档位={entities.transmission}")
    if entities.trim:
        extracted_info.append(f"版式={entities.trim}")
    
    if extracted_info:
        breakdown.append(f"识别结果: [{', '.join(extracted_info)}]")
    
    return " | ".join(breakdown)


def batch_match(input_file: str, output_file: str, limit: int = None, column: str = None):
    """
    批量匹配
    
    Args:
        input_file: 输入CSV文件路径
        output_file: 输出文件路径
        limit: 限制处理数量（调试用）
        column: 车辆列名（可选，不指定则自动检测）
    """
    # 加载索引
    extractor, index = load_or_rebuild_index()
    engine = MatchingEngine(extractor, index)
    
    # 加载力洋车型库用于获取完整记录
    liyang_df = pd.read_csv("data/力洋车型库精简5.csv")
    liyang_dict = {}
    for _, row in liyang_df.iterrows():
        level_id = row.get('level_id', '')
        if level_id:
            liyang_dict[level_id] = ','.join(str(v) for v in row.values)
    
    # 读取输入数据
    print(f"\n读取输入数据: {input_file}")
    df = pd.read_csv(input_file)
    
    # 确定车辆列名
    if column:
        vehicle_col = column
    elif '车型' in df.columns:
        vehicle_col = '车型'  # 有辆成交价格.csv 格式
    else:
        vehicle_col = df.columns[0]  # 默认第一列
    
    print(f"总记录数: {len(df)}, 车辆列名: {vehicle_col}")
    
    if limit:
        df = df.head(limit)
        print(f"限制处理数量: {limit}")
    
    # 批量处理
    print(f"\n开始批量匹配...")
    start_time = datetime.now()
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"批量匹配结果 - 生成时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"输入文件: {input_file}\n")
        f.write(f"总记录数: {len(df)}\n")
        f.write("=" * 120 + "\n\n")
        
        match_count = 0
        no_match_count = 0
        
        for idx, row in df.iterrows():
            vehicle_name = str(row[vehicle_col]).strip()
            # 获取输入行的完整原始记录
            input_row_csv = ','.join(str(v) for v in row.values)
            
            # 跳过空行或"中升车源"等非车辆行
            if not vehicle_name or vehicle_name.startswith("中升车源") or len(vehicle_name) < 5:
                continue
            
            # 进度提示
            if (idx + 1) % 1000 == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                print(f"  已处理 {idx + 1}/{len(df)}... ({elapsed:.1f}s)")
            
            # 匹配
            result = engine.match(vehicle_name, top_k=1)
            entities = extractor.extract(vehicle_name)
            
            if result.matches:
                best = result.matches[0]
                match_count += 1
                
                # 构建匹配车型的完整名称
                info = best.vehicle_info
                matched_name = f"{info.get('brand', '')} {info.get('series', '')}  {info.get('year', '')}款 {info.get('sales_name', '')}"
                
                # 获取力洋库完整记录
                liyang_record = liyang_dict.get(best.level_id, '')
                
                # 输出格式: 【输入】输入名称 | 输入完整CSV行
                f.write(f"【输入】{vehicle_name} | {input_row_csv}\n")
                # 【匹配】匹配名称 (level_id) | 力洋库完整CSV行
                f.write(f"【匹配】{matched_name.strip()} (level_id: {best.level_id}) | {liyang_record}\n")
                # 【得分】得分明细
                f.write(f"【得分】{format_score_breakdown(result, entities)}\n")
            else:
                no_match_count += 1
                f.write(f"【输入】{vehicle_name} | {input_row_csv}\n")
                f.write(f"【匹配】无匹配结果\n")
                f.write(f"【得分】识别结果: 品牌={entities.brand}, 车系={entities.series}, 年款={entities.year}\n")
            
            f.write("\n")
            f.write("\n")
    
    # 统计
    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    
    print("\n" + "=" * 60)
    print("匹配完成！")
    print("=" * 60)
    print(f"总处理数: {match_count + no_match_count}")
    print(f"匹配成功: {match_count} ({100*match_count/(match_count+no_match_count):.1f}%)")
    print(f"匹配失败: {no_match_count}")
    print(f"处理时间: {elapsed:.1f}秒")
    print(f"输出文件: {output_file}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="批量匹配车辆到力洋车型库")
    parser.add_argument("--input", "-i", default="data/cheyipai_data_clean.csv",
                        help="输入CSV文件路径 (默认: data/cheyipai_data_clean.csv)")
    parser.add_argument("--output", "-o", default="output/cheyipai_match_result.txt",
                        help="输出文件路径 (默认: output/cheyipai_match_result.txt)")
    parser.add_argument("--limit", "-n", type=int, default=None,
                        help="限制处理数量（调试用）")
    parser.add_argument("--column", "-c", default=None,
                        help="车辆列名（默认自动检测：优先'车型'列，否则第一列）")
    parser.add_argument("--rebuild", "-r", action="store_true",
                        help="强制重建索引")
    
    args = parser.parse_args()
    
    # 确保输出目录存在
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 如果需要重建索引
    if args.rebuild:
        rebuild_index()
    
    # 批量匹配
    batch_match(args.input, args.output, args.limit, args.column)
