# GCP Cloud Run 배포용 초경량 Nginx 웹서버 Dockerfile
FROM nginx:alpine

# Gzip 압축 및 Cloud Run 기본 포트(8080) 설정 파일 복사
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 웹앱 정적 파일 복사
COPY index.html /usr/share/nginx/html/
COPY styles.css /usr/share/nginx/html/
COPY app.js /usr/share/nginx/html/
COPY data.js /usr/share/nginx/html/

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
