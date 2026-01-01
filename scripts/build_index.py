"""
索引构建脚本
"""
import sys
import argparse
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
from src.entity_extractor import EntityExtractor
from src.vehicle_index import VehicleIndex


def main():
    parser = argparse.ArgumentParser(description='构建车型库索引')
    parser.add_argument('--input', type=str, default='data/力洋车型库精简5.csv',
                       help='车型库 CSV 文件路径')
    parser.add_argument('--output', type=str, default='index/vehicle_index.pkl',
                       help='索引输出路径')
    parser.add_argument('--config', type=str, default='config/entity_rules.yaml',
                       help='实体识别配置文件路径')
    
    args = parser.parse_args()
    
    # 切换到项目目录
    import os
    os.chdir(project_root)
    
    print(f"加载车型库: {args.input}")
    df = pd.read_csv(args.input)
    print(f"共 {len(df)} 条记录")
    
    print(f"\n初始化实体识别器...")
    extractor = EntityExtractor(args.config)
    
    print(f"\n构建索引...")
    index = VehicleIndex(extractor)
    index.build(df)
    
    print(f"\n保存索引到: {args.output}")
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    index.save(args.output)
    
    print("\n索引统计:")
    print(f"  品牌数: {len(index.brand_index)}")
    print(f"  车系数: {len(index.series_index)}")
    print(f"  特征数: {len(index.feature_index)}")
    print(f"  车型数: {len(index.detail_store)}")


if __name__ == "__main__":
    main()
