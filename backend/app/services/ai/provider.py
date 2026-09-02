"""لایهٔ ۲ — آداپتور یک سرویسِ سازگار با OpenAI.

هیچ‌چیزِ این فایل دربارهٔ ارزیابی عملکرد نمی‌داند؛ فقط پیام می‌گیرد و متن
(یا خواستهٔ فراخوانیِ ابزار) برمی‌گرداند.

قاعدهٔ این فایل: *هیچ* ورودی نباید از این‌جا استثنای پیش‌بینی‌نشده بیرون بدهد.
هر چه از این‌جا بالا می‌رود یا `AiUnavailable` است یا `AiRequestFailed` — چون
تنها لایهٔ بالاتر همان دو را می‌گیرد و هر چیز دیگری به ۵۰۰ و «به پشتیبانی اعلام
کنید» تبدیل می‌شود. دو راهِ فرار قبلاً باز بود و هر دو با ورودیِ کاملاً
معمولی می‌شکستند؛ توضیحشان سرِ جای خودشان.
"""
import json
import re
import unicodedata

import httpx

from app.services.ai.port import (
    AiRequestFailed,
    AiUnavailable,
    ChatMessage,
    ChatResponse,
    ToolCall,
    ToolProtocolUnsupported,
)


class OpenAiCompatibleAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 60,
        temperature: float = 0.3,
        max_tokens: int = 1200,
    ) -> None:
        self._base_url = (base_url or "").strip().rstrip("/")
        self._api_key = clean_secret(api_key)
        self._model = clean_secret(model)
        self._timeout = max(5, timeout_seconds)
        self._temperature = temperature
        self._max_tokens = max_tokens

    @property
    def available(self) -> bool:
        return bool(self._base_url and self._api_key and self._model)

    async def send(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> ChatResponse:
        if not self.available:
            raise AiUnavailable("دستیار هوشمند هنوز پیکربندی نشده است")

        # سرِ *ورودی* گرفته می‌شود و نه با try دورِ درخواست: خطای httpx در این
        # حالت `UnicodeEncodeError` است با متنی دربارهٔ «ascii codec» و شمارهٔ
        # بایت — چیزی که به کاربر نمی‌شود گفت. این‌جا می‌شود گفت *کدام* فیلد
        # مشکل دارد.
        for label, value in (("کلید API", self._api_key), ("نام مدل", self._model)):
            bad = _non_ascii(value)
            if bad:
                raise AiRequestFailed(
                    f"{label} نویسهٔ غیرانگلیسی دارد ({bad}) و سرویس‌ها فقط نویسهٔ انگلیسی "
                    "می‌پذیرند. معمولاً یعنی هنگام کپی‌کردن، نویسه‌ای از متنِ اطرافش هم "
                    "آمده؛ آن را دستی و بی‌فاصله دوباره وارد کنید."
                )

        payload: dict = {
            "model": self._model,
            "messages": [m.to_wire() for m in messages],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        if tools:
            payload["tools"] = tools
            # «الان حرف بزن، ابزار نزن» با «ابزاری وجود ندارد» یکی نیست. راهِ
            # اولی همین است و نه *حذفِ* شِما: گفت‌وگویی که پیام‌های `tool` در
            # خود دارد، بی `tools` از سوی چند سرویس (از جمله درگاه‌های سازگارِ
            # Anthropic و Gemini) با ۴۰۰ رد می‌شود — یعنی پلهٔ آخرِ حلقه، همان
            # پله‌ای که باید جمع‌بندی کند، خطا می‌داد.
            if tool_choice:
                payload["tool_choice"] = tool_choice

        url = f"{self._base_url}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.TimeoutException:
            # بدون این پیام، درخواستِ گیرکرده از مدلِ کُند قابل تشخیص نیست.
            raise AiRequestFailed(
                f"سرویس در {self._timeout} ثانیه پاسخ نداد. آدرس سرویس یا اتصال شبکه را بررسی کنید."
            ) from None
        except httpx.InvalidURL as err:
            # `InvalidURL` زیرمجموعهٔ `HTTPError` *نیست* (مستقیم از Exception
            # می‌آید)، پس تا امروز از همین‌جا فرار می‌کرد و به ۵۰۰ می‌رسید —
            # با یک آدرسِ کاملاً معمولیِ اشتباه، مثل پورتی که عدد نیست.
            raise AiRequestFailed(
                f"آدرس سرویس معتبر نیست: {err} — آدرس باید مثل "
                "https://api.openai.com/v1 باشد."
            ) from None
        except httpx.HTTPError as err:
            # متنِ خودِ کتابخانه می‌ماند: «نام میزبان پیدا نشد» و «اتصال رد شد»
            # دو رفعِ متفاوت‌اند.
            raise AiRequestFailed(f"اتصال به سرویس ممکن نشد: {err}") from None

        if response.status_code >= 400:
            text = _error_text(response)
            # برخی سرویس‌ها (و نسخه‌های قدیمیِ خودمیزبان) شِمای tools را
            # نمی‌شناسند. این خطا «سرویس خراب» نیست؛ «پروتکل را عوض کن» است.
            lowered = text.lower()
            if tools and response.status_code in (400, 404, 422) and any(
                needle in lowered
                for needle in ("tool", "function", "unrecognized", "unknown", "invalid type", "extra fields")
            ):
                raise ToolProtocolUnsupported(text, response.status_code)
            raise AiRequestFailed(text, response.status_code)

        try:
            body = response.json()
            choice = body["choices"][0]
            message = choice["message"]
            content = message.get("content") or ""
            raw_calls = message.get("tool_calls") or []
            finish_reason = str(choice.get("finish_reason") or "")
        except (ValueError, KeyError, IndexError, TypeError):
            raise AiRequestFailed(
                "پاسخ سرویس قابل خواندن نبود. معمولاً یعنی آدرس سرویس به یک نقطهٔ "
                f"پایانیِ سازگار با OpenAI اشاره نمی‌کند. پاسخ: {response.text[:200]}"
            ) from None

        calls: list[ToolCall] = []
        for raw in raw_calls:
            function = raw.get("function") or {}
            arguments = function.get("arguments")
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments or {}, ensure_ascii=False)
            calls.append(
                ToolCall(
                    id=str(raw.get("id") or f"call_{len(calls)}"),
                    name=str(function.get("name") or "").strip(),
                    arguments_json=arguments,
                )
            )

        return ChatResponse(
            content=content or "",
            tool_calls=tuple(calls),
            usage=body.get("usage") or {},
            truncated=finish_reason == "length",
        )


#: نویسه‌های *نامرئیِ* قالب‌بندی که با کپی‌کردن وارد می‌شوند و هیچ‌وقت بخشی از
#: یک کلید API نیستند: نشانه‌های جهتِ متن (در متن راست‌به‌چپ خیلی رایج)، فاصلهٔ
#: صفر، و علامتِ ترتیبِ بایت. حذفشان بی‌سروصدا درست است — چیزی از کلید کم
#: نمی‌کند و کاربر هم نمی‌تواند ببیندشان تا خودش پاکشان کند.
_INVISIBLE = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF, *range(0x202A, 0x202F)]
)


def clean_secret(value: str | None) -> str:
    """کلید و نام مدل، پاکیزه‌شده تا حدی که *بی‌خطر* است.

    فاصله‌های دو سرش و نویسه‌های نامرئی می‌روند، و فاصلهٔ بدونِ شکست به فاصلهٔ
    معمولی تبدیل می‌شود. نویسهٔ *دیدنیِ* غیرانگلیسی اما دست‌نخورده می‌ماند: پاک
    کردنش یعنی کلیدی به سرویس می‌رود که کاربر وارد نکرده، و پاسخِ ۴۰۱ او را
    دنبالِ اشکالی می‌فرستد که وجود ندارد. آن حالت در `send` صریح رد می‌شود.
    """
    if not value:
        return ""
    cleaned = unicodedata.normalize("NFKC", value.strip()).translate(_INVISIBLE)
    return cleaned.strip()


def _non_ascii(value: str) -> str:
    """نویسه‌های غیر-ASCII، به شکلی که در پیام خطا خوانده شود.

    خودِ نویسه‌ها را برمی‌گرداند و نه فقط «غیرانگلیسی دارد»: کاربری که یک «ی»
    فارسی وسط کلیدش جا مانده، باید بداند دنبالِ چه بگردد.
    """
    bad = sorted({ch for ch in value if ord(ch) > 127})
    return " ".join(f"«{ch}»" for ch in bad)


#: راهنمای کوتاه برای کدهایی که پیامِ خودِ سرویس معمولاً درباره‌شان ساکت است.
#: «Provider returned error» در پاسخِ ۴۲۹ چیزی به کاربر نمی‌گوید؛ این می‌گوید.
_STATUS_HINTS = {
    401: "کلید API پذیرفته نشد — منقضی یا اشتباه است.",
    403: "سرویس دسترسی را رد کرد. معمولاً یعنی کلید برای این مدل یا این کشور مجاز "
    "نیست، یا درخواست از مسیری رد شده که سرویس آن را مسدود می‌کند.",
    404: "این آدرس یا این نام مدل روی سرویس وجود ندارد.",
    413: "پیام برای این سرویس بزرگ بود.",
    429: "سهمیهٔ سرویس پر شده یا درخواست‌ها پشت سر هم بوده‌اند. کمی بعد دوباره "
    "امتحان کنید؛ اگر تکرار شد، اعتبار حساب و محدودیت نرخِ کلید را ببینید.",
    500: "خطا از سمتِ خودِ سرویس است، نه تنظیمات شما.",
    502: "خطا از سمتِ خودِ سرویس است، نه تنظیمات شما.",
    503: "سرویس موقتاً در دسترس نیست.",
    529: "سرویس زیر بار است. کمی بعد دوباره امتحان کنید.",
}

_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def _readable(text: str, limit: int = 180) -> str:
    """متنِ خطا، به شکلی که در یک نوار پیام جا شود.

    وقتی درخواست به *خودِ API* نمی‌رسد (مسیر اشتباه، دیوارِ میانی، صفحهٔ خطای
    ابر)، پاسخ یک صفحهٔ HTML است و نه JSON. ریختنِ ۳۰۰ نویسه از
    `<!DOCTYPE html>…` در رابط، هم چیزی نمی‌گوید و هم چیدمان را خراب می‌کند —
    پس عنوانِ صفحه بیرون کشیده می‌شود که تنها بخشِ معنادارِ آن است.
    """
    stripped = text.strip()
    if stripped[:400].lower().lstrip().startswith(("<!doctype", "<html")):
        title = re.search(r"<title[^>]*>(.*?)</title>", stripped, re.S | re.I)
        stripped = title.group(1) if title else _TAGS.sub(" ", stripped)
        stripped = f"پاسخ سرویس یک صفحهٔ وب بود و نه داده: {stripped}"
    stripped = _SPACES.sub(" ", _TAGS.sub(" ", stripped)).strip()
    return stripped[:limit] + ("…" if len(stripped) > limit else "")


def _error_text(response: httpx.Response) -> str:
    """جملهٔ خودِ سرویس، به‌علاوهٔ راهنمایی که خودش نمی‌دهد.

    نیمی از مشکلات راه‌اندازی «نام مدل اشتباه» است و تنها کسی که این را
    می‌داند خودِ سرویس است، پس متنِ او حذف نمی‌شود. ولی متنِ او هم گاهی
    «Provider returned error» است؛ آن‌جا کدِ وضعیت تنها چیزی است که معنا دارد و
    ترجمه‌اش کارِ ماست.
    """
    code = response.status_code
    message = ""
    try:
        body = response.json()
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                message = error.get("message") or ""
            elif isinstance(error, str):
                message = error
            message = message or body.get("message") or body.get("detail") or ""
    except ValueError:
        pass

    message = _readable(str(message) if message else response.text)
    hint = _STATUS_HINTS.get(code, "")
    parts = [f"{code}: {message or 'بدون توضیح'}"]
    # راهنما *بعد* از حرفِ سرویس می‌آید و جایش را نمی‌گیرد؛ و وقتی خودِ سرویس
    # همان را گفته باشد، تکرار نمی‌شود.
    if hint and hint[:20] not in parts[0]:
        parts.append(hint)
    return " — ".join(parts)
