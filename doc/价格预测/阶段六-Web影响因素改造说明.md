# 阶段六：Web 影响因素改造说明

> 记录日期：2026-04-17
> 目标：将 Web 界面中的“影响因素”从启发式规则说明，升级为 `LightGBM` 场景下基于模型真实特征贡献的解释

## 1. 改造前的问题

改造前，Web 界面中的“影响因素”栏虽然能够展示：

- 车龄
- 里程
- 车况

等内容，但这些因素并不是来自 `LightGBM` 多特征模型本身，而是由 `price_logic_step6.py` 中的固定启发式规则生成。

这带来两个问题：

1. 当主模型已经切换到 `lightgbm` 时，界面显示的“影响因素”并不是真实的模型贡献
2. 用户无法分辨当前解释是“规则推断”还是“模型真实判断”

## 2. 改造目标

本次改造的目标是：

1. 在 `lightgbm` 场景下，展示模型真实特征贡献
2. 在 `curve` 场景下，继续保留原有规则解释作为兼容兜底
3. 在 Web 界面中明确标出解释来源
4. 不改变 `/predict` 顶层接口结构

## 3. 改造思路

整体思路分三层：

### 3.1 模型层

在 `LightGBMResidualModel` 中新增特征贡献输出能力：

- 基于 `LightGBMRegressor.predict(..., pred_contrib=True)` 获取单样本特征贡献
- 输出每个特征的：
  - 残值率贡献
  - 换算后的价格贡献

### 3.2 预测链路层

将模型贡献从模型封装层透传到预测主链路：

1. `PricePredictor` 在命中 `lightgbm` 时，把特征贡献放入 `PredictionResult`
2. `ResidualPredictor` 再把它挂到 `debug`
3. 如果后续有启发式价格放大，则同步按比例缩放价格贡献

### 3.3 解释与前端层

1. `PriceExplainer` 新增 `lightgbm` 分支
2. 若 `debug.explanation_source == lightgbm_pred_contrib`
   - 优先使用真实特征贡献生成 `factors`
3. 否则继续走旧规则解释
4. 前端显示“解释来源”，区分：
   - `LightGBM 特征贡献`
   - `规则推断`

## 4. 实际修改文件

### 4.1 `src/lightgbm_residual_model.py`

新增方法：

- `predict_contributions(features)`

作用：

- 调用 `pred_contrib=True`
- 输出 bias 项与各特征贡献

### 4.2 `src/price_predictor_step5.py`

修改内容：

1. `PredictionResult` 新增字段：
   - `feature_contributions`
   - `explanation_source`
2. `lightgbm` 品牌车系 / 车型类别预测时：
   - 计算模型贡献
   - 将贡献放进返回结果
3. `curve` 场景下：
   - 仍标记 `explanation_source=heuristic_rules`

### 4.3 `src/residual_predictor_step5.py`

修改内容：

1. `PredictionDebugInfo` 新增字段：
   - `explanation_source`
   - `feature_contributions`
2. 主链路模型预测成功时，将贡献写入 `debug`
3. 当启发式修正调整了 `model_prediction` 后，同步缩放价格贡献，保证解释数值与展示价格一致

### 4.4 `src/price_logic_step6.py`

修改内容：

1. `PriceExplanationReport` 新增：
   - `explanation_source`
2. 新增 `FEATURE_LABELS`
3. 新增：
   - `extract_lightgbm_factors()`
   - `_describe_lightgbm_feature()`
4. `generate_report()` 改为双分支：
   - `lightgbm` 使用真实特征贡献
   - `curve` 继续使用启发式规则解释

### 4.5 `src/web/templates/home.html`

修改内容：

1. 新增“解释来源”展示
2. `lightgbm` 场景下将标题调整为：
   - `模型影响因素`
3. 增加提示语：
   - 当前显示的是 `LightGBM` 对预测价格的近似贡献

## 5. 改造后的行为

### 5.1 LightGBM 场景

现在 Web 界面中的“影响因素”会优先显示模型真实特征贡献，典型展示为：

- `车龄`
- `行驶里程`
- `车况评级`
- `城市`
- `新车指导价`

这些项来自 `LightGBM` 的真实贡献，而不是旧规则手工拼出的解释。

### 5.2 curve 场景

旧 `curve` 场景不受影响，仍保留：

- 车龄高 / 车龄低
- 里程高 / 里程少
- 车况中等 / 车况优秀

等规则解释。

## 6. 验证结果

本次已完成本地 smoke test：

### 6.1 LightGBM 场景

验证结果：

- `model_family = lightgbm`
- `explanation_source = lightgbm_pred_contrib`
- `factor_labels` 输出为：
  - `车龄`
  - `行驶里程`
  - `车况评级`
  - `城市`
  - `新车指导价`

说明：

- Web 影响因素已经切换为基于 `LightGBM` 模型贡献

### 6.2 curve 场景

验证结果：

- `model_family = curve`
- `explanation_source = heuristic_rules`

说明：

- 旧模型场景仍使用启发式解释，兼容性保持不变

## 7. 当前结论

本次改造后：

1. Web 界面中的“影响因素”在 `lightgbm` 场景下，已经不再是旧启发式逻辑
2. 其内容已经基于 `LightGBM` 的真实特征贡献生成
3. 用户可以在界面上明确看到“解释来源”
4. `curve` 场景继续保留原有规则解释作为兜底

因此，可以认为这次“Web 影响因素栏与 LightGBM 多特征模型对齐”的目标已经完成。
