# 使用可访问的 Python 镜像源，避免 Docker Hub 直连失败。
# 如需切换，可在构建时覆盖 PYTHON_BASE_IMAGE。
ARG PYTHON_BASE_IMAGE=docker.m.daocloud.io/library/python:3.11-slim
FROM ${PYTHON_BASE_IMAGE}

# 设置工作目录
WORKDIR /app

# 修正容器内代理地址。Windows 主机上的 127.0.0.1 在 Linux 容器内不可达。
ARG HTTP_PROXY=http://host.docker.internal:7897
ARG HTTPS_PROXY=http://host.docker.internal:7897
ARG NO_PROXY=localhost,127.0.0.1
ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    http_proxy=${HTTP_PROXY} \
    https_proxy=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    no_proxy=${NO_PROXY}

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # WebUI 默认配置
    WEBUI_HOST=0.0.0.0 \
    WEBUI_PORT=1455 \
    LOG_LEVEL=info \
    DEBUG=0

# 安装系统依赖
# (curl_cffi 等库可能需要编译工具)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 暴露端口
EXPOSE 1455

# 启动 WebUI
CMD ["python", "webui.py"]
