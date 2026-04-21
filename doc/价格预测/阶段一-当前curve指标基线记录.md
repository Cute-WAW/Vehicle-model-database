# 阶段一：当前 curve 指标基线记录

> 记录日期：2026-04-14
> 对应任务：`LightGBM模型改造实施清单.md` 阶段一「记录当前 curve 指标」

## 1. 结论先看

本次已将当前 `curve` 体系的基线分成两层记录，便于后续与 `LightGBM` 做对照：

1. `curve` 模型层基线：本地可复现，直接评估曲线模型本身，不包含相似车微调和价格矩阵。
2. `/predict` 整体链路基线：基于项目内已有优信拍真实成交测评结果，反映当前线上风格接口的整体表现。

当前建议后续改造时同时对齐这两层口径，不要只看其中一层。

## 2. 当前 curve 工作流程

当前主流程不是直接调用 `src/price_predictor_step5.py`，而是：

`src/web_predictor_debug_step5.py`
-> `src/residual_predictor_step5.py`
-> `src/price_predictor_step5.py`
-> `src/price_logic_step6.py`

其中关键步骤如下：

1. `/predict` 入口在 `src/web_predictor_debug_step5.py`，实际预测由 `ResidualPredictor.predict(...)` 执行。
2. `ResidualPredictor` 先检索相似车辆，用于辅助推断 `new_price`，数据源优先读取 `output/cheyipai_more_residual_value.csv`，不存在时回退到 `output/merged_residual_value_data_with_dates.csv` 或 `output/merged_residual_value_data.csv`。
3. `PricePredictor.predict_by_brand_series(...)` 的模型优先级为：
   - 分段品牌车系模型 `output/segmented_models`
   - 全量品牌车系模型 `output/brand_series_models`
   - 车型类别模型 `output/car_types_models`
4. 曲线模型本体来自 `src/batch_model_trainer_step4.py`，候选函数只有三类：
   - `Exponential`
   - `Polynomial`
   - `Power`
5. 得到曲线模型预测价后，`ResidualPredictor` 会继续叠加：
   - 新能源/新车/高价车的启发式微调
   - 相似车辆均价的 `confidence_dynamic` 微调
   - `C2B2CPricePredictor` 生成 `price_matrix`
6. 因此 `/predict` 对外返回值不是“纯 curve 模型输出”，而是“curve 模型 + 相似车 + 规则 + 价格矩阵”的组合结果。

## 3. 当前模型资产

按当前统一目录统计：

| 模型目录 | 数量 | 说明 |
|:---|---:|:---|
| `output/brand_series_models` | 119 | 全量品牌车系曲线模型 |
| `output/car_types_models` | 25 | 车型类别兜底模型 |
| `output/segmented_models` | 524 | 按车龄分段的品牌车系曲线模型 |

这与当前运行时“优先分段品牌车系、失败后再回退”的策略一致。

## 4. 基线口径一：curve 模型层指标

### 4.1 口径说明

这一层只看曲线模型本身的预测表现，使用 `src/evaluate_model_performance.py` 在本地复算。

- 数据集：`output/batch_modeling_results.csv`
- 样本数：1146
- 评估对象：
  - 品牌车系曲线模型
  - 车型类别曲线模型
  - 真实应用下的“品牌车系优先、车型类别兜底”混合策略
- 不包含：
  - 相似车微调
  - 新车价自动推断失败带来的覆盖率问题
  - `C2B2C` 价格矩阵

### 4.2 复现命令

在项目根目录执行：

```powershell
$env:PYTHONIOENCODING='utf-8'
..\venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); from evaluate_model_performance import evaluate_models_performance; evaluate_models_performance('output/batch_modeling_results.csv')"
```

### 4.3 本次记录结果

| 口径 | 覆盖率 | MAE(万元) | MAPE | R² |
|:---|---:|---:|---:|---:|
| 品牌车系曲线模型 | 100.0% | 0.92 | 27.11% | 0.8730 |
| 车型类别曲线模型 | 100.0% | 1.26 | 41.81% | 0.8312 |
| 混合策略 | 100.0% | - | 27.11% | 0.8730 |

补充观察：

- 品牌车系模型明显优于车型类别模型，后续 `LightGBM` 首版应优先对齐品牌车系主链路。
- 本地复算中，1146 条样本全部命中品牌车系模型，没有落到车型类别兜底。
- 本地复算时品牌车系模型类型分布为：
  - `Exponential(segmented)`: 535
  - `Polynomial(segmented)`: 404
  - `Power(segmented)`: 207
- 车型类别模型在本地复算中全部为 `Polynomial`。

### 4.4 本地重点品牌结果

| 品牌车系 | 样本量 | MAPE | 当前模型类型 |
|:---|---:|---:|:---|
| 日产-轩逸 | 286 | 34.69% | `Power(segmented)` |
| 大众-朗逸 | 275 | 19.51% | `Exponential(segmented)` |
| 丰田-汉兰达 | 155 | 20.33% | `Exponential(segmented)` |
| 别克-英朗 | 154 | 26.93% | `Exponential(segmented)` |
| 宝马-5系 | 80 | 31.24% | `Exponential(segmented)` |

## 5. 基线口径二：`/predict` 整体链路指标

### 5.1 口径说明

这一层记录当前对外预测链路的整体表现，直接采用项目内已有测评产物：

- 报告：`doc/价格预测/优信拍真实成交数据测评报告.md`
- 明细：`experiment/youxinpai_eval_results.csv`
- 统计：`experiment/youxinpai_eval_stats.json`

这套结果生成于 2026-03-04，对应脚本为 `experiment/youxinpai_evaluation.py`，调用的是当时的 `/predict` 接口，因此包含：

- 曲线模型预测
- 新车价自动推断
- 相似车微调
- `price_matrix`
- 接口级失败情况

### 5.2 当前记录结果

| 指标 | 数值 |
|:---|---:|
| 总样本数 | 799 |
| API 成功数 | 312 |
| API 成功率 | 39.05% |
| C2B 命中率 | 28.21% |
| B2B 命中率 | 42.95% |
| MAE | 0.532 万元 |
| MAPE | 18.77% |
| 中位数 APE | 13.03% |
| R² | 0.9466 |

补充观察：

- 312 条成功样本中，`debug.model_used` 全部为 `brand_series`。
- 487 条失败样本的失败原因都相同：`无法确定新车价格，请提供 new_price 参数`。
- 这说明当前整体链路的主要瓶颈并不是 curve 函数本体，而是 `new_price` 推断覆盖率。

## 6. 阶段一建议采用的对照基线

后续做 `LightGBM` 对照时，建议直接沿用下面两套基线：

### 6.1 模型层基线

用于回答“新模型本身是否优于旧 curve 模型”：

- 品牌车系：`MAPE 27.11%`，`R² 0.8730`
- 车型类别：`MAPE 41.81%`，`R² 0.8312`

### 6.2 整体链路基线

用于回答“新模型接入 `/predict` 后整体效果是否更好”：

- API 成功率：`39.05%`
- B2B 命中率：`42.95%`
- MAPE：`18.77%`
- R²：`0.9466`

## 7. 本次记录的边界说明

本次阶段一工作已完成“记录当前 curve 指标”，但需要明确两个边界：

1. 本地复算的是曲线模型层指标，可稳定复现，但不代表完整 `/predict` 链路。
2. `/predict` 整体链路指标本次采用项目内现有测评结果进行归档，没有在 2026-04-14 再次重跑远端接口。

因此后续如果要做最终切换决策，仍建议在同一套外部验证集上重新跑一版 `curve` 与 `LightGBM` 的并行对照。
