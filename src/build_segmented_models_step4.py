"""
分段模型训练脚本 (方案三)

功能：
1. 将数据按车龄分为 3 段：[0.5, 5), [5, 10), [10, 20]
2. 每个品牌车系在每个车龄段独立训练模型
3. 预测时根据车龄选择对应分段模型

使用方法：
    cd d:/antigravity/price_evaluation/车型库映射/src
    python build_segmented_models_step4.py
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
import pandas as pd

from batch_model_trainer_step4 import BatchModelTrainer, ResidualValueModel, safe_filename
from model_paths import get_model_dirs


# 车龄分段定义
AGE_SEGMENTS = [
    (0.5, 5.0, 'young'),   # 新车段
    (5.0, 10.0, 'mid'),    # 中龄段
    (10.0, 20.0, 'old'),   # 老车段
]


def build_segmented_models(
    data_path: str,
    output_dir: str,
    min_samples_per_segment: int = 30,
    iqr_factor: float = 1.0
) -> Dict[str, any]:
    """
    构建分段模型
    
    Args:
        data_path: 数据文件路径
        output_dir: 模型输出目录
        min_samples_per_segment: 每个分段的最小样本数
        iqr_factor: IQR 过滤系数
        
    Returns:
        训练报告字典
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("分段模型训练程序 (方案三)")
    print("=" * 60)
    print(f"数据文件: {data_path}")
    print(f"输出目录: {output_dir}")
    print(f"分段定义: {AGE_SEGMENTS}")
    print(f"每段最小样本数: {min_samples_per_segment}")
    print("=" * 60)
    
    # 加载数据
    df = pd.read_csv(data_path)
    print(f"总记录数: {len(df)}")
    
    # 初始化训练器 (用于数据清洗和模型训练)
    trainer = BatchModelTrainer(data_path, min_samples=10, iqr_factor=iqr_factor)
    
    # 统计
    success_count = 0
    fail_count = 0
    segment_stats = {seg[2]: {'success': 0, 'fail': 0} for seg in AGE_SEGMENTS}
    
    # 获取所有品牌车系
    brand_series_list = df['品牌车系'].value_counts()
    # 只处理样本数>=100的品牌车系（确保有足够数据分段）
    brand_series_list = brand_series_list[brand_series_list >= 100].index.tolist()
    total_series = len(brand_series_list)
    
    print(f"\n开始为 {total_series} 个品牌车系训练分段模型...\n")
    
    for idx, series_name in enumerate(brand_series_list, 1):
        if idx % 50 == 0:
            print(f"进度: {idx}/{total_series}")
        
        series_df = df[df['品牌车系'] == series_name]
        
        for low, high, seg_name in AGE_SEGMENTS:
            # 筛选该分段的数据
            segment_df = series_df[
                (series_df['使用年限'] >= low) & 
                (series_df['使用年限'] < high)
            ]
            
            if len(segment_df) < min_samples_per_segment:
                # 样本不足，跳过
                continue
            
            try:
                model, df_clean = trainer.train_for_group(segment_df, f"{series_name}_{seg_name}")
                
                if model:
                    # 保存模型，文件名格式: 品牌-车系_seg_young.pkl
                    filename = safe_filename(series_name) + f'_seg_{seg_name}.pkl'
                    model_path = output_path / filename
                    model.save(str(model_path))
                    
                    success_count += 1
                    segment_stats[seg_name]['success'] += 1
                else:
                    fail_count += 1
                    segment_stats[seg_name]['fail'] += 1
            except Exception as e:
                fail_count += 1
                segment_stats[seg_name]['fail'] += 1
    
    # 打印汇总
    print("\n" + "=" * 60)
    print("分段模型训练完成")
    print("=" * 60)
    print(f"成功: {success_count} 个模型")
    print(f"失败: {fail_count} 个")
    print("\n各分段统计:")
    for seg_name, stats in segment_stats.items():
        print(f"  {seg_name}: 成功 {stats['success']}, 失败 {stats['fail']}")
    
    print(f"\n模型已保存到: {output_dir}")
    
    return {
        'success': success_count,
        'failed': fail_count,
        'segment_stats': segment_stats
    }


def main():
    parser = argparse.ArgumentParser(description='分段模型训练程序')
    parser.add_argument('--data', default='../output/merged_residual_value_data_with_dates.csv', help='数据文件路径')
    parser.add_argument('--output', default=str(get_model_dirs(Path(__file__).parent.parent)['segmented']), help='模型输出目录')
    parser.add_argument('--min_samples', type=int, default=30, help='每段最小样本数')
    parser.add_argument('--iqr_factor', type=float, default=1.0, help='IQR过滤系数')
    
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    data_path = args.data if Path(args.data).is_absolute() else str(script_dir / args.data)
    output_dir = str(Path(args.output).resolve())
    
    if not Path(data_path).exists():
        print(f"错误: 数据文件不存在: {data_path}")
        sys.exit(1)
    
    build_segmented_models(
        data_path=data_path,
        output_dir=output_dir,
        min_samples_per_segment=args.min_samples,
        iqr_factor=args.iqr_factor
    )
    
    print("\n分段模型训练完成！")


if __name__ == '__main__':
    main()
