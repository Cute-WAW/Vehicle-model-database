# 测试框架规格说明 (Testing Framework Spec)

## 1. 目标

建立完整的测试体系，确保系统版本更新时的稳定性和准确率。

---

## 2. 测试层级

| 层级 | 类型 | 覆盖范围 |
|------|------|----------|
| L1 | 单元测试 | 各模块独立功能 |
| L2 | 集成测试 | 模块间协作 |
| L3 | 回归测试 | 标准测试集验证 |
| L4 | 性能测试 | 速度和资源消耗 |

---

## 3. 测试数据集格式

### 3.1 基础测试集
```csv
# tests/test_cases.csv
id,input_text,expected_level_id,expected_brand,expected_series,expected_year,category,notes
1,"宝马/X1/2016款 2.0T 自动 20Li豪华型前驱",BMW0X10A0015,宝马,X1,2016,燃油车,标准案例
2,"特斯拉 Model 3 2023款 长续航版",TES0M30A0005,特斯拉,Model 3,2023,电动车,纯电案例
3,"中升车源\n大众 帕萨特 2023款 1.4TSI 双离合 280TSI",VW0PS0A0023,大众,帕萨特,2023,燃油车,带噪音前缀
```

### 3.2 实体识别测试集
```csv
# tests/entity_test_cases.csv
id,input_text,expected_brand,expected_series,expected_year,expected_displacement,expected_transmission,expected_trim
1,"2.0T 自动 豪华版",,,,2.0T,自动,豪华版
2,"420KM 冠军版 超越型",,,,,冠军版 超越型
```

---

## 4. 评估指标

### 4.1 准确率指标

| 指标 | 计算方式 | 目标值 |
|------|----------|--------|
| Top1 Accuracy | Top1 == expected | > 85% |
| Top5 Recall | expected in Top5 | > 95% |
| Brand Accuracy | 品牌识别正确率 | > 98% |
| Year Accuracy | 年款识别正确率 | > 95% |

### 4.2 性能指标

| 指标 | 目标值 |
|------|--------|
| 平均单次查询时间 | < 15ms |
| P99 查询时间 | < 50ms |
| 批量 1000 条处理时间 | < 5s |

---

## 5. 接口定义

```python
class TestRunner:
    """测试运行器"""
    
    def __init__(self, matching_engine: MatchingEngine):
        self.engine = matching_engine
    
    def load_test_cases(self, path: str) -> List[TestCase]:
        """加载测试用例"""
        pass
    
    def run_tests(
        self, 
        test_cases: List[TestCase],
        verbose: bool = False
    ) -> TestReport:
        """
        运行测试
        
        Returns:
            TestReport: 测试报告
        """
        pass
    
    def run_performance_test(
        self,
        queries: List[str],
        iterations: int = 3
    ) -> PerformanceReport:
        """运行性能测试"""
        pass


@dataclass
class TestReport:
    total_cases: int
    passed_cases: int
    failed_cases: int
    top1_accuracy: float
    top5_recall: float
    brand_accuracy: float
    year_accuracy: float
    failed_details: List[FailedCase]
    
    def to_markdown(self) -> str:
        """生成 Markdown 格式报告"""
        pass


@dataclass
class PerformanceReport:
    avg_time_ms: float
    p50_time_ms: float
    p95_time_ms: float
    p99_time_ms: float
    throughput: float  # queries/sec
```

---

## 6. 测试命令

```bash
# 运行单元测试
python -m pytest tests/ -v

# 运行回归测试
python scripts/run_benchmark.py --test-set tests/test_cases.csv

# 运行性能测试
python scripts/run_benchmark.py --performance --iterations 5

# 生成测试报告
python scripts/run_benchmark.py --test-set tests/test_cases.csv --output reports/test_report.md
```

---

## 7. CI/CD 集成

```yaml
# .github/workflows/test.yml (示例)
name: Run Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: python -m pytest tests/ -v
      - name: Run benchmark
        run: python scripts/run_benchmark.py --test-set tests/test_cases.csv
```

---

## 8. 测试报告模板

```markdown
# 车型库映射测试报告

## 概览
- 测试时间: 2025-12-19 20:30:00
- 测试用例数: 500
- 通过率: 92.4%

## 准确率指标
| 指标 | 结果 | 目标 | 状态 |
|------|------|------|------|
| Top1 Accuracy | 87.2% | > 85% | ✅ |
| Top5 Recall | 96.8% | > 95% | ✅ |
| Brand Accuracy | 99.2% | > 98% | ✅ |

## 性能指标
| 指标 | 结果 | 目标 | 状态 |
|------|------|------|------|
| Avg Time | 12.3ms | < 15ms | ✅ |
| P99 Time | 45.2ms | < 50ms | ✅ |

## 失败案例
| ID | 输入 | 期望 | 实际 | 原因 |
|----|------|------|------|------|
| 23 | ... | ... | ... | 品牌别名未识别 |
```

---

## 9. 验收标准

- [ ] 测试集覆盖 500+ 案例
- [ ] 燃油车/电动车各占 50%
- [ ] 包含边界案例 (噪音、缺失实体)
- [ ] Top1 准确率 > 85%
- [ ] 测试报告自动生成
