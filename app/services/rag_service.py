"""小说 RAG 问答（无溯源返回）。"""
from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from langchain_core.documents import Document

from app.core.config import settings
from app.core.logger import setup_logger
from app.db import book_store
from app.db.vector_store import list_chapter_chunks, search_with_score
from app.services.hybrid_retrieval import hybrid_search
from app.services.llm_service import get_chat_model
from app.services.rerank_service import rerank

logger = setup_logger(__name__)

RRF_K = 60.0

RAG_SYSTEM_PROMPT = """你是长篇小说《阅读助手》。请依据本轮【小说原文片段】回答用户问题。

## 核心原则：有据推断，而不是死板复述
1. 像细心读者一样综合线索做合理推断；禁止书外常识或无根据脑补。
2. 原文明确写出的当事实说；综合得出的用「可以推断」等说法，并引出关键原句。
3. 只有片段完全对不上、连间接线索都没有时，才说「片段中不足以判断」。
4. 使用简体中文。本轮片段才是唯一依据。
5. 禁止使用训练记忆补全书常识。不得写出未出现在本轮片段中的回目、别名或情节（例如片段没有「第二十七回」就不要提它）。

## 篇幅（必须遵守，侧栏阅读）
- `**结论：**` 一行说清，尽量不超过 40 字。
- 依据最多 **3** 条；每条一两句，引用只摘最关键的一句。
- 不要长总结、不要复述同一结论、不要堆砌多个章节的旁支细节。
- 全文控制在约 280 字以内。

## 输出格式（前端按 Markdown 渲染）
- 规范 Markdown：`**结论：**`、`- ` 列表、`>` 引用；加粗必须成对 `**…**`。
- 不要 HTML；不要三级以上标题；不要零散的单个 `*`。

## 题型提示
- 真名/外号：串起介绍、称呼、否认外号或纠正称呼等线索。
- 人物关系：先交代如何认识/初始关系，再补后来变化（若片段有）。
- 动机/原因：言行 + 上下文合理推断。

## 引用
尽量写「据《章节标题》…」。不要伪造章节名。"""

_PRONOUN_FOLLOWUP_RE = re.compile(
    r"(他|她|它|他们|她们|这个人|那个人|这个|那个|前者|对方|还有呢|然后呢|后来呢)"
)
_NAME_QUESTION_RE = re.compile(
    r"(真名|本名|原名|全名|真实名字|叫什么名字|叫什么|名字是什么|是谁|是什么人)"
)
# 指代「正在读的这一章」。点名人物、回顾、剧透不走这条。
_CHAPTER_DEIXIS_RE = re.compile(
    r"(这一章|这章|本章|当前章|这回|本回|这一回|"
    r"刚发生了什么|刚才发生|刚刚发生|刚读到|"
    r"读到这里|读到这儿|这里发生了什么|这段发生了什么)"
)
# 关系/如何认识类：只保留通用问题类型，不含书目情节词。
_EARLY_RELATION_RE = re.compile(
    r"(什么关系|是什么关系|怎么认识|如何认识|怎么认识的|"
    r"初次见面|第一次见|第一次见面|认识的|"
    r"一开始|起初|开篇|第一次|最初|刚认识)"
)
# 双人关系短问：人名尽量短，后面必须接关系套话或句读
_PAIR_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9]{0,15}|[\u4e00-\u9fff]{2,4}?)"
    r"[和与]"
    r"([A-Za-z][A-Za-z0-9]{0,15}|[\u4e00-\u9fff]{2,4}?)"
    r"(?:是什么关系|什么关系|的关系|怎么认识|如何认识|(?=[？?，,。\s]|$))"
)
_NO_CHAPTER_ANSWER = (
    "这个问题是在问你正在读的这一章，但当前没有打开章节。"
    "请先在左侧目录打开一章再问。"
    "如果是回顾或剧透，直接问人物、关系或具体情节即可，不必加「这一章」。"
)
_EARLY_CHAPTER_WINDOW = 40
_OPENING_CHAPTER_WINDOW = 12  # 开篇关系优先窗口（更靠前）
_EARLY_RESERVE = 2
_OPENING_RESERVE = 2


def is_chapter_deixis(question: str) -> bool:
    """是否在问当前阅读位置，而不是全书。"""
    return bool(_CHAPTER_DEIXIS_RE.search(question or ""))


def wants_early_chapter_bias(question: str) -> bool:
    """关系/如何认识类问题：优先保留较早章节线索。"""
    q = (question or "").strip()
    if not q:
        return False
    if _EARLY_RELATION_RE.search(q):
        return True
    # 短问「A和B…」多半在问初始关系
    if _PAIR_RE.search(q) and len(q) <= 28:
        return True
    return False


def _excerpt(text: str, limit: int = 72) -> str:
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[:limit] + "…"


def sources_from_docs(
    docs: Sequence[tuple[Document, float]], limit: int = 3
) -> list[dict]:
    """按章节去重，保留先出现的片段摘要。"""
    out: list[dict] = []
    seen: set[int] = set()
    for doc, _ in docs:
        meta = doc.metadata or {}
        try:
            idx = int(meta.get("chapter_index"))
        except (TypeError, ValueError):
            continue
        if idx in seen:
            continue
        seen.add(idx)
        title = str(meta.get("chapter_title") or f"第{idx + 1}章")
        out.append(
            {
                "chapter_index": idx,
                "chapter_title": title,
                "excerpt": _excerpt(doc.page_content),
            }
        )
        if len(out) >= limit:
            break
    return out


@dataclass
class RagPrepared:
    messages: list = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    early_answer: str | None = None


def _build_context(documents: list[Document]) -> str:
    parts = []
    for i, doc in enumerate(documents, 1):
        meta = doc.metadata or {}
        title = str(meta.get("chapter_title") or "")
        book = str(meta.get("book_title") or "")
        bits = [f"片段{i}"]
        if book:
            bits.append(book)
        if title:
            bits.append(title)
        head = " · ".join(bits)
        parts.append(f"[{head}]\n{doc.page_content.strip()}")
    return "\n\n".join(parts)


def _build_user_prompt(question: str, context: str) -> str:
    early_hint = ""
    if wants_early_chapter_bias(question):
        early_hint = (
            "本题涉及人物关系或如何认识：若片段里有较早章节的初次相遇/初始纠葛，"
            "结论里必须先交代这一点，再提后来变化；不要只答后期状态。\n"
        )
    return (
        "下面是检索到的小说原文片段（可能来自不同章节）。\n"
        "只依据与问题最相关的片段作答；弱相关或后期旁支片段请忽略，不要为凑条数硬写。\n"
        "请主动综合线索做推断；涉及外号/真名时，重点看介绍、称呼、否认外号或纠正称呼。\n"
        "若片段不足以判断，直接说依据不足；不要根据记忆点出「应该去看第X回」，"
        "除非该回目已经出现在下方片段标题里。\n"
        f"{early_hint}\n"
        f"【小说原文片段】\n{context}\n\n"
        f"【用户问题】\n{question}\n\n"
        "输出：一行 `**结论：**` + 最多 3 条 `- ` 依据（可含一句 `>` 引用）。"
        "控制在约 280 字；仅当片段完全没有线索时才说无法判断。"
    )


# 问句里常见「人名 + 谓语/疑问」分界，避免把「白骨精一共骗了几」整段当主语
_ENTITY_BOUNDARY_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9]{0,15}|[\u4e00-\u9fff]{2,4})"
    r"(?:一共|到底|究竟|是谁|是什么|的|有|在|和|与|被|把|给|对|向|"
    r"怎么|怎样|如何|几|吗|呢|啊|会|能|骗|打|杀|去|来|说|做)"
)


def _topic_subject(text: str) -> str | None:
    """粗提取问题主语（人名/称呼），用于判断是否换题。"""
    t = text.strip()
    if not t or _PAIR_RE.search(t):
        return None
    m = re.match(
        r"^([A-Za-z][A-Za-z0-9]{0,15}|[\u4e00-\u9fff]{2,4})(?:是谁|是什么人|的)",
        t,
    )
    if m:
        return m.group(1)
    m = re.search(
        r"([A-Za-z][A-Za-z0-9]{0,15}|[\u4e00-\u9fff]{2,4})"
        r"的?(?:真名|本名|同学|丈夫|妻子|朋友|师父|徒弟|结义)",
        t,
    )
    if m:
        return m.group(1)
    m = _ENTITY_BOUNDARY_RE.match(t)
    if m:
        return m.group("name")
    return None


def _is_standalone_named_question(
    question: str, history: Sequence[dict] | None
) -> bool:
    """当前问点了明确人名，且与上一问不是同一人 → 独立新问题，禁止串历史。"""
    if _PRONOUN_FOLLOWUP_RE.search(question) and not re.search(
        r"[A-Za-z\u4e00-\u9fff]{2,}是谁", question
    ):
        # 纯代词追问需要历史；「某某是谁」即使短也不算代词题
        if re.fullmatch(
            r"[\s]*(他|她|它|他们|她们|这个|那个|前者|对方)[\s\S]{0,20}",
            question.strip(),
        ):
            return False

    cur = _topic_subject(question)
    if not cur:
        return False

    if not history:
        return True

    last_user = ""
    for msg in reversed(history):
        if msg.get("role") == "user":
            last_user = (msg.get("content") or "").strip()
            break

    prev = _topic_subject(last_user) if last_user else None
    if prev and prev != cur:
        return True
    if cur not in last_user:
        return True
    return False


def _recent_history(
    history: Sequence[dict] | None,
    question: str = "",
    *,
    max_turns: int = 2,
) -> list[dict]:
    """独立点名新问题不注入历史，避免上一题「找不到」污染本轮。"""
    if not history:
        return []
    if question and _is_standalone_named_question(question, history):
        return []

    cleaned: list[dict] = []
    for msg in history:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        if role == "assistant" and len(content) > 400:
            content = content[:400] + "…"
        cleaned.append({"role": role, "content": content})
    if not cleaned:
        return []
    return cleaned[-(max_turns * 2) :]


def _build_messages(
    question: str,
    context: str,
    history: Sequence[dict] | None = None,
    scope_note: str | None = None,
) -> list:
    messages: list = [("system", RAG_SYSTEM_PROMPT)]
    if scope_note:
        messages.append(("system", scope_note))
    recent = _recent_history(history, question)
    if recent:
        messages.append(
            (
                "system",
                "以下是最近对话，仅用于理解指代（如「他/她」）。"
                "若本轮已换人换题，忽略旧结论；一律以本轮【小说原文片段】为准。",
            )
        )
        for msg in recent:
            if msg["role"] == "user":
                messages.append(("human", msg["content"]))
            else:
                messages.append(("ai", msg["content"]))
    messages.append(("human", _build_user_prompt(question, context)))
    return messages


def _rewrite_query_with_history(
    question: str, history: Sequence[dict] | None
) -> str:
    """仅代词追问才拼历史；点名短问（「某某是谁」）绝不串上一题。"""
    q = question.strip()
    if not history:
        return q

    # 旧逻辑 len(q)<=12 会把独立短问拼进上一题，召回全偏
    if _is_standalone_named_question(q, history):
        return q

    if not _PRONOUN_FOLLOWUP_RE.search(q):
        return q

    last_user = ""
    last_assistant = ""
    for msg in reversed(history):
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if role == "user" and not last_user:
            last_user = content
        elif role == "assistant" and not last_assistant:
            last_assistant = content
        if last_user and last_assistant:
            break

    if not last_user:
        return q

    clue = last_assistant.replace("\n", " ").strip()
    if len(clue) > 60:
        clue = clue[:60]
    return f"{last_user} {q} {clue}".strip()


def _extract_subject(question: str) -> str | None:
    """从问题中提取称呼/实体主体（偏短，避免吞掉谓语）。"""
    q = question.strip()
    m = re.search(
        r"([A-Za-z][A-Za-z0-9]{0,15}|[\u4e00-\u9fff]{2,4})"
        r"的?(?:真名|本名|原名|全名|真实名字)",
        q,
    )
    if m:
        return m.group(1)
    m = re.search(
        r"([A-Za-z][A-Za-z0-9]{0,15}|[\u4e00-\u9fff]{2,4})"
        r"(?:叫什么|名字是什么|是谁|是什么人)",
        q,
    )
    if m:
        return m.group(1)
    m = re.search(
        r"([A-Za-z][A-Za-z0-9]{0,15}|[\u4e00-\u9fff]{2,4})"
        r"的(?:同学|朋友|丈夫|妻子)",
        q,
    )
    if m:
        return m.group(1)
    return _topic_subject(q)


def _entity_query_variants(subject: str) -> list[str]:
    """通用实体变体：白骨精→白骨，便于命中原文别称/回目用语。"""
    out = [subject]
    if len(subject) >= 3 and subject[-1] in "精怪魔妖神":
        stem = subject[:-1]
        if len(stem) >= 2:
            out.append(stem)
    return out


def _expand_retrieval_queries(question: str) -> list[str]:
    """为真名/身份/关系题扩展多路检索词（仅通用结构，不含书目情节词）。"""
    base = question.strip()
    queries = [base]
    pair = _PAIR_RE.search(base)
    # 双人关系题用两人姓名扩展，避免把「A和B是什么」误当主语
    subject = None if pair else _extract_subject(base)

    if subject:
        for ent in _entity_query_variants(subject):
            queries.extend(
                [
                    ent,
                    f"{ent} 是谁",
                    f"{ent} 介绍",
                    f"这是{ent}",
                ]
            )

    if subject and ("真名" in base or "本名" in base or "名字" in base):
        queries.extend(
            [
                f"叫{subject}",
                f"{subject} 名字",
                "向别人介绍",
            ]
        )

    if wants_early_chapter_bias(base):
        if pair:
            a, b = pair.group(1), pair.group(2)
            queries.extend(
                [
                    f"{a}",
                    f"{b}",
                    f"{a} {b}",
                    f"{a}和{b}",
                    f"{a} {b} 认识",
                    f"{a} {b} 见面",
                ]
            )
        queries.append("第一次见面")

    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out[:10]


def _doc_key(doc: Document) -> str:
    return doc.page_content[:240]


def _chapter_index_of(doc: Document) -> int | None:
    try:
        return int((doc.metadata or {}).get("chapter_index"))
    except (TypeError, ValueError):
        return None


def _rrf_merge(
    result_lists: list[list[tuple[Document, float]]], top_k: int
) -> list[tuple[Document, float]]:
    fused: dict[str, dict] = {}
    for results in result_lists:
        for rank, (doc, _) in enumerate(results, start=1):
            key = _doc_key(doc)
            if key not in fused:
                fused[key] = {"doc": doc, "rrf": 0.0}
            fused[key]["rrf"] += 1.0 / (RRF_K + rank)
    ordered = sorted(fused.values(), key=lambda x: x["rrf"], reverse=True)[:top_k]
    return [(item["doc"], item["rrf"]) for item in ordered]


def _apply_early_chapter_bias(
    docs: list[tuple[Document, float]],
    *,
    window: int = _EARLY_CHAPTER_WINDOW,
) -> list[tuple[Document, float]]:
    """对靠前章节做软加权，缓解后期片段淹没初始关系。"""
    if not docs:
        return docs
    boosted: list[tuple[Document, float]] = []
    for doc, score in docs:
        idx = _chapter_index_of(doc)
        if idx is not None and idx < window:
            factor = 1.0 + 0.55 * (1.0 - idx / max(window, 1))
            boosted.append((doc, float(score) * factor))
        else:
            boosted.append((doc, float(score)))
    boosted.sort(key=lambda x: x[1], reverse=True)
    return boosted


def _ensure_early_slots(
    ranked: list[tuple[Document, float]],
    pool: list[tuple[Document, float]],
    *,
    top_k: int,
    names: tuple[str, str] | None = None,
    window: int = _EARLY_CHAPTER_WINDOW,
    opening_window: int = _OPENING_CHAPTER_WINDOW,
    reserve: int = _EARLY_RESERVE,
    opening_reserve: int = _OPENING_RESERVE,
) -> list[tuple[Document, float]]:
    """最终结果优先保开篇窗口片段，再补早期章节（若候选里有）。"""
    if top_k <= 0:
        return []

    def _sort_key(item: tuple[Document, float]) -> tuple:
        doc, score = item
        idx = _chapter_index_of(doc)
        text = doc.page_content or ""
        name_hits = 0
        if names:
            name_hits = sum(1 for n in names if n and n in text)
        return (
            idx if idx is not None else 10**9,
            -name_hits,
            -score,
        )

    opening_pool = [
        (d, s)
        for d, s in pool
        if (_chapter_index_of(d) is not None and _chapter_index_of(d) < opening_window)
    ]
    opening_pool.sort(key=_sort_key)
    reserved = opening_pool[:opening_reserve]
    reserved_keys = {_doc_key(d) for d, _ in reserved}

    early_pool = [
        (d, s)
        for d, s in pool
        if (
            _chapter_index_of(d) is not None
            and _chapter_index_of(d) < window
            and _doc_key(d) not in reserved_keys
        )
    ]
    early_pool.sort(key=_sort_key)
    need = max(reserve - len(reserved), 0)
    reserved = reserved + early_pool[:need]
    reserved_keys = {_doc_key(d) for d, _ in reserved}

    rest = [(d, s) for d, s in ranked if _doc_key(d) not in reserved_keys]
    merged = reserved + rest
    out: list[tuple[Document, float]] = []
    seen: set[str] = set()
    for doc, score in merged:
        key = _doc_key(doc)
        if key in seen:
            continue
        seen.add(key)
        out.append((doc, score))
        if len(out) >= top_k:
            break
    return out


def _merge_doc_lists(
    primary: list[tuple[Document, float]],
    secondary: list[tuple[Document, float]],
    *,
    top_k: int,
) -> list[tuple[Document, float]]:
    out: list[tuple[Document, float]] = []
    seen: set[str] = set()
    for doc, score in primary + secondary:
        key = _doc_key(doc)
        if key in seen:
            continue
        seen.add(key)
        out.append((doc, score))
        if len(out) >= top_k:
            break
    return out


def _search_once(
    query: str,
    book_id: str,
    top_k: int,
    chapter_index: int | None = None,
    score_threshold: float | None = None,
) -> list[tuple[Document, float]]:
    if settings.hybrid_search_enabled:
        return hybrid_search(
            query,
            book_id=book_id,
            top_k=top_k,
            chapter_index=chapter_index,
            score_threshold=score_threshold,
        )
    return search_with_score(
        query,
        book_id=book_id,
        top_k=top_k,
        chapter_index=chapter_index,
        score_threshold=score_threshold,
    )


_HUI_RE = re.compile(r"第[一二三四五六七八九十百零〇0-9]+回")
_JUDGE_SYSTEM = (
    "你是阅读助手的「检索质检 + 二次检索规划器」，不是最终答题器。\n"
    "任务：看第一跳召回的片段，判断它们是否足以依据原文回答用户问题；"
    "若不足，动用你的训练知识（俗称、影视译名、名著常识）提出第二跳检索词，"
    "但必须对照本书目录挑选真实存在的回目关键词。\n"
    "硬规则：\n"
    "1. can_answer=true 仅当本轮片段正文或章题里已经出现所问之人/事，"
    "或片段已给出可直接作答的明确线索。\n"
    "2. 若你「记得」答案在某回，但本轮片段没有对应原文，必须 can_answer=false，"
    "并给出 aliases / title_hints / queries 供系统去知识库再搜。\n"
    "3. 禁止在本步叙述完整剧情或给出最终结论。\n"
    "4. title_hints 只能从用户提供的本书目录中挑选或截取，不得编造目录里没有的回目。\n"
    "只输出一个 JSON 对象：\n"
    '{"can_answer":false,"reason":"一句话","aliases":["原文可能用词"],'
    '"title_hints":["目录中的回目关键词"],"queries":["检索式"]}\n'
    "每类最多 4 个，每项不超过 16 字。"
)

_GENERIC_HINTS = frozenset(
    {
        "唐僧",
        "三藏",
        "唐三藏",
        "悟空",
        "行者",
        "八戒",
        "沙僧",
        "师父",
        "猴王",
        "美猴王",
    }
)


def _parse_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return {}
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


def _clean_hint_list(value: object, *, limit: int = 4) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        s = str(item or "").strip()
        s = re.sub(r"\s+", "", s)
        if len(s) < 2 or len(s) > 16 or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= limit:
            break
    return out


def _chapter_catalog(book_id: str) -> list[tuple[int, str]]:
    rows = book_store.list_chapters(book_id)
    catalog: list[tuple[int, str]] = []
    for row in rows:
        try:
            idx = int(row.get("chapter_index"))
        except (TypeError, ValueError):
            continue
        title = str(row.get("chapter_title") or "").strip()
        if title:
            catalog.append((idx, title))
    return catalog


def _hint_matches_title(hint: str, title: str) -> bool:
    if not hint or not title:
        return False
    if hint in title or (len(title) >= 4 and title in hint):
        return True
    hui_h = _HUI_RE.search(hint)
    hui_t = _HUI_RE.search(title)
    if hui_h and hui_t and hui_h.group(0) == hui_t.group(0):
        return True
    return False


def _fragment_briefs(
    docs: list[tuple[Document, float]], *, limit: int = 6
) -> str:
    lines: list[str] = []
    for i, (doc, _) in enumerate(docs[:limit], 1):
        meta = doc.metadata or {}
        title = str(meta.get("chapter_title") or "")
        idx = meta.get("chapter_index")
        preview = " ".join((doc.page_content or "").split())[:120]
        lines.append(f"{i}. [{idx}]{title} | {preview}")
    return "\n".join(lines) if lines else "（无片段）"


def _plan_second_hop_queries(
    aliases: list[str],
    title_hints: list[str],
    queries: list[str],
    catalog: list[tuple[int, str]],
) -> tuple[list[int], list[str]]:
    """回目必须对上目录才能灌章；别名/检索式可直接用于二次搜索。"""
    matched_idx: list[int] = []
    search_q: list[str] = []
    seen_idx: set[int] = set()
    seen_q: set[str] = set()

    def add_idx(idx: int) -> None:
        if idx not in seen_idx:
            seen_idx.add(idx)
            matched_idx.append(idx)

    def add_q(text: str) -> None:
        if (
            text
            and text not in seen_q
            and text not in _GENERIC_HINTS
            and len(text) <= 16
        ):
            seen_q.add(text)
            search_q.append(text)

    for hint in title_hints:
        for idx, title in catalog:
            if not _hint_matches_title(hint, title):
                continue
            add_idx(idx)
            add_q(hint)
            for piece in re.findall(r"[\u4e00-\u9fff]{2,8}", title):
                add_q(piece)
            break

    # 别名与模型给出的检索式：直接二次搜索（不要求出现在回目里）
    for alias in aliases:
        add_q(alias)
        for idx, title in catalog:
            if alias in title:
                add_idx(idx)
    for query in queries:
        add_q(query)
        for idx, title in catalog:
            if _hint_matches_title(query, title):
                add_idx(idx)

    return matched_idx[:2], search_q[:6]


async def _llm_judge_and_plan(
    question: str,
    book_title: str,
    first_docs: list[tuple[Document, float]],
    catalog: list[tuple[int, str]],
) -> dict:
    """让模型判断第一跳能否作答；不能则规划二次检索。"""
    toc_lines = ""
    if 0 < len(catalog) <= 160:
        toc_lines = "\n".join(
            f"{idx}:{title[:40]}" for idx, title in catalog[:160]
        )
    user = (
        f"书名：{book_title or '未知'}\n"
        f"用户问题：{question}\n"
        f"第一跳片段：\n{_fragment_briefs(first_docs)}\n"
    )
    if toc_lines:
        user += "本书目录（挑选 title_hints 只能用这里的回目）：\n" + toc_lines
    model = get_chat_model()
    resp = await model.ainvoke(
        [("system", _JUDGE_SYSTEM), ("human", user)]
    )
    text = resp.content if isinstance(resp.content, str) else str(resp.content)
    data = _parse_json_object(text)
    can_answer = bool(data.get("can_answer"))
    return {
        "can_answer": can_answer,
        "reason": str(data.get("reason") or "")[:120],
        "aliases": _clean_hint_list(data.get("aliases")),
        "title_hints": _clean_hint_list(data.get("title_hints")),
        "queries": _clean_hint_list(data.get("queries")),
    }


async def _second_hop_retrieve(
    question: str,
    book_id: str,
    plan: dict,
    catalog: list[tuple[int, str]],
) -> list[tuple[Document, float]]:
    """按规划二次检索：别名可搜；回目命中则灌章。"""
    indexes, queries = _plan_second_hop_queries(
        plan.get("aliases") or [],
        plan.get("title_hints") or [],
        plan.get("queries") or [],
        catalog,
    )
    logger.info(
        "二次检索 book=%s reason=%r idx=%s queries=%s",
        book_id,
        plan.get("reason"),
        indexes,
        queries,
    )
    if not indexes and not queries:
        return []

    gathered: list[list[tuple[Document, float]]] = []
    if queries:
        lists = await asyncio.gather(
            *[
                asyncio.to_thread(_search_once, q, book_id, 10, None, 0.0)
                for q in queries[:5]
            ]
        )
        gathered.extend(lists)
    chapter_docs: list[tuple[Document, float]] = []
    if indexes:
        chunk_lists = await asyncio.gather(
            *[
                asyncio.to_thread(list_chapter_chunks, book_id, idx)
                for idx in indexes[:2]
            ]
        )
        for docs in chunk_lists:
            for rank, doc in enumerate(docs[:6]):
                chapter_docs.append((doc, 3.0 - rank * 0.05))

    fused = _rrf_merge(gathered, top_k=16) if gathered else []
    merged = _merge_doc_lists(chapter_docs, fused, top_k=16)
    if not merged:
        return []
    if settings.rerank_enabled:
        candidates = [d.page_content for d, _ in merged]
        reranked = await rerank(question, candidates, top_n=min(8, len(merged)))
        ordered: list[tuple[Document, float]] = []
        for item in reranked:
            idx = item.get("index")
            if idx is not None and idx < len(merged):
                doc, _ = merged[idx]
                ordered.append((doc, item.get("relevance_score", 0.0)))
        if ordered:
            merged = ordered
    return merged[: max(settings.retrieval_top_k, 4)]


async def _maybe_second_hop(
    question: str,
    book_id: str,
    first_docs: list[tuple[Document, float]],
) -> tuple[list[tuple[Document, float]], int]:
    """第一跳后：LLM 判断 → 不足则二次检索并替换。"""
    book = book_store.get_book(book_id) or {}
    catalog = _chapter_catalog(book_id)
    if not catalog:
        return first_docs, 0
    plan = await _llm_judge_and_plan(
        question,
        str(book.get("title") or ""),
        first_docs,
        catalog,
    )
    logger.info(
        "检索质检 book=%s can_answer=%s reason=%r aliases=%s hints=%s",
        book_id,
        plan["can_answer"],
        plan["reason"],
        plan["aliases"],
        plan["title_hints"],
    )
    if plan["can_answer"]:
        return first_docs, 0
    extra = await _second_hop_retrieve(question, book_id, plan, catalog)
    if not extra:
        return first_docs, 0
    return extra, len(extra)


async def _opening_relation_hits(
    book_id: str,
    names: tuple[str, str],
    *,
    top_k: int = 10,
) -> list[tuple[Document, float]]:
    """专搜开篇双人共现，避免后期同人戏淹没初次见面。"""
    a, b = names
    queries = [f"{a} {b}", f"{a}和{b}", f"{a}与{b}"]
    lists = await asyncio.gather(
        *[
            asyncio.to_thread(_search_once, q, book_id, top_k, None, 0.0)
            for q in queries
        ]
    )
    merged = _rrf_merge(list(lists), top_k=top_k * 2)
    opening: list[tuple[Document, float]] = []
    for doc, score in merged:
        idx = _chapter_index_of(doc)
        if idx is None or idx >= _OPENING_CHAPTER_WINDOW:
            continue
        text = doc.page_content or ""
        if a not in text and b not in text:
            continue
        opening.append((doc, score))
    opening.sort(
        key=lambda x: (
            _chapter_index_of(x[0]) if _chapter_index_of(x[0]) is not None else 10**9,
            -sum(1 for n in names if n in (x[0].page_content or "")),
            -x[1],
        )
    )
    return opening[:_OPENING_RESERVE]


async def _retrieve(
    question: str, book_id: str
) -> list[tuple[Document, float]]:
    recall_k = (
        settings.rerank_recall_top_k
        if settings.rerank_enabled
        else (
            settings.hybrid_recall_top_k
            if settings.hybrid_search_enabled
            else settings.retrieval_top_k
        )
    )

    queries = _expand_retrieval_queries(question)
    per_query_k = max(recall_k // 2, 6)
    lists = await asyncio.gather(
        *[
            asyncio.to_thread(_search_once, q, book_id, per_query_k)
            for q in queries
        ]
    )
    docs = _rrf_merge(list(lists), top_k=recall_k)
    early_bias = wants_early_chapter_bias(question)
    pair_names: tuple[str, str] | None = None
    m = _PAIR_RE.search(question)
    if m:
        pair_names = (m.group(1), m.group(2))

    opening_injected = 0
    if early_bias and pair_names:
        already_opening = sum(
            1
            for d, _ in docs
            if (
                _chapter_index_of(d) is not None
                and _chapter_index_of(d) < _OPENING_CHAPTER_WINDOW
            )
        )
        if already_opening < _OPENING_RESERVE:
            opening = await _opening_relation_hits(book_id, pair_names)
            opening_injected = len(opening)
            if opening:
                docs = _merge_doc_lists(opening, docs, top_k=recall_k)
    if early_bias:
        docs = _apply_early_chapter_bias(docs)

    logger.info(
        "召回 queries=%s candidates=%d early_bias=%s opening_injected=%d",
        queries[:4],
        len(docs),
        early_bias,
        opening_injected,
    )

    if not settings.rerank_enabled or not docs:
        final = docs[: settings.retrieval_top_k]
        if early_bias:
            final = _ensure_early_slots(
                final,
                docs,
                top_k=settings.retrieval_top_k,
                names=pair_names,
            )
        return final

    candidates = [d.page_content for d, _ in docs]
    reranked = await rerank(question, candidates, top_n=settings.rerank_top_n)
    reordered: list[tuple[Document, float]] = []
    for item in reranked:
        idx = item.get("index")
        if idx is not None and idx < len(docs):
            doc, _ = docs[idx]
            reordered.append((doc, item.get("relevance_score", 0.0)))
    if early_bias:
        reordered = _ensure_early_slots(
            reordered,
            docs,
            top_k=settings.retrieval_top_k,
            names=pair_names,
        )
    return reordered[: settings.retrieval_top_k]


async def _retrieve_in_chapter(
    question: str,
    book_id: str,
    chapter_index: int,
    chapter_title: str,
) -> list[tuple[Document, float]]:
    """只在当前章内取片段，并始终带上章首，避免「刚发生什么」被别章抢走。"""
    opening_docs, hits = await asyncio.gather(
        asyncio.to_thread(list_chapter_chunks, book_id, chapter_index),
        asyncio.to_thread(
            _search_once, question, book_id, 6, chapter_index, 0.0
        ),
    )
    opening = [(doc, 1.0) for doc in opening_docs[:2]]
    merged: list[tuple[Document, float]] = []
    seen: set[str] = set()
    for doc, score in [*opening, *hits]:
        key = doc.page_content[:240]
        if key in seen:
            continue
        seen.add(key)
        merged.append((doc, score))
    if merged:
        logger.info("章内召回 chapter=%s hits=%d", chapter_index, len(merged))
        return merged[:8]

    chapter = book_store.get_chapter(book_id, chapter_index)
    text = str((chapter or {}).get("content") or "").strip()
    if not text:
        return []
    doc = Document(
        page_content=f"{chapter_title}\n\n{text[:4000]}",
        metadata={
            "book_id": book_id,
            "chapter_index": chapter_index,
            "chapter_title": chapter_title,
        },
    )
    return [(doc, 1.0)]


def _blend_open_chapter(
    global_docs: list[tuple[Document, float]],
    local_docs: list[tuple[Document, float]],
    *,
    top_k: int,
    reserve: int = 2,
) -> list[tuple[Document, float]]:
    """打开章节时：先占若干章内片段，再补全书命中，避免读着本章却答成别回。"""
    if top_k <= 0:
        return []
    if not local_docs:
        return global_docs[:top_k]
    reserved = local_docs[:reserve]
    reserved_keys = {_doc_key(d) for d, _ in reserved}
    rest = [(d, s) for d, s in global_docs if _doc_key(d) not in reserved_keys]
    return _merge_doc_lists(reserved, rest, top_k=top_k)


async def prepare_turn(
    question: str,
    book_id: str,
    history: Sequence[dict] | None = None,
    chapter_index: int | None = None,
) -> RagPrepared:
    """全局问题全书检索；「这一章」锁章；已打开章节则软混入章内片段。"""
    if is_chapter_deixis(question):
        if chapter_index is None:
            return RagPrepared(early_answer=_NO_CHAPTER_ANSWER)
        chapter = book_store.get_chapter(book_id, int(chapter_index))
        if not chapter:
            return RagPrepared(early_answer="当前章节不存在，请先从目录打开一章。")
        title = str(chapter.get("chapter_title") or f"第{int(chapter_index) + 1}章")
        docs = await _retrieve_in_chapter(
            question, book_id, int(chapter_index), title
        )
        sources = sources_from_docs(docs) or [
            {
                "chapter_index": int(chapter_index),
                "chapter_title": title,
                "excerpt": "",
            }
        ]
        if not docs:
            return RagPrepared(
                sources=sources,
                early_answer=f"《{title}》里没有足够内容回答这个问题。",
            )
        note = (
            f"用户正在阅读《{title}》。"
            "问题里的「这一章」「刚才」「这里」只指这一章。"
            "只依据本轮片段回答，禁止把其他章节的情节说成这一章刚刚发生的事。"
            "若本章没写到，就说明本章没有写到。"
        )
        context = _build_context([d for d, _ in docs])
        return RagPrepared(
            messages=_build_messages(question, context, history, scope_note=note),
            sources=sources,
        )

    retrieval_query = _rewrite_query_with_history(question, history)
    docs = await _retrieve(retrieval_query, book_id)

    open_blended = 0
    if chapter_index is not None:
        chapter = book_store.get_chapter(book_id, int(chapter_index))
        if chapter:
            title = str(
                chapter.get("chapter_title") or f"第{int(chapter_index) + 1}章"
            )
            local = await _retrieve_in_chapter(
                retrieval_query, book_id, int(chapter_index), title
            )
            if local:
                before = {_doc_key(d) for d, _ in docs}
                docs = _blend_open_chapter(
                    docs, local, top_k=settings.retrieval_top_k
                )
                open_blended = sum(
                    1 for d, _ in docs if _doc_key(d) not in before
                )

    docs, rescued = await _maybe_second_hop(question, book_id, docs)
    if rescued:
        logger.info("二次检索已替换第一跳 hits=%d", rescued)

    if not docs:
        return RagPrepared(early_answer="原文中未找到相关信息，无法回答该问题。")
    context = _build_context([d for d, _ in docs])
    scope_note = None
    if wants_early_chapter_bias(question):
        scope_note = (
            "本题偏「初始关系 / 如何认识」。"
            "若片段含较早章节，结论须先交代初次相遇或开篇纠葛，再提后来变化；"
            "不要只用后期身份覆盖初始事实。"
            "仍遵守篇幅：结论一行 + 最多 3 条依据。"
        )
    if open_blended and chapter_index is not None:
        ch = book_store.get_chapter(book_id, int(chapter_index))
        open_title = str(
            (ch or {}).get("chapter_title") or f"第{int(chapter_index) + 1}章"
        )
        blend_note = (
            f"用户当前打开了《{open_title}》。"
            "若片段含这一章且与问题相关，优先依据本章作答；"
            "不要说「片段未提及」却忽略本章已给出的情节。"
        )
        scope_note = f"{scope_note}\n{blend_note}" if scope_note else blend_note
    logger.info(
        "全局检索 book=%s q=%r retrieve=%r hits=%d early=%s open_blend=%d hypo=%d",
        book_id,
        question[:40],
        retrieval_query[:60],
        len(docs),
        bool(scope_note),
        open_blended,
        rescued,
    )
    return RagPrepared(
        messages=_build_messages(
            question, context, history, scope_note=scope_note
        ),
        sources=sources_from_docs(docs),
    )


async def rag_ask(
    question: str,
    book_id: str,
    history: Sequence[dict] | None = None,
    chapter_index: int | None = None,
) -> dict:
    prepared = await prepare_turn(
        question, book_id, history, chapter_index=chapter_index
    )
    if prepared.early_answer is not None:
        return {"answer": prepared.early_answer, "sources": prepared.sources}

    model = get_chat_model()
    resp = await model.ainvoke(prepared.messages)
    answer = resp.content if isinstance(resp.content, str) else str(resp.content)
    logger.info("问答完成 book=%s q=%r hits=%d", book_id, question[:40], len(prepared.sources))
    return {"answer": answer, "sources": prepared.sources}


async def rag_stream(
    question: str,
    book_id: str,
    history: Sequence[dict] | None = None,
    chapter_index: int | None = None,
) -> AsyncIterator[dict]:
    prepared = await prepare_turn(
        question, book_id, history, chapter_index=chapter_index
    )
    if prepared.early_answer is not None:
        yield {"type": "token", "content": prepared.early_answer}
        # 出处放在回答之后，避免侧栏先堆一排章节芯片造成噪声感
        if prepared.sources:
            yield {"type": "sources", "items": prepared.sources}
        return

    yield {"type": "status", "content": "正在组织回答…"}
    model = get_chat_model()
    async for chunk in model.astream(prepared.messages):
        content = chunk.content
        if isinstance(content, str) and content:
            yield {"type": "token", "content": content}
    if prepared.sources:
        yield {"type": "sources", "items": prepared.sources}
