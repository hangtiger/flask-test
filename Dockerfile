# 1. 使用官方轻量级 Python 镜像
FROM python:3.9-slim

# 2. 设置工作目录
WORKDIR /app

# 3. 安装依赖（测试环境直接装 flask 即可）
RUN pip install flask -i https://pypi.tuna.tsinghua.edu.cn/simple

# 4. 把当前目录下的代码复制到镜像里
COPY . .

# 5. 告诉云托管，程序运行在 80 端口
EXPOSE 80

# 6. 启动命令
CMD ["python", "app.py"]
