# Iron-Fall 智能钢结构拆除决策系统

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)
![Unity](https://img.shields.io/badge/Unity-2022.3%20LTS-black.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**基于多源力学校验与实时推演的智能拆除决策系统**

*让每一次拆除都经过 AI 智能推演，确保安全与效率*

</div>

---

## 项目简介

Iron-Fall 是一款专为钢结构建筑拆除工程设计的智能决策系统。通过融合 AI 大模型、结构力学仿真引擎与实时 3D 可视化技术，系统能够自动生成最优拆除方案，并对施工过程进行全程安全监测与风险预警。

### 核心能力

- **AI 智能规划** - 基于 LangChain 的多智能体协作，自动分析建筑结构并生成拆除策略
- **双轨力学校验** - Frame3DD（快速分析）+ OpenSeesPy（深度非线性），确保结果可靠
- **实时 3D 推演** - Unity 3D 可视化展示拆除过程，提前发现潜在风险
- **端到端响应** - 标准 3 层钢框架推演延迟 ≤ 3 秒

## 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Unity 3D 前端                         │
│                   (WebSocket 实时通信)                        │
├─────────────────────────────────────────────────────────────┤
│                      FastAPI 后端服务                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  AI 智能体 │  │ 力学校验器 │  │ 推演引擎  │  │ 风险评估  │    │
│  │ LangChain│  │ Frame3DD │  │ OpenSees │  │ 预警系统  │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## 技术栈

| 层级 | 技术选型 |
|------|----------|
| **后端框架** | Python 3.10 + FastAPI + Uvicorn |
| **AI 能力** | LangChain + 多智能体协作 |
| **结构仿真** | Frame3DD (静力分析) + OpenSeesPy (非线性) |
| **前端渲染** | Unity 3D 2022.3 LTS (URP) |
| **实时通信** | WebSocket |
| **数据格式** | IFC (Industry Foundation Classes) |

## 快速开始

### 环境要求

- Python 3.10+
- Unity 2022.3 LTS
- Windows / Linux / macOS

### 安装部署

```bash
# 1. 克隆项目
git clone https://github.com/your-repo/Iron-Fall.git
cd Iron-Fall

# 2. 创建虚拟环境
python -m venv venv
# Windows
.\venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

# 3. 安装依赖
pip install -e .

# 4. 启动后端服务
cd backend
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000

# 5. 运行测试
pytest backend/tests/
```

### 启动 Unity 前端

1. 使用 Unity Hub 打开 `frontend_unity/` 目录
2. 选择场景文件并运行
3. 连接至 `http://localhost:8000`

## 项目结构

```
Iron-Fall/
├── backend/
│   ├── app/
│   │   ├── core/          # 核心数据模型 (IFCS 结构解析)
│   │   ├── engine/         # 仿真求解器适配器
│   │   ├── agent/          # AI 智能体模块
│   │   ├── api/            # FastAPI 路由与接口
│   │   └── utils/          # 工具函数库
│   └── tests/              # 单元测试与集成测试
├── frontend_unity/          # Unity 3D 前端项目
│   └── Assets/
│       ├── Scripts/        # C# 业务逻辑
│       └── Scenes/         # 场景资源
├── README.md
└── requirements.txt
```

## 核心 KPI

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 推演延迟 | ≤ 3 秒 | 标准 3 层钢框架，端到端响应 |
| 力学校验 | 双轨并行 | Frame3DD 快速验证 + OpenSeesPy 高危复核 |
| 可视化帧率 | ≥ 30 FPS | Unity 3D 实时渲染性能 |

## 应用场景

- 🏗️ **工业厂房拆除** - 复杂钢结构厂房的分步拆除规划
- 🏢 **建筑改造评估** - 部分拆除前的结构安全性分析
- 🛡️ **风险预防** - 提前识别拆除过程中的结构失稳风险
- 📊 **方案比选** - 多方案经济性、安全性综合评估

## 许可协议

本项目采用 [MIT License](LICENSE) 开源，欢迎贡献与使用。

---

<div align="center">

**Made with precision, designed for safety**

</div>
