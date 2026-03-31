"""
LLM JSON 解析工具。
"""

import json
import re
from typing import Any, Dict, Optional

try:
    from json_repair import repair_json as _repair_json
except Exception:
    _repair_json = None

_LEADING_DECIMAL_RE = re.compile(r'(?<=[:\s\[,])\.(\d+)')
_LEADING_NEG_DECIMAL_RE = re.compile(r'(?<=[:\s\[,])-\.(\d+)')


def _normalize_json_like(text: str) -> str:
    if not text:
        return text
    text = _LEADING_DECIMAL_RE.sub(r'0.\1', text)
    text = _LEADING_NEG_DECIMAL_RE.sub(r'-0.\1', text)
    return text


def parse_llm_json(content: str, logger: Optional[Any] = None) -> Dict[str, Any]:
    """
    尝试从 LLM 返回的文本中解析 JSON，兼容：
    - ```json fenced code block
    - 单引号包裹
    - 前后夹杂的非 JSON 文本或截断
    """
    def _try_parse(s: str) -> Dict[str, Any]:
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return {}
    
    if logger:
        logger.debug("parse_llm_json input: %s", content[:500] if content else "")
    
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
    candidate = json_match.group(1).strip() if json_match else content.strip()
    candidate = _normalize_json_like(candidate)
    
    # 1) 直接解析
    parsed = _try_parse(candidate)
    if parsed:
        if logger:
            logger.debug("parse_llm_json parsed via direct candidate")
        return parsed
    
    # 2) 常见问题：单引号
    parsed = _try_parse(_normalize_json_like(candidate.replace("'", '"')))
    if parsed:
        if logger:
            logger.debug("parse_llm_json parsed via single-quote replacement")
        return parsed
    
    # 3) 尝试截取最外层完整的 JSON 片段（处理截断/多余文本）
    def _extract_balanced_json(text: str) -> str:
        start = None
        depth = 0
        last_ok = None
        in_string: Optional[str] = None
        escape = False
        openers = {"{": "}", "[": "]"}
        closers = {"}": "{", "]": "["}
        stack = []
        
        for i, ch in enumerate(text):
            if escape:
                escape = False
                continue
            if ch == "\\":
                if in_string:
                    escape = True
                continue
            if ch in ('"', "'"):
                if in_string == ch:
                    in_string = None
                elif not in_string:
                    in_string = ch
                continue
            if in_string:
                continue
            
            if ch in openers:
                if start is None:
                    start = i
                stack.append(ch)
                depth += 1
            elif ch in closers:
                if stack and stack[-1] == closers[ch]:
                    stack.pop()
                    depth -= 1
                    if depth == 0 and start is not None:
                        last_ok = i
                        break
                else:
                    # 不匹配，放弃
                    break
        if start is not None and last_ok is not None and last_ok > start:
            return text[start:last_ok + 1]
        return ""
    
    balanced = _extract_balanced_json(candidate)
    if balanced:
        parsed = _try_parse(_normalize_json_like(balanced))
        if parsed:
            if logger:
                logger.debug("parse_llm_json parsed via balanced extraction")
            return parsed

    def _repair_unbalanced_json(text: str) -> str:
        start = None
        in_string: Optional[str] = None
        escape = False
        stack = []
        openers = {"{": "}", "[": "]"}
        closers = {"}": "{", "]": "["}
        for i, ch in enumerate(text):
            if escape:
                escape = False
                continue
            if ch == "\\":
                if in_string:
                    escape = True
                continue
            if ch in ('"', "'"):
                if in_string == ch:
                    in_string = None
                elif not in_string:
                    in_string = ch
                continue
            if in_string:
                continue
            if ch in openers:
                if start is None:
                    start = i
                stack.append(ch)
            elif ch in closers:
                if stack and stack[-1] == closers[ch]:
                    stack.pop()
                else:
                    break
        if start is None or not stack:
            return ""
        tail = "".join(openers[ch] for ch in reversed(stack))
        repaired = text[start:] + tail
        return repaired

    def _repair_mismatched_closers(text: str) -> str:
        if not text:
            return ""
        out = []
        stack: list[str] = []
        in_string: Optional[str] = None
        escape = False
        openers = {"{": "}", "[": "]"}
        closers = {"}": "{", "]": "["}
        for ch in text:
            if escape:
                escape = False
                out.append(ch)
                continue
            if ch == "\\":
                if in_string:
                    escape = True
                out.append(ch)
                continue
            if ch in ('"', "'"):
                if in_string == ch:
                    in_string = None
                elif not in_string:
                    in_string = ch
                out.append(ch)
                continue
            if in_string:
                out.append(ch)
                continue
            if ch in openers:
                stack.append(ch)
                out.append(ch)
                continue
            if ch in closers:
                if stack and stack[-1] == closers[ch]:
                    stack.pop()
                    out.append(ch)
                    continue
                if stack:
                    while stack and stack[-1] != closers[ch]:
                        out.append(openers[stack.pop()])
                    if stack and stack[-1] == closers[ch]:
                        stack.pop()
                        out.append(ch)
                        continue
                out.append(ch)
                continue
            out.append(ch)
        if stack:
            out.extend(openers[ch] for ch in reversed(stack))
        repaired = "".join(out)
        return repaired if repaired != text else ""

    repaired = _repair_unbalanced_json(candidate)
    if repaired:
        repaired = _normalize_json_like(repaired)
        parsed = _try_parse(repaired)
        if parsed:
            if logger:
                logger.debug("parse_llm_json parsed via unbalanced repair")
            return parsed

    repaired = _repair_mismatched_closers(candidate)
    if repaired:
        repaired = _normalize_json_like(repaired)
        parsed = _try_parse(repaired)
        if parsed:
            if logger:
                logger.debug("parse_llm_json parsed via mismatched-closer repair")
            return parsed
    
    if _repair_json:
        repaired = _repair_json(candidate)
        if repaired:
            parsed = _try_parse(_normalize_json_like(repaired))
            if parsed:
                if logger:
                    logger.debug("parse_llm_json parsed via json_repair")
                return parsed

    if logger:
        logger.warning(f"无法解析 JSON 响应: {content[:200]}...")
    return {}
