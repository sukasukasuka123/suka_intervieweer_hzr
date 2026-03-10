# service/tools/db_tools.py
"""
数据库类工具集
- 学生历史记录查询（分页）
- 岗位信息查询
- 题库随机抽题
- 题库关键词搜索（分页）
- 题库统计
"""
import json
import random
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════
# ① 学生历史记录（分页）
# ═══════════════════════════════════════════════════════════════════

class StudentHistoryInput(BaseModel):
    student_id: int = Field(..., description="学生的唯一 ID")
    page:       int = Field(default=1,  description="页码，从 1 开始", ge=1)
    page_size:  int = Field(default=10, description="每页条数，默认 10，最大 50", ge=1, le=50)
    order_by:   str = Field(
        default="started_at_desc",
        description="排序方式：started_at_desc(最新优先) | started_at_asc(最早优先) | score_desc(高分优先) | score_asc(低分优先)",
    )


def create_history_tool(db):
    _ORDER_MAP = {
        "started_at_desc": "iss.started_at DESC",
        "started_at_asc":  "iss.started_at ASC",
        "score_desc":      "iss.overall_score DESC",
        "score_asc":       "iss.overall_score ASC",
    }

    @tool(args_schema=StudentHistoryInput)
    def get_student_interview_history(
        student_id: int,
        page: int = 1,
        page_size: int = 10,
        order_by: str = "started_at_desc",
    ) -> str:
        """
        查询指定学生的历史面试记录（支持分页和排序）。
        返回岗位、得分、时间、状态，以及总记录数和分页信息。
        """
        order_sql = _ORDER_MAP.get(order_by, "iss.started_at DESC")
        offset = (page - 1) * page_size

        total_row = db.fetchone(
            "SELECT COUNT(*) FROM interview_session WHERE student_id=?",
            (student_id,),
        )
        total = total_row[0] if total_row else 0
        if total == 0:
            return f"学生 ID={student_id} 暂无面试记录。"

        rows = db.fetchall(
            f"""SELECT s.name, jp.name, iss.started_at, iss.overall_score, iss.status
                FROM interview_session iss
                JOIN student s  ON iss.student_id      = s.id
                JOIN job_position jp ON iss.job_position_id = jp.id
                WHERE iss.student_id = ?
                ORDER BY {order_sql}
                LIMIT ? OFFSET ?""",
            (student_id, page_size, offset),
        )

        total_pages = (total + page_size - 1) // page_size
        lines = [
            f"学生「{rows[0][0]}」面试记录",
            f"第 {page}/{total_pages} 页，共 {total} 条（每页 {page_size} 条）\n",
        ]
        for i, (_, job_name, started_at, score, status) in enumerate(rows, offset + 1):
            score_str = f"{score:.1f}/10" if score is not None else "未评分"
            lines.append(
                f"  {i:>3}. [{started_at[:10]}] {job_name}  "
                f"得分: {score_str}  状态: {status}"
            )
        return "\n".join(lines)

    return get_student_interview_history


# ═══════════════════════════════════════════════════════════════════
# ② 岗位信息
# ═══════════════════════════════════════════════════════════════════

class JobInfoInput(BaseModel):
    job_position_id: Optional[int] = Field(default=None, description="岗位 ID，不传则列出所有")


def create_job_info_tool(db):
    @tool(args_schema=JobInfoInput)
    def get_job_position_info(job_position_id: Optional[int] = None) -> str:
        """查询岗位信息。不传 ID 则列出所有岗位；传入 ID 则返回详细技术栈。"""
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


# ═══════════════════════════════════════════════════════════════════
# ③ 随机抽题
# ═══════════════════════════════════════════════════════════════════

class QuizDrawInput(BaseModel):
    classify: str = Field(default="", description="题目分类，如 'Java基础'、'MySQL'，留空不限")
    level:    str = Field(default="", description="难度：初级/中级/高级，留空不限")
    count:    int = Field(default=5,  description="抽题数量，默认 5，最多 20", ge=1, le=20)


def create_quiz_draw_tool(db):
    @tool(args_schema=QuizDrawInput)
    def draw_questions_from_bank(classify: str = "", level: str = "", count: int = 5) -> str:
        """从题库按分类和难度随机抽题，适合生成模拟面试试卷或日常练习。"""
        count = min(count, 20)
        sql, params = "SELECT id, classify, level, content FROM question_bank WHERE 1=1", []
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
        lines = [f"📚 已从题库随机抽取 {len(selected)} 道题目：\n"]
        for i, (_, cls, lvl, content) in enumerate(selected, 1):
            lines.append(f"**Q{i}** [{cls} · {lvl}]\n{content}\n")
        return "\n".join(lines)

    return draw_questions_from_bank


# ═══════════════════════════════════════════════════════════════════
# ④ 题库关键词搜索（分页 + 排序）
# ═══════════════════════════════════════════════════════════════════

class QuizSearchInput(BaseModel):
    keyword:     str  = Field(...,          description="搜索关键词")
    classify:    str  = Field(default="",   description="按分类过滤，留空不限")
    level:       str  = Field(default="",   description="按难度过滤：初级/中级/高级，留空不限")
    show_answer: bool = Field(default=True, description="是否显示参考答案")
    page:        int  = Field(default=1,    description="页码，从 1 开始", ge=1)
    page_size:   int  = Field(default=5,    description="每页条数，默认 5，最大 20", ge=1, le=20)
    order_by:    str  = Field(
        default="classify_asc",
        description="排序：classify_asc(按分类) | level_asc(难度升序) | level_desc(难度降序) | id_asc(题号升序)",
    )


def create_quiz_search_tool(db):
    _ORDER_MAP = {
        "classify_asc": "classify ASC, level ASC",
        "level_asc":    "CASE level WHEN '初级' THEN 1 WHEN '中级' THEN 2 WHEN '高级' THEN 3 END ASC",
        "level_desc":   "CASE level WHEN '初级' THEN 1 WHEN '中级' THEN 2 WHEN '高级' THEN 3 END DESC",
        "id_asc":       "id ASC",
    }

    @tool(args_schema=QuizSearchInput)
    def search_question_bank(
        keyword: str,
        classify: str = "",
        level: str = "",
        show_answer: bool = True,
        page: int = 1,
        page_size: int = 5,
        order_by: str = "classify_asc",
    ) -> str:
        """在题库中关键词搜索题目，支持分类/难度过滤、分页和排序。"""
        order_sql = _ORDER_MAP.get(order_by, "classify ASC, level ASC")
        offset = (page - 1) * page_size

        # 构建 WHERE 条件
        conds, params = ["(content LIKE ? OR answer LIKE ?)"], [f"%{keyword}%", f"%{keyword}%"]
        if classify:
            conds.append("classify=?")
            params.append(classify)
        if level:
            conds.append("level=?")
            params.append(level)
        where = " AND ".join(conds)

        total_row = db.fetchone(f"SELECT COUNT(*) FROM question_bank WHERE {where}", tuple(params))
        total = total_row[0] if total_row else 0
        if total == 0:
            return f"题库中未找到包含「{keyword}」的题目。"

        rows = db.fetchall(
            f"SELECT id, classify, level, content, answer FROM question_bank "
            f"WHERE {where} ORDER BY {order_sql} LIMIT ? OFFSET ?",
            tuple(params) + (page_size, offset),
        )

        total_pages = (total + page_size - 1) // page_size
        lines = [
            f"🔍 搜索「{keyword}」共 {total} 条结果",
            f"第 {page}/{total_pages} 页（每页 {page_size} 条）\n",
        ]
        for qid, cls, lvl, content, answer in rows:
            lines.append(f"**[{cls} · {lvl}]** #{qid}  {content}")
            if show_answer:
                preview = answer[:200] + ("..." if len(answer) > 200 else "")
                lines.append(f"📝 参考答案：{preview}")
            lines.append("")
        return "\n".join(lines)

    return search_question_bank


# ═══════════════════════════════════════════════════════════════════
# ⑤ 题库统计
# ═══════════════════════════════════════════════════════════════════

class QuizStatsInput(BaseModel):
    pass


def create_quiz_stats_tool(db):
    @tool(args_schema=QuizStatsInput)
    def get_question_bank_stats() -> str:
        """查看题库的整体统计：各分类、各难度的题目数量分布。"""
        rows = db.fetchall(
            "SELECT classify, level, COUNT(*) FROM question_bank "
            "GROUP BY classify, level ORDER BY classify, "
            "CASE level WHEN '初级' THEN 1 WHEN '中级' THEN 2 WHEN '高级' THEN 3 END"
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

        classifies = db.fetchall("SELECT DISTINCT classify FROM question_bank ORDER BY classify")
        lines.append(f"\n📂 可用分类：{', '.join(r[0] for r in classifies)}")
        return "\n".join(lines)

    return get_question_bank_stats
