# 给支持 Docker 的托管平台用；本地运行不需要它。
FROM python:3.12-slim
WORKDIR /app
COPY . .
ENV PORT=8080
EXPOSE 8080
CMD ["python3", "server.py"]
