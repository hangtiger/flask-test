from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello():
    return "<h1>Hello, Cloud Run! 这是我的第一个测试版本。</h1>"

if __name__ == "__main__":
    # 注意：云托管默认监听 80 端口
    app.run(debug=True, host='0.0.0.0', port=80)
