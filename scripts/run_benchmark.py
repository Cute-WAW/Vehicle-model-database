"""
测试运行器 - 回归测试和性能测试
根据 .spec/spec_testing.md 规格实现
"""
import sys
import csv
import time
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.entity_extractor import EntityExtractor
from src.vehicle_index import VehicleIndex
from src.matching_engine import MatchingEngine


@dataclass
class TestCase:
    """测试用例"""
    id: int
    input_text: str
    expected_level_id: Optional[str]
    expected_brand: Optional[str]
    expected_series: Optional[str]
    expected_year: Optional[int]
    category: str
    notes: str


@dataclass
class TestResult:
    """测试结果"""
    test_case: TestCase
    passed: bool
    actual_brand: Optional[str]
    actual_series: Optional[str]
    actual_year: Optional[int]
    actual_level_id: Optional[str]
    actual_score: float
    error_message: str = ""


@dataclass
class TestReport:
    """测试报告"""
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    
    # 准确率指标
    top1_accuracy: float = 0.0
    top5_recall: float = 0.0
    brand_accuracy: float = 0.0
    series_accuracy: float = 0.0
    year_accuracy: float = 0.0
    
    # 性能指标
    avg_time_ms: float = 0.0
    p50_time_ms: float = 0.0
    p95_time_ms: float = 0.0
    p99_time_ms: float = 0.0
    
    # 详细结果
    results: List[TestResult] = field(default_factory=list)
    failed_details: List[TestResult] = field(default_factory=list)
    
    def to_markdown(self) -> str:
        """生成 Markdown 格式报告"""
        report = f"""# 车型库映射测试报告

## 概览
- **测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **测试用例数**: {self.total_cases}
- **通过数**: {self.passed_cases}
- **失败数**: {self.failed_cases}
- **通过率**: {(self.passed_cases / self.total_cases * 100) if self.total_cases > 0 else 0:.1f}%

## 准确率指标

| 指标 | 结果 | 目标 | 状态 |
|------|------|------|------|
| 品牌识别准确率 | {self.brand_accuracy:.1f}% | > 98% | {'✅' if self.brand_accuracy > 98 else '❌'} |
| 车系识别准确率 | {self.series_accuracy:.1f}% | > 95% | {'✅' if self.series_accuracy > 95 else '❌'} |
| 年款识别准确率 | {self.year_accuracy:.1f}% | > 95% | {'✅' if self.year_accuracy > 95 else '❌'} |

## 性能指标

| 指标 | 结果 | 目标 | 状态 |
|------|------|------|------|
| 平均处理时间 | {self.avg_time_ms:.2f}ms | < 15ms | {'✅' if self.avg_time_ms < 15 else '❌'} |
| P95 处理时间 | {self.p95_time_ms:.2f}ms | < 50ms | {'✅' if self.p95_time_ms < 50 else '❌'} |
| P99 处理时间 | {self.p99_time_ms:.2f}ms | < 50ms | {'✅' if self.p99_time_ms < 50 else '❌'} |

"""
        if self.failed_details:
            report += "## 失败案例\n\n"
            report += "| ID | 输入 | 期望品牌 | 实际品牌 | 期望车系 | 实际车系 | 原因 |\n"
            report += "|----|------|----------|----------|----------|----------|------|\n"
            for r in self.failed_details[:20]:  # 只显示前20个
                report += f"| {r.test_case.id} | {r.test_case.input_text[:30]}... | {r.test_case.expected_brand} | {r.actual_brand} | {r.test_case.expected_series} | {r.actual_series} | {r.error_message} |\n"
        
        return report


class TestRunner:
    """测试运行器"""
    
    def __init__(self, matching_engine: MatchingEngine):
        self.engine = matching_engine
    
    def load_test_cases(self, path: str) -> List[TestCase]:
        """加载测试用例"""
        test_cases = []
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                test_cases.append(TestCase(
                    id=int(row['id']),
                    input_text=row['input_text'],
                    expected_level_id=row.get('expected_level_id') or None,
                    expected_brand=row.get('expected_brand') or None,
                    expected_series=row.get('expected_series') or None,
                    expected_year=int(row['expected_year']) if row.get('expected_year') else None,
                    category=row.get('category', ''),
                    notes=row.get('notes', '')
                ))
        return test_cases
    
    def run_tests(
        self, 
        test_cases: List[TestCase],
        verbose: bool = False
    ) -> TestReport:
        """运行测试"""
        report = TestReport()
        report.total_cases = len(test_cases)
        
        times = []
        brand_correct = 0
        series_correct = 0
        year_correct = 0
        
        for tc in test_cases:
            start = time.time()
            result = self.engine.match(tc.input_text)
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)
            
            # 获取实际结果
            entities = result.extracted_entities
            actual_brand = entities.get('brand')
            actual_series = entities.get('series')
            actual_year = entities.get('year')
            
            # 获取 Top1 匹配结果
            actual_level_id = None
            actual_score = 0.0
            if result.matches:
                actual_level_id = result.matches[0].level_id
                actual_score = result.matches[0].score
            
            # 判断是否通过
            passed = True
            errors = []
            
            # 品牌判断
            if tc.expected_brand:
                if actual_brand == tc.expected_brand:
                    brand_correct += 1
                else:
                    passed = False
                    errors.append(f"品牌不匹配: 期望{tc.expected_brand}, 实际{actual_brand}")
            
            # 车系判断
            if tc.expected_series:
                if actual_series == tc.expected_series:
                    series_correct += 1
                else:
                    passed = False
                    errors.append(f"车系不匹配: 期望{tc.expected_series}, 实际{actual_series}")
            
            # 年款判断
            if tc.expected_year:
                if actual_year == tc.expected_year:
                    year_correct += 1
                else:
                    passed = False
                    errors.append(f"年款不匹配")
            
            test_result = TestResult(
                test_case=tc,
                passed=passed,
                actual_brand=actual_brand,
                actual_series=actual_series,
                actual_year=actual_year,
                actual_level_id=actual_level_id,
                actual_score=actual_score,
                error_message="; ".join(errors)
            )
            
            report.results.append(test_result)
            
            if passed:
                report.passed_cases += 1
            else:
                report.failed_cases += 1
                report.failed_details.append(test_result)
            
            if verbose:
                status = "✅" if passed else "❌"
                print(f"{status} [{tc.id}] {tc.input_text[:40]}... -> {actual_brand}/{actual_series}/{actual_year}")
        
        # 计算准确率
        brand_total = sum(1 for tc in test_cases if tc.expected_brand)
        series_total = sum(1 for tc in test_cases if tc.expected_series)
        year_total = sum(1 for tc in test_cases if tc.expected_year)
        
        report.brand_accuracy = (brand_correct / brand_total * 100) if brand_total > 0 else 0
        report.series_accuracy = (series_correct / series_total * 100) if series_total > 0 else 0
        report.year_accuracy = (year_correct / year_total * 100) if year_total > 0 else 0
        
        # 计算性能指标
        if times:
            times.sort()
            report.avg_time_ms = sum(times) / len(times)
            report.p50_time_ms = times[int(len(times) * 0.5)]
            report.p95_time_ms = times[int(len(times) * 0.95)]
            report.p99_time_ms = times[int(len(times) * 0.99)] if len(times) >= 100 else times[-1]
        
        return report
    
    def run_performance_test(
        self,
        queries: List[str],
        iterations: int = 3
    ) -> Dict[str, float]:
        """运行性能测试"""
        all_times = []
        
        for _ in range(iterations):
            for query in queries:
                start = time.time()
                self.engine.match(query)
                elapsed = (time.time() - start) * 1000
                all_times.append(elapsed)
        
        all_times.sort()
        
        return {
            "avg_time_ms": sum(all_times) / len(all_times),
            "p50_time_ms": all_times[int(len(all_times) * 0.5)],
            "p95_time_ms": all_times[int(len(all_times) * 0.95)],
            "p99_time_ms": all_times[-1],
            "total_queries": len(all_times),
            "throughput": len(all_times) / (sum(all_times) / 1000)  # queries/sec
        }


def main():
    parser = argparse.ArgumentParser(description='车型库匹配测试运行器')
    parser.add_argument('--test-set', type=str, default='tests/test_cases.csv',
                       help='测试数据集路径')
    parser.add_argument('--output', type=str, default=None,
                       help='报告输出路径')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='显示详细输出')
    parser.add_argument('--performance', action='store_true',
                       help='运行性能测试')
    parser.add_argument('--iterations', type=int, default=3,
                       help='性能测试迭代次数')
    
    args = parser.parse_args()
    
    # 切换到项目目录
    import os
    os.chdir(project_root)
    
    print("初始化匹配引擎...")
    
    # 初始化
    extractor = EntityExtractor("config/entity_rules.yaml")
    index = VehicleIndex(extractor)
    
    # 加载或构建索引
    index_path = Path("index/vehicle_index.pkl")
    if index_path.exists():
        index.load(str(index_path))
    else:
        import pandas as pd
        df = pd.read_csv("data/力洋车型库精简5.csv")
        index.build(df)
        index_path.parent.mkdir(exist_ok=True)
        index.save(str(index_path))
    
    engine = MatchingEngine(extractor, index, "config/matching_config.yaml")
    runner = TestRunner(engine)
    
    if args.performance:
        print("\n运行性能测试...")
        test_cases = runner.load_test_cases(args.test_set)
        queries = [tc.input_text for tc in test_cases]
        perf = runner.run_performance_test(queries, iterations=args.iterations)
        
        print("\n性能测试结果:")
        print(f"  平均时间: {perf['avg_time_ms']:.2f}ms")
        print(f"  P50 时间: {perf['p50_time_ms']:.2f}ms")
        print(f"  P95 时间: {perf['p95_time_ms']:.2f}ms")
        print(f"  P99 时间: {perf['p99_time_ms']:.2f}ms")
        print(f"  吞吐量: {perf['throughput']:.1f} queries/sec")
    else:
        print(f"\n加载测试用例: {args.test_set}")
        test_cases = runner.load_test_cases(args.test_set)
        print(f"共 {len(test_cases)} 个测试用例\n")
        
        print("运行测试...")
        report = runner.run_tests(test_cases, verbose=args.verbose)
        
        print("\n" + "=" * 50)
        print("测试结果摘要")
        print("=" * 50)
        print(f"总用例数: {report.total_cases}")
        print(f"通过: {report.passed_cases}")
        print(f"失败: {report.failed_cases}")
        print(f"通过率: {report.passed_cases / report.total_cases * 100:.1f}%")
        print()
        print(f"品牌准确率: {report.brand_accuracy:.1f}%")
        print(f"车系准确率: {report.series_accuracy:.1f}%")
        print(f"年款准确率: {report.year_accuracy:.1f}%")
        print()
        print(f"平均处理时间: {report.avg_time_ms:.2f}ms")
        print(f"P95 处理时间: {report.p95_time_ms:.2f}ms")
        
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report.to_markdown())
            print(f"\n报告已保存到: {args.output}")


if __name__ == "__main__":
    main()
