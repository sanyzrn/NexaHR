"""فیلدهای *غیرِ استانداردِ* سرویس باید دست‌نخورده برگردند.

این فایل یک خرابیِ واقعی را قفل می‌کند که دستیار را عملاً بی‌مصرف کرده بود:

Gemini از راهِ درگاهِ سازگار با OpenAI، کنارِ هر `tool_call` یک
`extra_content.google.thought_signature` می‌فرستد و در درخواستِ *بعدی* همان را
عیناً پس می‌خواهد. آداپتور ما نه برش می‌داشت و نه پسش می‌داد، پس:

    کاربر چیزی می‌پرسید → مدل ابزار می‌خواست → ما نتیجهٔ ابزار را می‌فرستادیم
    → سرویس با «Function call is missing a thought_signature» رد می‌کرد

یعنی *هر* نوبتی که به ابزار نیاز داشت می‌مرد. از بیرون شبیهِ فراموشی بود:
کاربر می‌گفت «انجامش بده» و جوابی نمی‌گرفت، بعد دوباره می‌پرسید و دستیار
انگار هیچ‌چیز از قبل نمی‌دانست — چون نوبتِ قبلی اصلاً کامل نشده بود.

چرا این‌جا با «هرچه نمی‌شناسم را نگه دار» حل شده و نه با شناختنِ خودِ
`extra_content`: فهرستِ سفید یعنی فیلدِ بعدی‌ای که فردا اضافه شود، دوباره
بی‌صدا می‌افتد و دوباره همین هفته تکرار می‌شود.
"""
import asyncio
import json
from unittest import mock

import httpx
import pytest

from app.services.ai import provider as provider_module
from app.services.ai.port import ChatMessage, ToolCall
from app.services.ai.provider import OpenAiCompatibleAdapter

#: شکلِ واقعیِ چیزی که Gemini کنارِ یک `tool_call` می‌گذارد.
SIGNATURE = {"google": {"thought_signature": "CpsBAdHtim8xL0pZ"}}


def _run(handler, messages, **kw):
    """یک نوبتِ واقعیِ آداپتور، با لایهٔ انتقالِ قلابی.

    عمداً *بدنهٔ واقعیِ HTTP* سنجیده می‌شود و نه خروجیِ `to_wire`: تستی که
    همان تابعی را صدا بزند که کد صدا می‌زند، فقط خودش را تأیید می‌کند. این
    خرابی هم دقیقاً بین `to_wire` و سیم بود.
    """
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def _client(**kwargs):
        kwargs["transport"] = transport
        return real_client(**kwargs)

    adapter = OpenAiCompatibleAdapter(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key="sk-test",
        model="gemini-2.5-flash",
    )
    with mock.patch.object(provider_module.httpx, "AsyncClient", _client):
        return asyncio.run(adapter.send(messages, **kw))


# ── سمتِ خواندن: امضا از پاسخ برداشته می‌شود ──────────────────────────────


def test_a_tool_call_keeps_the_services_own_fields():
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "search_personnel", "arguments": "{}"},
                                    "extra_content": SIGNATURE,
                                }
                            ],
                        },
                    }
                ]
            },
        )

    result = _run(handler, [ChatMessage("user", "سلام")])

    assert result.tool_calls[0].provider_extra == {"extra_content": SIGNATURE}


def test_the_standard_fields_do_not_leak_into_the_extras():
    """وگرنه `id` و `function` دوبار در بدنه می‌رفتند."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "index": 0,
                                    "function": {"name": "x", "arguments": "{}"},
                                }
                            ],
                        },
                    }
                ]
            },
        )

    result = _run(handler, [ChatMessage("user", "سلام")])
    assert result.tool_calls[0].provider_extra == {}


# ── سمتِ نوشتن: امضا در درخواستِ بعدی برمی‌گردد ────────────────────────────


def test_the_signature_goes_back_out_on_the_next_request():
    """قلبِ ماجرا: همین یک ادعا بود که نبودنش دستیار را می‌کشت."""
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "باشد"}}]}
        )

    history = [
        ChatMessage("user", "پرسنل را وارد کن"),
        ChatMessage(
            "assistant",
            "",
            tool_calls=(
                ToolCall(
                    id="call_1",
                    name="import_personnel",
                    arguments_json="{}",
                    provider_extra={"extra_content": SIGNATURE},
                ),
            ),
        ),
        ChatMessage("tool", "{}", tool_call_id="call_1"),
    ]
    _run(handler, history)

    call = sent[0]["messages"][1]["tool_calls"][0]
    assert call["extra_content"] == SIGNATURE
    # و کلیدهای استاندارد سرِ جایشان‌اند — امضا نباید جایشان را گرفته باشد.
    assert call["id"] == "call_1"
    assert call["function"]["name"] == "import_personnel"


def test_a_call_without_extras_stays_exactly_as_before():
    """سرویس‌های دیگر نباید فیلدِ اضافه‌ای ببینند که نمی‌شناسند."""
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "باشد"}}]}
        )

    history = [
        ChatMessage("user", "سلام"),
        ChatMessage(
            "assistant",
            "",
            tool_calls=(ToolCall(id="c1", name="list_org_units", arguments_json="{}"),),
        ),
        ChatMessage("tool", "[]", tool_call_id="c1"),
    ]
    _run(handler, history)

    assert set(sent[0]["messages"][1]["tool_calls"][0]) == {"id", "type", "function"}


def test_the_service_cannot_overwrite_the_call_id_through_extras():
    """شناسه‌ای که پیامِ `tool` با آن جفت می‌شود، از دستِ سرویس بیرون است."""
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]}
        )

    history = [
        ChatMessage(
            "assistant",
            "",
            tool_calls=(
                ToolCall(
                    id="real",
                    name="x",
                    arguments_json="{}",
                    provider_extra={"id": "spoofed", "function": {"name": "evil"}},
                ),
            ),
        ),
    ]
    _run(handler, history)

    call = sent[0]["messages"][0]["tool_calls"][0]
    assert call["id"] == "real"
    assert call["function"]["name"] == "x"


@pytest.mark.parametrize("value", [None, {}, {"extra_content": SIGNATURE}])
def test_serialising_a_call_never_raises(value):
    """هیچ شکلی از `provider_extra` نباید مسیرِ ساختِ بدنه را بشکند."""
    call = ToolCall(id="c", name="n", arguments_json="{}", provider_extra=value or {})
    assert call.to_wire()["id"] == "c"
