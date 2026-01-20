
import pandas as pd
import numpy as np
import os
from pathlib import Path

def analyze_cheyipai_results(csv_path: str):
    """
    分析车易拍数据的建模结果，生成业务分析报告
    """
    if not os.path.exists(csv_path):
        print(f"错误: 文件不存在 {csv_path}")
        return

    print(f"正在读取数据: {csv_path} ...")
    df = pd.read_csv(csv_path)
    
    # 基础数据清洗
    df['误差率'] = pd.to_numeric(df['误差率'], errors='coerce')
    df['使用年限'] = pd.to_numeric(df['使用年限'], errors='coerce')
    df['新车的价格'] = pd.to_numeric(df['新车的价格'], errors='coerce')
    df['二手车的成交价'] = pd.to_numeric(df['二手车的成交价'], errors='coerce')
    
    # 1. 整体概况
    total_count = len(df)
    valid_pred_count = df['预测值'].notna().sum()
    
    # 计算MAPE (平均绝对百分比误差)
    df['abs_error_pct'] = df['误差率'].abs()
    mape = df['abs_error_pct'].mean()
    
    # 计算准确率分布
    acc_5pct = (df['abs_error_pct'] <= 0.05).mean()
    acc_10pct = (df['abs_error_pct'] <= 0.10).mean()
    acc_20pct = (df['abs_error_pct'] <= 0.20).mean()

    print("\n" + "="*50)
    print("【车易拍新增数据业务分析报告】")
    print("="*50)
    
    print(f"\n1. 整体模型表现")
    print(f"   - 总样本量: {total_count} 条")
    print(f"   - 成功预测: {valid_pred_count} 条 ({valid_pred_count/total_count:.1%})")
    print(f"   - 平均误差 (MAPE): {mape:.2%}")
    print(f"   - 误差 ±5% 以内占比: {acc_5pct:.1%}")
    print(f"   - 误差 ±10% 以内占比: {acc_10pct:.1%}")
    print(f"   - 误差 ±20% 以内占比: {acc_20pct:.1%}")

    # 2. 品牌表现分析
    print(f"\n2. 品牌车系准确度分析 (Top 10 样本量)")
    # 按品牌分组计算
    brand_stats = df.groupby('品牌车系').agg({
        '车辆全称': 'count',
        'abs_error_pct': 'mean',
        '误差': 'mean' # 偏差方向
    }).reset_index()
    brand_stats.columns = ['品牌车系', '样本量', '平均误差率', '平均偏差(万)']
    
    # 筛选样本量 > 5 的品牌
    top_brands = brand_stats[brand_stats['样本量'] >= 5].sort_values('样本量', ascending=False).head(10)
    
    print(f"   {'品牌车系':<20} | {'样本量':<6} | {'平均误差率':<10} | {'平均偏差(万)':<10}")
    print("-" * 60)
    for _, row in top_brands.iterrows():
        print(f"   {row['品牌车系']:<20} | {row['样本量']:<6} | {row['平均误差率']:.2%}     | {row['平均偏差(万)']:.2f}")

    # 3. 车辆类别分析
    print(f"\n3. 不同车型保值率分析")
    # 计算实际保值率
    df['实际保值率'] = df['二手车的成交价'] / df['新车的价格']
    
    type_stats = df.groupby('车辆小类').agg({
        '车辆全称': 'count',
        '实际保值率': 'mean',
        'abs_error_pct': 'mean'
    }).reset_index()
    type_stats.columns = ['车辆小类', '样本量', '实际保值率', 'abs_error_pct']
    type_stats = type_stats.sort_values('实际保值率', ascending=False)
    
    print(f"   {'车辆类别':<10} | {'样本量':<6} | {'平均保值率':<10} | {'模型误差率':<10}")
    print("-" * 55)
    for _, row in type_stats.iterrows():
        if row['样本量'] > 10: # 只显示样本足够的类别
            print(f"   {row['车辆小类']:<10} | {row['样本量']:<6} | {row['实际保值率']:.1%}      | {row['abs_error_pct']:.2%}")

    # 4. 异常案例 (误差最大的Top 3)
    print(f"\n4. 重点关注异常案例 (Top 3 偏差)")
    bad_cases = df.sort_values('abs_error_pct', ascending=False).head(3)
    for _, row in bad_cases.iterrows():
        print(f"   - 车型: {row['车辆全称']}")
        print(f"     实际: {row['二手车的成交价']}万, 预测: {row['预测值']}万")
        print(f"     误差: {row['误差率']:.1%} (偏差 {row['误差']}万)")
        print(f"     原因线索: {row['城市']}, 里程{row['行驶里程']}万公里, {row['使用年限']}年车")
        print("")

    # 5. 车龄保值率曲线
    print(f"\n5. 车龄-保值率概览 (0-10年)")
    # 将车龄分段
    df['age_group'] = pd.cut(df['使用年限'], bins=[0, 1, 3, 5, 8, 10, 20], labels=['0-1年', '1-3年', '3-5年', '5-8年', '8-10年', '10年以上'])
    age_stats = df.groupby('age_group').agg({
        '实际保值率': 'mean',
        '车辆全称': 'count'
    }).reset_index()
    age_stats.columns = ['车龄段', '实际保值率', '样本量']
    
    print(f"   {'车龄段':<10} | {'样本量':<6} | {'平均保值率'}")
    for _, row in age_stats.iterrows():
        if row['样本量'] > 0:
            print(f"   {row['车龄段']:<10} | {row['样本量']:<6} | {row['实际保值率']:.1%}")

if __name__ == '__main__':
    # 路径根据实际情况调整
    csv_file = '../output/batch_modeling_results.csv'
    analyze_cheyipai_results(csv_file)
