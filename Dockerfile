# ComicHub — 静态前端 + nginx (含 MangaDex 反代)
FROM nginx:1.27-alpine

# nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 静态前端
COPY www/ /usr/share/nginx/html/

# 数据目录挂载点 (docker-compose 挂载 ./data → /data/manga)
RUN mkdir -p /data/manga

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
