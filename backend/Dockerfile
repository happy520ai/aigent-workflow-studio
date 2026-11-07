# T60：多阶段构建 + 非 root + HEALTHCHECK
FROM python:3.11-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.11-slim

WORKDIR /app

# 仅拷贝依赖产物，不带 gcc
COPY --from=builder /install /usr/local
COPY . .

# T60：非 root 运行
RUN useradd --create-home --shell /bin/bash aigent \
    && mkdir -p /app/data && chown -R aigent:aigent /app
USER aigent

ENV AIGENT_DB_PATH=/app/data/aigent_checkpoints.db
EXPOSE 8000

# T60：容器健康检查（/healthz 免鉴权，T20）
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status==200 else 1)"

# --proxy-headers + --forwarded-allow-ips：让 request.client.host 反映 X-Forwarded-For
# （nginx 反代场景下 require_admin 才能识别出本机访问者）。
# 默认仅信任回环，与"无管理令牌时只允许本机"的安全语义一致；
# compose 部署在受信内网时可通过 AIGENT_FORWARDED_ALLOW_IPS 放宽到容器网段。
CMD ["sh", "-c", "uvicorn perfect_main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"${AIGENT_FORWARDED_ALLOW_IPS:-127.0.0.1,::1}\""]
