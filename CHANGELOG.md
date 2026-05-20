# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-05-21

### Added

#### Phase 1: 核心基建 (Core Infrastructure)
- **IFCS 数据模型** (`core/models.py`)
  - `StructureModel` - 完整结构模型
  - `Node` - 节点模型
  - `Element` - 构件模型
  - `Section` - 截面模型
  - `Material` - 材料模型
  - `DemolitionAction` - 拆除动作模型
  - `DemolitionPlan` - 拆除方案模型
  - `AnalysisResult` - 分析结果模型

- **Frame3DD 求解器适配器** (`engine/frame3dd.py`)
  - 静力分析 (`run_static_analysis`)
  - 动力分析 (`run_dynamic_analysis`)
  - 稳定性检查 (`check_stability`)
  - 2秒超时保护机制

- **OpenSeesPy 求解器适配器** (`engine/opensees.py`)
  - 深度非线性分析支持

- **FastAPI 服务** (`api/main.py`)
  - `/api/v1/model/validate` - 模型验证接口
  - `/api/v1/analysis/static` - 静力分析接口
  - `/api/v1/analysis/dynamic` - 动力分析接口
  - `/api/v1/analysis/deep` - 深度分析接口
  - `/api/v1/stability/check` - 稳定性检查
  - `/api/v1/agent/plan` - AI 方案生成
  - `/api/v1/agent/validate` - 方案安全验证
  - `/ws/demolition` - WebSocket 实时接口

#### Phase 2: AI 决策引擎 (AI Decision Engine)
- **LangChain Agent** (`agent/agent.py`)
  - `DemolitionAgent` - GPT-4 驱动智能体
  - `SimpleDemolitionAgent` - 简化版本（无 API Key 时使用）
  - ReAct 推理范式

- **工具集** (`agent/tools.py`)
  - `CheckStabilityTool` - 稳定性检查工具
  - `PredictCollapseTool` - 倒塌预测工具
  - `AnalyzeLoadPathTool` - 荷载路径分析工具
  - `GetElementInfoTool` - 构件信息查询工具

- **知识库** (`agent/knowledge/`)
  - 钢结构拆除规范文本
  - ChromaDB RAG 向量库支持

#### Phase 3: 实时可视化 (Real-time Visualization)
- **Unity 前端** (`frontend_unity/`)
  - `IronFallWebSocket.cs` - WebSocket 客户端
  - `DemolitionController.cs` - 拆除物理控制器
  - `SteelFrameModel.cs` - 钢框架模型管理
  - `StructureBuilder.cs` - 结构构建器
  - `PerformanceOptimizer.cs` - 性能优化器

- **物理模拟**
  - 基于 Unity PhysX 的刚体动力学
  - 支持构件移除后的倒塌动画
  - 针对 AMD 4500U 的性能优化（30 FPS 目标）

#### Phase 4: 集成与开源 (Integration & Open Source)
- **文档**
  - `README.md` - 项目说明文档
  - `CONTRIBUTING.md` - 贡献指南
  - `docs/API.md` - API 接口文档
  - `CHANGELOG.md` - 变更日志

- **许可证**
  - MIT License (LICENSE)

### Technical Specifications

| 指标 | 目标值 | 状态 |
|------|--------|------|
| 推演延迟 | ≤ 3 秒 | 已达成 |
| 力学校验 | 双轨并行 | 已实现 |
| 可视化帧率 | ≥ 30 FPS | 已实现 |
| 单元测试覆盖 | - | 12 测试通过 |

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Unity 3D 前端                          │
│                   (WebSocket 实时通信)                         │
├─────────────────────────────────────────────────────────────┤
│                      FastAPI 后端服务                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │  AI 智能体 │  │ 力学校验器 │  │ 推演引擎  │  │ 风险评估  │     │
│  │ LangChain│  │ Frame3DD │  │ OpenSees │  │ 预警系统  │     │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### Dependencies

- Python 3.10+
- FastAPI 0.109+
- LangChain 0.1.0+
- Frame3DD (CLI)
- Unity 3D 2022.3 LTS

### Known Limitations

- OpenSeesPy 需手动安装 (`pip install openseespy`)
- Frame3DD 需单独安装并添加到 PATH
- 当前版本仅支持简单钢框架结构

---

## [0.1.0] - 2026-05-14

### Added
- 项目初始化
- 基础目录结构
- 项目宪法 (Constitution V1.0)

---

<!-- Links -->
[1.0.0]: https://github.com/LaobaiAi/Iron-Fall/releases/tag/v1.0.0
[0.1.0]: https://github.com/LaobaiAi/Iron-Fall/releases/tag/v0.1.0
