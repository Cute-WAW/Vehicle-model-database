
"""
全量模型重建脚本

功能：
1. 重建品牌车系模型 (Step 4)
2. 重建车辆类别模型 (Step 4)
3. 更新残值数据索引 (Step 5)

当 residual_value_data.csv 有新数据加入时，运行此脚本即可完成系统更新。
"""

import sys
import logging
from pathlib import Path
import argparse

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.build_brand_series_models_step4 import build_brand_series_models
from src.build_car_types_models_step4 import build_car_types_models
from src.model_paths import get_model_dirs
from src.residual_data_index_step5 import ResidualDataIndex

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='全量模型重建脚本')
    parser.add_argument('--min_samples', type=int, default=40, help='品牌车系最小样本数阈值')
    args = parser.parse_args()

    # 路径配置
    # data_file = project_root / 'output' / 'residual_value_data.csv'
    data_file = project_root / 'output' / 'merged_residual_value_data.csv'
    model_dirs = get_model_dirs(project_root)
    brand_series_model_dir = model_dirs['brand_series']
    car_types_model_dir = model_dirs['car_types']
    index_file = project_root / 'index' / 'residual_data_index.pkl'

    if not data_file.exists():
        logger.error(f"数据文件不存在: {data_file}")
        sys.exit(1)

    print("=" * 60)
    print("      车型库映射系统 - 全量模型重建")
    print("=" * 60)

    # 1. 重建品牌车系模型
    print("\n[Step 1/3] 重建品牌车系模型...")
    build_brand_series_models(
        data_path=str(data_file),
        output_dir=str(brand_series_model_dir),
        min_samples=args.min_samples, # 使用较低的阈值以覆盖更多车系
        iqr_factor=1.0
    )

    # 2. 重建车辆类别模型
    print("\n[Step 2/3] 重建车辆类别模型...")
    build_car_types_models(
        data_path=str(data_file),
        output_dir=str(car_types_model_dir),
        iqr_factor=1.0
    )

    # 3. 更新残值数据索引
    print("\n[Step 3/3] 更新残值数据索引...")
    try:
        index = ResidualDataIndex()
        # 强制重建索引
        index.build_from_csv(
            csv_path=str(data_file),
            index_path=str(index_file),
            force_rebuild=True
        )
        print(f"索引已更新: {index_file}")
        print(f"包含记录数: {len(index.records)}")
    except Exception as e:
        logger.error(f"索引更新失败: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✅ 所有模型和索引已更新完成！系统已就绪。")
    print("=" * 60)

if __name__ == "__main__":
    main()
