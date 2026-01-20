
import pandas as pd
import numpy as np
import sys
from pathlib import Path
import residual_value_modeling_step3 as modeler

def batch_process(input_file, output_file):
    print(f"开始批量处理: {input_file}")
    
    if not Path(input_file).exists():
        print(f"文件不存在: {input_file}")
        return

    # 读取原始数据获取车系列表
    try:
        raw_df = pd.read_csv(input_file)
        series_list = raw_df['品牌车系'].unique()
    except Exception as e:
        print(f"读取CSV失败: {e}")
        return

    print(f"检测到 {len(series_list)} 个车系: {series_list}")
    
    all_results = []
    summary_stats = []
    
    for series in series_list:
        print(f"\n{'='*50}")
        print(f"正在处理: {series}")
        print(f"{'='*50}")
        
        # 1. 加载和清洗
        df_clean = modeler.load_and_clean_data(input_file, series, iqr_factor=1.0)
        if df_clean is None or df_clean.empty:
            print(f"[{series}] 跳过: 数据不足或清洗后无数据")
            continue
            
        # 2. 训练
        models = modeler.train_models(df_clean)
        
        # 3. 评估
        best_model = modeler.evaluate_and_recommend(models)
        
        if not best_model:
            print(f"[{series}] 跳过: 无有效模型")
            continue
            
        name, data = best_model
        print(f">> 选中模型: {name} (R2={data['r2']:.4f}, RMSE={data['rmse']:.4f})")
        
        # 4. 预测并计算误差
        # 这里我们需要手动执行 save_prediction_details 中的逻辑来获取带有误差列的 df
        if name == 'Polynomial':
            params = data['params']
            predict_func = lambda x: np.polyval(params, x)
        elif name == 'Exponential':
            params = data['params']
            predict_func = lambda x: modeler.exponential_model(x, *params)
        elif name == 'Power':
            params = data['params']
            predict_func = lambda x: modeler.power_model(x, *params)
            
        # 预测
        df_clean = df_clean.copy()
        df_clean['预测保值率'] = df_clean['使用年限'].apply(predict_func)
        df_clean['预测保值率'] = df_clean['预测保值率'].clip(lower=0)
        
        df_clean['预测值'] = df_clean['预测保值率'] * df_clean['新车的价格']
        df_clean['预测值'] = df_clean['预测值'].round(2)
        
        df_clean['误差'] = df_clean['预测值'] - df_clean['车况校正价']
        df_clean['误差'] = df_clean['误差'].round(2)
        
        df_clean['误差率'] = df_clean.apply(lambda row: round(row['误差'] / row['车况校正价'], 4) if row['车况校正价'] != 0 else 0.0, axis=1)
        
        def calc_error_level(rate):
            v = abs(rate)
            if v <= 0.03: return 0
            if v <= 0.10: return 1
            return int(np.ceil(v * 10))

        df_clean['误差等级'] = df_clean['误差率'].apply(calc_error_level)
        df_clean['最佳模型'] = name
        
        all_results.append(df_clean)
        
        # 统计信息
        mape = np.mean(np.abs(df_clean['误差率']))
        within_10pct = len(df_clean[abs(df_clean['误差率']) <= 0.10])
        total = len(df_clean)
        
        summary_stats.append({
            '品牌车系': series,
            '样本数': total,
            '最佳模型': name,
            'R2': data['r2'],
            'RMSE': data['rmse'],
            'MAPE(平均绝对误差率)': mape,
            '10%以内准确率': within_10pct / total
        })

    # 合并所有结果
    if all_results:
        final_df = pd.concat(all_results, ignore_index=True)
        
        # 保存详细结果
        target_cols = [
            '数据来源', '车辆全称', '品牌车系', '新车的价格', '二手车的成交价', '车况校正价', 
            '使用年限', '车辆评级', '车辆大类', '车辆小类', '车辆属性', '城市', '行驶里程',
            '预测值', '误差', '误差率', '误差等级', '最佳模型'
        ]
        
        # 补齐列
        for col in target_cols:
            if col not in final_df.columns:
                final_df[col] = ''
                
        final_df[target_cols].to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\n{'='*50}")
        print(f"全部处理完成！详细结果已保存至: {output_file}")
        
        # 生成分析报告
        print_analysis_report(final_df, summary_stats)
        
    else:
        print("未生成任何有效结果。")

def print_analysis_report(df, summary_stats):
    print("\n" + "#" * 30)
    print("      数据源精确度分析报告      ")
    print("#" * 30)
    
    total_samples = len(df)
    print(f"\n1. 总体概况")
    print(f"   - 总有效样本数: {total_samples}")
    
    # 总体误差分布
    mape_overall = np.mean(np.abs(df['误差率']))
    print(f"   - 总体 MAPE (平均绝对误差率): {mape_overall:.2%}")
    
    level_counts = df['误差等级'].value_counts().sort_index()
    print(f"\n2. 误差等级分布 (越低越好)")
    print(f"   - Level 0 (误差<=3%):   {level_counts.get(0, 0)} ({level_counts.get(0, 0)/total_samples:.1%})")
    print(f"   - Level 1 (3%<误差<=10%): {level_counts.get(1, 0)} ({level_counts.get(1, 0)/total_samples:.1%})")
    print(f"   - Level 2 (10%<误差<=20%): {level_counts.get(2, 0)} ({level_counts.get(2, 0)/total_samples:.1%})")
    print(f"   - Level 3+ (误差>20%):    {level_counts[level_counts.index >= 3].sum()} ({level_counts[level_counts.index >= 3].sum()/total_samples:.1%})")
    
    print(f"\n3. 各车系表现详情")
    summary_df = pd.DataFrame(summary_stats)
    # 格式化输出
    print(summary_df.to_string(index=False, formatters={
        'R2': '{:.4f}'.format,
        'RMSE': '{:.4f}'.format,
        'MAPE(平均绝对误差率)': '{:.2%}'.format,
        '10%以内准确率': '{:.1%}'.format
    }))

if __name__ == "__main__":
    input_csv = "../output/residual_value_data.csv"
    output_csv = "../output/batch_modeling_results.csv"
    
    # 如果在 src 目录下运行，调整路径
    if Path("residual_value_modeling_step3.py").exists():
        # 我们在 src 目录
        pass
    else:
        # 假设在根目录运行，且 script 在 src
        sys.path.append("src")
        input_csv = "output/residual_value_data.csv"
        output_csv = "output/batch_modeling_results.csv"

    batch_process(input_csv, output_csv)
