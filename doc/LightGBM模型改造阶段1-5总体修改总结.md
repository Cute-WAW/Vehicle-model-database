# LightGBM 模型改造阶段1-5总体修改总结

> 记录日期：2026-04-16
> 范围：阶段 1 到阶段 5

## 1. 总体结论

本轮改造已经完成从“现状摸底”到“默认模型切换”的完整闭环：

1. 冻结了旧 `curve` 基线和运行路径
2. 冻结了首版 `LightGBM` 建模方案
3. 完成了 `LightGBM` 模型封装与训练流程
4. 完成了 `curve / lightgbm` 双模型接入主链路
5. 完成了离线评估、测试、Docker 验证和默认模型切换

当前默认模型家族已切换为：

- `lightgbm`

同时保留：

- `curve` 自动回退能力
- 相似车修正逻辑
- `C2B2C` 价格矩阵
- `/predict` 请求/响应结构兼容

## 2. 阶段 1：冻结当前基线

本阶段完成的核心工作：

1. 梳理当前主链路：
   - `web_predictor_debug_step5.py`
   - `residual_predictor_step5.py`
   - `price_predictor_step5.py`
2. 明确旧 `curve` 模型目录与回退顺序
3. 记录旧模型基线指标
4. 记录线上默认加载路径和行为说明

主要文档：

- `doc/价格预测/阶段一-当前curve指标基线记录.md`
- `doc/价格预测/模型路径统一记录.md`
- `doc/价格预测/阶段一-线上模型加载与旧模型指标验收说明.md`

## 3. 阶段 2：冻结 LightGBM 建模方案

本阶段完成的核心工作：

1. 冻结目标变量为 `残值率`
2. 冻结预测口径为“先预测残值率，再换算价格”
3. 冻结首版特征集、训练策略、异常样本定义
4. 冻结目录与命名规范
5. 冻结模型开关策略

主要文档：

- `doc/价格预测/阶段二-LightGBM建模方案冻结说明.md`

## 4. 阶段 3：新增模型封装与训练流程

本阶段完成的核心工作：

1. 新增 `LightGBMResidualModel`
2. 新增 `lightgbm_trainer.py`
3. 新增统一训练脚本 `build_lightgbm_models.py`
4. 新增 `output/lightgbm/...` 输出目录
5. 模型文件支持单独加载并直接预测

主要代码：

- `src/lightgbm_residual_model.py`
- `src/lightgbm_trainer.py`
- `src/build_lightgbm_models.py`
- `src/model_paths.py`

主要文档：

- `doc/价格预测/阶段三-LightGBM模型封装与训练流程说明.md`

## 5. 阶段 4：接入预测主链路

本阶段完成的核心工作：

1. `PricePredictor` 扩展为支持 `curve / lightgbm` 双模型
2. `ResidualPredictor` 接入模型家族开关
3. 新增 `config/model_strategy.yaml`
4. 更新 `debug` 字段以区分：
   - `curve`
   - `lightgbm`
   - 是否发生回退
5. 保持 `/predict` 顶层接口结构不变

主要代码：

- `src/price_predictor_step5.py`
- `src/residual_predictor_step5.py`
- `src/web_predictor_debug_step5.py`
- `src/web/templates/home.html`
- `config/model_strategy.yaml`

主要文档：

- `doc/价格预测/阶段四-双模型接入主链路说明.md`
- `doc/config配置文件.md`

## 6. 阶段 5：评估、测试与切换准备

本阶段完成的核心工作：

1. 新增本地离线对比评估脚本
2. 输出新旧模型对比报告
3. 完成分桶分析
4. 补齐单元测试、序列化测试、双模型切换测试
5. 完成 Docker 镜像构建、容器启动和容器内预测验证
6. 完成细粒度质量验证
7. 完成 `LightGBM` 弱点优化

主要脚本与结果：

- `experiment/compare_curve_vs_lightgbm.py`
- `experiment/curve_vs_lightgbm_results.csv`
- `experiment/curve_vs_lightgbm_summary.json`
- `experiment/curve_vs_lightgbm_bucket_stats.csv`
- `experiment/quality_validation_lightgbm.py`
- `experiment/lightgbm_quality_summary.json`
- `experiment/lightgbm_quality_bucket_stats.csv`
- `experiment/lightgbm_monotonicity_checks.csv`
- `experiment/lightgbm_quality_cases.csv`

主要测试：

- `tests/test_batch_modeling.py`
- `tests/test_lightgbm_model.py`
- `tests/test_dual_model_predictor.py`
- `tests/test_serialization.py`

主要文档：

- `doc/价格预测/阶段五-新旧模型对比报告.md`
- `doc/价格预测/阶段五-测试说明.md`
- `doc/价格预测/阶段五-部署与回滚说明.md`
- `doc/价格预测/阶段五-Docker验证工作流程.md`
- `doc/价格预测/阶段五-LightGBM优化记录.md`
- `doc/价格预测/阶段五-细粒度质量验证报告.md`

## 7. 关键优化记录

在阶段 5 中针对 `LightGBM` 的弱点进行了两项关键优化：

1. 修复 `LightGBM` 训练器中 `车辆类别` 复用历史脏列的问题
2. 增强品牌车系未命中时的车型类别兜底逻辑

优化后离线结果显示：

- `MAPE` 优于 `curve`
- `R²` 优于 `curve`
- `B2B` 命中率优于 `curve`
- 成功率不低于 `curve`

因此 `LightGBM` 已达到当前替换条件。

## 8. 默认模型切换结果

最终默认模型切换配置为：

```yaml
default_model_family: lightgbm
allow_curve_fallback: true
```

这意味着：

1. 默认优先使用 `lightgbm`
2. 若 `lightgbm` 失败，自动回退到 `curve`

本地环境与 Docker compose 重建后的 `web` 容器均已验证：

- 默认模式命中 `lightgbm`
- 健康检查通过
- 容器内真实预测通过

## 9. 当前状态

到本次总结为止：

- 阶段 1 到阶段 5 的实施项已全部完成
- 默认模型切换已完成
- 仅保留后续持续优化空间，不存在本轮必须继续完成的剩余开发任务
