"""
批量模型训练核心模块

功能：
1. 封装模型训练逻辑（复用 residual_value_modeling_step3.py 的思路）
2. 提供模型保存/加载功能
3. 数据清洗和过滤

使用方法：
    from batch_model_trainer_step4 import BatchModelTrainer, ResidualValueModel
    
    trainer = BatchModelTrainer(data_path)
    model = trainer.train_for_group(group_df)
    model.save(output_path)
"""

import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
from sklearn.metrics import r2_score
import pickle
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============= 模型函数定义 =============

def exponential_model(x, a, b):
    """指数模型: y = a * e^(b*x)"""
    return a * np.exp(b * x)


def polynomial_model(x, a, b, c):
    """二次多项式: y = ax^2 + bx + c"""
    return a * x**2 + b * x + c


def power_model(x, a, b):
    """幂函数: y = a * x^b"""
    return a * np.power(x, b)


def get_rmse(y_true, y_pred):
    """计算均方根误差"""
    return np.sqrt(np.mean((y_true - y_pred)**2))


# ============= 模型类定义 =============

@dataclass
class ResidualValueModel:
    """残值率模型封装类"""
    model_type: str  # 'Exponential', 'Polynomial', 'Power'
    params: np.ndarray  # 模型参数
    r2: float  # R2 分数
    rmse: float  # RMSE 误差
    sample_count: int  # 训练样本数
    group_name: str  # 分组名称（品牌车系或车辆类别）
    
    def predict(self, year: float) -> float:
        """
        预测指定年限的残值率
        
        Args:
            year: 使用年限
            
        Returns:
            残值率（0-1之间）
        """
        if self.model_type == 'Exponential':
            rate = exponential_model(year, *self.params)
        elif self.model_type == 'Polynomial':
            rate = np.polyval(self.params, year)
        elif self.model_type == 'Power':
            rate = power_model(year, *self.params)
        else:
            raise ValueError(f"未知模型类型: {self.model_type}")
        
        # 残值率修正：确保大于0且小于等于1
        return max(0.0, min(1.0, rate))
    
    def predict_price(self, year: float, new_price: float) -> float:
        """
        预测二手车价格
        
        Args:
            year: 使用年限
            new_price: 新车价格（万元）
            
        Returns:
            预测的二手车价格（万元）
        """
        rate = self.predict(year)
        return round(rate * new_price, 2)
    
    def save(self, filepath: str):
        """保存模型到文件"""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump(self, f)
        logger.debug(f"模型已保存: {filepath}")
    
    @classmethod
    def load(cls, filepath: str) -> 'ResidualValueModel':
        """从文件加载模型"""
        with open(filepath, 'rb') as f:
            model = pickle.load(f)
        return model
    
    def get_formula(self) -> str:
        """获取模型公式字符串"""
        if self.model_type == 'Exponential':
            return f"y = {self.params[0]:.4f} * e^({self.params[1]:.4f}x)"
        elif self.model_type == 'Polynomial':
            return f"y = {self.params[0]:.4f}x² + {self.params[1]:.4f}x + {self.params[2]:.4f}"
        elif self.model_type == 'Power':
            return f"y = {self.params[0]:.4f} * x^({self.params[1]:.4f})"
        return "未知公式"
    
    def __repr__(self):
        return f"ResidualValueModel({self.model_type}, R²={self.r2:.4f}, 样本={self.sample_count})"


# ============= 训练器类 =============

class BatchModelTrainer:
    """批量模型训练器"""
    
    def __init__(self, data_path: str, min_samples: int = 100, iqr_factor: float = 1.0):
        """
        初始化训练器
        
        Args:
            data_path: 数据文件路径
            min_samples: 最小样本数阈值
            iqr_factor: IQR异常值过滤系数
        """
        self.data_path = Path(data_path)
        self.min_samples = min_samples
        self.iqr_factor = iqr_factor
        self._df = None
    
    @property
    def df(self) -> pd.DataFrame:
        """延迟加载数据"""
        if self._df is None:
            logger.info(f"加载数据: {self.data_path}")
            self._df = pd.read_csv(self.data_path)
            logger.info(f"数据加载完成，共 {len(self._df)} 条记录")
        return self._df
    
    def _filter_outliers_by_iqr(self, df: pd.DataFrame) -> pd.DataFrame:
        """基于年限分组的IQR异常值过滤"""
        df_clean = pd.DataFrame()
        
        df = df.copy()
        df['rounded_year'] = df['使用年限'].round()
        grouped = df.groupby('rounded_year')
        
        for year, group in grouped:
            if len(group) < 5:
                # 样本太少不进行统计学过滤
                df_clean = pd.concat([df_clean, group])
                continue
            
            q1 = group['残值率'].quantile(0.25)
            q3 = group['残值率'].quantile(0.75)
            iqr = q3 - q1
            
            lower_bound = max(0, q1 - self.iqr_factor * iqr)
            upper_bound = q3 + self.iqr_factor * iqr
            
            mask = (group['残值率'] >= lower_bound) & (group['残值率'] <= upper_bound)
            df_clean = pd.concat([df_clean, group[mask]])
        
        return df_clean
    
    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """数据清洗"""
        df = df.copy()
        
        # 数据类型转换
        df['使用年限'] = pd.to_numeric(df['使用年限'], errors='coerce')
        df['车况校正价'] = pd.to_numeric(df['车况校正价'], errors='coerce')
        df['新车的价格'] = pd.to_numeric(df['新车的价格'], errors='coerce')
        
        # 过滤无效数据
        df = df[df['新车的价格'] > 0.1]
        
        # 计算残值率
        df['残值率'] = df['车况校正价'] / df['新车的价格']
        
        # 基础异常值过滤
        df = df[(df['使用年限'] >= 0.5) & (df['使用年限'] <= 20)]
        df = df[(df['残值率'] > 0.01) & (df['残值率'] <= 1.5)]
        
        # IQR 过滤
        df = self._filter_outliers_by_iqr(df)
        
        return df
    
    def _train_models(self, x_data: np.ndarray, y_data: np.ndarray) -> Dict:
        """训练三种模型并返回结果"""
        results = {}
        
        # 1. 指数模型
        try:
            popt_exp, _ = curve_fit(exponential_model, x_data, y_data, p0=[1.0, -0.1], maxfev=5000)
            y_pred_exp = exponential_model(x_data, *popt_exp)
            r2_exp = r2_score(y_data, y_pred_exp)
            rmse_exp = get_rmse(y_data, y_pred_exp)
            results['Exponential'] = {'params': popt_exp, 'r2': r2_exp, 'rmse': rmse_exp}
        except Exception as e:
            results['Exponential'] = {'error': str(e)}

        # 2. 二次多项式
        try:
            p_poly = np.polyfit(x_data, y_data, 2)
            y_pred_poly = np.polyval(p_poly, x_data)
            r2_poly = r2_score(y_data, y_pred_poly)
            rmse_poly = get_rmse(y_data, y_pred_poly)
            results['Polynomial'] = {'params': p_poly, 'r2': r2_poly, 'rmse': rmse_poly}
        except Exception as e:
            results['Polynomial'] = {'error': str(e)}

        # 3. 幂函数
        try:
            popt_pow, _ = curve_fit(power_model, x_data, y_data, p0=[1.0, -0.5], maxfev=5000)
            y_pred_pow = power_model(x_data, *popt_pow)
            r2_pow = r2_score(y_data, y_pred_pow)
            rmse_pow = get_rmse(y_data, y_pred_pow)
            results['Power'] = {'params': popt_pow, 'r2': r2_pow, 'rmse': rmse_pow}
        except Exception as e:
            results['Power'] = {'error': str(e)}

        return results
    
    def _select_best_model(self, results: Dict, sample_count: int, group_name: str) -> Optional[ResidualValueModel]:
        """选择最佳模型"""
        valid_models = []
        test_range = np.linspace(1, 15, 30)
        
        for name, res in results.items():
            if 'error' in res:
                continue
            
            # 物理意义检查：预测值必须大于0
            if name == 'Polynomial':
                preds = np.polyval(res['params'], test_range)
            elif name == 'Exponential':
                preds = exponential_model(test_range, *res['params'])
            elif name == 'Power':
                preds = power_model(test_range, *res['params'])
            else:
                continue
            
            if np.any(preds < 0):
                continue
            
            # 单调性检查：残值随年限增加不能上升
            is_monotonic = True
            if name == 'Polynomial':
                a, b, c = res['params']
                derivatives = 2 * a * test_range + b
                if np.any(derivatives > 0.001):
                    is_monotonic = False
            else:
                if np.any(np.diff(preds) > 0.001):
                    is_monotonic = False
            
            if not is_monotonic:
                continue
            
            valid_models.append((name, res))
        
        if not valid_models:
            return None
        
        # 选择 R2 最高的模型
        best_name, best_res = max(valid_models, key=lambda x: x[1]['r2'])
        
        return ResidualValueModel(
            model_type=best_name,
            params=best_res['params'],
            r2=best_res['r2'],
            rmse=best_res['rmse'],
            sample_count=sample_count,
            group_name=group_name
        )
    
    def train_for_group(self, group_df: pd.DataFrame, group_name: str) -> Tuple[Optional[ResidualValueModel], pd.DataFrame]:
        """
        为指定分组训练模型
        
        Args:
            group_df: 分组数据
            group_name: 分组名称
            
        Returns:
            (训练好的模型, 清洗后的数据)
        """
        # 数据清洗
        df_clean = self._clean_data(group_df)
        
        if len(df_clean) < 10:
            logger.warning(f"[{group_name}] 清洗后样本不足 ({len(df_clean)} 条)，跳过建模")
            return None, df_clean
        
        x_data = df_clean['使用年限'].values
        y_data = df_clean['残值率'].values
        
        # 训练模型
        results = self._train_models(x_data, y_data)
        
        # 选择最佳模型
        model = self._select_best_model(results, len(df_clean), group_name)
        
        if model:
            logger.info(f"[{group_name}] 建模成功: {model.model_type}, R²={model.r2:.4f}, 样本={model.sample_count}")
        else:
            logger.warning(f"[{group_name}] 无有效模型（可能数据分布异常）")
        
        return model, df_clean
    
    def get_brand_series_groups(self) -> Dict[str, pd.DataFrame]:
        """
        获取品牌车系分组（样本数>阈值）
        
        Returns:
            {品牌车系: 数据DataFrame}
        """
        counts = self.df['品牌车系'].value_counts()
        valid_series = counts[counts >= self.min_samples].index.tolist()
        
        groups = {}
        for series in valid_series:
            groups[series] = self.df[self.df['品牌车系'] == series].copy()
        
        logger.info(f"找到 {len(groups)} 个品牌车系（样本数≥{self.min_samples}）")
        return groups
    
    def get_car_type_groups(self) -> Dict[str, pd.DataFrame]:
        """
        获取车辆类别分组
        
        Returns:
            {车辆大类-车辆小类-车辆属性: 数据DataFrame}
        """
        df = self.df.copy()
        df['车辆类别'] = df['车辆大类'] + '-' + df['车辆小类'] + '-' + df['车辆属性']
        
        counts = df['车辆类别'].value_counts()
        # 车辆类别不需要样本数限制，因为每个类别都应该建模
        valid_types = counts.index.tolist()
        
        groups = {}
        for car_type in valid_types:
            groups[car_type] = df[df['车辆类别'] == car_type].copy()
        
        logger.info(f"找到 {len(groups)} 个车辆类别")
        return groups


# ============= 便捷函数 =============

def load_model(filepath: str) -> ResidualValueModel:
    """加载模型"""
    return ResidualValueModel.load(filepath)


def safe_filename(name: str) -> str:
    """
    将名称转换为安全的文件名
    替换不能作为文件名的字符
    """
    # 替换 Windows 文件名中不允许的字符
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    result = name
    for char in invalid_chars:
        result = result.replace(char, '_')
    return result

def main():
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='批量残值率模型训练工具')
    parser.add_argument('--file', required=True, help='输入数据文件路径 (CSV)')
    parser.add_argument('--output_dir', default='../output/models', help='模型保存目录')
    parser.add_argument('--min_samples', type=int, default=20, help='最小样本数阈值')
    parser.add_argument('--iqr_factor', type=float, default=1.0, help='IQR异常值过滤系数')
    
    args = parser.parse_args()
    
    input_path = Path(args.file)
    if not input_path.exists():
        # Try relative to src if not found
        base_dir = Path(__file__).parent
        input_path = base_dir / args.file
        
    if not input_path.exists():
        print(f"Error: 文件不存在: {args.file}")
        return

    print(f"正在加载数据: {input_path}")
    
    # 初始化训练器
    trainer = BatchModelTrainer(str(input_path), min_samples=args.min_samples, iqr_factor=args.iqr_factor)
    
    # 准备输出目录
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
         output_dir = Path(__file__).parent / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 获取所有符合条件的分组
    groups = trainer.get_brand_series_groups()
    print(f"找到 {len(groups)} 个有效品牌车系（样本数>={args.min_samples}）")
    
    summary_data = []
    
    # 遍历每个车系进行建模分析
    for series_name in groups:
        # 训练模型
        model, df_clean = trainer.train_for_group(groups[series_name], series_name)
        
        status = "失败"
        r2 = 0.0
        rmse = 0.0
        formula = ""
        model_type = ""
        sample_count = len(groups[series_name])
        valid_count = len(df_clean)
        
        if model:
            status = "成功"
            r2 = model.r2
            rmse = model.rmse
            formula = model.get_formula()
            model_type = model.model_type
            
            # 保存模型
            safe_name = safe_filename(series_name)
            model_path = output_dir / f"{safe_name}.pkl"
            model.save(str(model_path))
            
        summary_data.append({
            '品牌车系': series_name,
            '状态': status,
            '原始样本': sample_count,
            '有效样本': valid_count,
            '模型类型': model_type,
            'R2': round(r2, 4),
            'RMSE': round(rmse, 4),
            '公式': formula
        })

    # 保存汇总报表
    summary_df = pd.DataFrame(summary_data)
    summary_path = output_dir / "batch_training_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding='utf-8-sig')
    print(f"\n批量训练完成！")
    print(f"模型已保存至: {output_dir}")
    print(f"汇总报表已保存至: {summary_path}")
    
    # 打印简要统计
    success_count = summary_df[summary_df['状态'] == '成功'].shape[0]
    print(f"成功建模: {success_count}/{len(groups)}")
    if success_count > 0:
        avg_r2 = summary_df[summary_df['状态'] == '成功']['R2'].mean()
        print(f"平均 R2: {avg_r2:.4f}")

if __name__ == '__main__':
    main()
