# 阶段五：Docker 验证工作流程

> 记录日期：2026-04-16
> 对应阶段：`LightGBM模型改造实施清单.md` 阶段 5

## 1. 验证目标

验证当前代码在 Docker 环境中满足以下条件：

1. 镜像可构建
2. 容器可启动
3. `lightgbm` 已安装
4. 挂载后的模型文件和配置文件可访问
5. 服务健康检查通过
6. 容器内 `curve` 与 `lightgbm` 预测都可执行

## 2. 实际执行步骤

### 2.1 检查 Docker daemon

执行：

```powershell
docker info
```

结果：

- Docker daemon 已可访问
- Server 状态正常

### 2.2 检查 compose 服务

执行：

```powershell
docker compose ps
docker ps
```

结果：

- 已识别当前运行中的 `web` 服务容器

### 2.3 验证旧 compose 容器状态

执行：

```powershell
docker exec car_price_predictor python -c "import lightgbm"
```

结果：

- 旧运行容器中 `lightgbm` 不可用

结论：

- 说明当前 compose 容器是旧镜像，不能代表最新代码状态

### 2.4 构建最新镜像

执行：

```powershell
docker build -t vehicle-price-stage5 .
```

结果：

- 构建成功
- `requirements.txt` 中的 `lightgbm`、`pytest` 等依赖已安装进镜像

### 2.5 运行临时验证容器

执行：

```powershell
docker run -d --rm --name vehicle-price-stage5-check -p 18087:8087 vehicle-price-stage5
```

### 2.6 验证镜像内 `lightgbm`

执行：

```powershell
docker run --rm vehicle-price-stage5 python -c "import lightgbm; print(lightgbm.__version__)"
```

结果：

- `lightgbm==4.6.0`

### 2.7 验证临时容器健康检查

执行：

```powershell
Invoke-WebRequest http://localhost:18087/health -UseBasicParsing
```

结果：

```json
{"status":"ok","predictor_ready":true}
```

### 2.8 重建 compose `web` 服务

执行：

```powershell
docker compose up -d --build web
```

结果：

- `web` 服务已基于最新镜像重建

### 2.9 验证重建后 compose 容器依赖与文件

执行：

```powershell
docker exec car_price_predictor python -c "import lightgbm; print(lightgbm.__version__)"
docker exec car_price_predictor python -c "from pathlib import Path; print(...)"
```

结果：

- `lightgbm` 可导入
- `/app/output` 挂载存在
- `output/lightgbm/brand_series_models` 中存在 `265` 个模型文件
- `output/lightgbm/car_types_models` 中存在 `27` 个模型文件
- `config/model_strategy.yaml` 存在

### 2.10 验证 compose 服务健康检查

执行：

```powershell
Invoke-WebRequest http://localhost:8087/health -UseBasicParsing
```

结果：

```json
{"status":"ok","predictor_ready":true}
```

### 2.11 验证容器内真实预测

#### curve 模式

执行容器内预测脚本，结果：

```text
{'family': 'curve', 'success': True, 'predicted_price': 6.24, 'final_model_family': 'curve'}
```

#### lightgbm 模式

执行容器内预测脚本，结果：

```text
{'family': 'lightgbm', 'success': True, 'predicted_price': 5.44, 'final_model_family': 'lightgbm'}
```

结论：

- `curve` 容器内预测成功
- `lightgbm` 容器内预测成功

## 3. 结果总结

本轮 Docker 验证已确认：

1. Docker 镜像构建通过
2. `lightgbm` 在镜像和 compose 容器中均可用
3. 容器启动后健康检查通过
4. 预测器初始化成功
5. 模型文件和切换配置在容器内可见
6. `curve` / `lightgbm` 两种模式都能在容器内执行预测

## 4. 备注

验证日志中仍会出现旧 `C2B2C` 模型相关的 `scikit-learn` 反序列化版本提示，但本次 Docker 验证中未观察到因此导致的启动失败或预测失败。
