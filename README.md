# B/S 程序设计 · 图片管理网站

- 课程项目：图片管理网站（Browser/Server/Database）
- 技术栈：前端 Vue3 + Element Plus + Pinia + Axios + Vite；后端 Flask + JWT + SQLAlchemy；数据库 MySQL 8；部署 Docker & Compose
- 目标：先环境配置与最小框架 → 建库建表（与报告字段一致，含 avatar_url 等）→ 注册/登录联通 → 持续完善

## Docker 运行

1. 构建镜像：
   ```bash
   docker compose build
   ```
2. 启动服务：
   ```bash
   docker compose up -d
   ```
3. 访问：
   - 电脑：`http://localhost:8080`
   - 手机（同一局域网）：`http://<宿主机局域网IP>:8080`

停止服务：
```bash
docker compose down
```

说明：前端由 Nginx 提供，`/api` 与 `/files` 同源反向代理到后端，手机端上传保持一致。
