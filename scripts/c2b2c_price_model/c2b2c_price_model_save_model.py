#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模型保存脚本

训练多项式回归模型(degree=3)并保存到 price_model/c2b2c_model 目录

作者：Antigravity
日期：2025-12-31
"""

import os
import sys
import json
import pickle
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures

# 添加脚本目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from c2b2c_price_model_analysis import load_and_parse_data


def save_polynomial_model(prices_df: pd.DataFrame, model_dir: str, degree: int = 3):
    """
    训练并保存多项式回归模型
    
    Args:
        prices_df: 价格数据DataFrame
        model_dir: 模型保存目录
        degree: 多项式阶数
    """
    # 确保目录存在
    os.makedirs(model_dir, exist_ok=True)
    
    base_col = 'b2BPrices.b.mid'
    X = prices_df[[base_col]].values
    
    # 创建多项式特征
    poly = PolynomialFeatures(degree=degree)
    X_poly = poly.fit_transform(X)
    
    # 训练每个价格点的回归模型
    models = {}
    columns = list(prices_df.columns)
    
    for col in columns:
        model = LinearRegression()
        y = prices_df[col].values
        model.fit(X_poly, y)
        models[col] = model
    
    # 保存配置
    config = {
        'degree': degree,
        'columns': columns,
        'base_column': base_col,
        'sample_count': len(prices_df),
        'version': '1.0'
    }
    
    config_path = os.path.join(model_dir, 'config.json')
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"已保存配置: {config_path}")
    
    # 保存多项式转换器
    poly_path = os.path.join(model_dir, 'poly_transformer.pkl')
    with open(poly_path, 'wb') as f:
        pickle.dump(poly, f)
    print(f"已保存多项式转换器: {poly_path}")
    
    # 保存回归模型
    models_path = os.path.join(model_dir, 'regression_models.pkl')
    with open(models_path, 'wb') as f:
        pickle.dump(models, f)
    print(f"已保存回归模型: {models_path}")
    
    print(f"\n模型保存完成！")
    print(f"  - 多项式阶数: {degree}")
    print(f"  - 价格点数量: {len(columns)}")
    print(f"  - 训练样本数: {len(prices_df)}")


def main():
    # 路径配置
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(os.path.dirname(script_dir))  # 车型库映射目录
    data_dir = os.path.join(base_dir, 'data')
    model_dir = os.path.join(base_dir, 'price_model', 'c2b2c_model')
    
    csv_path = os.path.join(data_dir, 'jzg_results_merged_success.csv')
    
    print("=" * 60)
    print("多项式回归模型训练与保存")
    print("=" * 60)
    
    # 加载数据
    print(f"\n加载数据: {csv_path}")
    prices_df = load_and_parse_data(csv_path)
    
    # 训练并保存模型
    print(f"\n保存模型目录: {model_dir}")
    save_polynomial_model(prices_df, model_dir, degree=3)
    
    # 验证加载
    print("\n" + "=" * 60)
    print("验证模型加载")
    print("=" * 60)
    
    # 导入预测器
    sys.path.insert(0, model_dir)
    from predictor import C2B2CPricePredictor
    
    predictor = C2B2CPricePredictor(model_dir)
    if predictor.load():
        result = predictor.predict(2.24)
        print(f"\n测试预测 (b2BPrices.b.mid = 2.24):")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("\n模型验证成功！")
    else:
        print("模型验证失败！")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
