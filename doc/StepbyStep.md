# 残值预测系统流水线 (Step-by-Step)

本文档详细描述了从原始数据到最终残值预测API的完整处理流程。代码文件均位于 `src/` 目录下，并以 `_stepN` 后缀标识执行顺序。

---

## 整体流程概览

1.  **Step 1 批量匹配**: 将原始优信拍/有辆数据匹配到标准车型库 (Standardization)
2.  **Step 2 数据提取**: 从匹配结果中提取标准化的残值分析数据集 (Data Preparation)
3.  **Step 3 建模实验**: 针对单个车系进行残值曲线拟合与算法验证 (Prototype)
4.  **Step 4 模型构建**: 批量训练全量车系和车型大类模型，并持久化保存 (Training)
5.  **Step 5 综合预测**: 集成多级模型、相似车微调和 C2B2C 逻辑提供预测服务 (Inference)

---

## 详细步骤说明

### Step 1: 批量匹配 (Batch Match)
**脚本**: `src/batch_match_step1.py`

*   **功能**: 将输入的非标准车辆名称（如"优信拍"或"有辆"的描述）与"力洋标准车型库"进行模糊匹配，找到对应的标准 ID 和参数。
*   **输入**:
    *   `data/优信拍_上海_2024.csv` (原始数据)
    *   `data/力洋车型库精简5.csv` (标准库)
*   **依赖**: `src/matching_engine.py` (匹配引擎), `src/vehicle_index.py` (倒排索引)
*   **输出**:
    *   `output/batch_match_result_YYYYMMDD_HHMMSS.csv` (包含匹配得分和对应标准车型ID)

### Step 2: 数据提取 (Data Extraction)
**脚本**: `src/extract_residual_data_step2.py`

*   **功能**: 解析 Step 1 的匹配结果文件，结合原始成交数据，清洗并提取出用于建模的结构化数据。
*   **处理逻辑**:
    *   解析成交日期、注册日期 -> 计算 **使用年限**
    *   解析成交价、新车价 -> 计算 **保值率/残值率**
    *   统一 **评级标准** (优/中/差)
    *   计算 **车况校正价** (将非"中"级车价还原为标准车况价格)
*   **输入**:
    *   `output/youliang_match_result.txt` (支持多种来源格式)
    *   `output/youxinpai_match_result.txt`
*   **输出**:
    *   `output/residual_value_data.csv` (原始提取数据)
    *   `output/residual_value_data_for_build_model.csv` (**核心建模数据集**，经过进一步清洗和去重，后续步骤的基础)
    *   字段包括: 品牌车系, 新车的价格, 二手车的成交价, 车况校正价, 使用年限, 车辆评级, 车辆大类, 行驶里程...

### Step 3: 单车系建模实验 (Modeling Experiment)
**脚本**: `src/residual_value_modeling_step3.py`

*   **功能**: 开发和验证残值曲线拟合算法。允许针对单个"品牌-车系"运行，观察拟合效果。
*   **核心算法**:
    *   **异常值过滤**: 使用 IQR (四分位距) 算法剔除离群价格点。
    *   **曲线拟合**: 尝试三种模型 (指数模型, 二次多项式, 幂函数)。
    *   **模型评估**: 基于 R2 和 RMSE 选出最佳模型，并校验物理约束 (单调递减, 残值>0)。
*   **输入**:
    *   `output/residual_value_data_for_build_model.csv`
    *   参数: `--series '品牌-车系'`
*   **输出**:
    *   控制台打印的最佳模型参数和评估指标。
    *   `tests/result_details.csv` (预测详情，用于 Excel 分析)

### Step 4: 批量模型构建 (Batch Model Building)
**核心类**: `src/batch_model_trainer_step4.py`
**执行脚本**:
*   `src/build_brand_series_models_step4.py` (构建一级模型：具体车系)
*   `src/build_car_types_models_step4.py` (构建二级模型：车辆大类，如"紧凑型SUV")
*   `src/build_segmented_models_step4.py` (分段模型实验，暂未上线)

*   **功能**: 将 Step 3 验证过的算法应用到全量数据上。
*   **处理逻辑**:
    1.  遍历所有"品牌-车系"。
    2.  若样本足够 (>15条)，训练一级模型。
    3.  若样本不足，该车系不生成模型 (预测时将回退到二级模型)。
    4.  遍历所有"车辆大类"，训练二级通用模型。
*   **输入**: `output/residual_value_data_for_build_model.csv`
*   **输出**:
    *   `price_model/brand_series/*.pkl` (数千个车系模型文件)
    *   `price_model/car_type/*.pkl` (十几个大类模型文件)

### Step 5: 综合预测与应用 (Prediction & Inference)
**核心组件**:
*   `src/price_predictor_step5.py`: 基础价格预测器 (加载 Step 4 的模型)
*   `src/residual_data_index_step5.py`: 向量检索引擎 (用于查找相似成交案例)
*   `src/residual_predictor_step5.py`: **最终预测入口**

*   **功能**: 提供面向用户的最终估值服务。
*   **预测逻辑 (ResidualPredictor.predict)**:
    1.  **基础预测**: 优先调用 `brand_series` 模型，失败则降级调用 `car_type` 模型。
    2.  **相似检索**: 在历史成交库中查找最相似的 N 辆车 (同款、同年份、同里程)。
    3.  **微调校正**: 基于相似车的真实成交价，计算偏差系数，对基础预测价进行微调 (Adjustment)。
    4.  **区间生成**: 调用 `c2b2c_model` 将 B2B 交易中间价扩展为完整的价格矩阵 (B2B/C2B/B2C 的 优/中/差 上下限)。
*   **辅助工具**:
    *   `src/web_predictor_debug_step5.py`: 启动 Web 界面进行可视化调试。
    *   `src/tune_adjustment_params_step5.py`: 自动搜索最优微调参数。
*   **输入**: 车辆名称, 年限, 里程, 城市, 新车价
*   **输出**: `ResidualPredictionResult` 对象 (包含最终价格和完整价格矩阵)
