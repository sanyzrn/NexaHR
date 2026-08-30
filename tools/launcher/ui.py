"""پنجرهٔ راه‌انداز.

چرا انگلیسی است
----------------
بقیهٔ محصول فارسی و RTL است، ولی این پنجره نه — و این یک تصمیم است، نه غفلت.
Tk 8.6 (همانی که با پایتون روی ویندوز می‌آید) نه bidi دارد و نه شکل‌دهیِ حروفِ
عربی؛ متنِ فارسی داخلش به‌صورتِ حروفِ جدا و در جهتِ برعکس دیده می‌شود. یک
راه‌اندازِ ناخوانا از یک راه‌اندازِ انگلیسی بدتر است. فایلِ `setup_and_run.bat`
هم از اول انگلیسی بوده، پس چیزی هم عوض نمی‌شود.

اگر روزی Tk 9 پیش‌فرض شد، فقط همین فایل باید ترجمه شود.

چرا همه‌چیز با ویجت‌های کلاسیکِ `tk` ساخته شده و نه `ttk`
--------------------------------------------------------
`ttk` روی ویندوز تمِ بومی را می‌کشد و `background` را در بیشتر ویجت‌ها نادیده
می‌گیرد؛ نتیجه‌اش پنجره‌ای می‌شد نصفه‌تیره نصفه‌خاکستریِ سیستم. ویجت‌های کلاسیک
زشت‌ترند اگر رهایشان کنی، ولی رنگ را دقیقاً همان‌طور که گفته شود می‌گیرند.

نخِ کاری هیچ‌وقت به Tk دست نمی‌زند
----------------------------------
Tk تک‌نخی است و صدا زدنش از نخِ دیگر، خرابیِ تصادفی می‌دهد. کلِ ارتباطِ
`Session` با پنجره از یک صف رد می‌شود که خودِ نخِ رابط هر ۸۰ میلی‌ثانیه خالی‌اش
می‌کند.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from tkinter import font as tkfont

from .session import Session
from .steps import Outcome, Step
from .supervisor import Server

# ── پالت ────────────────────────────────────────────────────────────────
# همان تمِ «شب»ِ خودِ برنامه (سرمه‌ای، نه مشکی) تا راه‌انداز عضوِ همان محصول
# به‌نظر برسد و نه یک ابزارِ چسبانده‌شده.
BG = "#0b0e17"        # زمینهٔ پنجره
CARD = "#1b2031"      # کارت
LINE = "#313852"      # مرز
TEXT = "#c8cde0"      # متنِ اصلی
HEAD = "#eef0f8"      # عنوان
MUTED = "#858ca6"     # متنِ کم‌رنگ
BRAND = "#db1a18"     # قرمزِ برند
GREEN = "#34d399"
AMBER = "#fbbf24"
RED = "#f87171"
BLUE = "#7aa2f7"

# عرضِ ثابت است چون `wraplength` های داخلِ کارت‌ها به آن گره خورده‌اند؛ ارتفاع
# با محتوا عوض می‌شود (‏`_fit`).
WIDTH = 620


def _first_installed(candidates: tuple[str, ...], fallback: str) -> str:
    families = set(tkfont.families())
    return next((name for name in candidates if name in families), fallback)


def _fonts() -> dict[str, tuple]:
    # فونت‌ها به ترتیبِ ترجیح، با پایانِ مطمئن. اسمِ فونتِ نصب‌نشده در Tk خطا
    # نمی‌دهد؛ بی‌صدا به یک فونتِ پیش‌فرضِ زشت می‌افتد.
    ui = _first_installed(("Segoe UI", "Inter", "DejaVu Sans", "Helvetica"), "TkDefaultFont")
    mono = _first_installed(("Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Courier"), "TkFixedFont")
    return {
        "title": (ui, 15, "bold"),
        "body": (ui, 10),
        "small": (ui, 9),
        "strong": (ui, 10, "bold"),
        "mono": (mono, 9),
    }


class Dot(tk.Canvas):
    """چراغِ وضعیت. دایرهٔ کشیده‌شده و نه کاراکترِ «●»، چون آن یکی در هر فونتی
    اندازهٔ دیگری دارد و ردیفِ وضعیت را ناهم‌تراز می‌کند."""

    def __init__(self, parent: tk.Misc, size: int = 10, bg: str = CARD) -> None:
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
        pad = 1
        self._oval = self.create_oval(pad, pad, size - pad, size - pad, fill=MUTED, outline="")

    def set(self, color: str) -> None:
        self.itemconfigure(self._oval, fill=color)


def pill(parent: tk.Misc, text: str, command: Callable[[], None], *, primary: bool = False) -> tk.Button:
    """دکمه‌ای که روی ویندوز و لینوکس یک شکل دیده می‌شود.

    رنگ روی خودِ دکمه نگه داشته می‌شود (نه در یک تمِ سراسری) چون همین دکمه باید
    بتواند بین حالتِ خاموش و اصلی جابه‌جا شود: «Open NexaHR» تا وقتی سرورها
    جواب نداده‌اند نباید مثل یک دکمهٔ آماده به‌نظر برسد.
    """
    button = tk.Button(
        parent, text=text, command=command, font=_FONTS["body"],
        activeforeground="#ffffff", relief="flat", bd=0, highlightthickness=0,
        padx=14, pady=7, cursor="hand2", disabledforeground=MUTED,
    )

    def restyle(is_primary: bool) -> None:
        base = BRAND if is_primary else CARD
        hover = "#b61615" if is_primary else "#262c40"
        button.configure(bg=base, fg="#ffffff" if is_primary else TEXT, activebackground=hover)
        button.bind("<Enter>", lambda _e: button.configure(bg=hover) if str(button["state"]) != "disabled" else None)
        button.bind("<Leave>", lambda _e: button.configure(bg=base))

    restyle(primary)
    button.restyle = restyle  # type: ignore[attr-defined]
    return button


class LauncherWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        global _FONTS
        _FONTS = _fonts()

        self.title("NexaHR")
        self.configure(bg=BG)
        self.minsize(WIDTH, 200)

        self._events: queue.Queue[tuple] = queue.Queue()
        self._session: Session | None = None
        self._worker: threading.Thread | None = None
        self._chips: dict[str, tuple[Dot, tk.Label]] = {}
        self._log_visible = tk.BooleanVar(value=False)
        self._opened_browser = False

        self._build()
        self._fit()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(80, self._drain)
        self.start()

    def _fit(self) -> None:
        """پنجره به اندازهٔ محتوایش.

        ارتفاعِ ثابت یعنی وقتی گزارش بسته است یک ناحیهٔ خالیِ بزرگ می‌ماند، و
        وقتی کارتِ خطا باز می‌شود متن بریده می‌شود. هر دو حالت با یک قاعده حل
        می‌شوند: هر بار که محتوا عوض شد، ارتفاع دوباره حساب شود. عرض ثابت
        می‌ماند تا `wraplength` ها معنا داشته باشند.
        """
        self.update_idletasks()
        self.geometry(f"{WIDTH}x{max(self.winfo_reqheight(), 200)}")

    # ── ساختِ پنجره ──────────────────────────────────────────────────────

    def _build(self) -> None:
        self._header()
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=16)
        self._status_card(body)
        self._steps_card(body)
        # ظرفِ خالیِ اطلاعیه همین حالا در جای خودش بسته می‌شود. اگر به‌جایش کارت
        # را موقعِ نیاز می‌ساختیم، `pack(before=...)` وقتی گزارش بسته است شکست
        # می‌خورد — چون آن ویجت اصلاً packed نیست.
        self._notice = NoticeCard(body)
        self._log_card(body)
        self._footer()

    def _header(self) -> None:
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=16, pady=(14, 10))

        mark = tk.Canvas(bar, width=30, height=30, bg=BG, highlightthickness=0, bd=0)
        mark.create_rectangle(0, 0, 30, 30, fill=BRAND, outline="")
        mark.create_text(15, 15, text="N", fill="#ffffff", font=(_FONTS["title"][0], 14, "bold"))
        mark.pack(side="left")

        titles = tk.Frame(bar, bg=BG)
        titles.pack(side="left", padx=10)
        tk.Label(titles, text="NexaHR", bg=BG, fg=HEAD, font=_FONTS["title"]).pack(anchor="w")
        tk.Label(titles, text="local development", bg=BG, fg=MUTED, font=_FONTS["small"]).pack(anchor="w")

        self._phase_dot = Dot(bar, size=9, bg=BG)
        self._phase_dot.pack(side="right", padx=(6, 0))
        self._phase = tk.Label(bar, text="starting…", bg=BG, fg=MUTED, font=_FONTS["small"])
        self._phase.pack(side="right")

    def _status_card(self, parent: tk.Misc) -> None:
        card = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="x", pady=(0, 10))
        self._links = tk.Frame(card, bg=CARD)
        self._links.pack(fill="x", padx=14, pady=12)
        self._link_rows: list[tk.Frame] = []
        self._placeholder = tk.Label(
            self._links, text="Addresses appear once both servers answer.",
            bg=CARD, fg=MUTED, font=_FONTS["small"], anchor="w",
        )
        self._placeholder.pack(fill="x")

    def _steps_card(self, parent: tk.Misc) -> None:
        from .steps import PIPELINE

        card = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="x", pady=(0, 10))
        grid = tk.Frame(card, bg=CARD)
        grid.pack(fill="x", padx=14, pady=12)
        for index, step in enumerate(PIPELINE):
            row, column = divmod(index, 2)
            cell = tk.Frame(grid, bg=CARD)
            cell.grid(row=row, column=column, sticky="w", padx=(0, 18), pady=2)
            dot = Dot(cell, size=8)
            dot.pack(side="left", pady=(1, 0))
            label = tk.Label(cell, text=step.title, bg=CARD, fg=MUTED, font=_FONTS["small"], anchor="w")
            label.pack(side="left", padx=(7, 0))
            self._chips[step.key] = (dot, label)
        grid.columnconfigure(0, weight=1, uniform="steps")
        grid.columnconfigure(1, weight=1, uniform="steps")

    def _log_card(self, parent: tk.Misc) -> None:
        self._log_frame = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        wrap = tk.Frame(self._log_frame, bg=CARD)
        wrap.pack(fill="both", expand=True, padx=1, pady=1)

        self._text = tk.Text(
            wrap, bg=CARD, fg=TEXT, font=_FONTS["mono"], relief="flat", bd=0,
            highlightthickness=0, wrap="word", padx=12, pady=10, state="disabled",
            insertbackground=TEXT, selectbackground="#3f4763", height=14,
        )
        scroll = tk.Scrollbar(wrap, command=self._text.yview, width=10,
                              bg=CARD, troughcolor=CARD, activebackground=LINE, bd=0, relief="flat")
        self._text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._text.pack(side="left", fill="both", expand=True)

        for name, color in (("setup", MUTED), ("backend", BLUE), ("frontend", GREEN), ("launcher", HEAD)):
            # `lmargin2` ادامهٔ خطِ شکسته را زیرِ خودِ متن نگه می‌دارد و نه زیرِ
            # ستونِ نام. بدونش، خطوطِ بلندِ یووی‌کورن ستون‌بندی را به هم می‌ریزند
            # و پیدا کردنِ این‌که کدام خط از کدام سرور است سخت می‌شود.
            self._text.tag_configure(name, foreground=color, lmargin2=84)
        self._text.tag_configure("prefix", foreground=MUTED)

    def _footer(self) -> None:
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=16, pady=(6, 14))

        self._toggle = pill(bar, "Show log", self._toggle_log)
        self._toggle.pack(side="left")
        # «کپیِ گزارش» هست چون وقتی چیزی می‌شکند، اولین کاری که کاربر می‌کند
        # فرستادنِ همین متن است — و انتخاب‌کردنش با ماوس از داخلِ یک Text
        # اسکرول‌شونده کارِ خوشایندی نیست.
        self._copy_log_button = pill(bar, "Copy log", self._copy_log)
        self._copy_log_button.pack(side="left", padx=6)

        self._stop_button = pill(bar, "Stop", self._on_close)
        self._stop_button.pack(side="right")
        # تا وقتی هر دو سرور جواب نداده‌اند، این دکمه نه کار می‌کند و نه شبیهِ
        # دکمهٔ اصلی است. قاعدهٔ «روی پشتهٔ خراب مرورگر باز نکن»، این‌بار در
        # ظاهرِ دکمه.
        self._open_button = pill(bar, "Open NexaHR", self._open_browser)
        self._open_button.pack(side="right", padx=6)
        self._open_button.configure(state="disabled")

    # ── چرخهٔ اجرا ───────────────────────────────────────────────────────

    def start(self) -> None:
        self._session = Session(
            log=lambda source, line: self._events.put(("log", source, line)),
            ask_password=self._ask_password,
            on_step=lambda step, outcome: self._events.put(("step", step, outcome)),
            on_crash=lambda server: self._events.put(("crash", server)),
        )
        self._session.stop_on_exit()
        self._worker = threading.Thread(target=self._work, name="launcher", daemon=True)
        self._worker.start()

    def _work(self) -> None:
        session = self._session
        assert session
        if session.prepare() and session.serve():
            self._events.put(("ready",))
        else:
            self._events.put(("failed", session.failure))

    # ── صف رویدادها ─────────────────────────────────────────────────────

    def _drain(self) -> None:
        try:
            while True:
                event = self._events.get_nowait()
                self._handle(event)
        except queue.Empty:
            pass
        self.after(80, self._drain)

    def _handle(self, event: tuple) -> None:
        kind = event[0]
        if kind == "log":
            self._append(event[1], event[2])
        elif kind == "step":
            self._update_step(event[1], event[2])
        elif kind == "ready":
            self._on_ready()
        elif kind == "failed":
            self._on_failed(event[1])
        elif kind == "crash":
            self._on_crash(event[1])

    def _notify(self, *args, **kwargs) -> None:
        """اطلاعیه را نشان بده و پنجره را به اندازهٔ متنِ تازه‌اش برسان."""
        self._notice.show(*args, **kwargs)
        self._fit()

    def _update_step(self, step: Step, outcome: Outcome | None) -> None:
        dot, label = self._chips[step.key]
        if outcome is None:
            dot.set(AMBER)
            label.configure(fg=TEXT)
            self._phase.configure(text=f"{step.title.lower()}…")
            self._phase_dot.set(AMBER)
            return
        dot.set(GREEN if outcome.ok else RED)
        label.configure(fg=TEXT if outcome.ok else RED)
        if outcome.summary:
            self._append("setup", f"{step.title}: {outcome.summary}")

    def _on_ready(self) -> None:
        session = self._session
        assert session
        self._phase.configure(text="running", fg=GREEN)
        self._phase_dot.set(GREEN)
        self._show_links(session.links.all)
        self._open_button.configure(state="normal")
        self._open_button.restyle(True)
        if session.ctx.notes:
            self._notify("Worth knowing", "\n".join(session.ctx.notes), session.ctx.advice, tone=AMBER)
        if not self._opened_browser:
            self._opened_browser = True
            self._open_browser()

    def _on_failed(self, outcome: Outcome | None) -> None:
        self._phase.configure(text="stopped", fg=RED)
        self._phase_dot.set(RED)
        remedy = outcome.remedy if outcome else None
        summary = outcome.summary if outcome else "setup did not finish"
        self._notify(
            remedy.title if remedy else "NexaHR could not start",
            (remedy.body if remedy else "") or summary,
            (remedy.commands if remedy else []),
            tone=RED,
            url=remedy.url if remedy else "",
        )
        # گزارش خودش باز می‌شود: وقتی چیزی شکسته، جوابْ تقریباً همیشه چند خطِ
        # آخرِ همان گزارش است، و یک کلیکِ اضافه بینِ کاربر و آن جواب فاصله است.
        if not self._log_visible.get():
            self._toggle_log()
        self._stop_button.configure(text="Close")

    def _on_crash(self, server: Server) -> None:
        self._phase.configure(text=f"{server.spec.name} stopped", fg=RED)
        self._phase_dot.set(RED)
        self._notify(
            f"The {server.spec.name} stopped",
            "It was running and then exited. Last output:\n\n" + "\n".join(server.tail[-10:]),
            [],
            tone=RED,
        )

    # ── لینک‌ها ─────────────────────────────────────────────────────────

    def _show_links(self, pairs: list[tuple[str, str]]) -> None:
        self._placeholder.pack_forget()
        for row in self._link_rows:
            row.destroy()
        self._link_rows.clear()

        for label, url in pairs:
            row = tk.Frame(self._links, bg=CARD)
            row.pack(fill="x", pady=2)
            dot = Dot(row, size=8)
            dot.set(GREEN)
            dot.pack(side="left", pady=(2, 0))
            caption = tk.Label(row, text=label, bg=CARD, fg=MUTED, font=_FONTS["small"], width=17, anchor="w")
            caption.pack(side="left", padx=(7, 0))
            link = tk.Label(row, text=url, bg=CARD, fg=HEAD, font=_FONTS["strong"], cursor="hand2")
            link.pack(side="left")
            link.bind("<Button-1>", lambda _e, target=url: webbrowser.open(target))
            link.bind("<Enter>", lambda _e, w=link: w.configure(fg=BRAND))
            link.bind("<Leave>", lambda _e, w=link: w.configure(fg=HEAD))
            copy = tk.Label(row, text="copy", bg=CARD, fg=MUTED, font=_FONTS["small"], cursor="hand2")
            copy.pack(side="right")
            copy.bind("<Button-1>", lambda _e, target=url, w=copy: self._copy(target, w))
            self._link_rows.append(row)
        self._fit()

    def _copy(self, value: str, widget: tk.Label) -> None:
        self.clipboard_clear()
        self.clipboard_append(value)
        widget.configure(text="copied", fg=GREEN)
        self.after(1400, lambda: widget.configure(text="copy", fg=MUTED))

    # ── گزارش ──────────────────────────────────────────────────────────

    def _append(self, source: str, line: str) -> None:
        text = self._text
        at_bottom = text.yview()[1] > 0.999
        text.configure(state="normal")
        text.insert("end", f"{source:>9} │ ", "prefix")
        text.insert("end", line + "\n", source if source in ("backend", "frontend", "setup") else "launcher")
        # سقفِ بافر: یک `npm install` چند هزار خط است و بدونِ این، پنجره بعد از
        # چند دقیقه کند می‌شود.
        if int(text.index("end-1c").split(".")[0]) > 3000:
            text.delete("1.0", "500.0")
        text.configure(state="disabled")
        if at_bottom:
            text.see("end")

    def _toggle_log(self) -> None:
        showing = not self._log_visible.get()
        self._log_visible.set(showing)
        if showing:
            self._log_frame.pack(fill="both", expand=True, pady=(0, 10))
            self._toggle.configure(text="Hide log")
            self._text.see("end")
        else:
            self._log_frame.pack_forget()
            self._toggle.configure(text="Show log")
        self._fit()

    def _copy_log(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self._text.get("1.0", "end-1c"))
        self._copy_log_button.configure(text="Copied")
        self.after(1400, lambda: self._copy_log_button.configure(text="Copy log"))

    # ── کنش‌ها ─────────────────────────────────────────────────────────

    def _open_browser(self) -> None:
        if self._session and self._session.links.local:
            webbrowser.open(self._session.links.local)

    def _ask_password(self, prompt: str) -> str | None:
        """پرسشِ رمزِ ادمینِ پستگرس — از نخِ کاری صدا زده می‌شود.

        نخِ کاری اجازهٔ ساختِ ویجت ندارد، پس ساختِ پنجره به نخِ رابط سپرده
        می‌شود و این‌جا فقط منتظرِ جواب می‌مانیم.
        """
        answer: queue.Queue[str | None] = queue.Queue(maxsize=1)
        self.after(0, lambda: PasswordDialog(self, prompt, answer.put))
        return answer.get()

    def _on_close(self) -> None:
        self._phase.configure(text="stopping…", fg=MUTED)
        self._phase_dot.set(MUTED)
        self.update_idletasks()
        if self._session:
            self._session.stop()
        self.destroy()


class NoticeCard:
    """کارتی که فقط وقتی حرفی برای گفتن هست دیده می‌شود."""

    def __init__(self, parent: tk.Misc) -> None:
        self._holder = tk.Frame(parent, bg=BG)
        self._holder.pack(fill="x")
        self._frame: tk.Frame | None = None

    def show(self, title: str, body: str, commands: list[str], *, tone: str = AMBER, url: str = "") -> None:
        if self._frame is not None:
            self._frame.destroy()
        frame = tk.Frame(self._holder, bg=CARD, highlightbackground=tone, highlightthickness=1)
        frame.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(frame, bg=CARD)
        inner.pack(fill="x", padx=14, pady=12)

        tk.Label(inner, text=title, bg=CARD, fg=tone, font=_FONTS["strong"], anchor="w", justify="left").pack(fill="x")
        if body:
            tk.Label(
                inner, text=body, bg=CARD, fg=TEXT, font=_FONTS["small"],
                anchor="w", justify="left", wraplength=520,
            ).pack(fill="x", pady=(4, 0))
        for command in commands:
            row = tk.Label(
                inner, text=command, bg="#262c40", fg=TEXT, font=_FONTS["mono"],
                anchor="w", justify="left", padx=8, pady=5, wraplength=500,
            )
            row.pack(fill="x", pady=(6, 0))
        if url:
            link = tk.Label(inner, text=url, bg=CARD, fg=BLUE, font=_FONTS["small"], cursor="hand2", anchor="w")
            link.pack(fill="x", pady=(6, 0))
            link.bind("<Button-1>", lambda _e: webbrowser.open(url))
        self._frame = frame


class PasswordDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, prompt: str, deliver: Callable[[str | None], None]) -> None:
        super().__init__(parent)
        self._deliver = deliver
        self._sent = False
        self.title("PostgreSQL")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)

        body = tk.Frame(self, bg=BG)
        body.pack(padx=18, pady=16)
        tk.Label(body, text=prompt, bg=BG, fg=TEXT, font=_FONTS["small"],
                 wraplength=380, justify="left", anchor="w").pack(fill="x")
        self._entry = tk.Entry(body, show="•", bg=CARD, fg=HEAD, font=_FONTS["body"],
                               relief="flat", insertbackground=HEAD, highlightthickness=1,
                               highlightbackground=LINE, highlightcolor=BRAND)
        self._entry.pack(fill="x", pady=(12, 12), ipady=5)
        self._entry.focus_set()

        buttons = tk.Frame(body, bg=BG)
        buttons.pack(fill="x")
        pill(buttons, "Skip", self._cancel).pack(side="right")
        pill(buttons, "Continue", self._submit, primary=True).pack(side="right", padx=6)

        self.bind("<Return>", lambda _e: self._submit())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.grab_set()

    def _finish(self, value: str | None) -> None:
        if self._sent:
            return
        self._sent = True
        self._deliver(value)
        self.destroy()

    def _submit(self) -> None:
        self._finish(self._entry.get() or None)

    def _cancel(self) -> None:
        self._finish(None)


_FONTS: dict[str, tuple] = {
    "title": ("TkDefaultFont", 15, "bold"),
    "body": ("TkDefaultFont", 10),
    "small": ("TkDefaultFont", 9),
    "strong": ("TkDefaultFont", 10, "bold"),
    "mono": ("TkFixedFont", 9),
}


def run() -> int:
    LauncherWindow().mainloop()
    return 0


__all__ = ["LauncherWindow", "run"]
