"""آداپتورهای قلابی برای آزمودنِ حلقهٔ گفت‌وگو بدون هیچ درخواستی به بیرون.

دو خانواده:
* `ScriptedAdapter` — سرویسی که فراخوانیِ بومیِ ابزار دارد؛ سناریو پله‌پله
  از فهرست مصرف می‌شود.
* `NoToolsAdapter` — سرویسی که شِمای tools را نمی‌شناسد؛ خطای
  ToolProtocolUnsupported می‌دهد تا مسیرِ پروتکلِ جایگزین برود.
"""
from __future__ import annotations

import json

from app.services.ai.port import AiRequestFailed, ChatResponse, ToolCall, ToolProtocolUnsupported


def tool_call(call_id: str, name: str, arguments: dict) -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments_json=json.dumps(arguments, ensure_ascii=False))


def response(
    content: str = "", calls: list[ToolCall] | None = None, truncated: bool = False
) -> ChatResponse:
    return ChatResponse(
        content=content, tool_calls=tuple(calls or []), truncated=truncated
    )


def broken_call(call_id: str, name: str, arguments_json: str) -> ToolCall:
    """خواستهٔ ابزاری که آرگومان‌هایش JSONِ معتبر نیست — شکلِ پاسخِ بریده‌شده."""
    return ToolCall(id=call_id, name=name, arguments_json=arguments_json)


class ScriptedAdapter:
    """پاسخ‌ها به ترتیب سناریو. پایانِ سناریو = تکرارِ آخرین پاسخ.

    نکته: حلقهٔ گفت‌وگو در هر پله یک آداپتور *تازه* می‌سازد (همان کاری که با
    آداپتور واقعی می‌کند)، پس نشانگرِ سناریو باید در سطح کلاس بماند.
    """

    seen: list[list] = []
    #: `tools` و `tool_choice`ِ هر فراخوانی، هم‌ترتیب با `seen`. حلقه در پلهٔ
    #: آخر باید *شِما را نگه دارد* و فقط `tool_choice="none"` بدهد؛ بی این
    #: ثبت، آن قاعده از بیرون قابل سنجش نبود.
    wire: list[dict] = []
    script: list[ChatResponse] = []
    _cursor: int = 0

    def __init__(self, **_kwargs) -> None:
        pass

    @classmethod
    def _next(cls) -> ChatResponse:
        if cls._cursor < len(cls.script):
            item = cls.script[cls._cursor]
            cls._cursor += 1
            return item
        return cls.script[-1]

    @property
    def available(self) -> bool:
        return True

    async def send(self, messages, *, tools=None, tool_choice=None) -> ChatResponse:
        ScriptedAdapter.seen.append(list(messages))
        ScriptedAdapter.wire.append({"tools": tools, "tool_choice": tool_choice})
        return type(self)._next()


class NoToolsAdapter(ScriptedAdapter):
    """سرویسی که با tools در بدنه ۴xx می‌دهد؛ حلقه باید به JSON برود."""

    async def send(self, messages, *, tools=None, tool_choice=None) -> ChatResponse:
        if tools:
            raise ToolProtocolUnsupported("400: tools is not supported", 400)
        return await super().send(messages, tools=tools)


class FailingAdapter(ScriptedAdapter):
    async def send(self, messages, *, tools=None, tool_choice=None) -> ChatResponse:
        raise AiRequestFailed("401: Incorrect API key provided: sk-***", 401)


def reset(adapter_cls) -> None:
    ScriptedAdapter.seen = []
    ScriptedAdapter.wire = []
    ScriptedAdapter._cursor = 0
    adapter_cls.script = []
