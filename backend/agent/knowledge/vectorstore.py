"""ChromaDB 向量知识库

基于 ChromaDB 的 RAG 知识检索系统。
"""
import os
from pathlib import Path
from typing import Optional
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader


class KnowledgeBase:
    """钢结构拆除规范知识库"""

    def __init__(
        self,
        persist_directory: str = "backend/agent/knowledge/chroma_db",
        collection_name: str = "demolition_regulations"
    ):
        """初始化知识库
        
        Args:
            persist_directory: ChromaDB 持久化目录
            collection_name: 集合名称
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self._vectorstore: Optional[Chroma] = None
        self._embeddings = OpenAIEmbeddings()
        
    @property
    def vectorstore(self) -> Optional[Chroma]:
        """延迟加载向量数据库"""
        if self._vectorstore is None:
            self._vectorstore = self._load_or_create()
        return self._vectorstore
    
    def _load_or_create(self) -> Chroma:
        """加载已有知识库或创建新的"""
        persist_path = Path(self.persist_directory)
        
        if persist_path.exists() and any(persist_path.iterdir()):
            return Chroma(
                persist_directory=self.persist_directory,
                embedding_function=self._embeddings,
                collection_name=self.collection_name
            )
        return None
    
    def build(self, knowledge_dir: str = "backend/agent/knowledge") -> None:
        """构建知识库
        
        从知识目录加载文档，分块后存储到 ChromaDB。
        
        Args:
            knowledge_dir: 知识文件目录
        """
        docs_path = Path(knowledge_dir)
        if not docs_path.exists():
            raise FileNotFoundError(f"知识目录不存在: {knowledge_dir}")
        
        documents = []
        for txt_file in docs_path.glob("*.txt"):
            loader = TextLoader(str(txt_file), encoding="utf-8")
            documents.extend(loader.load())
        
        if not documents:
            raise ValueError(f"未找到知识文件: {knowledge_dir}/*.txt")
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            length_function=len
        )
        
        splits = text_splitter.split_documents(documents)
        
        self._vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=self._embeddings,
            persist_directory=self.persist_directory,
            collection_name=self.collection_name
        )
        
        self._vectorstore.persist()
    
    def query(self, query: str, k: int = 3) -> list[str]:
        """语义检索
        
        Args:
            query: 查询文本
            k: 返回结果数量
            
        Returns:
            检索到的文本片段列表
        """
        if self.vectorstore is None:
            return ["知识库未初始化，请先运行 build() 方法"]
        
        results = self.vectorstore.similarity_search(query, k=k)
        return [doc.page_content for doc in results]
    
    def query_with_score(self, query: str, k: int = 3, threshold: float = 0.7) -> list[tuple[str, float]]:
        """带相似度分数的检索
        
        Args:
            query: 查询文本
            k: 返回结果数量
            threshold: 相似度阈值
            
        Returns:
            (文本片段, 相似度分数) 元组列表
        """
        if self.vectorstore is None:
            return [("知识库未初始化，请先运行 build() 方法", 0.0)]
        
        results = self.vectorstore.similarity_search_with_score(query, k=k)
        return [
            (doc.page_content, score) 
            for doc, score in results 
            if score < threshold
        ]
    
    def clear(self) -> None:
        """清空知识库"""
        import shutil
        if Path(self.persist_directory).exists():
            shutil.rmtree(self.persist_directory)
        self._vectorstore = None


def main():
    """知识库构建脚本"""
    import argparse
    
    parser = argparse.ArgumentParser(description="构建钢结构拆除规范知识库")
    parser.add_argument("--rebuild", action="store_true", help="强制重建知识库")
    args = parser.parse_args()
    
    kb = KnowledgeBase()
    
    if args.rebuild:
        kb.clear()
        print("已清空旧知识库")
    
    print("开始构建知识库...")
    kb.build()
    print("知识库构建完成!")
    
    print("\n测试检索:")
    results = kb.query("底层柱拆除要求")
    for i, r in enumerate(results, 1):
        print(f"\n结果 {i}:\n{r[:200]}...")


if __name__ == "__main__":
    main()
