# Iron-Fall API 文档

> 智能钢结构拆除决策系统 API 参考

## 概述

Iron-Fall API 基于 FastAPI 构建，提供 RESTful 和 WebSocket 两种接口方式，用于与智能拆除决策系统进行交互。

**基础 URL**: `http://localhost:8000`

**API 文档**: `http://localhost:8000/docs` (Swagger UI)

## 认证

当前版本无需认证，请在生产环境中自行实现认证机制。

---

## 健康检查

### GET /health

检查服务健康状态和计算引擎状态。

**响应示例**:
```json
{
  "status": "healthy",
  "service": "Iron-Fall",
  "engines": {
    "frame3dd": "3.0.0",
    "opensees": "3.5.0"
  }
}
```

---

## 模型管理

### POST /api/v1/model/validate

验证结构模型的有效性。

**请求体**: [StructureModel](#structuremodel)

**响应**:
```json
{
  "success": true,
  "error": null,
  "latency_ms": 12.5
}
```

---

## 结构分析

### POST /api/v1/analysis/static

执行静力分析。

**请求体**: [StructureModel](#structuremodel)

**响应**:
```json
{
  "success": true,
  "analysis": {
    "node_displacements": {"1": [0.001, -0.005, 0.002]},
    "element_stresses": {"1": 125.5},
    "max_displacement": 0.005,
    "stability_status": "Stable",
    "is_safe": true,
    "warnings": []
  },
  "latency_ms": 156.2
}
```

### POST /api/v1/analysis/dynamic

执行动力分析（拆除模拟）。

**请求体**:
```json
{
  "model": { /* StructureModel */ },
  "action": {
    "step": 1,
    "target_element_ids": [5, 6],
    "action_type": "Remove"
  }
}
```

### POST /api/v1/analysis/deep

执行深度非线性分析（使用 OpenSeesPy）。

**请求参数**:
- `use_opensees` (bool, optional): 是否使用 OpenSeesPy，默认 `true`

**请求体**: [StructureModel](#structuremodel) + [DemolitionAction](#demolitionaction)

---

## 稳定性检查

### POST /api/v1/stability/check

检查结构稳定性。

**请求参数**:
- `threshold` (float, optional): 位移阈值（米），默认 `0.05`

**请求体**: [StructureModel](#structuremodel)

**响应**:
```json
{
  "is_stable": true,
  "max_displacement": 0.023,
  "threshold": 0.05,
  "latency_ms": 145.3
}
```

---

## AI 决策

### POST /api/v1/agent/plan

AI 智能体生成拆除方案。

**请求体**:
```json
{
  "model": { /* StructureModel */ },
  "user_request": "请生成安全的拆除方案"
}
```

**响应**:
```json
{
  "success": true,
  "plan": {
    "plan_id": "plan_20260521_001",
    "description": "分三步拆除上部非承重构件",
    "actions": [
      {
        "step": 1,
        "target_element_ids": [3, 4],
        "action_type": "Remove"
      }
    ],
    "risk_level": "Low"
  },
  "latency_ms": 2340.5
}
```

### POST /api/v1/agent/validate

验证拆除方案的安全性。

**请求体**:
```json
{
  "model": { /* StructureModel */ },
  "plan": { /* DemolitionPlan */ }
}
```

---

## WebSocket 实时接口

### WS /ws/demolition

实时拆除推演 WebSocket 接口。

**连接**: `ws://localhost:8000/ws/demolition`

### 客户端 → 服务端

#### ping 消息
```json
{"type": "ping"}
```

#### demolish 消息
```json
{
  "type": "demolish",
  "model": { /* StructureModel */ },
  "action": {
    "step": 1,
    "target_element_ids": [5],
    "action_type": "Remove"
  }
}
```

#### validate 消息
```json
{
  "type": "validate",
  "model": { /* StructureModel */ }
}
```

### 服务端 → 客户端

#### pong 响应
```json
{"type": "pong"}
```

#### result 响应
```json
{
  "type": "result",
  "success": true,
  "analysis": { /* AnalysisResult */ },
  "latency_ms": 156.2
}
```

#### validation_result 响应
```json
{
  "type": "validation_result",
  "is_valid": true,
  "error": null
}
```

#### error 响应
```json
{
  "type": "error",
  "message": "Unknown message type: unknown"
}
```

---

## 数据模型

### StructureModel

完整结构模型。

| 字段 | 类型 | 描述 |
|------|------|------|
| `model_id` | string | 模型唯一标识符 |
| `name` | string | 模型名称 |
| `nodes` | list[Node] | 节点列表 |
| `elements` | list[Element] | 构件列表 |
| `sections` | list[Section] | 截面列表 |
| `materials` | list[Material] | 材料列表 |
| `unit` | string | 单位系统，默认 "SI" |

### Node

节点模型。

| 字段 | 类型 | 描述 |
|------|------|------|
| `id` | int | 节点唯一标识符 |
| `x` | float | X 坐标 (m) |
| `y` | float | Y 坐标 (m) |
| `z` | float | Z 坐标 (m) |
| `restraint` | list[bool] | 约束条件 [Ux, Uy, Uz, Rx, Ry, Rz] |

### Element

构件模型。

| 字段 | 类型 | 描述 |
|------|------|------|
| `id` | int | 构件唯一标识符 |
| `node_i_id` | int | i 端节点 ID |
| `node_j_id` | int | j 端节点 ID |
| `section_id` | int | 截面 ID |
| `material_id` | int | 材料 ID |
| `element_type` | ElementType | 构件类型 (Column/Beam/Brace) |

### Section

截面模型。

| 字段 | 类型 | 描述 |
|------|------|------|
| `id` | int | 截面唯一标识符 |
| `name` | string | 截面名称 (如 "H400x200") |
| `A` | float | 截面积 (mm²) |
| `Iy` | float | 绕 y 轴惯性矩 (mm⁴) |
| `Iz` | float | 绕 z 轴惯性矩 (mm⁴) |
| `J` | float | 扭转常数 (mm⁴) |

### Material

材料模型。

| 字段 | 类型 | 描述 |
|------|------|------|
| `id` | int | 材料唯一标识符 |
| `name` | string | 材料牌号 (如 "Q355") |
| `E` | float | 弹性模量 (MPa) |
| `fy` | float | 屈服强度 (MPa) |
| `density` | float | 密度 (kg/m³) |

### DemolitionAction

拆除动作模型。

| 字段 | 类型 | 描述 |
|------|------|------|
| `step` | int | 操作步骤序号 |
| `target_element_ids` | list[int] | 目标构件 ID 列表 |
| `action_type` | string | 动作类型 ("Remove" 或 "ApplyForce") |
| `force_vector` | tuple[float] | 外力向量 (可选) |

### DemolitionPlan

拆除方案模型。

| 字段 | 类型 | 描述 |
|------|------|------|
| `plan_id` | string | 方案唯一标识符 |
| `description` | string | 方案描述 |
| `actions` | list[DemolitionAction] | 拆除动作序列 |
| `risk_level` | string | 风险等级 (Low/Medium/High/Critical) |

### AnalysisResult

分析结果模型。

| 字段 | 类型 | 描述 |
|------|------|------|
| `node_displacements` | dict | 节点位移 {node_id: [Ux, Uy, Uz, Rx, Ry, Rz]} |
| `element_stresses` | dict | 构件应力 {element_id: stress_value} |
| `max_displacement` | float | 最大位移值 (m) |
| `stability_status` | string | 稳定性状态 |
| `is_safe` | bool | 是否安全可执行 |
| `warnings` | list[str] | 警告信息 |

---

## 错误处理

API 使用标准 HTTP 状态码：

| 状态码 | 描述 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 404 | 资源未找到 |
| 422 | 请求体验证失败 |
| 500 | 服务器内部错误 |

错误响应格式：
```json
{
  "detail": "错误描述信息"
}
```

---

## 速率限制

当前版本未实现速率限制，请在生产环境中配置。

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0.0 | 2026-05-21 | 初始发布 |
