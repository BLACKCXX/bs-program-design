# -*- coding: utf-8 -*-
"""
AI 工作台路由：聊天检索 + 兜底内容分析。
"""

import json
import os
import re
from collections import Counter
from typing import Dict, List

from flask import Blueprint, Response, request, g, current_app
from flask_jwt_extended import get_jwt_identity, jwt_required

from server.ai_search_agent import (
    ai_build_search_query,
    search_images_with_query,
    fallback_content_search,
    find_images_by_tag_exact,
    _expand_keywords_with_synonyms,
    pick_display_keyword,
)
from server.db import query
from server.photo_analysis_agent import analyze_image_explain

bp = Blueprint("ai", __name__)

DEFAULT_UPLOAD_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.getenv("UPLOAD_DIR", "uploads"))
)

_SEARCH_HINTS = (
    "找",
    "搜",
    "搜索",
    "检索",
    "图片",
    "照片",
    "图",
    "有关",
    "相关",
    "帮我找",
    "请找",
    "帮我搜",
    "查找",
    "找找",
    "给我找",
    "帮忙找",
)
_GREETINGS = ("你好", "您好", "在吗", "hi", "hello", "嗨", "哈喽", "早上好", "晚上好")
_THANKS = ("谢谢", "多谢", "辛苦了", "感谢", "谢啦", "thx", "thanks")


def _json_response(payload: Dict, status: int = 200) -> Response:
    """Return JSON with explicit UTF-8 charset to avoid mojibake in clients."""
    body = json.dumps(payload, ensure_ascii=False)
    return Response(body, status=status, content_type="application/json; charset=utf-8")


def _current_user_id_from_jwt():
    uid = get_jwt_identity()
    if isinstance(uid, dict):
        return uid.get("user_id") or uid.get("id")
    if isinstance(uid, str) and uid.isdigit():
        return int(uid)
    return uid


def _get_upload_root() -> str:
    try:
        return os.path.abspath(current_app.config["UPLOAD_DIR"])
    except Exception:
        return DEFAULT_UPLOAD_DIR


def _safe_abs_path(rel_path: str) -> str:
    if not rel_path:
        return ""
    base_root = _get_upload_root()
    abs_path = os.path.abspath(os.path.join(base_root, rel_path))
    try:
        if os.path.commonpath([abs_path, base_root]) != base_root:
            return ""
    except Exception:
        return ""
    return abs_path


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower())


def _contains_any(text: str, keywords: tuple) -> bool:
    return any(k in text for k in keywords)


def _rule_intent(message: str) -> str:
    """Rule-based intent routing; unknown will fallback to chat."""
    text = _normalize_text(message)
    if not text:
        return "chat"
    if _contains_any(text, _SEARCH_HINTS):
        return "search"
    if _contains_any(text, _GREETINGS) or _contains_any(text, _THANKS):
        return "chat"
    return "unknown"


def _chat_reply(message: str) -> str:
    """Template replies when no text LLM is configured."""
    text = _normalize_text(message)
    if _contains_any(text, _THANKS):
        return "不客气，需要我再帮你找点什么吗？"
    if _contains_any(text, _GREETINGS):
        return "你好！我在。你想找图还是想聊点什么？"
    return "我在。你可以告诉我想找的图片关键词，或者继续聊聊。"


def _build_search_reply(display_keyword: str, results: List[Dict]) -> str:
    """Natural search response using purified keyword."""
    keyword = display_keyword or "目标"
    if results:
        return f"我找到了 {len(results)} 张与「{keyword}」有关的图片。点开可查看详情或继续编辑。"
    return f"我暂时没在图库里找到与「{keyword}」有关的图片。你可以换个更具体的关键词试试。"


def _run_search(message: str, user_id: int, limit: int) -> Dict:
    """Shared search workflow for unified and legacy endpoints."""
    query_obj = ai_build_search_query(message)
    display_keyword = pick_display_keyword(query_obj) or message
    if not (query_obj.get("keywords") or []):
        return {
            "reply": "关键词过少或过于宽泛，请提供更具体的描述再试试～",
            "results": [],
            "images": [],
            "usedFallback": False,
            "usedExpansion": False,
            "expandedKeywords": [],
            "displayKeyword": display_keyword,
        }

    expansion_threshold = 5
    fallback_threshold = 5
    tag_exact_hits = []
    if len(query_obj.get("keywords") or []) == 1:
        tag_exact_hits = find_images_by_tag_exact(query_obj["keywords"][0], user_id=user_id, limit=limit)

    results_meta = list(tag_exact_hits)
    if len(results_meta) < limit:
        text_meta = search_images_with_query(query_obj, user_id=user_id, limit=limit)
        # 合并，tag 精准命中优先
        exist_map = {it["id"]: it for it in results_meta}
        for item in text_meta:
            if item["id"] in exist_map:
                base = exist_map[item["id"]]
                base["score"] = max(base.get("score") or 0, item.get("score") or 0)
                if item.get("matched_fields"):
                    base["matched_fields"] = sorted(
                        set(base.get("matched_fields") or []) | set(item.get("matched_fields") or [])
                    )
                if not base.get("match_reason"):
                    base["match_reason"] = item.get("match_reason") or "text_match"
            else:
                exist_map[item["id"]] = item
        results_meta = list(exist_map.values())

    used_expansion = False
    expanded_keywords = []
    if len(results_meta) < expansion_threshold:
        expanded_keywords = _expand_keywords_with_synonyms(
            query_obj.get("keywords") or [], query_obj.get("cleaned_keyword") or ""
        )
        if expanded_keywords:
            print(f"[ai chat-search] expanded keywords: {expanded_keywords}")
            new_keywords = list(dict.fromkeys((query_obj.get("keywords") or []) + expanded_keywords))
            expanded_query = {**query_obj, "keywords": new_keywords}
            more_meta = search_images_with_query(expanded_query, user_id=user_id, limit=limit)
            if more_meta:
                used_expansion = True
                # merge new results into meta list while keeping highest score/suggestions
                exist_map = {it["id"]: it for it in results_meta}
                for item in more_meta:
                    if item["id"] in exist_map:
                        base = exist_map[item["id"]]
                        base["score"] = max(base.get("score") or 0, item.get("score") or 0)
                        if item.get("matched_fields"):
                            base["matched_fields"] = sorted(
                                set(base.get("matched_fields") or []) | set(item.get("matched_fields") or [])
                            )
                        if item.get("short_caption") and not base.get("short_caption"):
                            base["short_caption"] = item.get("short_caption")
                        if not base.get("suggested_tags"):
                            base["suggested_tags"] = item.get("suggested_tags") or []
                    else:
                        exist_map[item["id"]] = item
                results_meta = list(exist_map.values())

    results_fallback = []
    fallback_called = len(results_meta) < fallback_threshold
    used_fallback = False
    if fallback_called:
        results_fallback = fallback_content_search(message, user_id=user_id, limit=limit)
        used_fallback = True

    merged = {}
    for item in results_meta:
        merged[item["id"]] = item
    for item in results_fallback:
        if item["id"] in merged:
            base = merged[item["id"]]
            base["score"] = max(base.get("score") or 0, item.get("score") or 0)
            if item.get("matched_fields"):
                base["matched_fields"] = sorted(
                    set(base.get("matched_fields") or []) | set(item.get("matched_fields") or [])
                )
            if not base.get("suggested_tags"):
                base["suggested_tags"] = item.get("suggested_tags") or []
            if item.get("short_caption") and not base.get("short_caption"):
                base["short_caption"] = item.get("short_caption")
        else:
            merged[item["id"]] = item

    final_list = []
    for item in merged.values():
        fields = set(item.get("matched_fields") or [])
        score = item.get("score") or 0
        reason = item.get("match_reason") or ""
        # 强相关过滤：需要有命中的字段；文本匹配时若无标签/标题命中且分低则丢弃
        if not fields:
            continue
        if reason in ("", "text_match") and (not ({"tags", "title"} & fields)) and score < 3.0:
            continue
        final_list.append(item)

    final_list.sort(key=lambda x: (-(x.get("score") or 0), x.get("title") or ""))
    if len(final_list) > limit:
        final_list = final_list[:limit]
    reply = _build_search_reply(display_keyword, final_list)
    results = [_to_camel(it) for it in final_list]

    return {
        "reply": reply,
        "results": results,
        "images": results,
        "usedFallback": used_fallback,
        "usedExpansion": used_expansion,
        "expandedKeywords": expanded_keywords,
        "displayKeyword": display_keyword,
    }


def _to_camel(item: Dict) -> Dict:
    return {
        "id": item.get("id"),
        "title": item.get("title") or "未命名",
        "description": item.get("description") or "",
        "thumbUrl": item.get("thumb_url") or item.get("cover_url") or "",
        "coverUrl": item.get("cover_url") or item.get("thumb_url") or "",
        "tags": item.get("tags") or [],
        "suggestedTags": item.get("suggested_tags") or [],
        "shortCaption": item.get("short_caption") or "",
        "matchedFields": item.get("matched_fields") or [],
        "matchReason": item.get("match_reason") or "",
        "detailUrl": item.get("detail_url") or (f"/images/{item.get('id')}" if item.get("id") else ""),
        "score": item.get("score"),
    }


def _build_match_summary(results: List[Dict]) -> str:
    field_map = {"tags": "标签", "title": "标题", "description": "描述"}
    counts: Counter = Counter()
    for item in results:
        for field in item.get("matched_fields") or []:
            if field in field_map:
                counts[field] += 1
    if not counts:
        return ""
    top = [field_map[k] for k, _ in counts.most_common(2)]
    return "、".join(top)


def _summarize_results(results: List[Dict]) -> str:
    if not results:
        return ""
    item = results[0]
    text = (item.get("description") or item.get("title") or "").strip()
    if not text:
        return "与主题最相关的图片"
    text = " ".join(text.split())
    if len(text) > 36:
        text = text[:36].rstrip("，。;；,") + "..."
    for prefix in ("这是一张", "一张", "一幅", "一组", "一处"):
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip(" ，。:：")
            break
    return text


def _build_reply(
    message: str,
    results: List[Dict],
    used_expansion: bool,
    used_fallback: bool,
    expanded_keywords: List[str],
) -> str:
    if not results:
        return f"图库里暂时没有命中「{message}」的图片。你可以换个关键词或补充标签再试试。"

    count = len(results)
    summary = _summarize_results(results)
    return f"我找到了 {count} 张与「{message}」相关的图片，这是一张{summary}。"


@bp.post("/api/ai/chat-search")
@bp.post("/api/ai/chat_search")
@jwt_required()
def chat_search():
    """AI 对话检索：元数据优先，数量不足时兜底内容分析。"""
    try:
        g.user_id = _current_user_id_from_jwt()
        data = request.get_json(silent=True) or {}
        message = (data.get("message") or data.get("q") or "").strip()
        if not message:
            return _json_response({"ok": False, "error": "缺少搜索内容"}, 400)

        limit = int(data.get("limit") or 12)
        limit = max(1, min(limit, 30))
        payload = _run_search(message, g.user_id, limit)
        payload["ok"] = True
        return _json_response(payload)
    except Exception as exc:
        return _json_response({"ok": False, "error": "数据库或检索异常", "detail": str(exc)}, 500)


@bp.post("/api/ai/message")
@jwt_required()
def ai_message():
    """统一对话入口：聊天/检索意图分流。"""
    try:
        g.user_id = _current_user_id_from_jwt()
        data = request.get_json(silent=True) or {}
        message = (data.get("message") or data.get("q") or "").strip()
        if not message:
            return _json_response({"ok": False, "error": "缺少对话内容"}, 400)

        limit = int(data.get("limit") or 12)
        limit = max(1, min(limit, 30))
        intent = _rule_intent(message)
        if intent == "unknown":
            intent = "chat"
        if intent == "search":
            payload = _run_search(message, g.user_id, limit)
            payload.update({"ok": True, "intent": "search"})
            return _json_response(payload)

        reply = _chat_reply(message)
        return _json_response({"ok": True, "intent": "chat", "reply": reply, "images": [], "results": []})
    except Exception as exc:
        return _json_response({"ok": False, "error": "AI 服务异常", "detail": str(exc)}, 500)


@bp.post("/api/ai/explain-images")
@jwt_required()
def explain_images():
    """对图片列表做内容讲解，不写入数据库。"""
    try:
        g.user_id = _current_user_id_from_jwt()
        data = request.get_json(silent=True) or {}
        image_ids = data.get("imageIds") or data.get("image_ids") or []
        if not isinstance(image_ids, (list, tuple)):
            return _json_response({"ok": False, "error": "imageIds 必须是数组"}, 400)

        ids: List[int] = []
        for raw in image_ids:
            try:
                val = int(raw)
            except Exception:
                continue
            if val not in ids:
                ids.append(val)
        if not ids:
            return _json_response({"ok": False, "error": "缺少可分析的图片"}, 400)
        if len(ids) > 6:
            return _json_response({"ok": False, "error": "一次最多分析 6 张图片"}, 400)

        style = (data.get("style") or "friendly").strip()
        placeholders = ",".join(["%s"] * len(ids))
        rows = query(
            f"""
            SELECT id, title, stored_path, path
            FROM images
            WHERE owner_id=%s AND id IN ({placeholders})
            """,
            [g.user_id or 0, *ids],
        )
        row_map = {r["id"]: r for r in rows}

        items = []
        for image_id in ids:
            row = row_map.get(image_id)
            if not row:
                items.append(
                    {
                        "imageId": image_id,
                        "title": "",
                        "explanation": "分析失败：图片不存在或无权限",
                        "highlights": [],
                    }
                )
                continue
            rel_path = (row.get("stored_path") or row.get("path") or "").strip()
            abs_path = _safe_abs_path(rel_path)
            if not abs_path or not os.path.exists(abs_path):
                items.append(
                    {
                        "imageId": image_id,
                        "title": row.get("title") or "",
                        "explanation": "分析失败：图片文件不存在",
                        "highlights": [],
                    }
                )
                continue
            try:
                result = analyze_image_explain(abs_path, style=style)
                items.append(
                    {
                        "imageId": image_id,
                        "title": result.get("title") or row.get("title") or "",
                        "explanation": result.get("explanation") or "",
                        "highlights": result.get("highlights") or [],
                        "tags": result.get("tags") or [],
                    }
                )
            except Exception as exc:
                items.append(
                    {
                        "imageId": image_id,
                        "title": row.get("title") or "",
                        "explanation": f"分析失败：{exc}",
                        "highlights": [],
                    }
                )

        return _json_response({"ok": True, "items": items})
    except Exception as exc:
        return _json_response({"ok": False, "error": "AI 服务异常", "detail": str(exc)}, 500)
