# -*- coding: utf-8 -*-
"""
AI 工作台路由：聊天检索 + 兜底内容分析。
"""

from typing import Dict

from flask import Blueprint, jsonify, request, g
from flask_jwt_extended import get_jwt_identity, jwt_required

from server.ai_search_agent import (
    ai_build_search_query,
    search_images_with_query,
    fallback_content_search,
    find_images_by_tag_exact,
    _expand_keywords_with_synonyms,
)

bp = Blueprint("ai", __name__)


def _current_user_id_from_jwt():
    uid = get_jwt_identity()
    if isinstance(uid, dict):
        return uid.get("user_id") or uid.get("id")
    if isinstance(uid, str) and uid.isdigit():
        return int(uid)
    return uid


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


@bp.post("/api/ai/chat-search")
@jwt_required()
def chat_search():
    """AI 对话检索：元数据优先，数量不足时兜底内容分析。"""
    try:
        g.user_id = _current_user_id_from_jwt()
        data = request.get_json(silent=True) or {}
        message = (data.get("message") or data.get("q") or "").strip()
        if not message:
            return jsonify({"ok": False, "error": "缺少搜索内容"}), 400

        limit = int(data.get("limit") or 12)
        limit = max(1, min(limit, 30))
        expansion_threshold = 5
        fallback_threshold = 5

        query_obj = ai_build_search_query(message)
        if not (query_obj.get("keywords") or []):
            return jsonify(
                {
                    "ok": True,
                    "reply": "关键词过少或过于宽泛，请提供更具体的描述再试试～",
                    "results": [],
                    "usedFallback": False,
                    "usedExpansion": False,
                    "expandedKeywords": [],
                }
            )
        tag_exact_hits = []
        if len(query_obj.get("keywords") or []) == 1:
            tag_exact_hits = find_images_by_tag_exact(query_obj["keywords"][0], user_id=g.user_id, limit=limit)

        results_meta = list(tag_exact_hits)
        if len(results_meta) < limit:
            text_meta = search_images_with_query(query_obj, user_id=g.user_id, limit=limit)
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
                more_meta = search_images_with_query(expanded_query, user_id=g.user_id, limit=limit)
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
            results_fallback = fallback_content_search(message, user_id=g.user_id, limit=limit)
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
        if fallback_called:
            reply = f"元数据命中较少，我补充了关键词扩展并用 AI 分析内容，最终找到 {len(final_list)} 张可能相关的图片。"
        elif used_expansion:
            reply = f"我为你扩展了搜索词（如：{'、'.join(expanded_keywords)}），共找到 {len(final_list)} 张相关图片。"
        else:
            reply = f"我帮你找到了 {len(final_list)} 张与「{message}」相关的图片。"

        return jsonify(
            {
                "ok": True,
                "reply": reply,
                "results": [_to_camel(it) for it in final_list],
                "usedFallback": used_fallback,
                "usedExpansion": used_expansion,
                "expandedKeywords": expanded_keywords,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": "数据库或检索异常", "detail": str(exc)}), 500
