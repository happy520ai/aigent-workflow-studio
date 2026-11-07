# T60：npm ci 按 lockfile 精确安装 + nginx 非 root（unprivileged 镜像，监听 8080）
FROM node:24-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# T60：容器健康检查（前端静态页可达）
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
