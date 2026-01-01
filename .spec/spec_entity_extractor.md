# 实体识别器规格说明 (Entity Extractor Spec)

## 1. 目标

从车辆名称字符串中提取结构化实体信息，支持燃油车和电动车两种模式。

---

## 2. 输入/输出

### 输入
```python
input_text: str  # 车辆名称，如 "宝马/X1/2016款 2.0T 自动 20Li豪华型前驱"
```

### 输出
```python
@dataclass
class ExtractedEntities:
    brand: Optional[str]        # 品牌
    series: Optional[str]       # 车系
    year: Optional[int]         # 年款
    displacement: Optional[str] # 排量 (燃油车)
    range_km: Optional[int]     # 续航里程 (电动车)
    transmission: Optional[str] # 档位
    drive: Optional[str]        # 驱动方式
    edition: Optional[str]      # 款式
    trim: Optional[str]         # 版式
    vehicle_type: str           # 动力类型: 燃油/纯电/混动/增程
    raw_text: str               # 原始输入
    confidence: float           # 置信度 0-1
```

---

## 3. 实体类型定义

| 实体 | 英文名 | 识别方式 | 优先级 | 示例 |
|------|--------|----------|--------|------|
| 品牌 | `brand` | 词典匹配 | 100 | 宝马、大众、特斯拉 |
| 车系 | `series` | 词典匹配 | 90 | X1、帕萨特、Model 3 |
| 年款 | `year` | 正则 | 80 | 2016、2023款 |
| 排量 | `displacement` | 正则 | 70 | 2.0T、1.5L、1.4TSI |
| 续航 | `range_km` | 正则 | 70 | 400KM、420km |
| 档位 | `transmission` | 词典 | 60 | 自动、双离合 |
| 驱动 | `drive` | 词典 | 50 | 四驱、前驱 |
| 款式 | `edition` | 正则 | 40 | 改款、京彩款 |
| 版式 | `trim` | 正则 | 30 | 豪华版、尊贵型 |

---

## 4. 识别规则

### 4.1 正则表达式

```python
PATTERNS = {
    # 年款: 2016款、2023
    "year": r"(\d{4})款?",
    
    # 排量: 2.0T、1.4TSI、1.5L、2.0TFSI
    "displacement": r"(\d+\.?\d*)\s*(T|TSI|THP|TFSI|L|t)?(?![Kk])",
    
    # 续航: 400KM、420km、500公里
    "range_km": r"(\d{3,4})\s*([Kk][Mm]|公里)?",
    
    # 款式: **款
    "edition": r"([\u4e00-\u9fa5]+款)",
    
    # 版式: **版、**型、**型Plus
    "trim": r"([\u4e00-\u9fa5\w]+(?:版|型)(?:Plus)?)"
}
```

### 4.2 词典

```yaml
# 档位词典
transmission:
  - 自动
  - 手动
  - 手自一体
  - 双离合
  - 单离合
  - CVT
  - AT
  - MT
  - DCT
  - AMT

# 驱动词典
drive:
  - 四驱
  - 前驱
  - 后驱
  - 两驱
  - AWD
  - 4WD
```

### 4.3 动力类型推断规则

```python
def infer_vehicle_type(entities: dict) -> str:
    text = entities.get("raw_text", "").lower()
    
    if "增程" in text:
        return "增程"
    elif "纯电" in text or "ev" in text or entities.get("range_km"):
        return "纯电"
    elif "混动" in text or "phev" in text or "dmi" in text:
        return "混动"
    elif entities.get("displacement"):
        return "燃油"
    else:
        return "未知"
```

---

## 5. 接口定义

```python
class EntityExtractor:
    """实体识别器"""
    
    def __init__(self, config_path: str = "config/entity_rules.yaml"):
        """
        初始化识别器
        
        Args:
            config_path: 配置文件路径
        """
        pass
    
    def extract(self, text: str) -> ExtractedEntities:
        """
        从文本中提取实体
        
        Args:
            text: 车辆名称字符串
            
        Returns:
            ExtractedEntities: 提取的实体结构
        """
        pass
    
    def preprocess(self, text: str) -> str:
        """
        预处理：去除噪音
        
        Rules:
        - 去除 "**车源"、"**车行" 等前缀
        - 统一分隔符 "/" -> " "
        - 去除多余空格
        """
        pass
```

---

## 6. 配置文件格式

```yaml
# config/entity_rules.yaml

# 噪音清洗规则
preprocessing:
  remove_patterns:
    - ".*车源"
    - ".*车行"
  separator_normalize:
    from: ["/", "\\", "|"]
    to: " "

# 实体规则
entities:
  brand:
    type: dictionary
    file: dictionaries/brands.txt
    priority: 100
    
  series:
    type: dictionary
    file: dictionaries/series.txt
    priority: 90
    
  year:
    type: regex
    pattern: '(\d{4})款?'
    group: 1
    priority: 80
    
  displacement:
    type: regex
    pattern: '(\d+\.?\d*)\s*(T|TSI|THP|TFSI|L|t)?(?![Kk])'
    group: [1, 2]
    priority: 70
    
  range_km:
    type: regex
    pattern: '(\d{3,4})\s*([Kk][Mm]|公里)?'
    group: 1
    priority: 70
```

---

## 7. 示例

### 示例 1：燃油车
**输入**: `"中升车源\n宝马/X1/2016款 2.0T 自动 20Li豪华型前驱"`

**输出**:
```json
{
  "brand": "宝马",
  "series": "X1",
  "year": 2016,
  "displacement": "2.0T",
  "range_km": null,
  "transmission": "自动",
  "drive": "前驱",
  "edition": null,
  "trim": "豪华型",
  "vehicle_type": "燃油",
  "raw_text": "宝马/X1/2016款 2.0T 自动 20Li豪华型前驱",
  "confidence": 0.95
}
```

### 示例 2：电动车
**输入**: `"特斯拉 Model 3 2023款 长续航版 420KM"`

**输出**:
```json
{
  "brand": "特斯拉",
  "series": "Model 3",
  "year": 2023,
  "displacement": null,
  "range_km": 420,
  "transmission": null,
  "drive": null,
  "edition": null,
  "trim": "长续航版",
  "vehicle_type": "纯电",
  "raw_text": "特斯拉 Model 3 2023款 长续航版 420KM",
  "confidence": 0.92
}
```

---

## 8. 验收标准

- [ ] 品牌识别准确率 > 98%
- [ ] 年款识别准确率 > 95%
- [ ] 排量/续航识别准确率 > 90%
- [ ] 单条处理时间 < 5ms
- [ ] 配置文件可热加载
