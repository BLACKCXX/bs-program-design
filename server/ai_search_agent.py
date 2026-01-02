# -*- coding: utf-8 -*-
"""
AI 检索助手：先走元数据检索，不足时对图片内容做兜底分析，并返回推荐标签。
"""

import json
import os
import re
from http import HTTPStatus
from typing import Any, Dict, List, Set

from dotenv import load_dotenv
import dashscope
from dashscope import MultiModalConversation
import jieba

from server.db import query

load_dotenv()
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY") or dashscope.api_key

DEFAULT_MODEL = os.getenv("DASHSCOPE_MODEL", "qwen-vl-plus")
UPLOAD_DIR = os.path.abspath(os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "uploads")))
CONTENT_PROMPT = (
    "你现在是图片检索助手。"
    "用户的搜索意图是：{user_message}。"
    "给定这张图片，请你判断它是否与用户意图相关，并只输出一个 JSON："
    '{"match_score": 0到1之间的数值, "suggested_tags": ["标签1","标签2","标签3"], "short_caption": "简短描述"} '
    "严格输出 JSON，不要输出多余文字。"
)

_POLITE_PREFIXES = [
    "请帮我找一下",
    "请帮我找一份",
    "请帮我找一张",
    "请帮我找",
    "帮我找一下",
    "帮我找一份",
    "帮我找一张",
    "帮我找",
    "帮我",
    "我想找",
    "我想要",
    "我想搜",
    "想找",
    "想搜",
    "找一下",
    "帮忙找",
    "给我找",
    "麻烦帮忙找",
]
_TRAILING_PARTICLES_RE = re.compile(r"[吗嘛呢吧呀啊哦哇啦喽呗～~。！？!,，、\\s]+$")
_KEYWORD_SPLIT_RE = re.compile(r"[\\s,，。；;、/]+")
_QUOTE_RE = re.compile(r"[\"“”‘’']([^\"“”‘’']+)[\"“”‘’']")
_DISPLAY_TRIM_RE = re.compile(r"(有关|相关|关于|图片|照片|图)+$")
_DEBUG = os.getenv("DEBUG", "").lower() in ("1", "true", "yes", "on", "debug")

# 尝试加载自定义词典
_CUSTOM_DICT = os.path.join(os.path.dirname(__file__), "kb", "custom_dict.txt")
if os.path.exists(_CUSTOM_DICT):
    try:
        jieba.load_userdict(_CUSTOM_DICT)
    except Exception as exc:  # pragma: no cover - 日志即可
        print(f"[ai_search] load custom dict failed: {exc}")

_STOPWORDS = {
    "请",
    "帮我",
    "帮忙",
    "一下",
    "一个",
    "一份",
    "一些",
    "找",
    "一下",
    "寻找",
    "想要",
    "想找",
    "给我",
    "有没有",
    "图片",
    "照片",
    "图",
    "的",
    "与",
    "关于",
    "有关",
    "相关的",
    "下",
    "呢",
    "吗",
    "了",
    "和",
    "是",
    "你",
    "这个",
    "那个",
    "相关",
    "搜索",
    "推荐",
}
_SYNONYM_MAP = {
    "实习鉴定表": ["实习评价表", "实践鉴定表", "实习证明", "鉴定表", "实习考核表"],
    "鉴定表": ["评价表", "考核表", "证明"],
}
MIN_SCORE = float(os.getenv("AI_SEARCH_MIN_SCORE", "2.5"))


def _strip_polite_prefixes(text: str) -> str:
    """
    Remove common Chinese polite or helper phrases so metadata search uses the core noun.
    Example: "请帮我找一份实习鉴定表" -> "实习鉴定表".
    """
    t = (text or "").strip()
    if not t:
        return ""
    for prefix in _POLITE_PREFIXES:
        if t.startswith(prefix):
            t = t[len(prefix) :].lstrip()
            break
    for filler in ("一份", "一张", "一个", "一些", "一条"):
        if t.startswith(filler):
            t = t[len(filler) :].lstrip()
            break
    t = t.lstrip("的").strip()
    t = _TRAILING_PARTICLES_RE.sub("", t).strip()
    return t


def _extract_quotes(text: str) -> List[str]:
    """优先保留引号内的关键词短语"""
    phrases = []
    for m in _QUOTE_RE.finditer(text):
        val = m.group(1).strip()
        if val and val not in phrases:
            phrases.append(val)
    return phrases


def normalize_query(q: str) -> str:
    base = _strip_polite_prefixes(q or "")
    base = re.sub(r'["“”‘’\'\[\]{}()（）]+', " ", base)
    base = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", " ", base)
    return re.sub(r"\s+", " ", base).strip()


def tokenize_zh(q: str) -> List[str]:
    raw = (q or "").strip()
    normalized = normalize_query(raw)
    if not normalized:
        return []
    tokens: List[str] = []
    for seg in jieba.cut(normalized, cut_all=False):
        seg = seg.strip()
        if seg:
            tokens.append(seg)
    # 引号内容作为强关键词优先加入
    quotes = _extract_quotes(raw)
    tokens = quotes + tokens
    return tokens


def filter_tokens(tokens: List[str]) -> List[str]:
    filtered: List[str] = []
    seen: Set[str] = set()
    for tok in tokens:
        t = (tok or "").strip()
        if not t:
            continue
        if t in _STOPWORDS:
            continue
        # 丢弃绝大多数单字（保留数字/英文）
        if len(t) == 1 and not re.match(r"[0-9A-Za-z]", t):
            continue
        if t in seen:
            continue
        seen.add(t)
        filtered.append(t)
    return filtered[:10]


def pick_display_keyword(query_obj: Dict[str, Any]) -> str:
    """Return a concise keyword for UI replies, avoiding full-sentence echoes."""
    keywords = [k for k in (query_obj.get("keywords") or []) if k]
    if keywords:
        return "、".join(keywords[:3])
    cleaned = (query_obj.get("cleaned_keyword") or "").strip()
    if cleaned:
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = _DISPLAY_TRIM_RE.sub("", cleaned).strip(" 的")
        if cleaned:
            return cleaned
    return (query_obj.get("keyword") or "").strip()


def _expand_keywords_with_synonyms(keywords: List[str], cleaned_keyword: str = "") -> List[str]:
    """
    Provide lightweight synonym/alias expansions for common nouns to improve recall without a model.
    """
    base = [k for k in keywords if k]
    if cleaned_keyword:
        base.append(cleaned_keyword)
    expansions: List[str] = []
    for kw in base:
        for key, syns in _SYNONYM_MAP.items():
            if key in kw or kw in key:
                for s in syns:
                    if s not in expansions and s not in base:
                        expansions.append(s)
    return expansions


def ai_build_search_query(user_message: str) -> Dict[str, Any]:
    """构造元数据检索条件（标题/描述/标签模糊匹配）。"""
    raw_kw = (user_message or "").strip()
    normalized = normalize_query(raw_kw)
    tokens_raw = tokenize_zh(raw_kw)
    keywords = filter_tokens(tokens_raw)
    cleaned = normalized
    if _DEBUG:
        print(f"[chat-search] title_query={raw_kw} tokens={keywords}")
    return {
        "keyword": raw_kw,
        "keywords": keywords,
        "tokens": keywords,
        "cleaned_keyword": cleaned,
        "normalized": normalized,
    }


def _normalize_tags(tags_raw: Any) -> List[str]:
    if isinstance(tags_raw, str):
        tags_raw = [tags_raw]
    tags: List[str] = []
    if isinstance(tags_raw, (list, tuple)):
        for t in tags_raw:
            name = str(t).strip()
            if not name or name in tags:
                continue
            tags.append(name)
            if len(tags) >= 5:
                break
    return tags


def _load_tags_map(ids: List[int]) -> Dict[int, List[str]]:
    if not ids:
        return {}
    placeholders = ",".join(["%s"] * len(ids))
    rows = query(
        f"""
        SELECT it.image_id, t.name
        FROM image_tags it
        JOIN tags t ON t.id = it.tag_id
        WHERE it.image_id IN ({placeholders})
        """,
        ids,
    )
    tags_map: Dict[int, List[str]] = {}
    for r in rows:
        tags_map.setdefault(r["image_id"], []).append(r["name"])
    return tags_map


def _score_row(row: Dict[str, Any], tags: List[str], keywords: List[str], query_phrase: str) -> tuple:
    title = (row.get("title") or "").lower()
    desc = (row.get("description") or "").lower()
    tag_text = " ".join(tags).lower()
    matched = set()
    score = 0.0
    hit_tokens: Set[str] = set()
    strong_tokens: Set[str] = set()
    for kw in keywords:
        k = str(kw or "").lower().strip()
        if not k:
            continue
        strong = False
        matched_any = False
        if k in title:
            matched.add("title")
            matched_any = True
            strong = True
            score += 3.0
        if tag_text and k in tag_text:
            matched.add("tags")
            matched_any = True
            strong = True
            score += 2.0
        if k in desc:
            matched.add("description")
            matched_any = True
            score += 1.0
        if matched_any:
            hit_tokens.add(k)
        if strong:
            strong_tokens.add(k)
    phrase = (query_phrase or "").lower().strip()
    if phrase and phrase in title:
        matched.add("title")
        score += 5.0
    if phrase and tag_text and phrase in tag_text:
        matched.add("tags")
        score += 4.0
    if "title" in matched and "tags" in matched:
        score += 2.0
    return score, sorted(matched), hit_tokens, strong_tokens


def _result_dict(row: Dict[str, Any], tags_map: Dict[int, List[str]], keywords: List[str], match_reason: str = "text_match") -> Dict[str, Any]:
    rel_path = (row.get("stored_path") or row.get("path") or "").strip()
    url = f"/files/{rel_path}" if rel_path else ""
    tags = tags_map.get(row["id"], [])
    score, matched_fields, _, _ = _score_row(row, tags, keywords, "")
    return {
        "id": row["id"],
        "title": row.get("title") or "未命名",
        "description": row.get("description") or "",
        "cover_url": url,
        "thumb_url": url,
        "tags": tags,
        "matched_fields": matched_fields,
        "score": round(score, 4) if score else 0.0,
        "detail_url": f"/images/{row['id']}",
        "sort_time": row.get("sort_time"),
        "match_reason": match_reason,
    }


def find_images_by_tag_exact(tag: str, user_id: int, limit: int = 12) -> List[Dict[str, Any]]:
    """标签精准匹配：严格命中标签名，优先返回。"""
    name = (tag or "").strip()
    if not name:
        return []
    rows = query(
        """
        SELECT DISTINCT i.id, i.title, i.description, i.stored_path, i.path,
               COALESCE(i.taken_at, i.created_at) AS sort_time
        FROM images i
        JOIN image_tags it ON it.image_id = i.id
        JOIN tags t ON t.id = it.tag_id
        WHERE i.owner_id=%s AND t.name=%s
        ORDER BY sort_time DESC
        LIMIT %s
        """,
        (user_id, name, limit),
    )
    if not rows:
        return []
    tags_map = _load_tags_map([r["id"] for r in rows])
    results = []
    for r in rows:
        res = _result_dict(r, tags_map, [name], match_reason="tag_exact")
        res["matched_fields"] = ["tags"]
        # 提升标签命中分，保持排序稳定（时间 + 固定分）
        res["score"] = max(res.get("score") or 0.0, 10.0)
        results.append(res)
    results.sort(key=lambda x: (-(x.get("score") or 0), -(x.get("sort_time") or 0).timestamp() if x.get("sort_time") else 0))
    return results[:limit]


def search_images_with_query(query_obj: Dict[str, Any], user_id: int, limit: int = 12) -> List[Dict[str, Any]]:
    """基于标题/描述/标签的元数据检索。"""
    kw_raw = (query_obj.get("keyword") or "").strip()
    cleaned_kw = (query_obj.get("cleaned_keyword") or kw_raw).strip()
    tokens = [k.strip() for k in (query_obj.get("tokens") or query_obj.get("keywords") or []) if k and str(k).strip()]
    if not tokens:
        return []
    keywords: List[str] = list(dict.fromkeys(tokens))

    def _run_query(keywords_for_sql: List[str]) -> List[Dict[str, Any]]:
        if not keywords_for_sql:
            return []
        params: List[Any] = [user_id]
        conds = ["i.owner_id=%s"]
        joins = "LEFT JOIN image_tags it ON it.image_id = i.id LEFT JOIN tags t ON t.id = it.tag_id"
        clauses = []
        for kw in keywords_for_sql:
            like = f"%{kw}%"
            clauses.append(
                "(i.title LIKE %s OR i.description LIKE %s OR t.name LIKE %s OR i.stored_path LIKE %s OR i.path LIKE %s)"
            )
            params.extend([like, like, like, like, like])
        conds.append("(" + " OR ".join(clauses) + ")")
        params.append(limit * 2)  # allow extra for dedupe/sorting
        sql = f"""
            SELECT DISTINCT i.id, i.title, i.description, i.stored_path, i.path,
                   COALESCE(i.taken_at, i.created_at) AS sort_time
            FROM images i
            {joins}
            WHERE {" AND ".join(conds)}
            ORDER BY sort_time DESC
            LIMIT %s
        """
        return query(sql, params)

    rows = _run_query(keywords)
    seen = set()
    unique_rows: List[Dict[str, Any]] = []
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        unique_rows.append(r)

    tags_map = _load_tags_map([r["id"] for r in unique_rows])
    results = []
    for r in unique_rows:
        res = _result_dict(r, tags_map, keywords, match_reason="text_match")
        res["_sort_ts"] = r.get("sort_time").timestamp() if r.get("sort_time") else 0
        # 二次打分 + 过滤
        score, matched_fields, hit_tokens, strong_tokens = _score_row(r, tags_map.get(r["id"], []), keywords, cleaned_kw)
        res["matched_fields"] = matched_fields
        res["score"] = round(score, 4) if score else 0.0
        res["_hit_tokens"] = hit_tokens
        res["_strong_tokens"] = strong_tokens
        results.append(res)

    filtered: List[Dict[str, Any]] = []
    token_count = len(keywords)
    for item in results:
        hit_tokens = item.pop("_hit_tokens", set())
        strong_tokens = item.pop("_strong_tokens", set())
        # 至少要有命中的字段
        if not item.get("matched_fields"):
            continue
        # 单个短词时，要求命中标签或标题（避免描述长文本噪声）
        if len(keywords) == 1:
            fields = set(item.get("matched_fields") or [])
            if not ({"tags", "title"} & fields):
                continue
        if token_count >= 2:
            if len(hit_tokens) < 2 and not (len(hit_tokens) == 1 and strong_tokens):
                continue
        elif token_count == 1:
            if not strong_tokens:
                continue
        if (item.get("score") or 0) < MIN_SCORE:
            continue
        item["match_reason"] = item.get("match_reason") or "text_match"
        filtered.append(item)

    filtered.sort(key=lambda x: (-(x.get("score") or 0), -(x.get("_sort_ts") or 0)))
    for r in filtered:
        r.pop("_sort_ts", None)
    if _DEBUG:
        print(f"[chat-search] candidate_count={len(results)} filtered={len(filtered)}")
    return filtered[:limit]


def _abs_path(rel_path: str) -> str:
    rel = (rel_path or "").lstrip("/\\")
    return os.path.abspath(os.path.join(UPLOAD_DIR, rel))


def _parse_match_json(text: str) -> Dict[str, Any]:
    base = {"match_score": 0.0, "suggested_tags": [], "short_caption": ""}
    if not text:
        return base
    candidate = text.strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            fragment = candidate[start : end + 1]
            try:
                data = json.loads(fragment)
            except Exception:
                return base
        else:
            return base

    if not isinstance(data, dict):
        return base

    try:
        score = float(data.get("match_score") or 0)
    except Exception:
        score = 0.0
    score = max(0.0, min(1.0, score))
    return {
        "match_score": score,
        "suggested_tags": _normalize_tags(data.get("suggested_tags") or []),
        "short_caption": str(data.get("short_caption") or "").strip(),
    }


def _call_match_model(abs_path: str, user_message: str) -> Dict[str, Any]:
    """调用通义千问做单张图片的相似度评估。"""
    messages = [
        {"role": "system", "content": [{"text": "你是一个图片检索助手"}]},
        {
            "role": "user",
            "content": [
                {"image": f"file://{abs_path}"},
                {"text": CONTENT_PROMPT.format(user_message=user_message)},
            ],
        },
    ]
    try:
        resp = MultiModalConversation.call(model=DEFAULT_MODEL, messages=messages)
    except Exception as exc:  # 网络/鉴权等异常
        print(f"[ai_search] call error: {exc}")
        return {"match_score": 0.0, "suggested_tags": [], "short_caption": "", "error": str(exc)}

    if resp.status_code != HTTPStatus.OK:
        print(f"[ai_search] invalid status: {resp.status_code}, message: {getattr(resp, 'message', None)}")
        return {"match_score": 0.0, "suggested_tags": [], "short_caption": "", "error": getattr(resp, "message", None)}

    contents = resp.output.choices[0]["message"]["content"]
    text_parts = [c.get("text") for c in contents if isinstance(c, dict) and c.get("text")]
    combined = "\n".join(filter(None, text_parts)).strip()
    parsed = _parse_match_json(combined)
    return parsed


def _candidate_images(user_id: int, limit: int = 80) -> List[Dict[str, Any]]:
    rows = query(
        """
        SELECT id, title, description, stored_path, path,
               COALESCE(taken_at, created_at) AS sort_time
        FROM images
        WHERE owner_id=%s
        ORDER BY sort_time DESC
        LIMIT %s
        """,
        (user_id, limit),
    )
    return rows


def fallback_content_search(user_message: str, user_id: int, limit: int = 12, score_threshold: float = 0.6) -> List[Dict[str, Any]]:
    """
    元数据不足时的兜底：对图片内容做相似度分析，返回包含推荐标签的结果。
    """
    candidates = _candidate_images(user_id, limit=80)
    tags_map = _load_tags_map([c["id"] for c in candidates])
    results: List[Dict[str, Any]] = []
    for cand in candidates:
        rel_path = (cand.get("stored_path") or cand.get("path") or "").strip()
        if not rel_path:
            continue
        abs_path = _abs_path(rel_path)
        if not os.path.exists(abs_path):
            continue
        parsed = _call_match_model(abs_path, user_message)
        score = parsed.get("match_score") or 0.0
        try:
            score_val = float(score)
        except Exception:
            score_val = 0.0
        if score_val < score_threshold:
            continue
        url = f"/files/{rel_path}"
        results.append(
            {
                "id": cand["id"],
                "title": cand.get("title") or "未命名",
                "description": cand.get("description") or "",
                "cover_url": url,
                "thumb_url": url,
                "tags": tags_map.get(cand["id"], []),
                "suggested_tags": parsed.get("suggested_tags") or [],
                "short_caption": parsed.get("short_caption") or "",
                "match_score": score_val,
                "score": score_val,
                "matched_fields": ["visual"],
                "match_reason": "semantic_fallback",
                "detail_url": f"/images/{cand['id']}",
            }
        )
    results.sort(key=lambda x: x.get("match_score") or 0, reverse=True)
    return results[:limit]
