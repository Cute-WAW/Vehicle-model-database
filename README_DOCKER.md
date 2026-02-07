# Docker 部署指南

本项目已支持 Docker 容器化部署。

## 1. 准备工作

确保您的系统已安装 Docker 和 Docker Compose。

### 配置文件

确保项目根目录下存在 `.env` 文件，其中包含必要的环境变量（Supabase 配置）：

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
# DATABASE_URL=your_database_url (可选)
```

## 2. 构建与运行

### 使用 Docker Compose (推荐)

在项目根目录下运行：

```bash
docker-compose up --build -d
```

这将会：
1. 构建 Docker 镜像。
2. 启动容器，并将服务绑定到宿主机的 8087 端口。
3. 挂载 `output` 目录和 `users.db` 文件，确保数据持久化。

查看日志：
```bash
docker-compose logs -f
```

停止服务：
```bash
docker-compose down
```

### 使用 Docker 命令

1. 构建镜像：
```bash
docker build -t car-price-predictor .
```

2. 运行容器：
```bash
docker run -d -p 8087:8087 \
  -v $(pwd)/output:/app/output \
  -v $(pwd)/users.db:/app/users.db \
  --env-file .env \
  --name car_predictor \
  car-price-predictor
```

## 3. 访问应用

服务启动后，可以通过浏览器访问：

- Web 界面: http://localhost:8087/
- API 文档: http://localhost:8087/docs

## 4. 远程访问与域名配置（推荐）

如果您希望远端用户通过域名访问，推荐使用 **Nginx 反向代理** 方案。

### 步骤 1：准备工作
1. 拥有一台云服务器（阿里云/腾讯云/AWS等），并安装好 Docker。
2. 拥有一个域名，并将其 A 记录解析到服务器 IP。

### 步骤 2：配置 Nginx
修改项目中的 `nginx/default.conf`，将 `server_name` 替换为您的域名：
```nginx
server {
    listen 80;
    server_name www.example.com;  # <--- 修改这里

    location / {
        proxy_pass http://web:8087;
        # ... 其他配置保持不变
    }
}
```

### 步骤 3：启动生产环境服务
使用专门的生产环境配置文件 `docker-compose.prod.yml`：

```bash
docker-compose -f docker-compose.prod.yml up --build -d
```

该命令会启动两个容器：
1. `car_price_predictor`: 核心应用服务（内部端口 8087）。
2. `nginx_proxy`: 反向代理服务（对外暴露 80 端口）。

访问 `http://your_domain.com` 即可使用。

---

## 5. 注意事项

- **数据文件**: 确保 `output` 目录下有 `merged_residual_value_data.csv`，或者让容器有权限生成它。
- **模型文件**: Docker 镜像会包含构建时的 `price_model` 和 `index` 目录下的文件。如果更新了模型，需要重新构建镜像。
