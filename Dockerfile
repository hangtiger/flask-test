FROM python:3.9-slim

# 安装 ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt -i https://mirrors.tencent.com/pypi/simple/

COPY . .

EXPOSE 80

CMD ["python", "app.py"]
