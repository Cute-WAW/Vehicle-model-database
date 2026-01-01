# Web 调试界面规格说明 (Web Debug UI Spec)

## 1. 目标

提供可视化调试界面，展示实体识别和匹配过程，方便调试和优化规则。

---

## 2. 功能需求

| 功能 | 描述 |
|------|------|
| 输入框 | 输入车辆名称 |
| 实体识别展示 | 显示提取的各实体及置信度 |
| 匹配过程展示 | 显示过滤候选数量变化 |
| 结果展示 | TopK 结果、分数、匹配实体 |
| 配置调整 | 实时调整阈值和权重 |

---

## 3. 页面布局

```
+----------------------------------------------------------+
|                    车型库匹配调试工具                      |
+----------------------------------------------------------+
| 输入车辆名称:                                              |
| [________________________________________________] [匹配]  |
+----------------------------------------------------------+
|                                                          |
|  实体识别结果                      匹配过程               |
|  +------------------------+      +-------------------+   |
|  | 品牌: 宝马      ✓     |      | 初始候选: 85000   |   |
|  | 车系: X1        ✓     |      | 品牌过滤: 1560    |   |
|  | 年款: 2016      ✓     |      | 车系过滤: 234     |   |
|  | 排量: 2.0T      ✓     |      | 年款过滤: 45      |   |
|  | 档位: 自动      ✓     |      | 最终结果: 5       |   |
|  | 驱动: 前驱      ✓     |      |                   |   |
|  | 版式: 豪华型    ✓     |      | 处理时间: 8.5ms   |   |
|  +------------------------+      +-------------------+   |
|                                                          |
+----------------------------------------------------------+
|  匹配结果 (Top 5)                                         |
|  +------------------------------------------------------+|
|  | #1 | BMW0X10A0015 | 2.0T 自动 20Li豪华版 | 295分 94% ||
|  |    | 匹配: brand, series, year, displacement...     ||
|  +------------------------------------------------------+|
|  | #2 | BMW0X10A0016 | 2.0T 自动 20Li尊享版 | 280分 89% ||
|  +------------------------------------------------------+|
+----------------------------------------------------------+
|  配置调整                                                 |
|  阈值: [150] 年款容差: [2年] [应用]                       |
+----------------------------------------------------------+
```

---

## 4. 技术栈

| 组件 | 技术 |
|------|------|
| 后端框架 | FastAPI |
| 前端 | 原生 HTML + CSS + JavaScript |
| 通信 | REST API (JSON) |
| 部署 | uvicorn 本地运行 |

---

## 5. API 接口

### 5.1 匹配接口

```
POST /api/match

Request:
{
  "query": "宝马/X1/2016款 2.0T 自动 豪华型",
  "top_k": 5,
  "min_score": 150
}

Response:
{
  "query": "...",
  "entities": {
    "brand": "宝马",
    "series": "X1",
    ...
  },
  "matches": [...],
  "debug": {
    "candidates_after_brand": 1560,
    ...
  },
  "processing_time_ms": 8.5
}
```

### 5.2 配置接口

```
GET /api/config
Response: 当前配置

POST /api/config
Request: 更新配置
Response: 更新后配置
```

### 5.3 健康检查

```
GET /api/health
Response: {"status": "ok", "index_size": 85000}
```

---

## 6. 文件结构

```
src/web/
├── app.py              # FastAPI 主应用
├── static/
│   ├── style.css       # 样式
│   └── script.js       # 前端逻辑
└── templates/
    └── index.html      # 页面模板
```

---

## 7. 后端实现

```python
# src/web/app.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="车型库匹配调试工具")

# 挂载静态文件
app.mount("/static", StaticFiles(directory="src/web/static"), name="static")
templates = Jinja2Templates(directory="src/web/templates")

# 初始化引擎
entity_extractor = EntityExtractor()
vehicle_index = VehicleIndex(entity_extractor)
vehicle_index.load("index/vehicle_index.pkl")
matching_engine = MatchingEngine(entity_extractor, vehicle_index)

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/match")
async def match(request: MatchRequest):
    result = matching_engine.match(
        request.query, 
        top_k=request.top_k,
        min_score=request.min_score
    )
    return result.to_dict()

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "index_size": len(vehicle_index.detail_store)
    }
```

---

## 8. 前端实现要点

### 8.1 样式设计
- 深色主题，专业调试风格
- 使用 CSS Grid 布局
- 实体标签使用彩色 Tag 展示
- 匹配分数使用渐变色条

### 8.2 交互逻辑
- Enter 键触发匹配
- 结果实时更新，无刷新
- 匹配实体高亮显示
- 展开/折叠详细信息

---

## 9. 启动命令

```bash
# 开发模式
cd 车型库映射
..\venv_car_price_20251216\Scripts\activate
uvicorn src.web.app:app --reload --port 8000

# 生产模式
uvicorn src.web.app:app --host 0.0.0.0 --port 8000
```

---

## 10. 验收标准

- [ ] 页面加载 < 2秒
- [ ] 匹配响应 < 500ms（含网络）
- [ ] 实体识别结果清晰展示
- [ ] 匹配过程可视化
- [ ] 配置可实时调整
- [ ] 支持复制匹配结果
