
import pandas as pd
import numpy as np
import os
import logging
from pathlib import Path
from typing import Dict, List, Tuple
from price_predictor_step5 import PricePredictor

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def evaluate_models_performance(data_path: str):
    """
    评估新训练模型在数据集上的性能
    
    Args:
        data_path: 包含真实成交数据的CSV文件路径
    """
    if not os.path.exists(data_path):
        logger.error(f"数据文件不存在: {data_path}")
        return

    logger.info(f"正在读取数据: {data_path}")
    df = pd.read_csv(data_path)
    
    # 初始化预测器
    predictor = PricePredictor()
    
    # 统计变量
    results = []
    
    # 遍历每条数据进行预测
    total = len(df)
    logger.info(f"开始评估 {total} 条数据...")
    
    for idx, row in df.iterrows():
        # 获取车辆信息
        brand_series = row['品牌车系']
        
        # 构建车辆类别名称 (按照 build_car_types_models_step4.py 的逻辑)
        # 假设列名存在，如果不存在则尝试拼接
        if '车辆类别' in row:
            car_type = row['车辆类别']
        else:
            # 兼容 batch_modeling_results.csv 的列名
            v_type = row.get('车辆大类', '')
            v_subtype = row.get('车辆小类', '')
            v_attr = row.get('车辆属性', '')
            car_type = f"{v_type}-{v_subtype}-{v_attr}"
            
        year = float(row['使用年限'])
        new_price = float(row['新车的价格'])
        actual_price = float(row['二手车的成交价'])
        
        if pd.isna(year) or pd.isna(new_price) or pd.isna(actual_price):
            continue
            
        if year <= 0 or new_price <= 0:
            continue
            
        # 1. 尝试使用品牌车系模型预测
        bs_res = predictor.predict_by_brand_series(brand_series, year, new_price)
        
        # 2. 尝试使用车辆类别模型预测
        ct_res = predictor.predict_by_car_type(car_type, year, new_price)
        
        # 记录结果
        results.append({
            'brand_series': brand_series,
            'car_type': car_type,
            'actual_price': actual_price,
            'bs_pred': bs_res.predicted_price if bs_res.success else None,
            'bs_model_type': bs_res.model_type if bs_res.success else None,
            'ct_pred': ct_res.predicted_price if ct_res.success else None,
            'ct_model_type': ct_res.model_type if ct_res.success else None
        })
        
        if (idx + 1) % 100 == 0:
            print(f"进度: {idx + 1}/{total}", end='\r')
            
    print(f"进度: {total}/{total}")
    
    # 转换为DataFrame进行分析
    res_df = pd.DataFrame(results)
    
    # 计算误差
    # 品牌车系模型误差
    bs_valid = res_df.dropna(subset=['bs_pred'])
    if not bs_valid.empty:
        bs_mae = np.mean(np.abs(bs_valid['bs_pred'] - bs_valid['actual_price']))
        bs_mape = np.mean(np.abs((bs_valid['bs_pred'] - bs_valid['actual_price']) / bs_valid['actual_price']))
        bs_r2 = 1 - np.sum((bs_valid['bs_pred'] - bs_valid['actual_price'])**2) / np.sum((bs_valid['actual_price'] - np.mean(bs_valid['actual_price']))**2)
    else:
        bs_mae, bs_mape, bs_r2 = 0, 0, 0
        
    # 车辆类别模型误差
    ct_valid = res_df.dropna(subset=['ct_pred'])
    if not ct_valid.empty:
        ct_mae = np.mean(np.abs(ct_valid['ct_pred'] - ct_valid['actual_price']))
        ct_mape = np.mean(np.abs((ct_valid['ct_pred'] - ct_valid['actual_price']) / ct_valid['actual_price']))
        ct_r2 = 1 - np.sum((ct_valid['ct_pred'] - ct_valid['actual_price'])**2) / np.sum((ct_valid['actual_price'] - np.mean(ct_valid['actual_price']))**2)
    else:
        ct_mae, ct_mape, ct_r2 = 0, 0, 0
        
    # 输出报告
    print("\n" + "="*60)
    print("【新模型性能评估报告】")
    print("="*60)
    
    print(f"\n1. 品牌车系模型 (覆盖率: {len(bs_valid)/total:.1%})")
    print(f"   - 可预测样本: {len(bs_valid)}")
    print(f"   - 平均绝对误差 (MAE): {bs_mae:.2f} 万元")
    print(f"   - 平均相对误差 (MAPE): {bs_mape:.2%} (越低越好)")
    print(f"   - 决定系数 (R²): {bs_r2:.4f} (越接近1越好)")
    
    print(f"\n2. 车辆类别模型 (覆盖率: {len(ct_valid)/total:.1%})")
    print(f"   - 可预测样本: {len(ct_valid)}")
    print(f"   - 平均绝对误差 (MAE): {ct_mae:.2f} 万元")
    print(f"   - 平均相对误差 (MAPE): {ct_mape:.2%}")
    print(f"   - 决定系数 (R²): {ct_r2:.4f}")
    
    # 3. 详细模型分析 (Top 5 品牌)
    print(f"\n3. 重点品牌模型性能 (Top 5 样本量)")
    if not bs_valid.empty:
        bs_valid['abs_pct_err'] = np.abs((bs_valid['bs_pred'] - bs_valid['actual_price']) / bs_valid['actual_price'])
        
        brand_stats = bs_valid.groupby('brand_series').agg({
            'actual_price': 'count',
            'abs_pct_err': 'mean',
            'bs_model_type': 'first'
        }).reset_index()
        brand_stats.columns = ['品牌车系', '样本量', 'MAPE', '模型类型']
        
        top_brands = brand_stats.sort_values('样本量', ascending=False).head(5)
        
        print(f"   {'品牌车系':<20} | {'样本量':<6} | {'MAPE':<10} | {'模型类型'}")
        print("-" * 65)
        for _, row in top_brands.iterrows():
            print(f"   {row['品牌车系']:<20} | {row['样本量']:<6} | {row['MAPE']:.2%}     | {row['模型类型']}")

    # 4. 混合策略效果 (模拟真实场景：优先品牌，兜底类别)
    print(f"\n4. 混合策略效果 (真实应用场景)")
    res_df['final_pred'] = res_df['bs_pred'].fillna(res_df['ct_pred'])
    final_valid = res_df.dropna(subset=['final_pred'])
    
    final_mape = np.mean(np.abs((final_valid['final_pred'] - final_valid['actual_price']) / final_valid['actual_price']))
    final_r2 = 1 - np.sum((final_valid['final_pred'] - final_valid['actual_price'])**2) / np.sum((final_valid['actual_price'] - np.mean(final_valid['actual_price']))**2)
    
    print(f"   - 综合覆盖率: {len(final_valid)/total:.1%}")
    print(f"   - 综合 MAPE: {final_mape:.2%}")
    print(f"   - 综合 R²: {final_r2:.4f}")

if __name__ == '__main__':
    # 路径根据实际情况调整
    csv_file = '../output/batch_modeling_results.csv'
    evaluate_models_performance(csv_file)
