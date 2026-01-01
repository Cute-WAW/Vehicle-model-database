#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
二手车价格预测模型分析脚本

目标：根据 b2BPrices.b.mid 预测完整的价格结构
数据源：jzg_results_merged_success.csv

作者：Antigravity
日期：2025-12-31
"""

import pandas as pd
import numpy as np
import json
import os
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# 第一部分：数据解析
# ============================================================

def parse_jzg_result(json_str: str) -> dict:
    """
    解析jzg_result JSON字符串，提取价格数据
    
    Returns:
        dict: 包含所有价格点的字典，key为 'b2BPrices.a.low' 格式
    """
    try:
        if not isinstance(json_str, str):
            return {}
        
        # 尝试直接解析
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # 备用：处理可能的双引号转义
            cleaned = json_str.replace('""', '"')
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]
            data = json.loads(cleaned)
        
        result = data.get('Result', {})
        
        prices = {}
        price_types = ['b2BPrices', 'b2CPrices', 'c2BPrices']
        conditions = ['a', 'b', 'c']
        levels = ['low', 'mid', 'up']
        
        for pt in price_types:
            if pt in result:
                for cond in conditions:
                    if cond in result[pt]:
                        for level in levels:
                            if level in result[pt][cond]:
                                key = f"{pt}.{cond}.{level}"
                                try:
                                    prices[key] = float(result[pt][cond][level])
                                except (ValueError, TypeError):
                                    prices[key] = None
        
        return prices
    except (json.JSONDecodeError, TypeError, KeyError, AttributeError) as e:
        return {}


def load_and_parse_data(csv_path: str) -> pd.DataFrame:
    """
    加载CSV并解析所有价格点
    
    Returns:
        DataFrame: 每行为一条记录，每列为一个价格点
    """
    print(f"正在加载数据: {csv_path}")
    df = pd.read_csv(csv_path)
    print(f"原始数据行数: {len(df)}")
    
    # 解析所有记录
    all_prices = []
    for idx, row in df.iterrows():
        prices = parse_jzg_result(row['jzg_result'])
        if prices and 'b2BPrices.b.mid' in prices:
            all_prices.append(prices)
    
    prices_df = pd.DataFrame(all_prices)
    print(f"解析成功记录数: {len(prices_df)}")
    
    # 删除含有空值的行
    prices_df = prices_df.dropna()
    print(f"有效记录数（无空值）: {len(prices_df)}")
    
    return prices_df


# ============================================================
# 第二部分：统计分析
# ============================================================

def calculate_ratios(prices_df: pd.DataFrame) -> pd.DataFrame:
    """
    计算所有价格点与 b2BPrices.b.mid 的比例
    """
    base_col = 'b2BPrices.b.mid'
    ratio_df = pd.DataFrame()
    
    for col in prices_df.columns:
        ratio_df[col] = prices_df[col] / prices_df[base_col]
    
    return ratio_df


def analyze_ratios(ratio_df: pd.DataFrame) -> pd.DataFrame:
    """
    统计分析各价格点的比例分布
    
    Returns:
        DataFrame: 包含均值、标准差、中位数等统计量
    """
    stats = pd.DataFrame({
        'mean': ratio_df.mean(),
        'std': ratio_df.std(),
        'median': ratio_df.median(),
        'min': ratio_df.min(),
        'max': ratio_df.max(),
        'q25': ratio_df.quantile(0.25),
        'q75': ratio_df.quantile(0.75),
        'cv': ratio_df.std() / ratio_df.mean()  # 变异系数
    })
    return stats.round(4)


# ============================================================
# 第三部分：建模方案
# ============================================================

class RatioModel:
    """方案1：基于统计比例的模型"""
    
    def __init__(self):
        self.ratios = {}
        self.name = "统计比例模型"
    
    def fit(self, prices_df: pd.DataFrame):
        """训练：计算各价格点的平均比例"""
        base_col = 'b2BPrices.b.mid'
        base_values = prices_df[base_col]
        
        for col in prices_df.columns:
            if col != base_col:
                ratio = (prices_df[col] / base_values).mean()
                self.ratios[col] = ratio
        
        # 基准列比例为1
        self.ratios[base_col] = 1.0
    
    def predict(self, b2b_b_mid: float) -> dict:
        """预测：使用比例系数乘以输入值"""
        return {col: b2b_b_mid * ratio for col, ratio in self.ratios.items()}
    
    def predict_batch(self, base_values: np.ndarray) -> pd.DataFrame:
        """批量预测"""
        result = {}
        for col, ratio in self.ratios.items():
            result[col] = base_values * ratio
        return pd.DataFrame(result)


class LinearRegressionModel:
    """方案2：线性回归模型"""
    
    def __init__(self):
        self.models = {}
        self.name = "线性回归模型"
    
    def fit(self, prices_df: pd.DataFrame):
        """为每个价格点训练独立的线性回归"""
        base_col = 'b2BPrices.b.mid'
        X = prices_df[[base_col]].values
        
        for col in prices_df.columns:
            model = LinearRegression()
            y = prices_df[col].values
            model.fit(X, y)
            self.models[col] = model
    
    def predict(self, b2b_b_mid: float) -> dict:
        """单值预测"""
        X = np.array([[b2b_b_mid]])
        return {col: model.predict(X)[0] for col, model in self.models.items()}
    
    def predict_batch(self, base_values: np.ndarray) -> pd.DataFrame:
        """批量预测"""
        X = base_values.reshape(-1, 1)
        result = {}
        for col, model in self.models.items():
            result[col] = model.predict(X)
        return pd.DataFrame(result)


class PolynomialRegressionModel:
    """方案3：多项式回归模型"""
    
    def __init__(self, degree=2):
        self.degree = degree
        self.models = {}
        self.poly = PolynomialFeatures(degree=degree)
        self.name = f"多项式回归模型(degree={degree})"
    
    def fit(self, prices_df: pd.DataFrame):
        """训练多项式回归"""
        base_col = 'b2BPrices.b.mid'
        X = prices_df[[base_col]].values
        X_poly = self.poly.fit_transform(X)
        
        for col in prices_df.columns:
            model = LinearRegression()
            y = prices_df[col].values
            model.fit(X_poly, y)
            self.models[col] = model
    
    def predict(self, b2b_b_mid: float) -> dict:
        """单值预测"""
        X = np.array([[b2b_b_mid]])
        X_poly = self.poly.transform(X)
        return {col: model.predict(X_poly)[0] for col, model in self.models.items()}
    
    def predict_batch(self, base_values: np.ndarray) -> pd.DataFrame:
        """批量预测"""
        X = base_values.reshape(-1, 1)
        X_poly = self.poly.transform(X)
        result = {}
        for col, model in self.models.items():
            result[col] = model.predict(X_poly)
        return pd.DataFrame(result)


class SegmentedRatioModel:
    """方案4：分段统计模型"""
    
    def __init__(self, n_segments=3):
        self.n_segments = n_segments
        self.segment_ratios = {}
        self.segment_bounds = []
        self.name = f"分段统计模型(segments={n_segments})"
    
    def fit(self, prices_df: pd.DataFrame):
        """根据价格区间分段训练"""
        base_col = 'b2BPrices.b.mid'
        base_values = prices_df[base_col]
        
        # 计算分段边界（使用分位数）
        quantiles = np.linspace(0, 1, self.n_segments + 1)
        self.segment_bounds = [base_values.quantile(q) for q in quantiles]
        
        # 为每个分段计算比例
        for i in range(self.n_segments):
            lower = self.segment_bounds[i]
            upper = self.segment_bounds[i + 1]
            
            if i == self.n_segments - 1:
                mask = (base_values >= lower) & (base_values <= upper)
            else:
                mask = (base_values >= lower) & (base_values < upper)
            
            segment_df = prices_df[mask]
            segment_base = segment_df[base_col]
            
            self.segment_ratios[i] = {}
            for col in prices_df.columns:
                if len(segment_df) > 0:
                    ratio = (segment_df[col] / segment_base).mean()
                    self.segment_ratios[i][col] = ratio
                else:
                    self.segment_ratios[i][col] = 1.0
    
    def _get_segment(self, value: float) -> int:
        """确定值属于哪个分段"""
        for i in range(self.n_segments):
            if value < self.segment_bounds[i + 1]:
                return i
        return self.n_segments - 1
    
    def predict(self, b2b_b_mid: float) -> dict:
        """单值预测"""
        segment = self._get_segment(b2b_b_mid)
        ratios = self.segment_ratios[segment]
        return {col: b2b_b_mid * ratio for col, ratio in ratios.items()}
    
    def predict_batch(self, base_values: np.ndarray) -> pd.DataFrame:
        """批量预测"""
        results = []
        for val in base_values:
            results.append(self.predict(val))
        return pd.DataFrame(results)


# ============================================================
# 第四部分：模型评估
# ============================================================

def evaluate_model(model, X_test: pd.DataFrame, y_test: pd.DataFrame) -> dict:
    """
    评估模型性能
    
    Returns:
        dict: 包含各指标的评估结果
    """
    base_col = 'b2BPrices.b.mid'
    base_values = X_test[base_col].values
    
    # 预测
    predictions = model.predict_batch(base_values)
    
    # 计算误差
    errors = {}
    for col in y_test.columns:
        actual = y_test[col].values
        pred = predictions[col].values
        
        mae = mean_absolute_error(actual, pred)
        rmse = np.sqrt(mean_squared_error(actual, pred))
        mape = np.mean(np.abs((actual - pred) / actual)) * 100
        max_error = np.max(np.abs(actual - pred))
        
        errors[col] = {
            'MAE': mae,
            'RMSE': rmse,
            'MAPE': mape,
            'MaxError': max_error
        }
    
    # 汇总
    all_mae = np.mean([e['MAE'] for e in errors.values()])
    all_rmse = np.mean([e['RMSE'] for e in errors.values()])
    all_mape = np.mean([e['MAPE'] for e in errors.values()])
    all_max_error = np.max([e['MaxError'] for e in errors.values()])
    
    return {
        'model_name': model.name,
        'overall': {
            'MAE': all_mae,
            'RMSE': all_rmse,
            'MAPE': all_mape,
            'MaxError': all_max_error
        },
        'by_column': errors
    }


def run_evaluation(prices_df: pd.DataFrame, test_size=0.2, random_state=42):
    """
    运行完整的模型评估流程
    """
    # 划分训练集和测试集
    train_df, test_df = train_test_split(prices_df, test_size=test_size, random_state=random_state)
    print(f"\n训练集大小: {len(train_df)}, 测试集大小: {len(test_df)}")
    
    # 初始化模型
    models = [
        RatioModel(),
        LinearRegressionModel(),
        PolynomialRegressionModel(degree=2),
        PolynomialRegressionModel(degree=3),
        SegmentedRatioModel(n_segments=3),
        SegmentedRatioModel(n_segments=5),
    ]
    
    results = []
    
    for model in models:
        print(f"\n正在评估: {model.name}")
        model.fit(train_df)
        eval_result = evaluate_model(model, test_df, test_df)
        results.append(eval_result)
        
        print(f"  整体 MAE: {eval_result['overall']['MAE']:.4f}")
        print(f"  整体 MAPE: {eval_result['overall']['MAPE']:.2f}%")
        print(f"  整体 RMSE: {eval_result['overall']['RMSE']:.4f}")
    
    return results, train_df, test_df


# ============================================================
# 第五部分：结果输出
# ============================================================

def generate_report(results: list, ratio_stats: pd.DataFrame, output_path: str):
    """生成分析报告"""
    
    report = []
    report.append("# 二手车价格预测模型分析报告\n")
    report.append(f"生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # 1. 比例统计
    report.append("\n## 1. 价格比例统计分析\n")
    report.append("以 `b2BPrices.b.mid` 为基准，各价格点的比例系数:\n")
    report.append("\n| 价格点 | 均值 | 标准差 | 变异系数 | 中位数 |\n")
    report.append("|--------|------|--------|----------|--------|\n")
    
    for idx, row in ratio_stats.iterrows():
        report.append(f"| {idx} | {row['mean']:.4f} | {row['std']:.4f} | {row['cv']:.4f} | {row['median']:.4f} |\n")
    
    # 2. 模型对比
    report.append("\n## 2. 模型误差对比\n")
    report.append("\n| 模型 | MAE | MAPE (%) | RMSE | 最大误差 |\n")
    report.append("|------|-----|----------|------|----------|\n")
    
    for r in results:
        o = r['overall']
        report.append(f"| {r['model_name']} | {o['MAE']:.4f} | {o['MAPE']:.2f} | {o['RMSE']:.4f} | {o['MaxError']:.4f} |\n")
    
    # 3. 最优模型
    best_idx = np.argmin([r['overall']['MAPE'] for r in results])
    best = results[best_idx]
    
    report.append(f"\n## 3. 最优模型选择\n")
    report.append(f"\n**推荐模型**: {best['model_name']}\n")
    report.append(f"\n**理由**: 该模型在测试集上的平均绝对百分比误差(MAPE)最低，为 {best['overall']['MAPE']:.2f}%\n")
    
    # 4. 各价格点详细误差
    report.append(f"\n## 4. 最优模型各价格点误差详情\n")
    report.append("\n| 价格点 | MAE | MAPE (%) | RMSE |\n")
    report.append("|--------|-----|----------|------|\n")
    
    for col, errors in best['by_column'].items():
        report.append(f"| {col} | {errors['MAE']:.4f} | {errors['MAPE']:.2f} | {errors['RMSE']:.4f} |\n")
    
    # 5. 使用示例
    report.append("\n## 5. 使用示例\n")
    report.append("""
```python
from c2b2c_price_model_analysis import load_and_parse_data, RatioModel

# 加载数据并训练模型
prices_df = load_and_parse_data('jzg_results_merged_success.csv')
model = RatioModel()
model.fit(prices_df)

# 预测：给定 b2BPrices.b.mid = 2.24
result = model.predict(2.24)
print(result)
```
""")
    
    # 写入文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(report)
    
    print(f"\n报告已保存至: {output_path}")


def create_prediction_function(model) -> callable:
    """创建最终的预测函数"""
    
    def predict_prices(b2b_b_mid: float) -> dict:
        """
        根据 b2BPrices.b.mid 预测完整价格结构
        
        Args:
            b2b_b_mid: 车商B级车况中间价格（万元）
        
        Returns:
            dict: 包含 b2BPrices, b2CPrices, c2BPrices 的完整价格字典
        """
        flat_result = model.predict(b2b_b_mid)
        
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
                    structured[price_type][condition][level] = round(value, 2)
        
        return structured
    
    return predict_prices


# ============================================================
# 主程序
# ============================================================

def main():
    # 配置路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(os.path.dirname(script_dir))  # 车型库映射目录
    data_dir = os.path.join(base_dir, 'data')
    csv_path = os.path.join(data_dir, 'jzg_results_merged_success.csv')
    report_path = os.path.join(script_dir, 'c2b2c_price_model_report.md')
    
    print("=" * 60)
    print("二手车价格预测模型分析")
    print("=" * 60)
    
    # 1. 加载数据
    prices_df = load_and_parse_data(csv_path)
    
    # 2. 统计分析
    print("\n" + "=" * 60)
    print("比例统计分析")
    print("=" * 60)
    ratio_df = calculate_ratios(prices_df)
    ratio_stats = analyze_ratios(ratio_df)
    print(ratio_stats)
    
    # 3. 模型评估
    print("\n" + "=" * 60)
    print("模型评估")
    print("=" * 60)
    results, train_df, test_df = run_evaluation(prices_df)
    
    # 4. 生成报告
    generate_report(results, ratio_stats, report_path)
    
    # 5. 演示预测函数
    print("\n" + "=" * 60)
    print("预测示例")
    print("=" * 60)
    
    # 使用最优模型创建预测函数
    best_idx = np.argmin([r['overall']['MAPE'] for r in results])
    
    # 重新训练最优模型（使用全部数据）
    if best_idx == 0:
        final_model = RatioModel()
    elif best_idx == 1:
        final_model = LinearRegressionModel()
    elif best_idx == 2:
        final_model = PolynomialRegressionModel(degree=2)
    elif best_idx == 3:
        final_model = PolynomialRegressionModel(degree=3)
    elif best_idx == 4:
        final_model = SegmentedRatioModel(n_segments=3)
    else:
        final_model = SegmentedRatioModel(n_segments=5)
    
    final_model.fit(prices_df)
    predict_func = create_prediction_function(final_model)
    
    # 示例预测
    test_value = 2.24
    prediction = predict_func(test_value)
    print(f"\n输入 b2BPrices.b.mid = {test_value}")
    print(f"\n预测结果:")
    print(json.dumps(prediction, indent=2, ensure_ascii=False))
    
    print("\n分析完成！")
    return predict_func


if __name__ == "__main__":
    main()
