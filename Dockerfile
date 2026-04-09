# 使用官方 Python 3.9 slim 镜像作为基础
FROM python:3.9-slim

# Replace apt sources with Aliyun mirrors for China connectivity
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources; \
    else \
        sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list && \
        sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list; \
    fi

# 设置容器内的工作目录
WORKDIR /app

# 安装系统依赖（如果需要构建某些 python 包）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件到容器中
COPY requirements.txt .

# 安装 Python 依赖
# 使用阿里云镜像源加速下载 (可选，如果部署环境在中国)
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 复制项目代码到容器中
COPY . .

# 暴露应用运行的端口
EXPOSE 8087

# 设置环境变量
ENV PYTHONPATH=/app/src
# 解决中文编码问题
ENV LANG=C.UTF-8

# 运行应用
# 注意：这里假设 web_predictor_debug_step5.py 会自动切换工作目录到 project_root
CMD ["python", "src/web_predictor_debug_step5.py", "--port", "8087", "--host", "0.0.0.0"]
