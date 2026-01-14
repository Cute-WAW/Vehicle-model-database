# 二手车残值预测 API 接口文档

本文档描述了二手车残值预测服务 (`/predict`) 的调用方式、输入参数及返回结果结构。

## 1. 接口概览

- **接口地址**: `http://60.205.246.51:8090/predict`
- **请求方法**: `POST`
- **内容类型**: `application/json`

## 2. 输入参数 (Request)

请求体为一个 JSON 对象，包含待评估车辆的详细信息。

| 字段名 | 类型 | 必填 | 示例值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| `vehicle_full_name` | string | 是 | "吉利 帝豪 2017款 1.5L CVT向上互联版" | 车辆完整名称 (用于匹配和定价) |
| `brand_series` | string | 是 | "吉利-帝豪" | 品牌和车系组合，格式为 `品牌-车系` |
| `years` | float | 是 | 8.33 | 车龄 (年) |
| `grade` | string | 否 | "中" | 车况评级，可选值: `"优"`, `"中"`, `"差"` (默认为 "中") |
| `city` | string | 否 | "邢台" | 车辆所在城市 (可能影响区域定价权重) |
| `mileage` | float | 否 | 8.0 | 行驶里程 (万公里) |
| `new_price` | float | 否 | 7.98 | 新车指导价 (万元)，若不传则尝试自动推断 |

### 请求示例 (JSON)

```json
{
    "vehicle_full_name": "吉利 帝豪 2017款 1.5L CVT向上互联版",
    "brand_series": "吉利-帝豪",
    "years": 8.33,
    "grade": "中",
    "city": "邢台",
    "mileage": 8.0,
    "new_price": 7.98
}
```

## 3. 输出参数 (Response)

接口返回预测结果，包括预测价格、残值率、详细的价格矩阵（B2B/C2B/B2C 在不同车况下的价格）以及调试和解释信息。

### 顶层字段

| 字段名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `success` | bool | 预测是否成功 |
| `predicted_price` | float | 最终预测价格 (万元) |
| `new_price` | float | 使用的新车价格 (万元) |
| `residual_rate` | float | 残值率 (预测价格 / 新车价格) |
| `price_matrix` | object | 价格矩阵，包含不同交易模式的三级价格 |
| `identical_records` | array | 历史完全匹配的成交记录 |
| `explanation` | object | 价格解释报告 (置信度、影响因素) |
| `debug` | object | 调试信息 (模型中间结果、相近车辆等) |
| `error_message` | string | 错误信息 (如果 success 为 false) |

### 3.1 价格矩阵 (price_matrix) 结构

`price_matrix` 包含三个子对象：
- `c2BPrices`: 车商收购价 (Customer to Business)
- `b2BPrices`: 车商批发价 (Business to Business)
- `b2CPrices`: 车商零售价 (Business to Customer)

每个子对象包含 `a` (优), `b` (中), `c` (差) 三个等级的价格区间：

| 字段 | 描述 |
| :--- | :--- |
| `low` | 价格下限 (万元) |
| `mid` | 价格中位数 (万元) |
| `up` | 价格上限 (万元) |

### 3.2 解释报告 (explanation) 结构

| 字段名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `summary` | string | 简短的价格分析总结 |
| `confidence` | string | 预测置信度 (`high`, `medium`, `low`) |
| `factors` | array | 影响价格的具体因素列表 |

### 响应示例 (JSON)

```json
{
  "success": true,
  "predicted_price": 1.58,
  "new_price": 7.98,
  "residual_rate": 0.198,
  "price_matrix": {
    "c2BPrices": {
      "a": { "low": 1.55, "mid": 1.62, "up": 1.68 },
      "b": { "low": 1.45, "mid": 1.52, "up": 1.58 },
      "c": { "low": 1.35, "mid": 1.42, "up": 1.48 }
    },
    "b2BPrices": {
      "a": { "low": 1.65, "mid": 1.72, "up": 1.79 },
      "b": { "low": 1.55, "mid": 1.62, "up": 1.69 },
      "c": { "low": 1.45, "mid": 1.52, "up": 1.59 }
    },
    "b2CPrices": {
      "a": { "low": 1.85, "mid": 1.95, "up": 2.05 },
      "b": { "low": 1.75, "mid": 1.85, "up": 1.95 },
      "c": { "low": 1.65, "mid": 1.75, "up": 1.85 }
    }
  },
  "identical_records": [
    {
      "vehicle_full_name": "吉利 帝豪 2017款 1.5L CVT向上互联版",
      "used_price": 1.60,
      "years": 8.1,
      "city": "石家庄",
      "in_range": true
    }
  ],
  "explanation": {
    "summary": "该车龄处于加速贬值期，行驶里程正常。",
    "confidence": "high",
    "factors": [
      { "label": "品牌保值率", "reason": "品牌市场认可度一般", "delta": -0.05 },
      { "label": "车龄因素", "reason": "8年以上老旧车型", "delta": -0.20 }
    ]
  },
  "debug": {
    "model_used": "XGBoost",
    "model_prediction": 1.65,
    "adjustment_method": "similar_vehicle_match",
    "adjustment_delta": -0.07,
    "similar_vehicles": [...]
  }
}
```

## 4. Python 调用示例

以下是使用 `requests` 库调用该 API 的完整代码示例：

```python
import requests
import json

url = "http://localhost:8087/predict"
payload = {
    "vehicle_full_name": "吉利 帝豪 2017款 1.5L CVT向上互联版",
    "brand_series": "吉利-帝豪",
    "years": 8.33,
    "grade": "中",
    "city": "邢台",
    "mileage": 8.0,
    "new_price": 7.98
}

try:
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"预测结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print(f"请求失败: {response.text}")

except Exception as e:
    print(f"调用出错: {e}")
```
