"""
专利性能验证测试脚本

功能：
1. 测试预测精度（MAPE）
2. 测试响应时间
3. 测试覆盖率
4. 生成测试报告

使用方法：
    python test_patent_performance.py
"""

import sys
import time
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
import logging

# 添加src路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from residual_predictor_step5 import ResidualPredictor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PerformanceValidator:
    """性能验证器"""
    
    def __init__(self, data_path: str):
        """
        初始化验证器
        
        Args:
            data_path: 测试数据路径
        """
        self.data_path = Path(data_path)
        self.predictor = ResidualPredictor()
        self.df = None
        self.results = []
        
    def load_test_data(self, sample_size: int = 500) -> pd.DataFrame:
        """
        加载测试数据
        
        Args:
            sample_size: 测试样本数量
            
        Returns:
            测试数据DataFrame
        """
        logger.info(f"加载测试数据: {self.data_path}")
        df = pd.read_csv(self.data_path)
        
        # 数据清洗
        df = df[df['新车的价格'] > 0.1]
        df = df[df['二手车的成交价'] > 0.1]
        df = df[(df['使用年限'] >= 0.5) & (df['使用年限'] <= 20)]
        
        # 随机采样
        if len(df) > sample_size:
            df = df.sample(n=sample_size, random_state=42)
        
        self.df = df
        logger.info(f"测试数据加载完成，共 {len(df)} 条记录")
        return df
    
    def test_prediction_accuracy(self) -> Dict:
        """
        测试预测精度
        
        Returns:
            精度测试结果
        """
        logger.info("开始测试预测精度...")
        
        predictions = []
        actuals = []
        errors = []
        response_times = []
        
        for idx, row in self.df.iterrows():
            try:
                # 记录响应时间
                start_time = time.time()
                
                result = self.predictor.predict(
                    vehicle_full_name=row['车辆全称'],
                    brand_series=row['品牌车系'],
                    years=float(row['使用年限']),
                    grade=row['车辆评级'],
                    city=row['城市'],
                    mileage=float(row.get('行驶里程', 0))
                )
                
                elapsed_time = (time.time() - start_time) * 1000  # 转换为毫秒
                response_times.append(elapsed_time)
                
                if result.success and result.predicted_price > 0:
                    pred_price = result.predicted_price
                    actual_price = float(row['车况校正价'])
                    
                    predictions.append(pred_price)
                    actuals.append(actual_price)
                    
                    # 计算误差
                    error = abs(pred_price - actual_price) / actual_price
                    errors.append(error)
                    
                    self.results.append({
                        '车辆全称': row['车辆全称'],
                        '品牌车系': row['品牌车系'],
                        '实际价格': actual_price,
                        '预测价格': pred_price,
                        '误差率': error,
                        '响应时间ms': elapsed_time,
                        '成功': True
                    })
                else:
                    self.results.append({
                        '车辆全称': row['车辆全称'],
                        '品牌车系': row['品牌车系'],
                        '实际价格': float(row['车况校正价']),
                        '预测价格': 0,
                        '误差率': np.nan,
                        '响应时间ms': elapsed_time,
                        '成功': False
                    })
                    
            except Exception as e:
                logger.warning(f"预测失败: {row['车辆全称']}, 错误: {e}")
                self.results.append({
                    '车辆全称': row['车辆全称'],
                    '品牌车系': row['品牌车系'],
                    '实际价格': float(row['车况校正价']),
                    '预测价格': 0,
                    '误差率': np.nan,
                    '响应时间ms': 0,
                    '成功': False
                })
        
        # 计算统计指标
        if errors:
            mape = np.mean(errors) * 100
            median_error = np.median(errors) * 100
            p90_error = np.percentile(errors, 90) * 100
            p95_error = np.percentile(errors, 95) * 100
        else:
            mape = median_error = p90_error = p95_error = 0
        
        if response_times:
            avg_response_time = np.mean(response_times)
            median_response_time = np.median(response_times)
            p95_response_time = np.percentile(response_times, 95)
        else:
            avg_response_time = median_response_time = p95_response_time = 0
        
        success_count = sum(1 for r in self.results if r['成功'])
        coverage_rate = success_count / len(self.results) * 100 if self.results else 0
        
        accuracy_results = {
            'MAPE': mape,
            '中位数误差率': median_error,
            'P90误差率': p90_error,
            'P95误差率': p95_error,
            '成功预测数': success_count,
            '总测试数': len(self.results),
            '覆盖率': coverage_rate,
            '平均响应时间ms': avg_response_time,
            '中位数响应时间ms': median_response_time,
            'P95响应时间ms': p95_response_time
        }
        
        logger.info(f"预测精度测试完成:")
        logger.info(f"  MAPE: {mape:.2f}%")
        logger.info(f"  覆盖率: {coverage_rate:.2f}%")
        logger.info(f"  平均响应时间: {avg_response_time:.2f}ms")
        
        return accuracy_results
    
    def analyze_by_category(self) -> Dict:
        """
        按类别分析性能
        
        Returns:
            分类分析结果
        """
        logger.info("开始分类分析...")
        
        results_df = pd.DataFrame(self.results)
        results_df = results_df[results_df['成功'] == True]
        
        # 合并原始数据
        results_df = results_df.merge(
            self.df[['车辆全称', '品牌车系', '车辆大类', '新车的价格']],
            on=['车辆全称', '品牌车系'],
            how='left'
        )
        
        # 按价格区间分类
        results_df['价格区间'] = pd.cut(
            results_df['新车的价格'],
            bins=[0, 10, 20, 100],
            labels=['经济型(<10万)', '中档型(10-20万)', '豪华型(>20万)']
        )
        
        category_stats = {}
        
        # 按价格区间统计
        for category in ['经济型(<10万)', '中档型(10-20万)', '豪华型(>20万)']:
            subset = results_df[results_df['价格区间'] == category]
            if len(subset) > 0:
                category_stats[category] = {
                    'MAPE': subset['误差率'].mean() * 100,
                    '样本数': len(subset),
                    '平均响应时间ms': subset['响应时间ms'].mean()
                }
        
        # 按车辆大类统计
        for car_type in results_df['车辆大类'].unique():
            if pd.notna(car_type):
                subset = results_df[results_df['车辆大类'] == car_type]
                if len(subset) > 0:
                    category_stats[f'车型_{car_type}'] = {
                        'MAPE': subset['误差率'].mean() * 100,
                        '样本数': len(subset),
                        '平均响应时间ms': subset['响应时间ms'].mean()
                    }
        
        return category_stats
    
    def generate_report(self, output_path: str) -> None:
        """
        生成测试报告
        
        Args:
            output_path: 报告输出路径
        """
        logger.info("生成测试报告...")
        
        # 测试精度
        accuracy_results = self.test_prediction_accuracy()
        
        # 分类分析
        category_stats = self.analyze_by_category()
        
        # 生成Markdown报告
        report_lines = [
            "# 专利性能验证测试报告",
            "",
            f"**测试时间**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**测试样本数**: {accuracy_results['总测试数']}",
            "",
            "## 1. 整体性能指标",
            "",
            "### 1.1 预测精度",
            "",
            f"- **平均绝对百分比误差（MAPE）**: {accuracy_results['MAPE']:.2f}%",
            f"- **中位数误差率**: {accuracy_results['中位数误差率']:.2f}%",
            f"- **P90误差率**: {accuracy_results['P90误差率']:.2f}%",
            f"- **P95误差率**: {accuracy_results['P95误差率']:.2f}%",
            "",
            "### 1.2 计算效率",
            "",
            f"- **平均响应时间**: {accuracy_results['平均响应时间ms']:.2f}ms",
            f"- **中位数响应时间**: {accuracy_results['中位数响应时间ms']:.2f}ms",
            f"- **P95响应时间**: {accuracy_results['P95响应时间ms']:.2f}ms",
            "",
            "### 1.3 覆盖率",
            "",
            f"- **成功预测数**: {accuracy_results['成功预测数']}",
            f"- **预测覆盖率**: {accuracy_results['覆盖率']:.2f}%",
            "",
            "## 2. 分类性能分析",
            "",
        ]
        
        # 添加分类统计
        for category, stats in category_stats.items():
            report_lines.extend([
                f"### {category}",
                "",
                f"- **MAPE**: {stats['MAPE']:.2f}%",
                f"- **样本数**: {stats['样本数']}",
                f"- **平均响应时间**: {stats['平均响应时间ms']:.2f}ms",
                ""
            ])
        
        # 添加详细结果表格
        report_lines.extend([
            "## 3. 详细测试结果（前20条）",
            "",
            "| 车辆全称 | 实际价格 | 预测价格 | 误差率 | 响应时间(ms) |",
            "|---------|---------|---------|--------|-------------|"
        ])
        
        results_df = pd.DataFrame(self.results)
        successful_results = results_df[results_df['成功'] == True].head(20)
        
        for _, row in successful_results.iterrows():
            report_lines.append(
                f"| {row['车辆全称'][:30]}... | {row['实际价格']:.2f} | "
                f"{row['预测价格']:.2f} | {row['误差率']*100:.2f}% | {row['响应时间ms']:.2f} |"
            )
        
        # 保存报告
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))
        
        logger.info(f"测试报告已保存: {output_file}")
        
        # 保存详细结果CSV
        csv_path = output_file.with_suffix('.csv')
        results_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        logger.info(f"详细结果已保存: {csv_path}")
        
        return accuracy_results, category_stats


def main():
    """主函数"""
    import os
    
    # 切换到项目根目录
    os.chdir(Path(__file__).parent.parent)
    
    # 数据路径
    data_path = 'output/residual_value_data.csv'
    
    if not Path(data_path).exists():
        print(f"错误: 数据文件不存在 {data_path}")
        return
    
    # 创建验证器
    validator = PerformanceValidator(data_path)
    
    # 加载测试数据
    validator.load_test_data(sample_size=500)
    
    # 生成报告
    report_path = 'output/patent_performance_test_report.md'
    accuracy_results, category_stats = validator.generate_report(report_path)
    
    print("\n" + "="*60)
    print("测试完成！主要指标：")
    print("="*60)
    print(f"MAPE: {accuracy_results['MAPE']:.2f}%")
    print(f"覆盖率: {accuracy_results['覆盖率']:.2f}%")
    print(f"平均响应时间: {accuracy_results['平均响应时间ms']:.2f}ms")
    print(f"P95响应时间: {accuracy_results['P95响应时间ms']:.2f}ms")
    print("="*60)
    print(f"\n详细报告已保存至: {report_path}")


if __name__ == '__main__':
    main()
