# 部署与更新指南

本文档总结了近期的修改内容，并提供了后续更新部署的操作指南。

## 1. 近期修改摘要

### 前端 (Web)
*   **上牌时间选择优化**：将原本的精确日期选择改为仅选择月份 (`type="month"`)，简化用户操作。
*   **随机下一辆修复**：修复了点击“随机下一辆”按钮时的 `Cannot read properties of undefined` 报错。
*   **相似车辆筛选**：在结果页面的“相似车辆”部分增加了上牌时间范围筛选功能。

### 后端与架构 (Docker/Server)
*   **依赖更新**：增加了 `captcha` (验证码) 库。
*   **数据库修复**：修复了部署时 `users.sqlite` 被错误挂载为文件夹导致服务无法启动的问题。
*   **端口冲突解决**：修复了腾讯云上旧容器 (`car-price-predictor-v2`) 占用端口导致新代码不生效的问题。
*   **部署脚本增强**：更新脚本支持自动清理冲突容器、强制重新构建镜像 (`--build`) 以确保依赖安装。

---

## 2. 如何更新部署

### A. 本地 Docker 环境更新

如果你在本地修改了代码（如 `src/` 目录下的文件或 `requirements.txt`），请在终端执行以下指令来更新本地运行的服务：

```powershell
# 1. 停止并移除旧容器（推荐，防止缓存问题）
docker-compose down

# 2. 重新构建并启动（必须加 --build 以确保安装新依赖）
docker-compose up -d --build
```

*   **访问地址**：`http://localhost:8087`

### B. 部署到远程服务器 (腾讯云 & 阿里云)

我们已经封装了一个自动化脚本，可以一键将本地代码同步到所有服务器并重启服务。

**执行指令：**

```powershell
python scripts/update_all_servers.py
```

**脚本内部执行的步骤（自动完成）：**
1.  **打包**：将本地的 `src/`, `nginx/`, `Dockerfile`, `requirements.txt`, `users.sqlite` 等核心文件打包。
2.  **上传**：通过 SSH 将压缩包上传到服务器的 `/root/car_price_predictor/` 目录。
3.  **清理**：自动检测并删除可能冲突的旧容器（如 `car-price-predictor-v2`）。
4.  **修复**：检查并修复 `users.sqlite` 数据库文件权限。
5.  **重启**：执行 `docker-compose up -d --build --force-recreate`，强制重建镜像并启动服务。

### C. 常用故障排查

如果部署后访问报错（如 502 Bad Gateway）：

1.  **检查服务状态**：
    ```powershell
    python scripts/check_servers_status.py
    ```
2.  **查看日志**（用于查看详细报错）：
    *   **腾讯云**：SSH 登录后运行 `docker logs --tail 100 car_price_predictor`
    *   **阿里云**：SSH 登录后运行 `docker logs --tail 100 car_price_predictor_web`
    *   *注意：如果刚部署完显示 502，通常是因为系统正在重建索引（耗时约 1-3 分钟），请耐心等待。*
