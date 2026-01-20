"""
二手车残值率建模分析程序

功能：
1. 读取残值率数据 (residual_value_data.csv)
2. 针对指定“品牌-车系”进行数据清洗
   - 过滤异常年限 (0 < year <= 20)
   - 过滤异常残值率 (0.05 < rate <= 1.2)
   - 使用 车况校正价 / 新车价格 计算残值率
3. 拟合多种模型：
   - 指数模型 (Exponential): y = a * e^(b*x)
   - 二次多项式 (Polynomial-2): y = ax^2 + bx + c
   - 幂函数 (Power): y = a * x^b
4. 评估模型 (R2, RMSE) 并推荐最佳模型
5. 输出 1-10 年保值率预测
"""

import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
from sklearn.metrics import r2_score, mean_squared_error
import argparse
import sys
from pathlib import Path

# 定义模型函数
def exponential_model(x, a, b):
    return a * np.exp(b * x)

def polynomial_model(x, a, b, c):
    return a * x**2 + b * x + c

def power_model(x, a, b):
    return a * np.power(x, b)

def get_rmse(y_true, y_pred):
    return np.sqrt(np.mean((y_true - y_pred)**2))



def filter_outliers_by_iqr(df, iqr_factor=1.0):
    """
    基于年限分组的 IQR (四分位距) 异常值过滤
    原理：
    1. 将车辆按车龄(四舍五入)分组。
    2. 对每组计算 Q1(25%分位) 和 Q3(75%分位)。
    2. 对每组计算 Q1(25%分位) 和 Q3(75%分位)。
    3. 定义正常区间：[Q1 - factor*IQR, Q3 + factor*IQR]。
    4. 剔除区间外的数据。
    """
    df_clean = pd.DataFrame()
    outliers = pd.DataFrame()
    
    # 按年限分组处理 (四舍五入)
    df['rounded_year'] = df['使用年限'].round()
    grouped = df.groupby('rounded_year')
    
    df['rounded_year'] = df['使用年限'].round()
    grouped = df.groupby('rounded_year')
    
    print(f"\n--- 噪音数据过滤详情 (IQR 算法, factor={iqr_factor}) ---")
    print(f"{'年限':<5} {'数量(前)':<8} {'正常区间':<20} {'过滤数':<5} {'示例(被剔除)'}")
    print("-" * 65)
    
    for year, group in grouped:
        if len(group) < 5:
            # 样本太少不进行统计学过滤，直接保留
            df_clean = pd.concat([df_clean, group])
            print(f"{int(year):<5} {len(group):<8} {'(样本少不通过滤)':<20} {0:<5}")
            continue
            
        q1 = group['残值率'].quantile(0.25)
        q3 = group['残值率'].quantile(0.75)
        iqr = q3 - q1
        
        iqr = q3 - q1
        
        lower_bound = q1 - iqr_factor * iqr
        upper_bound = q3 + iqr_factor * iqr
        
        # 能够接受一定的最小值 (e.g. 0)
        lower_bound = max(0, lower_bound)
        
        mask = (group['残值率'] >= lower_bound) & (group['残值率'] <= upper_bound)
        
        normal_data = group[mask]
        outlier_data = group[~mask]
        
        df_clean = pd.concat([df_clean, normal_data])
        outliers = pd.concat([outliers, outlier_data])
        
        # 记录日志
        example_price = ""
        if len(outlier_data) > 0:
            # 取一个示例
            ex = outlier_data.iloc[0]
            example_price = f"{ex['残值率']:.1%} (价:{ex['车况校正价']}w)"
            
        range_str = f"[{lower_bound:.1%}, {upper_bound:.1%}]"
        print(f"{int(year):<5} {len(group):<8} {range_str:<20} {len(outlier_data):<5} {example_price}")

    if len(outliers) > 0:
        print(f"\n>> 共过滤 {len(outliers)} 条噪音数据，占总量的 {len(outliers)/len(df):.1%}")
    else:
        print("\n>> 未发现明显噪音数据")
    
    # 将过滤数量写入文件以便获取
    try:
        with open('filtered_count.txt', 'w') as f:
            f.write(str(len(outliers)))
    except:
        pass
        
    return df_clean

def load_and_clean_data(file_path, brand_series, iqr_factor=1.0):
    """加载并清洗数据"""
    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}")
        return None

    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return None
        
    # 筛选品牌车系
    df_series = df[df['品牌车系'] == brand_series].copy()
    if len(df_series) < 10:
        print(f"Error: 样本数据不足 (仅 {len(df_series)} 条)，无法建模。")
        return None

    # 必要的列检查
    required_cols = ['车况校正价', '新车的价格', '使用年限']
    for col in required_cols:
        if col not in df_series.columns:
            print(f"Error: 缺少必要列: {col}")
            return None

    # 数据转换
    df_series['使用年限'] = pd.to_numeric(df_series['使用年限'], errors='coerce')
    df_series['车况校正价'] = pd.to_numeric(df_series['车况校正价'], errors='coerce')
    df_series['新车的价格'] = pd.to_numeric(df_series['新车的价格'], errors='coerce')
    
    # 计算残值率
    # 过滤掉新车价格异常的 (比如0或空)
    df_series = df_series[df_series['新车的价格'] > 0.1]
    df_series['残值率'] = df_series['车况校正价'] / df_series['新车的价格']

    # 基础异常值过滤
    # 1. 年限：0.5年 - 20年
    df_pre_clean = df_series[(df_series['使用年限'] >= 0.5) & (df_series['使用年限'] <= 20)]
    
    # 2. 残值率：1% - 150% (放宽初始范围，交给IQR处理)
    df_pre_clean = df_pre_clean[(df_pre_clean['残值率'] > 0.01) & (df_pre_clean['残值率'] <= 1.5)]

    if len(df_pre_clean) < 5:
        print(f"Error: 清洗后有效样本过少 ({len(df_pre_clean)} 条)，建议检查数据质量。")
        return None

    print(f"[{brand_series}] 原始样本: {len(df_series)} 条")
    
    # 进阶过滤: IQR
    df_final = filter_outliers_by_iqr(df_pre_clean, iqr_factor)
    
    print(f"最终有效样本: {len(df_final)} 条")
    return df_final

def train_models(df):
    """训练三种模型并返回结果"""
    x_data = df['使用年限'].values
    y_data = df['残值率'].values
    
    results = {}
    
    # 1. 指数模型
    try:
        popt_exp, _ = curve_fit(exponential_model, x_data, y_data, p0=[1.0, -0.1], maxfev=5000)
        y_pred_exp = exponential_model(x_data, *popt_exp)
        r2_exp = r2_score(y_data, y_pred_exp)
        rmse_exp = get_rmse(y_data, y_pred_exp)
        results['Exponential'] = {'params': popt_exp, 'r2': r2_exp, 'rmse': rmse_exp, 'func': exponential_model}
    except Exception as e:
        results['Exponential'] = {'error': str(e)}

    # 2. 二次多项式
    try:
        # 使用 polyfit 更稳定
        p_poly = np.polyfit(x_data, y_data, 2)
        # polyfit 返回 [a, b, c], 对应 ax^2 + bx + c
        y_pred_poly = np.polyval(p_poly, x_data)
        r2_poly = r2_score(y_data, y_pred_poly)
        rmse_poly = get_rmse(y_data, y_pred_poly)
        results['Polynomial'] = {'params': p_poly, 'r2': r2_poly, 'rmse': rmse_poly, 'func': polynomial_model}
    except Exception as e:
        results['Polynomial'] = {'error': str(e)}

    # 3. 幂函数
    try:
        popt_pow, _ = curve_fit(power_model, x_data, y_data, p0=[1.0, -0.5], maxfev=5000)
        y_pred_pow = power_model(x_data, *popt_pow)
        r2_pow = r2_score(y_data, y_pred_pow)
        rmse_pow = get_rmse(y_data, y_pred_pow)
        results['Power'] = {'params': popt_pow, 'r2': r2_pow, 'rmse': rmse_pow, 'func': power_model}
    except Exception as e:
        results['Power'] = {'error': str(e)}

    return results

def evaluate_and_recommend(results):
    """评估模型并给出推荐"""
    valid_models = []
    print("\n--- 模型评估结果 ---")
    print(f"{'模型名称':<15} {'R2 (拟合度)':<10} {'RMSE (误差)':<10} {'状态'}")
    
    test_range = np.linspace(1, 15, 30)
    
    for name, res in results.items():
        if 'error' in res:
            print(f"{name:<15} {'-':<10} {'-':<10} 拟合失败")
            continue
            
        # 1. 物理意义检查：保值率必须大于0
        if name == 'Polynomial':
             preds = np.polyval(res['params'], test_range)
        else:
             preds = res['func'](test_range, *res['params'])
             
        if np.any(preds < 0):
            print(f"{name:<15} {res['r2']:.4f}     {res['rmse']:.4f}     拒绝: 存在负数残值")
            continue
            
        # 2. 单调性检查：残值随年限增加不能上升
        # 对于多项式 y = ax^2 + bx + c, 导数 y' = 2ax + b
        is_monotonic = True
        if name == 'Polynomial':
            a, b, c = res['params']
            # 检查测试范围内的导数是否都 <= 0
            derivatives = 2 * a * test_range + b
            if np.any(derivatives > 0.001): # 允许极小的浮动
                is_monotonic = False
        else:
            # 对于指数和幂函数，根据系数正负通常是单调的，但也检查一下
            if np.any(np.diff(preds) > 0.001):
                is_monotonic = False
                
        if not is_monotonic:
            print(f"{name:<15} {res['r2']:.4f}     {res['rmse']:.4f}     拒绝: 非单调递减")
            continue

        print(f"{name:<15} {res['r2']:.4f}     {res['rmse']:.4f}     有效")
        valid_models.append((name, res))
    
    if not valid_models:
        print("\n没有符合物理逻辑(单调递减且大于0)的模型可用。")
        return None

    # 选择策略：R2 最高
    best_model = sorted(valid_models, key=lambda x: x[1]['r2'], reverse=True)[0]
    return best_model

def predict_future(model_name, model_data, df, years=range(1, 16)):
    """生成预测数据，包含样本分布统计"""
    print(f"\n--- {model_name} 模型预测 (1-15年) ---")
    if model_name == 'Polynomial':
        params = model_data['params']
        # param string for display
        formula = f"y = {params[0]:.4f}x^2 + {params[1]:.4f}x + {params[2]:.4f}"
        predict_func = lambda x: np.polyval(params, x)
    elif model_name == 'Exponential':
        params = model_data['params']
        formula = f"y = {params[0]:.4f} * e^({params[1]:.4f}x)"
        predict_func = lambda x: exponential_model(x, *params)
    elif model_name == 'Power':
        params = model_data['params']
        formula = f"y = {params[0]:.4f} * x^({params[1]:.4f})"
        predict_func = lambda x: power_model(x, *params)
    
    print(f"公式: {formula}")
    print("\n年限    预测保值率    样本数")
    print("-" * 30)
    
    # 统计样本分布 (按四舍五入年限)
    year_counts = df['使用年限'].round().value_counts()
    
    predictions = []
    for y in years:
        rate = predict_func(y)
        rate = max(0, rate) # 修正负值
        count = year_counts.get(y, 0)
        print(f"{y:<2}年    {rate:.2%}       {count}")
        predictions.append((y, rate, count))
        
    return predictions

def save_prediction_details(df, model_name, model_data, output_file):
    """保存详细预测结果到CSV"""
    print(f"\n>> 正在保存预测详情到: {output_file}")
    
    # 准备预测函数
    if model_name == 'Polynomial':
        params = model_data['params']
        predict_func = lambda x: np.polyval(params, x)
    elif model_name == 'Exponential':
        params = model_data['params']
        predict_func = lambda x: exponential_model(x, *params)
    elif model_name == 'Power':
        params = model_data['params']
        predict_func = lambda x: power_model(x, *params)
    else:
        print("未知的模型类型，跳过保存详情。")
        return

    # 计算预测值
    # df 已经是清洗后的数据，直接在上面操作
    # 预测保值率
    df['预测保值率'] = df['使用年限'].apply(predict_func)
    df['预测保值率'] = df['预测保值率'].clip(lower=0) # 非负修正
    
    # 预测价格 = 预测保值率 * 新车价格
    df['预测值'] = df['预测保值率'] * df['新车的价格']
    df['预测值'] = df['预测值'].round(2)
    
    # 误差 = 预测值 - 车况校正价
    df['误差'] = df['预测值'] - df['车况校正价']
    df['误差'] = df['误差'].round(2)

    # 误差率 = 误差 / 车况校正价 (保留4位小数)
    # 避免除以0
    df['误差率'] = df.apply(lambda row: round(row['误差'] / row['车况校正价'], 4) if row['车况校正价'] != 0 else 0.0, axis=1)
    
    # 误差等级逻辑:
    # 3%以内(<=0.03): 0
    # 3-10%(0.03 < x <= 0.10): 1
    # 10-20%(0.10 < x <= 0.20): 2
    # 20-30%: 3
    # 以此类推: ceil(abs(rate) * 10)
    # 注意: 0.03 是个特例断点，需要单独处理
    def calc_error_level(rate):
        v = abs(rate)
        if v <= 0.03:
            return 0
        if v <= 0.10:
            return 1
        return int(np.ceil(v * 10))

    df['误差等级'] = df['误差率'].apply(calc_error_level)

    # 整理输出列
    # 用户要求的列: 数据来源,车辆全称,品牌车系,新车的价格,二手车的成交价,车况校正价,使用年限,车辆评级,车辆大类,车辆小类,车辆属性,城市,行驶里程
    # + 预测值, 误差, 误差率, 误差等级
    
    target_cols = [
        '数据来源', '车辆全称', '品牌车系', '新车的价格', '二手车的成交价', '车况校正价', 
        '使用年限', '车辆评级', '车辆大类', '车辆小类', '车辆属性', '城市', '行驶里程',
        '预测值', '误差', '误差率', '误差等级'
    ]
    
    # 确保列存在，不存在的填空
    for col in target_cols:
        if col not in df.columns:
            df[col] = ''
            
    df_out = df[target_cols]
    
    try:
        # 确保目录存在
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        # 覆盖写入
        df_out.to_csv(output_file, index=False, encoding='utf-8-sig')
        print("保存成功！")
    except Exception as e:
        print(f"保存失败: {e}")

def main():
    parser = argparse.ArgumentParser(description='二手车残值率建模工具')
    parser.add_argument('--file', default='../output/residual_value_data.csv', help='数据文件路径')
    parser.add_argument('--series', required=True, help='品牌-车系，如"本田-飞度"')
    parser.add_argument('--iqr_factor', type=float, default=1.0, help='IQR过滤系数，默认1.0，越小过滤越严格')
    
    # 如果没有命令行参数，默认使用测试案例
    if len(sys.argv) == 1:
        print("Usage: python residual_value_modeling.py --series '品牌-车系'")
        return

    args = parser.parse_args()
    
    # 路径修正：如果是在 src 目录下运行
    file_path = args.file
    if not Path(file_path).is_absolute():
        # 尝试相对于当前脚本的路径
        base_dir = Path(__file__).parent
        file_path = base_dir / file_path

    print(f"正在分析: {args.series}")
    df = load_and_clean_data(str(file_path), args.series, args.iqr_factor)
    
    models = train_models(df)
    best_model = evaluate_and_recommend(models)
    
    if best_model:
        name, data = best_model
        print(f"\n>> 推荐模型: {name} (R2={data['r2']:.4f})")
        print("理由: 在保证物理意义(残值>0)的前提下，该模型的拟合度(R2)最高，误差(RMSE)最小。")
        
        print("理由: 在保证物理意义(残值>0)的前提下，该模型的拟合度(R2)最高，误差(RMSE)最小。")
        
        predict_future(name, data, df)
        
        # 保存详情
        # default path: ../tests/result_details.csv from src/
        # construct absolute path based on script location
        script_dir = Path(__file__).parent
        details_path = script_dir.parent / 'tests' / 'result_details.csv'
        save_prediction_details(df, name, data, str(details_path))

if __name__ == '__main__':
    main()
