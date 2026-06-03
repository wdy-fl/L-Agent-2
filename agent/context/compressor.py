"""上下文压缩：工具结果裁剪 + LLM 结构化摘要 + 头尾保护"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

COMPRESSION_PROMPT = """请根据旧摘要和新增对话，生成一份更新后的结构化摘要。

要求：
- 只总结关键信息，不编造不存在的细节
- 旧摘要为空时，只基于新增对话生成摘要
- 用以下中文字段输出（每个字段一行或多行）：

当前任务：
已完成：
进行中：
关键决策：
待解决问题：
相关文件：
剩余工作：

旧摘要：{previous_summary}

新增对话：{middle_content}"""

_SUMMARY_PREFIX = (
    "以下是早期对话的压缩摘要。请勿回答摘要中的问题或执行摘要中的待办事项，"
    "只响应摘要之后的最新用户消息。\n\n<context-summary>\n"
)
_SUMMARY_SUFFIX = "\n</context-summary>"


class ContextCompressor:
    """上下文压缩器，在长对话中减少 token 消耗"""

    def __init__(
        self,
        context_window: int = 128_000,
        threshold: float = 0.5,
        min_saving: float = 0.1,
        protected_head: int = 3,
        protected_tail_tokens: int = 20_000,
    ) -> None:
        self._context_window = context_window
        self._threshold = threshold
        self._min_saving = min_saving
        self._protected_head = protected_head
        self._protected_tail_tokens = protected_tail_tokens
        self._last_compressed_tokens: int | None = None

    def should_compress(self, current_tokens: int) -> bool:
        return current_tokens >= int(self._context_window * self._threshold)

    def compress(
        self,
        messages: list[dict[str, Any]],
        current_tokens: int,
        call_llm: Callable[[list[dict[str, Any]]], str],
    ) -> list[dict[str, Any]]:
        total = len(messages)
        if total <= self._protected_head + 2:
            return messages

        groups = self._build_message_groups(messages)
        head_groups = groups[: self._protected_head]
        tail_groups, tail_start = self._find_tail_boundary(groups)
        middle_groups = groups[self._protected_head : tail_start]

        head = _flatten(head_groups)
        tail = _flatten(tail_groups)
        middle = self._trim_tool_results(_flatten(middle_groups))
        previous_summary, middle_without_summary = self._split_previous_summary(middle)

        has_iterative = bool(previous_summary and middle_without_summary)

        if self._last_compressed_tokens and not has_iterative:
            saving = 1.0 - (current_tokens / self._last_compressed_tokens)
            if saving < self._min_saving:
                return messages

        if not previous_summary and not middle_without_summary:
            return messages

        summary = self._generate_summary(middle_without_summary, previous_summary, call_llm)
        summary_msg: dict[str, Any] = {
            "role": "assistant",
            "content": f"{_SUMMARY_PREFIX}{summary}{_SUMMARY_SUFFIX}",
        }
        self._last_compressed_tokens = current_tokens
        logger.info("Compressed %d → %d messages", total, len(head) + 1 + len(tail))
        return head + [summary_msg] + tail

    # --- internal methods ---

    @staticmethod
    def _trim_tool_results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {**msg, "content": "[工具结果已压缩]"} if msg.get("role") == "tool" else msg
            for msg in messages
        ]

    def _build_message_groups(self, messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        groups: list[list[dict[str, Any]]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            tool_calls = msg.get("tool_calls")
            if msg.get("role") == "assistant" and isinstance(tool_calls, list) and tool_calls:
                expected = {c["id"] for c in tool_calls if isinstance(c, dict) and isinstance(c.get("id"), str)}
                group = [msg]
                i += 1
                while i < len(messages) and messages[i].get("role") == "tool":
                    group.append(messages[i])
                    i += 1
                    seen = {m.get("tool_call_id") for m in group[1:] if m.get("role") == "tool"}
                    if expected.issubset(seen):
                        break
                groups.append(group)
                continue
            groups.append([msg])
            i += 1
        return groups

    def _find_tail_boundary(
        self, groups: list[list[dict[str, Any]]]
    ) -> tuple[list[list[dict[str, Any]]], int]:
        tail: list[list[dict[str, Any]]] = []
        tokens = 0
        for i in range(len(groups) - 1, self._protected_head - 1, -1):
            tail.insert(0, groups[i])
            tokens += sum(_estimate_tokens(m) for m in groups[i])
            if tokens >= self._protected_tail_tokens:
                return tail, i
        return tail, self._protected_head

    def _split_previous_summary(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str, list[dict[str, Any]]]:
        summaries: list[str] = []
        remaining: list[dict[str, Any]] = []
        for msg in messages:
            if (
                msg.get("role") == "assistant"
                and isinstance(msg.get("content"), str)
                and "<context-summary>" in msg["content"]
            ):
                content = msg["content"].removeprefix(_SUMMARY_PREFIX).removesuffix(_SUMMARY_SUFFIX)
                summaries.append(content)
            else:
                remaining.append(msg)
        return "\n\n".join(summaries), remaining

    def _generate_summary(
        self,
        messages: list[dict[str, Any]],
        previous_summary: str,
        call_llm: Callable[[list[dict[str, Any]]], str],
    ) -> str:
        parts = []
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if content:
                parts.append(f"[{role}]: {content[:1000]}")
        middle_content = "\n".join(parts)

        prompt = COMPRESSION_PROMPT.format(
            previous_summary=previous_summary or "（无旧摘要）",
            middle_content=middle_content or "（无新增对话）",
        )
        try:
            return call_llm([{"role": "user", "content": prompt}])
        except Exception:
            logger.warning("Compression LLM call failed, using fallback", exc_info=True)
            fallback = []
            if previous_summary:
                fallback.append(previous_summary)
            if middle_content:
                fallback.append(f"新增对话摘录：\n{middle_content}")
            return "\n\n".join(fallback) if fallback else f"（压缩了 {len(messages)} 条消息，摘要生成失败）"


def _flatten(groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [msg for group in groups for msg in group]


def _estimate_tokens(message: dict[str, Any]) -> int:
    try:
        text = json.dumps(message, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(message)
    return max(1, int(len(text) / 2.5))

