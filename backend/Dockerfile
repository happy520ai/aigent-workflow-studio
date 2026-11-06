FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# --proxy-headers + --forwarded-allow-ips：让 request.client.host 反映 X-Forwarded-For
# （nginx 反代场景下 require_admin 才能识别出本机访问者）。
# 默认仅信任回环，与"无管理令牌时只允许本机"的安全语义一致；
# compose 部署在受信内网时可通过 AIGENT_FORWARDED_ALLOW_IPS 放宽到容器网段。
CMD ["sh", "-c", "uvicorn perfect_main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"${AIGENT_FORWARDED_ALLOW_IPS:-127.0.0.1,::1}\""]
