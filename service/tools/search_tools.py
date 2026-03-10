# service/tools/search_tools.py
"""
联网搜索工具
- 博查 Web Search（国内可用）
- Wikipedia 中文条目查询
"""
import os

import requests
from langchain_core.tools import tool
from pydantic import BaseModel, Field

# ── Wikipedia 可选依赖 ────────────────────────────────────────────────────────
try:
    from langchain_community.tools import WikipediaQueryRun
    from langchain_community.utilities import WikipediaAPIWrapper
    _WIKI_OK = True
except ImportError:
    _WIKI_OK = False


# ═══════════════════════════════════════════════════════════════════
# 博查 Web Search
# ═══════════════════════════════════════════════════════════════════

class WebSearchInput(BaseModel):
    query:     str = Field(..., description="搜索查询词，用于查找最新技术资料、新闻或框架更新")
    count:     int = Field(default=6, description="返回结果数，1~10", ge=1, le=10)
    freshness: str = Field(
        default="noLimit",
        description="时间范围：noLimit | day（24h内）| week | month",
    )


def create_web_search_tool():
    api_key = os.getenv("BOCHA_API_KEY", "")
    if not api_key:
        raise ValueError(
            "未找到 BOCHA_API_KEY。\n"
            "请前往 https://open.bochaai.com 注册获取 API Key，\n"
            "在 .env 中添加：BOCHA_API_KEY=your_key"
        )

    @tool(args_schema=WebSearchInput)
    def web_search(query: str, count: int = 6, freshness: str = "noLimit") -> str:
        """
        通过博查搜索引擎搜索最新技术资料、框架更新、行业新闻（国内可直接访问）。
        在 search_knowledge_base 无结果时使用，或需要最新信息时优先使用。
        """
        try:
            resp = requests.post(
                "https://api.bochaai.com/v1/web-search",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "query":     query,
                    "summary":   True,
                    "count":     min(count, 10),
                    "freshness": freshness,
                },
                timeout=20,
            )
            if resp.status_code != 200:
                return f"博查搜索失败 HTTP {resp.status_code}：{resp.text[:200]}"

            data        = resp.json()
            result_data = data.get("data", {})
            ai_answer   = result_data.get("answer", "")
            web_pages   = result_data.get("webPages", {}).get("value", [])

            lines = [f"🌐 搜索结果（{query}）：\n"]
            if ai_answer:
                lines.append(f"**AI 摘要：**\n{ai_answer}\n")
            for i, page in enumerate(web_pages[:count], 1):
                name    = page.get("name", "无标题")
                url     = page.get("url", "")
                snippet = page.get("snippet", "").strip()[:300]
                lines.append(f"[{i}] {name}")
                if url:
                    lines.append(f"   🔗 {url}")
                if snippet:
                    lines.append(f"   {snippet}...")
                lines.append("")
            return "\n".join(lines) if len(lines) > 2 else "搜索未返回任何结果。"

        except requests.exceptions.Timeout:
            return "博查搜索超时，请稍后重试。"
        except Exception as e:
            return f"博查搜索失败：{type(e).__name__}: {e}"

    return web_search


# ═══════════════════════════════════════════════════════════════════
# Wikipedia 中文查询
# ═══════════════════════════════════════════════════════════════════

class WikiSearchInput(BaseModel):
    query:   str = Field(..., description="技术概念名称，用于查询权威定义和背景知识")
    lang:    str = Field(default="zh", description="语言：zh（中文）| en（英文）")
    top_k:   int = Field(default=2,   description="返回条目数，1~3", ge=1, le=3)


def create_wiki_tool():
    if not _WIKI_OK:
        raise ImportError("langchain_community 未安装，请执行: pip install langchain-community wikipedia")

    def _make_wiki(lang: str):
        return WikipediaQueryRun(
            api_wrapper=WikipediaAPIWrapper(
                lang=lang, top_k_results=2, doc_content_chars_max=800
            )
        )

    @tool(args_schema=WikiSearchInput)
    def search_wikipedia(query: str, lang: str = "zh", top_k: int = 2) -> str:
        """
        从 Wikipedia 查询技术概念的权威定义和背景知识。
        适合查询算法、数据结构、设计模式等基础理论知识。
        """
        try:
            wiki = _make_wiki(lang)
            result = wiki.run(query)
            return f"📖 Wikipedia（{lang}）：\n{result}" if result else "Wikipedia 未找到相关词条。"
        except Exception as e:
            return f"Wikipedia 查询失败：{e}"

    return search_wikipedia
