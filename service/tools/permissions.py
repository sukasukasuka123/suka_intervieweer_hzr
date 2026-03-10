# service/tools/permissions.py
"""
工具权限集合定义
定义不同场景下允许使用的工具集合名称常量，
以及各集合的描述，供 registry.py 和调用方使用。

权限集合：
  INTERVIEW_SKILLS  — 面试引擎专用：题库抽题 + 岗位信息（只读，无历史写入）
  ASSISTANT_SKILLS  — AI 知识助手：全量工具（题库 + RAG + 联网搜索 + 历史查询）
  READONLY_SKILLS   — 只读查询：题库搜索/统计 + 知识库（无历史、无联网）
  ADMIN_SKILLS      — 管理员：全量 + 统计，预留扩展
"""

from dataclasses import dataclass, field
from typing import FrozenSet


@dataclass(frozen=True)
class SkillSet:
    name:        str
    description: str
    tool_names:  FrozenSet[str]

    def __contains__(self, tool_name: str) -> bool:
        return tool_name in self.tool_names


# ── 工具名称常量 ──────────────────────────────────────────────────────────────
TOOL_HISTORY     = "get_student_interview_history"
TOOL_JOB_INFO    = "get_job_position_info"
TOOL_QUIZ_DRAW   = "draw_questions_from_bank"
TOOL_QUIZ_SEARCH = "search_question_bank"
TOOL_QUIZ_STATS  = "get_question_bank_stats"
TOOL_RAG         = "search_knowledge_base"
TOOL_WEB_SEARCH  = "web_search"
TOOL_WIKIPEDIA   = "search_wikipedia"

# ── 权限集合定义 ──────────────────────────────────────────────────────────────

INTERVIEW_SKILLS = SkillSet(
    name="interview",
    description="面试引擎专用工具集：题库抽题、岗位信息查询（轻量，无历史记录、无联网）",
    tool_names=frozenset({
        TOOL_JOB_INFO,
        TOOL_QUIZ_DRAW,
        TOOL_QUIZ_STATS,
    }),
)

READONLY_SKILLS = SkillSet(
    name="readonly",
    description="只读查询工具集：题库搜索/统计 + 知识库检索（无历史、无联网搜索）",
    tool_names=frozenset({
        TOOL_JOB_INFO,
        TOOL_QUIZ_DRAW,
        TOOL_QUIZ_SEARCH,
        TOOL_QUIZ_STATS,
        TOOL_RAG,
    }),
)

ASSISTANT_SKILLS = SkillSet(
    name="assistant",
    description="AI 知识助手全量工具集：题库 + RAG + 联网搜索 + 历史查询",
    tool_names=frozenset({
        TOOL_HISTORY,
        TOOL_JOB_INFO,
        TOOL_QUIZ_DRAW,
        TOOL_QUIZ_SEARCH,
        TOOL_QUIZ_STATS,
        TOOL_RAG,
        TOOL_WEB_SEARCH,
        TOOL_WIKIPEDIA,
    }),
)

ADMIN_SKILLS = SkillSet(
    name="admin",
    description="管理员工具集：全量工具，预留扩展",
    tool_names=frozenset({
        TOOL_HISTORY,
        TOOL_JOB_INFO,
        TOOL_QUIZ_DRAW,
        TOOL_QUIZ_SEARCH,
        TOOL_QUIZ_STATS,
        TOOL_RAG,
        TOOL_WEB_SEARCH,
        TOOL_WIKIPEDIA,
    }),
)

# 所有集合的注册表，供外部遍历
ALL_SKILL_SETS: dict[str, SkillSet] = {
    INTERVIEW_SKILLS.name: INTERVIEW_SKILLS,
    READONLY_SKILLS.name:  READONLY_SKILLS,
    ASSISTANT_SKILLS.name: ASSISTANT_SKILLS,
    ADMIN_SKILLS.name:     ADMIN_SKILLS,
}
