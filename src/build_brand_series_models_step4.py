"""
品牌车系批量建模脚本

功能：
1. 读取残值率数据
2. 筛选样本数>100的品牌车系
3. 批量训练模型并保存

使用方法：
    python build_brand_series_models.py
    python build_brand_series_models.py --min_samples 50  # 自定义样本阈值
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict

from batch_model_trainer_step4 import BatchModelTrainer, ResidualValueModel, safe_filename


def build_brand_series_models(
    data_path: str,
    output_dir: str,
    min_samples: int = 100,
    iqr_factor: float = 1.0
) -> Dict[str, any]:
    """
    批量训练品牌车系模型
    
    Args:
        data_path: 数据文件路径
        output_dir: 模型输出目录
        min_samples: 最小样本数阈值
        iqr_factor: IQR 过滤系数
        
    Returns:
        训练报告字典
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("品牌车系批量建模程序")
    print("=" * 60)
    print(f"数据文件: {data_path}")
    print(f"输出目录: {output_dir}")
    print(f"最小样本数: {min_samples}")
    print(f"IQR 系数: {iqr_factor}")
    print("=" * 60)
    
    # 初始化训练器
    trainer = BatchModelTrainer(data_path, min_samples=min_samples, iqr_factor=iqr_factor)
    
    # 获取品牌车系分组
    groups = trainer.get_brand_series_groups()
    total = len(groups)
    
    print(f"\n开始训练 {total} 个品牌车系模型...\n")
    
    # 统计信息
    success_count = 0
    fail_count = 0
    success_models = []
    failed_series = []
    all_clean_data = []  # 收集有效数据
    
    for idx, (series_name, group_df) in enumerate(groups.items(), 1):
        print(f"[{idx}/{total}] 正在训练: {series_name} (样本数: {len(group_df)})")
        
        try:
            model, df_clean = trainer.train_for_group(group_df, series_name)
            
            if model:
                # 保存模型
                filename = safe_filename(series_name) + '.pkl'
                model_path = output_path / filename
                model.save(str(model_path))
                
                # 收集用于建模的清洗后数据
                all_clean_data.append(df_clean)
                
                success_count += 1
                success_models.append({
                    'name': series_name,
                    'model_type': model.model_type,
                    'r2': model.r2,
                    'sample_count': model.sample_count,
                    'file': filename
                })
                print(f"    ✓ 成功: {model.model_type}, R²={model.r2:.4f}")
            else:
                fail_count += 1
                failed_series.append(series_name)
                print(f"    ✗ 失败: 无有效模型")
        except Exception as e:
            fail_count += 1
            failed_series.append(series_name)
            print(f"    ✗ 异常: {str(e)}")
    
    # 保存参与建模的数据
    if all_clean_data:
        import pandas as pd
        clean_data_path = output_path.parent.parent / 'output' / 'residual_value_data_for_build_model.csv'
        print(f"\n正在保存参与建模的数据至: {clean_data_path}")
        pd.concat(all_clean_data, ignore_index=True).to_csv(clean_data_path, index=False)

    # 生成报告
    report = {
        'total': total,
        'success': success_count,
        'failed': fail_count,
        'success_rate': f"{success_count/total*100:.1f}%",
        'models': success_models,
        'failed_series': failed_series,
        'timestamp': datetime.now().isoformat()
    }
    
    # 打印汇总
    print("\n" + "=" * 60)
    print("训练完成汇总")
    print("=" * 60)
    print(f"总计: {total} 个品牌车系")
    print(f"成功: {success_count} 个 ({success_count/total*100:.1f}%)")
    print(f"失败: {fail_count} 个")
    
    if success_models:
        # R2 分布统计
        r2_values = [m['r2'] for m in success_models]
        print(f"\nR² 分布:")
        print(f"  最小: {min(r2_values):.4f}")
        print(f"  最大: {max(r2_values):.4f}")
        print(f"  平均: {sum(r2_values)/len(r2_values):.4f}")
        
        # 前10个模型
        print(f"\n前10个模型（按R²排序）:")
        top_models = sorted(success_models, key=lambda x: x['r2'], reverse=True)[:10]
        for m in top_models:
            print(f"  {m['name']}: {m['model_type']}, R²={m['r2']:.4f}, 样本={m['sample_count']}")
    
    if failed_series:
        print(f"\n失败的车系:")
        for s in failed_series[:10]:
            print(f"  - {s}")
        if len(failed_series) > 10:
            print(f"  ... 还有 {len(failed_series) - 10} 个")
    
    print(f"\n模型已保存到: {output_dir}")
    
    return report


def main():
    parser = argparse.ArgumentParser(description='品牌车系批量建模程序')
    parser.add_argument('--data', default='../output/residual_value_data.csv', help='数据文件路径')
    parser.add_argument('--output', default='../price_model/brand_series_model', help='模型输出目录')
    parser.add_argument('--min_samples', type=int, default=100, help='最小样本数阈值')
    parser.add_argument('--iqr_factor', type=float, default=1.0, help='IQR过滤系数')
    
    args = parser.parse_args()
    
    # 处理相对路径
    script_dir = Path(__file__).parent
    data_path = args.data if Path(args.data).is_absolute() else str(script_dir / args.data)
    output_dir = args.output if Path(args.output).is_absolute() else str(script_dir / args.output)
    
    # 检查数据文件
    if not Path(data_path).exists():
        print(f"错误: 数据文件不存在: {data_path}")
        sys.exit(1)
    
    # 执行建模
    report = build_brand_series_models(
        data_path=data_path,
        output_dir=output_dir,
        min_samples=args.min_samples,
        iqr_factor=args.iqr_factor
    )
    
    print("\n建模程序执行完成！")


if __name__ == '__main__':
    main()
