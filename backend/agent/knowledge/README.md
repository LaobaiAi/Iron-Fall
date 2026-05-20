# 钢结构拆除规范知识库

本目录存放 Iron-Fall 系统的规范知识库文件。

## 文件说明

- `demolition_regulations.txt` - 钢结构拆除施工安全技术规范
- `structural_mechanics.txt` - 结构力学基础知识
- `risk_control.txt` - 风险控制要点

## 知识库构建

使用 ChromaDB 构建向量数据库，支持语义检索。

### 构建命令

```bash
python -m backend.agent.knowledge.build
```

### 查询示例

```python
from backend.agent.knowledge.vectorstore import KnowledgeBase

kb = KnowledgeBase()
results = kb.query("底层柱拆除要求")
```
