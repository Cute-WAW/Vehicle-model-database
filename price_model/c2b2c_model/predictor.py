#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
C2B2C 价格预测器模块

用于加载已训练的多项式回归模型并进行价格预测。
模型保存位置：price_model/c2b2c_model/

作者：Antigravity
日期：2025-12-31
"""

import os
import json
import pickle
import numpy as np


class C2B2CPricePredictor:
    """
    C2B2C 价格预测器
    
    根据 b2BPrices.b.mid 预测完整的价格结构
    支持 b2BPrices, b2CPrices, c2BPrices
    """
    
    def __init__(self, model_dir: str = None):
        """
        初始化预测器
        
        Args:
            model_dir: 模型目录路径，默认为 price_model/c2b2c_model
        """
        if model_dir is None:
            # 默认路径：相对于当前文件
            current_dir = os.path.dirname(os.path.abspath(__file__))
            model_dir = os.path.join(os.path.dirname(current_dir), 'price_model', 'c2b2c_model')
        
        self.model_dir = model_dir
        self.models = {}
        self.poly = None
        self.degree = 3
        self.price_columns = []
        self._loaded = False
    
    def load(self) -> bool:
        """
        加载模型参数
        
        Returns:
            bool: 是否加载成功
        """
        try:
            # 加载配置
            config_path = os.path.join(self.model_dir, 'config.json')
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            self.degree = config['degree']
            self.price_columns = config['columns']
            
            # 加载多项式转换器
            poly_path = os.path.join(self.model_dir, 'poly_transformer.pkl')
            with open(poly_path, 'rb') as f:
                self.poly = pickle.load(f)
            
            # 加载各价格点的回归模型
            models_path = os.path.join(self.model_dir, 'regression_models.pkl')
            with open(models_path, 'rb') as f:
                self.models = pickle.load(f)
            
            self._loaded = True
            return True
        
        except Exception as e:
            print(f"加载模型失败: {e}")
            self._loaded = False
            return False
    
    def predict(self, b2b_b_mid: float) -> dict:
        """
        根据 b2BPrices.b.mid 预测完整价格结构
        
        Args:
            b2b_b_mid: 车商B级车况中间价格（万元）
        
        Returns:
            dict: 包含 b2BPrices, b2CPrices, c2BPrices 的完整价格字典
                  所有价格值为字符串格式，保留2位小数
        """
        if not self._loaded:
            if not self.load():
                raise RuntimeError("模型未加载，请先调用 load() 方法")
        
        # 多项式特征转换
        X = np.array([[b2b_b_mid]])
        X_poly = self.poly.transform(X)
        
        # 预测各价格点
        flat_result = {}
        for col in self.price_columns:
            pred = self.models[col].predict(X_poly)[0]
            flat_result[col] = pred
        
        # 转换为嵌套结构
        structured = {
            'b2BPrices': {'a': {}, 'b': {}, 'c': {}},
            'b2CPrices': {'a': {}, 'b': {}, 'c': {}},
            'c2BPrices': {'a': {}, 'b': {}, 'c': {}}
        }
        
        for key, value in flat_result.items():
            parts = key.split('.')
            if len(parts) == 3:
                price_type, condition, level = parts
                if price_type in structured:
                    # 格式化为字符串，保留2位小数
                    structured[price_type][condition][level] = f"{value:.2f}"
        
        return structured
    
    def predict_numeric(self, b2b_b_mid: float) -> dict:
        """
        预测并返回数值格式（float）
        
        Args:
            b2b_b_mid: 车商B级车况中间价格（万元）
        
        Returns:
            dict: 价格值为float类型
        """
        if not self._loaded:
            if not self.load():
                raise RuntimeError("模型未加载")
        
        X = np.array([[b2b_b_mid]])
        X_poly = self.poly.transform(X)
        
        flat_result = {}
        for col in self.price_columns:
            pred = self.models[col].predict(X_poly)[0]
            flat_result[col] = round(pred, 2)
        
        structured = {
            'b2BPrices': {'a': {}, 'b': {}, 'c': {}},
            'b2CPrices': {'a': {}, 'b': {}, 'c': {}},
            'c2BPrices': {'a': {}, 'b': {}, 'c': {}}
        }
        
        for key, value in flat_result.items():
            parts = key.split('.')
            if len(parts) == 3:
                price_type, condition, level = parts
                if price_type in structured:
                    structured[price_type][condition][level] = value
        
        return structured


def get_predictor(model_dir: str = None) -> C2B2CPricePredictor:
    """
    获取已加载的预测器实例
    
    Args:
        model_dir: 模型目录路径
    
    Returns:
        C2B2CPricePredictor: 已加载的预测器
    """
    predictor = C2B2CPricePredictor(model_dir)
    predictor.load()
    return predictor


if __name__ == "__main__":
    # 测试
    predictor = C2B2CPricePredictor()
    if predictor.load():
        result = predictor.predict(2.24)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("请先运行 c2b2c_price_model_save_model.py 保存模型")
