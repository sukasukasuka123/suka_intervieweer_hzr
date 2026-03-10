# service/tools/knowledge_tools.py
"""
知识库 RAG 检索工具
"""
from langchain_core.tools import tool
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════
# 知识库检索
# ═══════════════════════════════════════════════════════════════════

class KnowledgeSearchInput(BaseModel):
    query:           str = Field(...,       description="检索关键词或问题描述")
    job_position_id: int = Field(default=0, description="岗位 ID 过滤，0=通用")
    top_k:           int = Field(default=3, description="返回结果数，1~5", ge=1, le=5)


def create_rag_tool(knowledge_store):
    @tool(args_schema=KnowledgeSearchInput)
    def search_knowledge_base(
        query: str,
        job_position_id: int = 0,
        top_k: int = 3,
    ) -> str:
        """
        从阿里云百炼知识库检索与问题相关的技术知识。
        适合查询面试题答案、技术概念、最佳实践。
        优先于联网搜索使用，结果更权威且针对岗位定制。
        """
        results = knowledge_store.retrieve(
            query, job_position_id=job_position_id, top_k=top_k
        )
        if not results:
            return "知识库中未找到相关内容，建议使用联网搜索。"

        # 过滤无效结果
        valid = [r for r in results if not r.startswith("📭") and not r.startswith("⚠️")]
        if not valid:
            return results[0]  # 返回原始错误信息

        lines = [f"📚 知识库检索结果（关键词：{query}，共 {len(valid)} 条）：\n"]
        for i, r in enumerate(valid, 1):
            lines.append(f"[{i}] {r}\n")
        return "\n".join(lines)

    return search_knowledge_base
