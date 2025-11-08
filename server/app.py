from flask import Flask, jsonify
from flask_cors import CORS

# 创建 Flask 应用（最小可用），先不接数据库，保证能跑通
app = Flask(__name__)
CORS(app)  # 允许前端本地联调访问 /api/*

@app.get("/api/health")
def health():
    """最小健康检查接口：用于前端、Docker、CI 自测"""
    return jsonify(ok=True, service="server", version="v0"), 200

if __name__ == "__main__":
    # 开发模式启动：0.0.0.0 便于容器/局域访问
    app.run(host="0.0.0.0", port=8000, debug=True)
