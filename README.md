# 车型库映射系统

## 项目结构

```
车型库映射/
├── .spec/                          # Spec 文档
│   ├── requirements.md             # 需求文档
│   ├── spec_entity_extractor.md    # 实体识别器规格
│   ├── spec_vehicle_index.md       # 车型库索引规格
│   ├── spec_matching_engine.md     # 匹配引擎规格
│   ├── spec_testing.md             # 测试框架规格
│   └── spec_web_ui.md              # Web界面规格
│
├── config/                         # 配置文件
│   ├── entity_rules.yaml           # 实体识别规则
│   └── matching_config.yaml        # 匹配引擎配置
│
├── src/                            # 源代码
│   ├── web/                        # 匹配调试 Web 应用
│   │   └── app.py
│   │
│   ├── entity_extractor.py         # 实体识别器 (通用)
│   ├── vehicle_index.py            # 车型库索引 (通用)
│   ├── matching_engine.py          # 匹配引擎 (通用)
│   │
│   │   # === C2B2C 价格模型 Pipeline (Step 1-5) ===
│   ├── batch_match_step1.py                # Step 1: 批量匹配
│   ├── extract_residual_data_step2.py      # Step 2: 提取残值数据
│   ├── residual_value_modeling_step3.py    # Step 3: 残值建模
│   ├── batch_model_trainer_step4.py        # Step 4: 批量模型训练器
│   ├── build_brand_series_models_step4.py  # Step 4: 构建品牌车系模型
│   ├── build_car_types_models_step4.py     # Step 4: 构建车型类别模型
│   ├── price_predictor_step5.py            # Step 5: 价格预测器
│   ├── residual_data_index_step5.py        # Step 5: 残值数据索引
│   ├── residual_predictor_step5.py         # Step 5: 残值预测核心
│   ├── tune_adjustment_params_step5.py     # Step 5: 调参工具
│   └── web_predictor_debug_step5.py        # Step 5: 价格预测 Web 调试界面
│
├── scripts/                        # 工具脚本
│   ├── build_index.py              # 构建索引
│   ├── run_benchmark.py            # 运行测试
│   └── c2b2c_price_model/          # C2B2C 模型分析脚本
│
├── data/                           # 数据文件
├── output/                         # 输出文件
├── price_model/                    # 模型文件
└── tests/                          # 测试
```

## 快速开始

### 1. 激活虚拟环境

```bash
cd D:\antigravity\price_evaluation\车型库映射
..\venv_car_price_20251216\Scripts\activate
```

### 2. 安装依赖

```bash
pip install fastapi uvicorn pyyaml pandas jinja2 python-multipart scikit-learn
```

### 3. 构建索引

```bash
python scripts/build_index.py
```

### 4. 启动服务

#### 4.1 启动价格预测调试 (Step 5)

功能：输入车辆信息，预测残值及B2B/B2C/C2B价格矩阵。

```bash
python src/web_predictor_debug_step5.py
```

访问: http://localhost:8003

#### 4.2 启动匹配引擎调试 (通用)

功能：调试车辆名称的清洗、实体提取及车型库匹配。

```bash
python src/web/app.py
```

访问: http://127.0.0.1:8000

### 5. 运行测试

```bash
# 回归测试
python scripts/run_benchmark.py -v

# 性能测试
python scripts/run_benchmark.py --performance

# 生成报告
python scripts/run_benchmark.py --output reports/test_report.md
```

## API 接口

### 匹配引擎 (Port 8000)
- `POST /api/match`: 匹配车辆名称
- `GET /api/extract`: 仅实体识别
- `GET /api/config`: 获取配置

### 价格预测 (Port 8003)
- `POST /predict`: 预测残值
- `POST /batch_predict`: 批量预测
- `GET /models`: 获取可用模型列表
- `GET /random_vehicle`: 获取随机车辆数据
