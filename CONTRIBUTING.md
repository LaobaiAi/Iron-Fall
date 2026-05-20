# 贡献指南

感谢您对 Iron-Fall 项目的关注！我们欢迎所有形式的贡献，包括但不限于代码提交、问题报告、文档改进等。

## 行为准则

参与本项目的所有成员必须遵守以下行为准则：
- 保持友好和包容的交流氛围
- 尊重不同的观点和经历
- 建设性地处理分歧
- 专注于对项目最有利的事情

## 开发环境设置

### 前置要求

- Python 3.10+
- Git
- Unity 2022.3 LTS (仅前端开发需要)

### 克隆与安装

```bash
# 1. Fork 项目到您的 GitHub 账户
# 2. 克隆您的 Fork
git clone https://github.com/YOUR_USERNAME/Iron-Fall.git
cd Iron-Fall

# 3. 创建虚拟环境
python -m venv venv

# Windows
.\venv\Scripts\activate

# Linux / macOS
source venv/bin/activate

# 4. 安装依赖
pip install -e .

# 5. 安装开发依赖
pip install black isort pytest pytest-asyncio
```

### 代码格式化

项目使用 `black` 和 `isort` 保持代码风格一致：

```bash
# 格式化 Python 代码
black backend/
isort backend/

# 检查格式
black --check backend/
isort --check backend/
```

## 分支策略

```
main (保护分支)
  └── develop
        └── feature/*   # 新功能开发
        └── bugfix/*    # Bug 修复
        └── docs/*      # 文档更新
```

- `main`: 稳定版本，仅通过 PR 合并
- `develop`: 开发分支，所有功能合并至此
- 功能分支命名: `feat/{功能描述}`, `fix/{问题描述}`

## 开发工作流

### 1. 创建功能分支

```bash
# 从 develop 创建新分支
git checkout develop
git pull origin develop
git checkout -b feature/your-feature-name
```

### 2. 开发与提交

```bash
# 编写代码...
# 运行测试
pytest backend/tests/ -v

# 格式化代码
black backend/
isort backend/

# 提交 (遵循 Commit 规范)
git add .
git commit -m "feat(engine): add OpenSeesPy adapter for nonlinear analysis"
```

### 3. Commit 规范

项目遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

**类型 (type)**:
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建/工具相关

**示例**:
```bash
git commit -m "feat(agent): add CheckStabilityTool for structural analysis"
git commit -m "fix(api): resolve websocket reconnect issue on timeout"
git commit -m "docs(readme): update installation steps for Windows"
```

### 4. 推送与 Pull Request

```bash
# 推送分支
git push origin feature/your-feature-name

# 在 GitHub 上创建 Pull Request
# 目标分支: develop
```

### 5. Pull Request 检查清单

提交 PR 前，请确保：

- [ ] 代码遵循项目编码规范
- [ ] 添加了必要的单元测试
- [ ] 所有测试通过 (`pytest backend/tests/`)
- [ ] 代码已格式化 (`black`, `isort`)
- [ ] 提交信息符合规范
- [ ] 更新了相关文档（如有必要）

## 代码审查

所有 PR 需要经过代码审查：
- 至少一名维护者 approve
- 无未解决的评论
- CI/CD 检查全部通过

## 报告问题

通过 GitHub Issues 报告问题时，请包含：
- 问题描述（清晰简洁）
- 复现步骤
- 预期行为 vs 实际行为
- 环境信息（OS, Python 版本等）
- 相关日志或截图

## 许可证

通过贡献代码，您同意将您的作品按照 [MIT License](LICENSE) 授权。

---

再次感谢您的贡献！
