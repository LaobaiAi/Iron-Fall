# Iron-Fall 启动说明

## 环境要求

- Python 3.10+
- Windows / Linux / macOS
- （可选）Unity 2022.3 LTS

## 快速启动

### 1. 创建虚拟环境（首次使用）

```bash
cd Iron-Fall
python -m venv venv
```

### 2. 激活虚拟环境

**Windows:**
```bash
.\venv\Scripts\activate
```

**Linux / macOS:**
```bash
source venv/bin/activate
```

### 3. 安装依赖（首次使用）

```bash
pip install -e .
```

### 4. 启动后端服务

```bash
cd backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

看到以下输出表示启动成功：

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [xxxxx] using WatchFiles
```

### 5. 打开前端

**方式一：Web 客户端（推荐）**

直接双击或在浏览器中打开 `web_client.html`

**方式二：Unity 3D 前端**

用 Unity Hub 打开 `frontend_unity/` 目录，选择场景文件运行。

---

## 使用流程

1. 在打开的 Web 页面中，点击 **"连接服务器"** 建立 WebSocket 连接
2. 点击 **"生成拆除方案"**，AI 自动分析结构并规划拆除顺序
3. 点击 **"开始推演"**，3D 视图实时展示拆除过程
4. 还可使用 **"力学校验"** 对当前方案进行安全性复核

---

## 各服务端口

| 服务 | 地址 |
|------|------|
| 后端 API | `http://localhost:8000` |
| API 文档 (Swagger) | `http://localhost:8000/docs` |
| WebSocket | `ws://localhost:8000/ws/demolition` |

## 停止服务

在后端终端按 `Ctrl+C` 即可停止 FastAPI 服务。
