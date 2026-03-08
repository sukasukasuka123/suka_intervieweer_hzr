# service/tools/registry.py
"""
面试 Agent 工具集
包含：
  1. 查询学生历史面试记录
  2. 查询岗位信息
  3. 知识库检索（RAG）
  4. 题库抽题工具（按分类/难度随机抽题）
  5. 题库内容查询（精确搜索）
  6. 题库分类统计
  7. Tavily 网络搜索
  8. Wikipedia 技术概念查询
"""
import json
import os
import random
from typing import List, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from dotenv import load_dotenv
load_dotenv()  # 加载 .env 文件到 os.environ

# ── Tavily 搜索（使用新包 langchain-tavily）────────────────────────────────────
try:
    from langchain_tavily import TavilySearch
except ImportError:
    # 兼容旧版本
    try:
        from langchain_community.tools.tavily_search import TavilySearchResults as TavilySearch
    except ImportError:
        TavilySearch = None

# ── Wikipedia 查询 ────────────────────────────────────────────────────────────
try:
    from langchain_community.tools import WikipediaQueryRun
    from langchain_community.utilities import WikipediaAPIWrapper
except ImportError:
    from langchain_community.tools.wikipedia.tool import WikipediaQueryRun
    from langchain_community.utilities.wikipedia import WikipediaAPIWrapper

# ── Model 1：查询学生面试历史输入 ──────────────────────────────────────────────

class StudentHistoryInput(BaseModel):
    """查询学生历史面试记录工具的输入参数"""
    student_id: int = Field(..., description="学生的唯一 ID，用于查询其面试历史")

def create_history_tool(db):
    @tool(args_schema=StudentHistoryInput)
    def get_student_interview_history(student_id: int) -> str:
        """查询指定学生的历史面试记录，包含各次面试的岗位、得分和时间。"""
        rows = db.fetchall(
            """
            SELECT s.name, jp.name, iss.started_at, iss.overall_score, iss.status
            FROM interview_session iss
            JOIN student s ON iss.student_id = s.id
            JOIN job_position jp ON iss.job_position_id = jp.id
            WHERE iss.student_id = ?
            ORDER BY iss.started_at DESC
            """,
            (student_id,),
        )
        if not rows:
            return f"学生 ID={student_id} 暂无面试记录。"

        lines = [f"学生「{rows[0][0]}」历史面试记录（共 {len(rows)} 次）："]
        for student_name, job_name, started_at, score, status in rows:
            score_str = f"{score:.1f}/10" if score else "未完成"
            lines.append(f"  - 岗位：{job_name}  得分：{score_str}  时间：{started_at[:10]}  状态：{status}")
        return "\n".join(lines)

    return get_student_interview_history


# ── Model 2：查询岗位信息输入 ──────────────────────────────────────────────────

class JobInfoInput(BaseModel):
    """查询岗位信息工具的输入参数"""
    job_position_id: Optional[int] = Field(default=None, description="岗位 ID。不传则列出所有岗位；传入则返回该岗位详细技术栈")

def create_job_info_tool(db):
    @tool(args_schema=JobInfoInput)
    def get_job_position_info(job_position_id: Optional[int] = None) -> str:
        """查询岗位信息。不传 ID 则列出所有岗位；传入 ID 则返回该岗位的详细技术栈。"""
        if job_position_id is None:
            rows = db.fetchall("SELECT id, name, description FROM job_position")
            if not rows:
                return "暂无岗位信息。"
            lines = ["当前支持的面试岗位："]
            for jid, name, desc in rows:
                lines.append(f"  [{jid}] {name}：{desc or '无描述'}")
            return "\n".join(lines)

        row = db.fetchone(
            "SELECT name, description, tech_stack FROM job_position WHERE id=?",
            (job_position_id,),
        )
        if not row:
            return f"未找到岗位 ID={job_position_id}"
        name, desc, tech_json = row
        tech = json.loads(tech_json)
        return f"岗位：{name}\n描述：{desc}\n核心技术栈：{', '.join(tech)}"

    return get_job_position_info


# ── Model 3：知识库 RAG 检索输入 ───────────────────────────────────────────────

class KnowledgeSearchInput(BaseModel):
    """知识库检索工具的输入参数"""
    query: str = Field(..., description="检索关键词或问题描述")
    job_position_id: int = Field(default=0, description="岗位 ID 过滤。0=通用知识库；1=Java 后端；2=前端等")

def create_rag_tool(knowledge_store):
    @tool(args_schema=KnowledgeSearchInput)
    def search_knowledge_base(query: str, job_position_id: int = 0) -> str:
        """
        从本地知识库检索与问题相关的技术知识。
        适合查询面试题答案、技术概念、最佳实践。
        """
        results = knowledge_store.retrieve(query, job_position_id=job_position_id, top_k=3)
        if not results:
            return "知识库中未找到相关内容。"
        lines = [f"知识库检索结果（关键词：{query}）："]
        for i, r in enumerate(results, 1):
            lines.append(f"\n[{i}] {r}")
        return "\n".join(lines)

    return search_knowledge_base


# ── Model 4：题库抽题输入 ──────────────────────────────────────────────────────

class QuizDrawInput(BaseModel):
    """题库抽题工具的输入参数"""
    classify: str = Field(default="", description="题目分类，如 'Java 基础'、'MySQL' 等。留空则不限分类")
    level: str = Field(default="", description="难度，'初级'/'中级'/'高级'。留空则不限难度")
    count: int = Field(default=5, description="抽题数量，默认 5 题，最多 20 题", ge=1, le=20)

def create_quiz_draw_tool(db):
    @tool(args_schema=QuizDrawInput)
    def draw_questions_from_bank(
        classify: str = "",
        level: str = "",
        count: int = 5,
    ) -> str:
        """
        从题库按分类和难度随机抽题。
        适合用于生成模拟面试试卷或日常练习。
        """
        count = min(count, 20)
        sql = "SELECT id, classify, level, content FROM question_bank WHERE 1=1"
        params = []
        if classify:
            sql += " AND classify=?"
            params.append(classify)
        if level:
            sql += " AND level=?"
            params.append(level)

        rows = db.fetchall(sql, tuple(params))
        if not rows:
            return f"未找到符合条件的题目（分类={classify or '不限'}，难度={level or '不限'}）。"

        selected = random.sample(rows, min(count, len(rows)))
        lines = [f"📚 已从题库抽取 {len(selected)} 道题目：\n"]
        for i, (qid, cls, lvl, content) in enumerate(selected, 1):
            lines.append(f"**Q{i}** [{cls} · {lvl}]\n{content}\n")
        return "\n".join(lines)

    return draw_questions_from_bank


# ── Model 5：题库内容精确查询输入 ──────────────────────────────────────────────

class QuizSearchInput(BaseModel):
    """题库内容搜索工具的输入参数"""
    keyword: str = Field(..., description="搜索关键词，将在题目内容和答案中模糊匹配")
    show_answer: bool = Field(default=True, description="是否显示参考答案，默认显示")

def create_quiz_search_tool(db):
    @tool(args_schema=QuizSearchInput)
    def search_question_bank(keyword: str, show_answer: bool = True) -> str:
        """
        在题库中关键词搜索题目。
        适合查找特定知识点的题目及参考解析。
        """
        rows = db.fetchall(
            "SELECT id, classify, level, content, answer FROM question_bank "
            "WHERE content LIKE ? OR answer LIKE ? LIMIT 10",
            (f"%{keyword}%", f"%{keyword}%"),
        )
        if not rows:
            return f"题库中未找到包含「{keyword}」的题目。"

        lines = [f"🔍 搜索「{keyword}」共找到 {len(rows)} 道题目：\n"]
        for qid, cls, lvl, content, answer in rows:
            lines.append(f"**[{cls} · {lvl}]** {content}")
            if show_answer:
                lines.append(f"📝 参考答案：{answer[:200]}{'...' if len(answer) > 200 else ''}")
            lines.append("")
        return "\n".join(lines)

    return search_question_bank


# ── Model 6：题库分类统计输入 ──────────────────────────────────────────────────

class QuizStatsInput(BaseModel):
    """题库统计工具的输入参数（无需参数）"""
    pass

def create_quiz_stats_tool(db):
    @tool(args_schema=QuizStatsInput)
    def get_question_bank_stats() -> str:
        """
        查看题库的整体统计：各分类、各难度的题目数量分布。
        适合用于了解题库覆盖范围。
        """
        rows = db.fetchall(
            "SELECT classify, level, COUNT(*) as cnt FROM question_bank GROUP BY classify, level ORDER BY classify, level"
        )
        if not rows:
            return "题库暂无数据。"

        total = db.fetchone("SELECT COUNT(*) FROM question_bank")[0]
        lines = [f"📊 题库统计（共 {total} 题）：\n"]

        current_cls = None
        for cls, lvl, cnt in rows:
            if cls != current_cls:
                current_cls = cls
                lines.append(f"\n**{cls}**")
            lines.append(f"  {lvl}：{cnt} 题")

        # 获取所有分类列表
        classifies = db.fetchall("SELECT DISTINCT classify FROM question_bank ORDER BY classify")
        lines.append(f"\n可用分类：{', '.join(r[0] for r in classifies)}")
        return "\n".join(lines)

    return get_question_bank_stats


# ── Model 7：网络搜索输入 ──────────────────────────────────────────────────────

class WebSearchInput(BaseModel):
    """网络搜索工具的输入参数"""
    query: str = Field(..., description="搜索查询词，用于查找最新技术资料、新闻或框架更新")

def create_web_search_tool():
    """
    创建 Tavily 搜索工具。
    需要环境变量 TAVILY_API_KEY 已设置。
    """
    if TavilySearch is None:
        raise ImportError("请安装 langchain-tavily: pip install -U langchain-tavily")

    # ── 注入 API KEY ──────────────────────────────────────────────────────
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        # 如果没找到环境变量，抛出明确错误，防止运行时报错难排查
        raise ValueError("未找到 TAVILY_API_KEY 环境变量，请在 .env 文件中配置")

    # 新包使用 TavilySearch 类，通过 api_key 参数注入
    tavily_tool = TavilySearch(
        api_key=api_key,  # 🔑 关键：在这里注入 API KEY
        max_results=6,
        search_depth="advanced",
        include_answer=True,
        include_raw_content=False,
        include_images=False,
    )

    @tool(args_schema=WebSearchInput)
    def web_search(query: str) -> str:
        """
        通过 Tavily 搜索最新技术资料、新闻、框架更新、API 变更等。
        适合查询本地知识库没有的实时/最新信息。
        """
        try:
            # 新包直接调用 run 或 invoke
            results = tavily_tool.invoke({"query": query})

            if not results:
                return "Tavily 搜索未返回任何结果。"

            lines = [f"🔍 Tavily 搜索结果（查询：{query}）：\n"]
            for i, res in enumerate(results, 1):
                title = res.get("title", "无标题")
                url = res.get("url", "无链接")
                content = res.get("content", "").strip()[:400]
                answer = res.get("answer", "")

                lines.append(f"[{i}] {title}")
                lines.append(f"   链接：{url}")
                if answer:
                    lines.append(f"   总结：{answer}")
                if content:
                    lines.append(f"   内容片段：{content}...")
                lines.append("")

            return "\n".join(lines)

        except Exception as e:
            return f"Tavily 搜索失败：{str(e)}（请检查 TAVILY_API_KEY 是否正确）"

    return web_search

# ── Model 8：Wikipedia 技术概念查询输入 ────────────────────────────────────────

class WikiSearchInput(BaseModel):
    """Wikipedia 查询工具的输入参数"""
    query: str = Field(..., description="技术概念名称，用于查询权威定义和背景知识")

def create_wiki_tool():
    _wiki = WikipediaQueryRun(
        api_wrapper=WikipediaAPIWrapper(lang="zh", top_k_results=2, doc_content_chars_max=800)
    )

    @tool(args_schema=WikiSearchInput)
    def search_wikipedia(query: str) -> str:
        """
        从 Wikipedia 查询技术概念的权威定义和背景知识。
        适合查询算法、数据结构、设计模式、计算机科学概念等基础知识。
        优先使用中文维基百科。
        """
        try:
            return _wiki.run(query)
        except Exception as e:
            return f"Wikipedia 查询失败：{e}"

    return search_wikipedia


# ── 工具注册入口 ──────────────────────────────────────────────────────────────

def get_tools(db, knowledge_store) -> list:
    """返回面试 Agent 的全部工具列表。"""
    return [
        create_history_tool(db),
        create_job_info_tool(db),
        create_rag_tool(knowledge_store),
        create_quiz_draw_tool(db),
        create_quiz_search_tool(db),
        create_quiz_stats_tool(db),
        create_web_search_tool(),
        create_wiki_tool(),
    ]