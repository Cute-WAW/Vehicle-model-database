"""
精真估(JZG) vs 我方系统 对比分析脚本

功能：
1. 随机抽取500辆车
2. 同时使用我方算法和精真估接口进行估价
3. 对比各维度的命中率
"""

import pandas as pd
import numpy as np
import json
import sys
import os
import requests
from pathlib import Path
from datetime import datetime

# 添加src目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
os.chdir(Path(__file__).parent.parent)

from residual_predictor_step5 import ResidualPredictor


def parse_jzg_result(jzg_json_str: str) -> dict:
    """解析精真估返回结果"""
    if not jzg_json_str:
        return None
    try:
        data = json.loads(jzg_json_str)
        if data.get('Code') == 0 and data.get('Result'):
            result = data['Result']
            return {
                'b2BPrices': result.get('b2BPrices', {}),
                'b2CPrices': result.get('b2CPrices', {}),
                'c2BPrices': result.get('c2BPrices', {})
            }
    except:
        pass
    return None


def check_in_range(actual: float, price_data: dict, grade: str = 'b') -> bool:
    """检查实际价格是否在区间内"""
    if not price_data:
        return None
    
    grade_key = {'优': 'a', '中': 'b', '差': 'c'}.get(grade, 'b')
    prices = price_data.get(grade_key, {})
    
    low = prices.get('low')
    high = prices.get('up')
    
    if low is None or high is None:
        return None
    
    return float(low) <= actual <= float(high)


def main():
    print("=" * 60)
    print("精真估 vs 我方系统 对比分析")
    print(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 加载已有的精真估结果
    print("\n[1] 加载精真估API结果...")
    jzg_df = pd.read_csv('data/jzg_results_merged_success.csv')
    print(f"  精真估有效结果: {len(jzg_df)} 条")
    
    # 加载我方数据
    print("\n[2] 加载我方成交数据...")
    our_df = pd.read_csv('output/residual_value_data_for_build_model.csv', on_bad_lines='skip')
    print(f"  我方数据总量: {len(our_df)} 条")
    
    # 初始化预测器
    print("\n[3] 初始化我方预测器...")
    predictor = ResidualPredictor(residual_data_csv='output/residual_value_data_for_build_model.csv')
    
    # 随机抽取500条进行对比
    sample_size = min(500, len(jzg_df))
    sample_df = jzg_df.sample(n=sample_size, random_state=123).reset_index(drop=True)
    print(f"\n[4] 随机抽样 {sample_size} 条进行对比...")
    
    # 解析精真估结果
    results = []
    jzg_valid = 0
    our_valid = 0
    both_valid = 0
    
    for idx, row in sample_df.iterrows():
        jzg_data = parse_jzg_result(row.get('jzg_result', ''))
        
        if jzg_data:
            jzg_valid += 1
            # 获取B2B价格区间
            jzg_b2b = jzg_data.get('b2BPrices', {})
            
            results.append({
                'index': idx,
                'jzg_b2b_a_low': jzg_b2b.get('a', {}).get('low'),
                'jzg_b2b_a_mid': jzg_b2b.get('a', {}).get('mid'),
                'jzg_b2b_a_up': jzg_b2b.get('a', {}).get('up'),
                'jzg_b2b_b_low': jzg_b2b.get('b', {}).get('low'),
                'jzg_b2b_b_mid': jzg_b2b.get('b', {}).get('mid'),
                'jzg_b2b_b_up': jzg_b2b.get('b', {}).get('up'),
                'jzg_b2b_c_low': jzg_b2b.get('c', {}).get('low'),
                'jzg_b2b_c_mid': jzg_b2b.get('c', {}).get('mid'),
                'jzg_b2b_c_up': jzg_b2b.get('c', {}).get('up'),
                'jzg_valid': True
            })
        else:
            results.append({
                'index': idx,
                'jzg_valid': False
            })
        
        if (idx + 1) % 100 == 0:
            print(f"  已处理 {idx + 1}/{sample_size}...")
    
    results_df = pd.DataFrame(results)
    
    # 统计
    print("\n" + "=" * 60)
    print("[5] 统计结果")
    print("=" * 60)
    
    jzg_valid_df = results_df[results_df['jzg_valid'] == True]
    
    print(f"\n精真估API统计:")
    print(f"  样本总数: {sample_size}")
    print(f"  有效返回: {len(jzg_valid_df)} ({len(jzg_valid_df)/sample_size*100:.1f}%)")
    print(f"  无效/空返回: {sample_size - len(jzg_valid_df)}")
    
    # 保存结果
    results_df.to_csv('experiment/jzg_comparison_results.csv', index=False, encoding='utf-8-sig')
    print(f"\n已保存: experiment/jzg_comparison_results.csv")
    
    # 分析价格区间宽度
    if len(jzg_valid_df) > 0:
        print("\n精真估价格区间统计 (B2B-中等评级):")
        jzg_valid_df = jzg_valid_df.copy()
        jzg_valid_df['jzg_range'] = jzg_valid_df['jzg_b2b_b_up'].astype(float) - jzg_valid_df['jzg_b2b_b_low'].astype(float)
        print(f"  平均区间宽度: {jzg_valid_df['jzg_range'].mean():.2f}万")
        print(f"  最小区间: {jzg_valid_df['jzg_range'].min():.2f}万")
        print(f"  最大区间: {jzg_valid_df['jzg_range'].max():.2f}万")
    
    print("\n" + "=" * 60)
    print("对比分析完成!")
    print("=" * 60)
    print("\n注意: 由于缺少匹配的车辆信息，无法直接计算命中率对比。")
    print("请确保有完整的车辆信息(VIN、上牌日期、里程等)以进行完整对比。")


if __name__ == '__main__':
    main()
