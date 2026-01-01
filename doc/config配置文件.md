# 配置文件说明文档

本文档详细说明 `config/` 目录下各个配置文件的作用、应用场景及配置项含义。

## 1. 实体识别规则配置 (`config/entity_rules.yaml`)

**应用场景：**
主要用于 `src/entity_extractor.py` (实体识别器)。
> [!NOTE]
> 当前版本的 `EntityExtractor` 部分规则（如正则模式）已硬编码在 Python 代码中，本配置文件中的 `entities` 规则可能不会直接生效。但本文件的**位置**很重要，程序会基于此文件路径去查找 `dictionaries` 目录。

**主要资源：**

### 1.1 品牌与车系库
程序并不读取 `entities` 中配置的 `brands.txt` 或 `series.txt`，而是直接加载同级目录下 `dictionaries/car_series.csv` 文件。
*   `dictionaries/car_series.csv`: 包含品牌、车系、别名、单匹模式等完整信息的CSV文件。

### 1.2 预处理与正则
虽然配置文件中定义了预处理和正则规则，但目前 `EntityExtractor` 类内部方法 `_compile_patterns` 使用了硬编码的正则表达式。若需修改匹配逻辑，请直接查看源码 `src/entity_extractor.py`。

---

## 2. 匹配引擎配置 (`config/matching_config.yaml`)

**应用场景：**
主要用于 `src/matching_engine.py` (匹配引擎)。在将用户输入的车辆信息与标准车型库进行模糊匹配时，该文件定义了评分权重、阈值和等价逻辑。

**主要配置项：**

### 2.1 权重配置 (`weights`)
定义各个特征在相似度计算中的得分权重。
*   `brand` (100分): 品牌必须匹配。
*   `series` (80分): 车系必须匹配。
*   `year`, `displacement`, `transmission` 等: 其他属性的匹配得分权重。

### 2.2 阈值配置 (`thresholds`)
*   `min_score`: 候选车辆被返回的最低分数线 (例如 150)。
*   `high_confidence`: 判定为高置信度匹配的分数线 (例如 250)。

### 2.3 模糊匹配规则 (`fuzzy_rules`)
定义非精确匹配时的扣分或得分逻辑。
*   `year`: 年款不一致时的容错逻辑（差1年得30分，差2年得10分）。
*   `range_km`: 续航里程的容差范围 (±20km)。

### 2.4 等价映射 (`*_equivalents`)
定义语义上相同的词汇，用于归一化匹配。
*   `displacement_equivalents`: 如 "1.4T" 等价于 "1.4TSI", "1.4THP"。
*   `transmission_equivalents`: 如 "自动" 等价于 "AT", "手自一体"。
*   `drive_equivalents`: 如 "两驱" 等价于 "前驱" 或 "后驱"。

### 2.5 批量处理 (`batch`)
*   `chunk_size`: 批量匹配时的分块大小。
*   `max_workers`: 并行处理的线程数。

---

## 3. 自适应价格区间配置 (`config/adaptive_range.yaml`)

**应用场景：**
用于 `src/residual_predictor_step5.py` (残值预测器)。解决低价车 B2B 区间过窄导致命中率低的问题。

**核心逻辑：**
对于预测价格 <3万 的车辆，自动扩展 B2B 价格区间。扩展后的半宽 = max(mid × percentage, absolute)。

**主要配置项：**

### 3.1 启用开关
```yaml
enabled: true  # 是否启用自适应区间扩展
```

### 3.2 价格区间规则 (`rules`)
每条规则包含三个参数：
*   `threshold`: 此规则适用的价格上限（万元）
*   `percentage`: 相对于中间价的百分比（0.20 = 20%）
*   `absolute`: 最小绝对半宽（万元）（0.20 = 2000元）

**默认配置 (v2 参数)**：
```yaml
rules:
  low_price:      # <1万的车
    threshold: 1.0
    percentage: 0.20  # ±20%
    absolute: 0.20    # 或 ±2000元

  mid_price:      # 1-2万的车
    threshold: 2.0
    percentage: 0.12  # ±12%
    absolute: 0.15    # 或 ±1500元

  high_price:     # 2-3万的车
    threshold: 3.0
    percentage: 0.08  # ±8%
    absolute: 0.0     # 无绝对下限
```

**效果**：
开启后，命中率从 36.25% 提升至 **48.15%** (v2 参数)。详见 `experiment/hit_rate_20251231.md`。
