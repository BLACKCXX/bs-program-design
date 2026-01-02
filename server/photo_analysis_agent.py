# -*- coding: utf-8 -*-
"""
AI 图片自动分析封装：调用 DashScope 多模态模型，返回描述与标签。
"""

import json
import os
import re
from http import HTTPStatus
from typing import Any, Dict, List

from dotenv import load_dotenv
import dashscope
from dashscope import MultiModalConversation

# 兼容 app.py 已经 load_dotenv 的情况；重复调用也安全
load_dotenv()
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY") or dashscope.api_key

DEFAULT_MODEL = os.getenv("DASHSCOPE_MODEL", "qwen-vl-plus")
PROMPT_TEXT = (
    "请用中文给出这张图片的推荐标题、描述和标签。标题要求 10~16 个汉字左右，简洁概括主题；"
    "描述保持一句话概括；标签不超过 5 个、使用单个名词（如：风景、人物、动物、建筑、植物）。"
    '请返回严格的 JSON：{"title": "...", "description": "...", "tags":["...", "..."]}'
)
EXPLAIN_PROMPT_TEXT = (
    "请用自然中文讲解这张图片内容，像在给朋友介绍。"
    "explanation 2~5 句，语气自然；highlights 3~6 条要点；title 可选简短。"
    "不要复述用户问题，不要提及模型或分析过程。"
    '请返回严格的 JSON：{"title":"...", "explanation":"...", "highlights":["..."], "tags":["..."]}'
)


def _normalize_tags(tags_raw: Any) -> List[str]:
    """标签去重、截断到 5 个。"""
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


def _normalize_highlights(raw: Any) -> List[str]:
    """要点清洗：去重、截断到 6 条。"""
    parts: List[str] = []
    if isinstance(raw, str):
        parts = [p.strip() for p in re.split(r"[；;。.!?\\n,，]+", raw) if p.strip()]
    elif isinstance(raw, (list, tuple)):
        parts = [str(p).strip() for p in raw if str(p).strip()]
    deduped: List[str] = []
    for p in parts:
        if p in deduped:
            continue
        deduped.append(p)
        if len(deduped) >= 6:
            break
    return deduped


def _extract_json(text: str) -> Dict[str, Any]:
    """解析模型返回的文本为 JSON。"""
    if not text:
        raise ValueError("模型未返回有效文本")

    candidate = text.strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        # 模型可能带有额外说明，这里仅提取花括号部分尝试解析
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            fragment = candidate[start : end + 1]
            data = json.loads(fragment)
        else:
            raise ValueError("AI 返回格式无法解析")

    if not isinstance(data, dict):
        raise ValueError("AI 返回数据类型异常")

    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    tags = _normalize_tags(data.get("tags") or [])
    return {"title": title, "description": description, "tags": tags}


def _extract_explain_json(text: str) -> Dict[str, Any]:
    """解析讲解 JSON，保证字段类型稳定。"""
    if not text:
        raise ValueError("模型未返回有效文本")

    candidate = text.strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            fragment = candidate[start : end + 1]
            data = json.loads(fragment)
        else:
            raise ValueError("AI 返回格式无法解析")

    if not isinstance(data, dict):
        raise ValueError("AI 返回数据类型异常")

    title = str(data.get("title") or "").strip()
    explanation = str(data.get("explanation") or "").strip()
    highlights = _normalize_highlights(data.get("highlights") or [])
    tags = _normalize_tags(data.get("tags") or [])
    return {"title": title, "explanation": explanation, "highlights": highlights, "tags": tags}


def analyze_image(image_path: str) -> Dict[str, Any]:
    """
    调用通义千问多模态模型，对图片进行理解，返回描述与标签。
    - image_path: 服务器本地图片路径
    - 返回: {"description": "...", "tags": ["标签1", ...]}
    - 出错时抛出异常，由上层捕获并转换为 HTTP 错误响应
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError("待分析的图片不存在")
    if not dashscope.api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 未配置")

    abs_path = os.path.abspath(image_path)
    messages = [
        {"role": "system", "content": [{"text": "你是一个图片标注助手"}]},
        {
            "role": "user",
            "content": [
                {"image": f"file://{abs_path}"},
                {"text": PROMPT_TEXT},
            ],
        },
    ]

    try:
        response = MultiModalConversation.call(model=DEFAULT_MODEL, messages=messages)
    except Exception as exc:
        # 网络/鉴权等异常
        raise RuntimeError(f"调用多模态模型失败: {exc}") from exc

    if response.status_code != HTTPStatus.OK:
        err_msg = getattr(response, "message", None) or str(getattr(response, "code", "")) or "DashScope 返回错误"
        raise RuntimeError(err_msg)

    contents = response.output.choices[0]["message"]["content"]
    text_parts = [c.get("text") for c in contents if isinstance(c, dict) and c.get("text")]
    combined_text = "\n".join(filter(None, text_parts)).strip()

    parsed = _extract_json(combined_text)
    # 兜底：确保字段存在
    parsed.setdefault("title", "")
    parsed.setdefault("description", "")
    parsed.setdefault("tags", [])
    parsed["title"] = (parsed.get("title") or "").strip()
    parsed["tags"] = _normalize_tags(parsed.get("tags") or [])
    return parsed


def analyze_image_explain(image_path: str, style: str = "friendly") -> Dict[str, Any]:
    """
    调用多模态模型，输出自然中文讲解与要点。
    - style: 讲解风格提示（当前用于扩展）
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError("待分析的图片不存在")
    if not dashscope.api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 未配置")

    abs_path = os.path.abspath(image_path)
    system_prompt = "你是图片内容讲解助手，擅长用自然中文描述画面。"
    if style and style != "friendly":
        system_prompt = f"{system_prompt} 请使用{style}风格表达。"
    messages = [
        {"role": "system", "content": [{"text": system_prompt}]},
        {
            "role": "user",
            "content": [
                {"image": f"file://{abs_path}"},
                {"text": EXPLAIN_PROMPT_TEXT},
            ],
        },
    ]

    try:
        response = MultiModalConversation.call(model=DEFAULT_MODEL, messages=messages, temperature=0.3)
    except Exception as exc:
        raise RuntimeError(f"调用多模态模型失败: {exc}") from exc

    if response.status_code != HTTPStatus.OK:
        err_msg = getattr(response, "message", None) or str(getattr(response, "code", "")) or "DashScope 返回错误"
        raise RuntimeError(err_msg)

    contents = response.output.choices[0]["message"]["content"]
    text_parts = [c.get("text") for c in contents if isinstance(c, dict) and c.get("text")]
    combined_text = "\n".join(filter(None, text_parts)).strip()

    parsed = _extract_explain_json(combined_text)
    parsed.setdefault("title", "")
    parsed.setdefault("explanation", "")
    parsed.setdefault("highlights", [])
    parsed.setdefault("tags", [])
    parsed["title"] = (parsed.get("title") or "").strip()
    parsed["explanation"] = (parsed.get("explanation") or "").strip()
    parsed["highlights"] = _normalize_highlights(parsed.get("highlights") or [])
    parsed["tags"] = _normalize_tags(parsed.get("tags") or [])
    return parsed
