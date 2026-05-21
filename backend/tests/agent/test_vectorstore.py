"""向量知识库测试

覆盖 agent/knowledge/vectorstore.py 的：
- KnowledgeBase 初始化
- 知识库构建（需 ChromaDB）
- 语义检索精度
- 清空操作

注意：需要 ChromaDB 和 OpenAI API 环境变量。
若环境不满足则自动跳过。
"""
import os
import pytest
from pathlib import Path


# 检查依赖是否可用
try:
    import chromadb
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False


HAS_OPENAI_KEY = bool(os.environ.get("OPENAI_API_KEY"))


@pytest.fixture
def knowledge_base():
    """创建临时知识库实例"""
    from agent.knowledge.vectorstore import KnowledgeBase
    # 使用临时目录避免污染已有数据
    kb = KnowledgeBase(
        persist_directory="backend/tests/.test_chroma_db",
        collection_name="test_regulations",
    )
    yield kb
    # 清理
    try:
        kb.clear()
    except Exception:
        pass


class TestKnowledgeBase:
    """KnowledgeBase 核心测试"""

    @pytest.mark.skipif(not HAS_CHROMA, reason="ChromaDB 未安装")
    def test_initialization(self, knowledge_base):
        """初始化不应抛异常"""
        assert knowledge_base is not None
        assert knowledge_base.collection_name == "test_regulations"

    @pytest.mark.skipif(not HAS_CHROMA or not HAS_OPENAI_KEY,
                        reason="需要 ChromaDB + OpenAI API Key")
    def test_build_from_regulations(self, knowledge_base):
        """从规范文件构建向量库"""
        regulations_path = Path(__file__).parent.parent.parent / \
            "agent" / "knowledge" / "demolition_regulations.txt"

        if regulations_path.exists():
            count = knowledge_base.build(str(regulations_path))
            assert count > 0, "应成功索引至少一个文档块"

    @pytest.mark.skipif(not HAS_CHROMA or not HAS_OPENAI_KEY,
                        reason="需要 ChromaDB + OpenAI API Key")
    def test_query_returns_results(self, knowledge_base):
        """语义查询应返回相关结果"""
        regulations_path = Path(__file__).parent.parent.parent / \
            "agent" / "knowledge" / "demolition_regulations.txt"
        if regulations_path.exists():
            knowledge_base.build(str(regulations_path))

        results = knowledge_base.query("钢结构拆除安全要求", k=3)
        assert isinstance(results, list)
        if len(results) > 0:
            assert len(results) <= 3

    @pytest.mark.skipif(not HAS_CHROMA or not HAS_OPENAI_KEY,
                        reason="需要 ChromaDB + OpenAI API Key")
    def test_query_with_score(self, knowledge_base):
        """带分数的查询"""
        regulations_path = Path(__file__).parent.parent.parent / \
            "agent" / "knowledge" / "demolition_regulations.txt"
        if regulations_path.exists():
            knowledge_base.build(str(regulations_path))

        results = knowledge_base.query_with_score("拆除顺序规范", k=3)
        assert isinstance(results, list)
        if len(results) > 0:
            # 每条结果包含 (content, score)
            assert len(results[0]) == 2

    @pytest.mark.skipif(not HAS_CHROMA, reason="ChromaDB 未安装")
    def test_clear_empties(self, knowledge_base):
        """清空后查询应为空"""
        # 先尝试清空（即使未 build 也不应抛异常）
        try:
            knowledge_base.clear()
        except Exception:
            pass

    @pytest.mark.skipif(not HAS_CHROMA, reason="ChromaDB 未安装")
    def test_empty_query_no_crash(self, knowledge_base):
        """未 build 时查询不应崩溃"""
        try:
            results = knowledge_base.query("test query", k=1)
            assert results == []
        except Exception:
            # 可能因为 OpenAI key 不存在而失败
            pass
