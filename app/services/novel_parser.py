"""小说解析：编码探测、去广告头、章节探测。

支持：
- 网文：第N章 / 【第N章】 / Chapter N
- 古典章回体：第N回（如《三国演义》）
- 卷：第N卷（作弱边界，优先回/章）
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)

# 中文数字 + 阿拉伯数字（含全角）
_CN_NUM = r"[0-9０-９一二三四五六七八九十百千零两〇]+"

# 常见章节标题（整行匹配，按优先级）
CHAPTER_PATTERNS = [
    # 古典章回：《三国演义》「第一回 宴桃园…」
    re.compile(rf"^第{_CN_NUM}回[\s　:：].+$"),
    re.compile(rf"^第{_CN_NUM}回$"),
    # 网文章节
    re.compile(rf"^第{_CN_NUM}章[：:\s　]*.*$"),
    re.compile(rf"^【第{_CN_NUM}章】.*$"),
    # 英文
    re.compile(r"^Chapter\s*\d+[:\s].*$", re.IGNORECASE),
    re.compile(r"^Chapter\s*\d+$", re.IGNORECASE),
]

HEADER_MARKERS = (
    "用户上传之内容开始",
    "---------------------------",
)

BOOK_TITLE_RE = re.compile(r"^《(.+?)》\s*$")
_CHAPTER_UNIT_RE = re.compile(rf"第({_CN_NUM})([回章节])")


@dataclass
class Chapter:
    """解析出的一章。"""

    chapter_index: int
    chapter_no: int | None
    chapter_title: str
    content: str


@dataclass
class ParseResult:
    """整书解析结果。"""

    title: str
    chapters: list[Chapter]
    split_mode: str  # chapter | window
    warning: str = ""


def detect_encoding(raw: bytes) -> str:
    """在 utf-8 / gb18030 间按中文标点得分选最佳编码。"""
    best_enc = "utf-8"
    best_score = -1
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        score = (
            text.count("，")
            + text.count("。")
            + text.count("“")
            + text.count("《")
        )
        if score > best_score:
            best_score = score
            best_enc = enc
    return best_enc


def _strip_header(text: str) -> str:
    """去掉上传站声明头，尽量从书名或第一章/回开始。"""
    head = text[:8000]
    cut = 0
    for marker in HEADER_MARKERS:
        pos = head.find(marker)
        if pos >= 0:
            nl = head.find("\n", pos)
            if nl >= 0:
                cut = max(cut, nl + 1)
    if cut:
        text = text[cut:]
        head = text[:8000]

    m = re.search(r"《[^》\n]{1,40}》", head)
    if m:
        return text[m.start() :]
    m = re.search(rf"第{_CN_NUM}[回章]", head)
    if m:
        line_start = head.rfind("\n", 0, m.start()) + 1
        return text[line_start:]
    return text


def _extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines()[:30]:
        s = line.strip()
        m = BOOK_TITLE_RE.match(s)
        if m:
            # 《三国演义》无删节 → 三国演义
            title = m.group(1).strip()
            title = re.sub(r"（.*?）|\(.*?\)|无删节|全本|全集", "", title).strip()
            return title or fallback
        # 行内带书名号
        m2 = re.search(r"《([^》]{1,40})》", s)
        if m2 and ("演义" in m2.group(1) or "传" in m2.group(1) or len(s) < 40):
            title = re.sub(r"（.*?）|\(.*?\)|无删节|全本|全集", "", m2.group(1)).strip()
            return title or fallback
    return fallback


def _match_chapter_line(line: str) -> re.Match | None:
    s = line.strip()
    if not s or len(s) > 80:
        # 过长行多半是正文误匹配，古典回目通常较短
        return None
    for pat in CHAPTER_PATTERNS:
        m = pat.match(s)
        if m:
            return m
    return None


def _cn_num_to_int(num: str) -> int | None:
    """中文数字 / 阿拉伯数字 → int。"""
    num = num.translate(str.maketrans("０１２３４５６７８９〇", "01234567890"))
    if num.isdigit():
        return int(num)

    digit = {
        "零": 0, "〇": 0,
        "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    }
    if num == "十":
        return 10
    if num.startswith("十"):
        rest = num[1:]
        return 10 + (digit.get(rest, 0) if rest else 0)
    if "百" in num:
        # 一百二十三 / 一百零八
        parts = num.split("百", 1)
        hundreds = digit.get(parts[0], 0) if parts[0] else 1
        rest = parts[1] if len(parts) > 1 else ""
        if not rest:
            return hundreds * 100
        if rest.startswith("零"):
            rest = rest[1:]
            return hundreds * 100 + digit.get(rest, 0)
        if rest.startswith("十"):
            return hundreds * 100 + _cn_num_to_int(rest)  # type: ignore[operator]
        # 一百二三 少见；一百二十
        if "十" in rest:
            return hundreds * 100 + (_cn_num_to_int(rest) or 0)
        return hundreds * 100 + digit.get(rest, 0)
    if "十" in num:
        left, _, right = num.partition("十")
        tens = digit.get(left, 1) if left else 1
        ones = digit.get(right, 0) if right else 0
        return tens * 10 + ones
    if len(num) == 1 and num in digit:
        return digit[num]
    return None


def _parse_chapter_no(title: str) -> int | None:
    m = _CHAPTER_UNIT_RE.search(title)
    if not m:
        return None
    return _cn_num_to_int(m.group(1))


def _split_by_chapters(text: str) -> list[Chapter]:
    lines = text.splitlines()
    starts: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if _match_chapter_line(line):
            starts.append((i, line.strip()))

    chapters: list[Chapter] = []
    for idx, (start, title) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        body_lines = lines[start + 1 : end]
        content = "\n".join(body_lines).strip()
        if len(content) < settings.min_chapter_chars:
            logger.info("跳过过短章节: %s (%d 字)", title, len(content))
            continue
        chapters.append(
            Chapter(
                chapter_index=len(chapters),
                chapter_no=_parse_chapter_no(title),
                chapter_title=title,
                content=content,
            )
        )
    return chapters


def _split_by_window(text: str, window: int = 3000) -> list[Chapter]:
    """无章节时按固定窗口切成伪章节，便于阅读器浏览。"""
    text = text.strip()
    chapters: list[Chapter] = []
    i = 0
    while i < len(text):
        piece = text[i : i + window]
        chapters.append(
            Chapter(
                chapter_index=len(chapters),
                chapter_no=len(chapters) + 1,
                chapter_title=f"片段 {len(chapters) + 1}",
                content=piece.strip(),
            )
        )
        i += window
    return chapters


def parse_novel_bytes(raw: bytes, filename: str = "未命名") -> ParseResult:
    """解析小说字节流为章节结构。"""
    enc = detect_encoding(raw)
    text = raw.decode(enc)
    text = _strip_header(text)
    title = _extract_title(text, fallback=filename.rsplit(".", 1)[0])

    chapters = _split_by_chapters(text)
    warning = ""
    split_mode = "chapter"

    # 命中不足则降级（三国演义约 120 回，阈值 20 合理）
    if len(chapters) < 20:
        warning = (
            f"章节探测仅命中 {len(chapters)} 处，已降级为固定窗口切分。"
            "支持「第N章」「第N回」独立成行的 TXT。"
        )
        logger.warning(warning)
        chapters = _split_by_window(text)
        split_mode = "window"
        for i, ch in enumerate(chapters):
            ch.chapter_index = i

    logger.info(
        "解析完成: title=%s, mode=%s, chapters=%d, encoding=%s",
        title,
        split_mode,
        len(chapters),
        enc,
    )
    return ParseResult(
        title=title,
        chapters=chapters,
        split_mode=split_mode,
        warning=warning,
    )
