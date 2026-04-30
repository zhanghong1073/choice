# Quant Fullstack (Python + Node + React + Vite)

## 1) 启动后端
```bash
cd /Users/zhanghong/Desktop/choice
./run_backend.sh
```
后端地址: http://127.0.0.1:8000

## 2) 启动前端
新开一个终端:
```bash
cd /Users/zhanghong/Desktop/choice
./run_frontend.sh
```
前端地址: http://127.0.0.1:5173

## 3) 环境变量（可选）
前端默认请求 `http://127.0.0.1:8000`。
如果你要改后端地址，在 `frontend/.env` 配置:
```bash
VITE_API_BASE=http://127.0.0.1:8000
```
