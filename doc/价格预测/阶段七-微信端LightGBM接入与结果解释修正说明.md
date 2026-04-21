# 阶段七：微信端 LightGBM 接入与结果解释修正说明

> 记录日期：2026-04-17
> 目标：
> 1. 修正微信端后端预测器初始化方式
> 2. 让微信端默认使用当前主模型 `lightgbm`
> 3. 修正小程序 `result` 页中的“影响因素”展示，使其与 `LightGBM` 多特征模型解释一致

## 1. 本次发现的问题

在检查 `wechat` 目录时，发现存在两个问题：

### 1.1 微信后端没有真正复用单例预测器

虽然 `wechat/backend/main.py` 设计了单例预测器，但 `wechat/backend/api.py` 在接口内部仍然反复执行：

- `from residual_predictor_step5 import ResidualPredictor`
- `ResidualPredictor(...)`

这会导致：

1. 每次请求重复初始化预测器
2. 单例补丁无法稳定生效
3. 启动性能和请求性能都受到影响

### 1.2 微信后端使用的数据源过小

微信端原来固定使用：

- `output/residual_value_data_for_build_model.csv`

这份数据只有约 `1` 万条，远小于当前主链路使用的：

- `output/merged_residual_value_data_with_dates.csv`

因此会导致：

1. 微信端相似车检索覆盖范围偏小
2. 与主 Web 端的行为不完全一致

### 1.3 小程序 `result` 页的“影响因素”说明不够准确

小程序结果页虽然已经展示 `result.explanation.factors`，但页面上没有明确区分：

- `LightGBM` 特征贡献
- 旧 `curve` 规则解释

这会导致用户难以判断当前显示的因素究竟来自模型真实贡献，还是规则推断。

## 2. 本次修改内容

## 2.1 微信后端：统一预测器获取方式

修改文件：

- `wechat/backend/main.py`
- `wechat/backend/api.py`

### 修改点 A：新增统一数据源选择逻辑

在 `wechat/backend/main.py` 中新增：

- `resolve_wechat_residual_data()`

优先级固定为：

1. `output/merged_residual_value_data_with_dates.csv`
2. `output/merged_residual_value_data.csv`
3. `output/residual_value_data_for_build_model.csv`

这样微信端默认使用与主链路更一致、覆盖更完整的数据源。

### 修改点 B：真正注入共享预测器

在 `wechat/backend/main.py` 中，不再通过替换 `ResidualPredictor` 类实现补丁，而是改为向 `api.py` 注入：

- `get_shared_predictor`

在 `wechat/backend/api.py` 中新增：

- `_get_predictor_instance()`

优先逻辑：

1. 若 `main.py` 已注入 `get_shared_predictor`
2. 则直接复用单例
3. 否则再按兜底逻辑本地初始化

这样可以保证：

- WebChat backend 真正复用单例预测器
- 不再每个请求重复初始化

## 2.2 微信后端：默认继续跟随主模型为 `lightgbm`

本次修改后，微信端仍通过：

- `ResidualPredictor`

读取统一的：

- `config/model_strategy.yaml`

因此当前默认模型家族保持为：

```yaml
default_model_family: lightgbm
allow_curve_fallback: true
```

这意味着：

1. 微信端默认优先使用 `lightgbm`
2. 当 `lightgbm` 失败时仍允许自动回退到 `curve`

## 2.3 小程序结果页：修正影响因素说明

修改文件：

- `wechat/miniprogram/pages/result/result.wxml`

新增展示内容：

1. `解释来源`
2. `LightGBM 特征贡献` / `规则推断`
3. 在 `LightGBM` 场景下，将标题改为：
   - `模型影响因素`
4. 在 `LightGBM` 场景下增加提示语：
   - 当前显示的是模型对预测价格的近似贡献

这样用户可以在微信小程序结果页直接看出：

- 当前解释是否来自 `LightGBM`
- “影响因素”是否为真实模型贡献

## 3. 修改后的效果

### 3.1 微信端预测器行为

修改后，微信端具备以下行为：

1. 启动时懒加载预测器
2. 后续请求复用同一个预测器实例
3. 数据索引默认使用更完整的 `merged_residual_value_data_with_dates.csv`
4. 默认模型家族为 `lightgbm`

### 3.2 小程序 result 页行为

修改后：

1. 若主模型为 `lightgbm`
   - 页面会显示 `解释来源: LightGBM 特征贡献`
   - “影响因素”标题会显示为 `模型影响因素`
2. 若主模型为 `curve`
   - 页面会显示 `解释来源: 规则推断`
   - 保留旧的因素解释方式

## 4. 本次验证结果

本次已完成本地 smoke test。

### 4.1 单例预测器验证

结果：

- `singleton_same = true`

说明：

- 微信后端的预测器单例已真正生效

### 4.2 默认模型验证

结果：

- `default_model_family = lightgbm`

说明：

- 微信后端默认已与主链路保持一致，优先使用 `lightgbm`

### 4.3 数据索引规模验证

结果：

- `records_count = 142322`

说明：

- 微信后端已经不再只使用 1 万条级别的小数据集
- 当前索引覆盖已与主链路一致

### 4.4 结果解释验证

结果：

- `explanation_source = lightgbm_pred_contrib`
- `factor_labels` 为：
  - `车龄`
  - `行驶里程`
  - `车况评级`
  - `城市`
  - `新车指导价`

说明：

- 微信端结果页现在使用的“影响因素”已经来自 `LightGBM` 的真实特征贡献

## 5. 结论

本次修改后：

1. 微信端模型预测默认已正常跟随当前主模型 `lightgbm`
2. 微信后端不再重复初始化预测器
3. 微信端相似车索引与主链路使用同级别数据集
4. 微信小程序 `result` 页中的“影响因素”已经能够明确区分解释来源
5. 在 `lightgbm` 场景下，“影响因素”已与 `LightGBM` 多特征模型解释保持一致
