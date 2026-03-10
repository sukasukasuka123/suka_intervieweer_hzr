# service/tools/registry.py
"""
工具注册中心

职责：
  1. 构建所有可用工具实例（懒加载，失败时跳过并打印警告）
  2. 根据 SkillSet 权限集合筛选并返回对应工具列表
  3. 提供兼容旧接口的 get_tools() 快捷函数

用法示例：
    from service.tools import get_tools_for, ASSISTANT_SKILLS, INTERVIEW_SKILLS

    # AI 助手（全量）
    agent.register_tools(get_tools_for(db, ks, ASSISTANT_SKILLS))

    # 面试引擎（轻量）
    engine_tools = get_tools_for(db, ks, INTERVIEW_SKILLS)
"""
from __future__ import annotations

from typing import Any

from .db_tools import (
    create_history_tool,
    create_job_info_tool,
    create_quiz_draw_tool,
    create_quiz_search_tool,
    create_quiz_stats_tool,
)
from .knowledge_tools import create_rag_tool
from .search_tools import create_web_search_tool, create_wiki_tool
from .permissions import (
    SkillSet,
    INTERVIEW_SKILLS,
    READONLY_SKILLS,
    ASSISTANT_SKILLS,
    ADMIN_SKILLS,
)


# ── 工具工厂注册表 ────────────────────────────────────────────────────────────
# 每条记录：(工具名称, 工厂函数, 需要的参数列表)
# 参数列表中的字符串对应 _build_all_tools() 的 kwargs key
_TOOL_FACTORIES = [
    # (tool_name,                    factory_fn,               kwargs_keys)
    ("get_student_interview_history", create_history_tool,      ["db"]),
    ("get_job_position_info",         create_job_info_tool,     ["db"]),
    ("draw_questions_from_bank",      create_quiz_draw_tool,    ["db"]),
    ("search_question_bank",          create_quiz_search_tool,  ["db"]),
    ("get_question_bank_stats",       create_quiz_stats_tool,   ["db"]),
    ("search_knowledge_base",         create_rag_tool,          ["knowledge_store"]),
    ("web_search",                    create_web_search_tool,   []),           # 无参，从 env 读
    ("search_wikipedia",              create_wiki_tool,         []),           # 无参
]


def _build_all_tools(db=None, knowledge_store=None) -> dict[str, Any]:
    """
    尝试构建所有工具，失败时打印警告并跳过。
    返回 {tool_name: tool_obj} 字典。
    """
    kwargs = {"db": db, "knowledge_store": knowledge_store}
    result: dict[str, Any] = {}

    for tool_name, factory, kwarg_keys in _TOOL_FACTORIES:
        try:
            call_kwargs = {k: kwargs[k] for k in kwarg_keys}
            tool_obj = factory(**call_kwargs)
            result[tool_name] = tool_obj
            print(f"[Registry] ✅ {tool_name}")
        except Exception as e:
            print(f"[Registry] ⚠️  {tool_name} 加载失败：{e}")

    return result


def get_tools_for(
    db,
    knowledge_store=None,
    skill_set: SkillSet = ASSISTANT_SKILLS,
) -> list:
    """
    根据 SkillSet 权限集合返回对应的工具列表。

    Args:
        db:              DatabaseManager 实例
        knowledge_store: KnowledgeStore 实例（可选，READONLY/ASSISTANT/ADMIN 需要）
        skill_set:       权限集合，默认 ASSISTANT_SKILLS

    Returns:
        符合权限的工具对象列表
    """
    all_tools = _build_all_tools(db=db, knowledge_store=knowledge_store)
    selected = [
        tool_obj
        for name, tool_obj in all_tools.items()
        if name in skill_set
    ]
    print(
        f"[Registry] 集合「{skill_set.name}」加载 {len(selected)}/{len(skill_set.tool_names)} 个工具"
    )
    return selected


# ── 便捷函数 ──────────────────────────────────────────────────────────────────

def get_interview_tools(db) -> list:
    """面试引擎专用工具（轻量，无历史、无联网）。"""
    return get_tools_for(db, knowledge_store=None, skill_set=INTERVIEW_SKILLS)


def get_assistant_tools(db, knowledge_store) -> list:
    """AI 助手全量工具。"""
    return get_tools_for(db, knowledge_store=knowledge_store, skill_set=ASSISTANT_SKILLS)


def get_readonly_tools(db, knowledge_store) -> list:
    """只读工具集：题库 + 知识库，无历史、无联网。"""
    return get_tools_for(db, knowledge_store=knowledge_store, skill_set=READONLY_SKILLS)


def get_tools(db, knowledge_store) -> list:
    """兼容旧接口，等同于 get_assistant_tools。"""
    return get_assistant_tools(db, knowledge_store)
