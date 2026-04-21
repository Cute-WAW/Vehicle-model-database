# 阶段三：LightGBM 模型封装与训练流程说明

> 记录日期：2026-04-15
> 对应阶段：`LightGBM模型改造实施清单.md` 阶段 3「新增模型封装与训练流程」

## 1. 本阶段完成内容

本阶段已新增一套与旧 `curve` 模型并行的 `LightGBM` 模型封装与训练流程，目标是做到：

1. 模型文件可单独加载并完成预测
2. 模型文件内包含运行时所需的元数据
3. 训练脚本可直接产出品牌车系模型、车型类别模型和评估报告

## 2. 新增代码文件

- `src/lightgbm_residual_model.py`
- `src/lightgbm_trainer.py`
- `src/build_lightgbm_models.py`

## 3. 模型封装说明

### 3.1 模型类

新增模型类：

- `LightGBMResidualModel`

用途：

- 封装 `LightGBMRegressor`
- 提供 `save()` / `load()`
- 提供 `predict(...)` / `predict_price(...)`
- 保存运行时所需元数据

### 3.2 保留的兼容字段

与旧模型保持风格兼容的字段包括：

- `model_type`
- `r2`
- `rmse`
- `sample_count`
- `group_name`

补充的 `LightGBM` 元数据包括：

- `group_kind`
- `feature_names`
- `categorical_features`
- `category_levels`
- `monotone_constraints`
- `clip_range`
- `train_metrics`
- `abnormal_prediction_ratio`

### 3.3 公式接口

保留 `get_formula()` 风格接口，但返回固定说明文本：

```text
LightGBM tree ensemble model (no closed-form formula)
```

## 4. 模型文件格式说明

### 4.1 文件后缀

模型文件后缀统一为：

- `.pkl`

### 4.2 文件内容

每个 `.pkl` 文件直接序列化一个完整的 `LightGBMResidualModel` 对象，包含：

1. 训练好的 `LightGBMRegressor`
2. 特征顺序
3. 类别特征列表
4. 类别取值集合
5. 单调约束
6. 输出裁剪范围
7. 训练评估指标
8. 异常预测比例

因此，单独加载模型文件即可完成预测，不依赖额外配置文件才能还原特征元数据。

## 5. 训练脚本说明

统一训练入口：

- `src/build_lightgbm_models.py`

支持训练：

1. 品牌车系 `LightGBM` 模型
2. 车型类别 `LightGBM` 模型
3. 或同时训练两者

### 5.1 示例命令

在项目根目录执行：

```powershell
$env:PYTHONIOENCODING='utf-8'
..\venv\Scripts\python.exe src\build_lightgbm_models.py --group-by both
```

用于快速验证的小样本命令：

```powershell
$env:PYTHONIOENCODING='utf-8'
..\venv\Scripts\python.exe src\build_lightgbm_models.py --group-by both --max-groups 1
```

## 6. 训练流程

训练流程如下：

1. 读取训练数据
2. 按统一口径清洗字段
3. 计算或校验目标值 `残值率`
4. 按品牌车系或车辆类别分组
5. 按时间优先策略切分训练集 / 验证集
6. 训练 `LightGBMRegressor`
7. 计算 `MAE`、`MAPE`、`R²`、`RMSE`
8. 统计异常预测样本
9. 序列化保存模型
10. 输出汇总报告

## 7. 输出目录

阶段三已明确并实现以下输出目录：

- `output/lightgbm/brand_series_models`
- `output/lightgbm/car_types_models`
- `output/lightgbm/reports`

## 8. 报告文件

训练脚本会输出以下报告文件：

- `output/lightgbm/reports/training_summary.csv`
- `output/lightgbm/reports/eval_summary.json`
- `output/lightgbm/reports/abnormal_predictions.csv`

## 9. 异常预测样本

本阶段已按阶段二冻结的定义落地异常预测样本统计，异常条件包括：

1. 原始预测值非有限数
2. 原始残值率小于 0
3. 原始残值率大于 1
4. 裁剪前后发生变化

报告文件中会输出异常样本明细与异常比例。

## 10. 与后续阶段的关系

阶段三完成后：

1. `LightGBM` 模型已经可以被单独训练和单独加载
2. 模型文件格式已经固定
3. 阶段四只需要把这套模型封装接入现有预测主链路

本阶段不包含：

- `/predict` 主链路切换
- `curve` / `lightgbm` 运行时双模型开关接入
- 线上默认模型切换
