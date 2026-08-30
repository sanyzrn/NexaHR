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
می‌کند. هر کارِ نگهداری (پشتیبان، عوض کردنِ دیتابیس، ساختِ حساب) هم روی نخِ
خودش می‌رود و نتیجه‌اش از همان صف برمی‌گردد — وگرنه پنجره در تمامِ مدت یخ
می‌زند و کاربر فکر می‌کند برنامه مرده است.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog
from tkinter import font as tkfont

from . import admin as adminlib
from . import autostart
from .database import Endpoint
from .prerequisites import Feature
from .session import Session
from .shell import Result
from .steps import Outcome, Step
from .supervisor import Server

# ── پالت ────────────────────────────────────────────────────────────────
# همان تمِ «شب»ِ خودِ برنامه (سرمه‌ای، نه مشکی) تا راه‌انداز عضوِ همان محصول
# به‌نظر برسد و نه یک ابزارِ چسبانده‌شده.
BG = "#0b0e17"        # زمینهٔ پنجره
CARD = "#1b2031"      # کارت
FILL = "#262c40"      # پرکنندهٔ ملایم روی کارت
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
WIDTH = 660


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
        hover = "#b61615" if is_primary else FILL
        button.configure(bg=base, fg="#ffffff" if is_primary else TEXT, activebackground=hover)
        button.bind("<Enter>", lambda _e: button.configure(bg=hover) if str(button["state"]) != "disabled" else None)
        button.bind("<Leave>", lambda _e: button.configure(bg=base))

    restyle(primary)
    button.restyle = restyle  # type: ignore[attr-defined]
    return button


def action(parent: tk.Misc, text: str, command: Callable[[], None]) -> tk.Label:
    """کنشِ کم‌وزن، به شکلِ یک کلمهٔ کلیک‌شدنی.

    دکمهٔ کامل برای این‌ها زیادی است: کارتِ مدیریت پنج‌شش کنش دارد و شش دکمه
    آن را به یک نوارِ ابزار تبدیل می‌کند که چشم را از وضعیت — که مهم‌تر است —
    برمی‌دارد.
    """
    label = tk.Label(parent, text=text, bg=CARD, fg=BLUE, font=_FONTS["small"], cursor="hand2")
    label.bind("<Button-1>", lambda _e: label.invoke())  # type: ignore[attr-defined]
    label.bind("<Enter>", lambda _e: label.configure(fg=HEAD) if label.enabled else None)  # type: ignore[attr-defined]
    label.bind("<Leave>", lambda _e: label.configure(fg=BLUE) if label.enabled else None)  # type: ignore[attr-defined]

    label.enabled = True  # type: ignore[attr-defined]

    def invoke() -> None:
        if label.enabled:  # type: ignore[attr-defined]
            command()

    def enable(on: bool) -> None:
        label.enabled = on  # type: ignore[attr-defined]
        label.configure(fg=BLUE if on else MUTED, cursor="hand2" if on else "")

    label.invoke = invoke  # type: ignore[attr-defined]
    label.enable = enable  # type: ignore[attr-defined]
    return label


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
        self._chips: dict[str, tuple[Dot, tk.Label]] = {}
        self._actions: list[tk.Label] = []
        self._log_visible = tk.BooleanVar(value=False)
        self._opened_browser = False
        self._busy = False
        self._features: list[Feature] = []

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
        self._manage_card(body)
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

    def _manage_card(self, parent: tk.Misc) -> None:
        """کارتِ نگهداری: دیتابیس، قابلیت‌های اختیاری، حسابِ مدیر، بالا آمدن با ویندوز.

        تا وقتی سرورها بالا نیامده‌اند، مقدارها «…» می‌مانند و کنش‌ها خاموش‌اند:
        هر کدامشان به venv یا به دیتابیس دست می‌زنند، و اجرایشان وسطِ راه‌اندازی
        فقط دو کار را هم‌زمان خراب می‌کند.
        """
        card = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="x", pady=(0, 10))
        grid = tk.Frame(card, bg=CARD)
        grid.pack(fill="x", padx=14, pady=12)
        grid.columnconfigure(1, weight=1)

        self._values: dict[str, tk.Label] = {}
        rows = (
            ("database", "Database", (("Change…", self._change_database),
                                      ("Back up", self._back_up),
                                      ("Restore…", self._restore))),
            ("admin", "Admin account", (("Create…", self._create_admin),)),
            ("pdf", "PDF export", (("Fix…", lambda: self._fix_feature("pdf")),)),
        )
        for index, (key, title, links) in enumerate(rows):
            tk.Label(grid, text=title, bg=CARD, fg=MUTED, font=_FONTS["small"], anchor="w", width=14).grid(
                row=index, column=0, sticky="w", pady=2
            )
            value = tk.Label(grid, text="…", bg=CARD, fg=TEXT, font=_FONTS["small"], anchor="w")
            value.grid(row=index, column=1, sticky="w", pady=2)
            self._values[key] = value

            strip = tk.Frame(grid, bg=CARD)
            strip.grid(row=index, column=2, sticky="e", pady=2)
            for offset, (text, command) in enumerate(links):
                if offset:
                    tk.Label(strip, text="·", bg=CARD, fg=LINE, font=_FONTS["small"]).pack(side="left", padx=4)
                link = action(strip, text, command)
                link.pack(side="left")
                link.enable(False)
                self._actions.append(link)

        self._autostart = tk.BooleanVar(value=autostart.enabled())
        box = tk.Checkbutton(
            grid, text="Start NexaHR when Windows starts", variable=self._autostart,
            command=self._toggle_autostart, bg=CARD, fg=TEXT, font=_FONTS["small"],
            selectcolor=FILL, activebackground=CARD, activeforeground=HEAD,
            highlightthickness=0, bd=0, anchor="w", cursor="hand2",
            disabledforeground=MUTED,
        )
        box.grid(row=len(rows), column=0, columnspan=3, sticky="w", pady=(8, 0))
        if not autostart.supported():
            box.configure(state="disabled")
            tk.Label(
                grid, text=autostart.describe(), bg=CARD, fg=MUTED, font=_FONTS["small"], anchor="w",
            ).grid(row=len(rows) + 1, column=0, columnspan=3, sticky="w")
        self._autostart_box = box

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
        # تا وقتی سرورها جواب نداده‌اند، این دکمه نه کار می‌کند و نه شبیهِ
        # دکمهٔ اصلی است. قاعدهٔ «روی پشتهٔ خراب مرورگر باز نکن»، این‌بار در
        # ظاهرِ دکمه.
        self._open_button = pill(bar, "Open NexaHR", self._open_browser)
        self._open_button.pack(side="right", padx=6)
        self._open_button.configure(state="disabled")
        self._restart_button = pill(bar, "Restart", self._restart)
        self._restart_button.pack(side="right")
        self._restart_button.configure(state="disabled")

    # ── چرخهٔ اجرا ───────────────────────────────────────────────────────

    def start(self) -> None:
        self._session = Session(
            log=lambda source, line: self._events.put(("log", source, line)),
            ask_password=self._ask_password,
            on_step=lambda step, outcome: self._events.put(("step", step, outcome)),
            on_crash=lambda server: self._events.put(("crash", server)),
        )
        self._session.stop_on_exit()
        threading.Thread(target=self._work, name="launcher", daemon=True).start()

    def _work(self, restarting: bool = False) -> None:
        session = self._session
        assert session
        started = session.restart() if restarting else (session.prepare() and session.serve())
        if started:
            self._events.put(("ready",))
            self._events.put(("manage", self._gather()))
        else:
            self._events.put(("failed", session.failure))

    def _gather(self) -> dict:
        """وضعیتِ کارتِ نگهداری. روی نخِ کاری، چون هر سه‌تایش زیرپروسه می‌زنند."""
        session = self._session
        assert session
        return {
            "endpoint": session.endpoint(),
            "database": session.database_report(),
            "admin": session.admin_status(),
            "features": session.features(),
        }

    # ── صف رویدادها ─────────────────────────────────────────────────────

    def _drain(self) -> None:
        try:
            while True:
                self._handle(self._events.get_nowait())
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
        elif kind == "manage":
            self._on_manage(event[1])
        elif kind == "task":
            self._on_task(event[1], event[2])

    def _notify(self, *args, **kwargs) -> None:
        """اطلاعیه را نشان بده و پنجره را به اندازهٔ متنِ تازه‌اش برسان."""
        self._notice.show(*args, **kwargs)
        self._fit()

    def _update_step(self, step: Step, outcome: Outcome | None) -> None:
        dot, label = self._chips[step.key]
        if outcome is None:
            dot.set(AMBER)
            label.configure(fg=TEXT)
            self._phase.configure(text=f"{step.title.lower()}…", fg=MUTED)
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
        self._restart_button.configure(state="normal")
        self._stop_button.configure(text="Stop")
        self._set_actions(True)
        if session.ctx.notes:
            self._notify("Worth knowing", "\n".join(session.ctx.notes), session.ctx.advice, tone=AMBER)
        else:
            self._notice.clear()
            self._fit()
        if not self._opened_browser:
            self._opened_browser = True
            self._open_browser()

    def _on_failed(self, outcome: Outcome | None) -> None:
        self._phase.configure(text="stopped", fg=RED)
        self._phase_dot.set(RED)
        self._set_actions(False)
        self._restart_button.configure(state="normal")
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

    def _on_crash(self, server: Server) -> None:
        self._phase.configure(text=f"{server.spec.name} stopped", fg=RED)
        self._phase_dot.set(RED)
        self._notify(
            f"The {server.spec.name} stopped",
            "It was running and then exited. Last output:\n\n" + "\n".join(server.tail[-10:]),
            [],
            tone=RED,
        )

    def _on_manage(self, info: dict) -> None:
        endpoint: Endpoint = info["endpoint"]
        report: dict = info["database"]
        status: adminlib.Status = info["admin"]
        self._features = list(info["features"].features)

        suffix = "" if report.get("database_exists") else "  (not reachable)"
        self._values["database"].configure(text=endpoint.label + suffix,
                                           fg=TEXT if report.get("database_exists") else AMBER)
        self._values["admin"].configure(text=status.summary,
                                        fg=TEXT if status.has_active_admin else AMBER)

        pdf = next((feature for feature in self._features if feature.key == "pdf"), None)
        if pdf:
            self._values["pdf"].configure(
                text="available" if pdf.available else "not available",
                fg=TEXT if pdf.available else AMBER,
            )
        self._fit()

    def _on_task(self, label: str, result: Result) -> None:
        self._busy = False
        self._set_actions(True)
        self._phase.configure(text="running", fg=GREEN)
        self._phase_dot.set(GREEN)
        self._notify(label, result.message, [], tone=GREEN if result.ok else RED)
        threading.Thread(
            target=lambda: self._events.put(("manage", self._gather())), daemon=True
        ).start()

    def _set_actions(self, on: bool) -> None:
        for link in self._actions:
            link.enable(on)  # type: ignore[attr-defined]

    # ── کارهای نگهداری ─────────────────────────────────────────────────

    def _run_task(self, label: str, work: Callable[[Session], Result]) -> None:
        """یک کارِ نگهداری روی نخِ خودش، با قفلِ ساده در برابرِ دو تا هم‌زمان."""
        session = self._session
        if session is None or self._busy:
            return
        self._busy = True
        self._set_actions(False)
        self._phase.configure(text=f"{label.lower()}…", fg=AMBER)
        self._phase_dot.set(AMBER)
        if not self._log_visible.get():
            self._toggle_log()

        def run() -> None:
            try:
                result = work(session)
            except Exception as error:  # noqa: BLE001 - نباید نخ را بی‌صدا بکشد
                result = Result(False, f"{type(error).__name__}: {error}")
            self._events.put(("task", label, result))

        threading.Thread(target=run, name="task", daemon=True).start()

    def _change_database(self) -> None:
        session = self._session
        if not session:
            return
        current = session.endpoint()
        known = ", ".join(session.database_report().get("databases") or []) or "—"
        form = FormDialog(
            self, "Connect to a database",
            "The settings file is rewritten and NexaHR restarts on the new database. "
            "If it does not exist yet, it is created.\n\nOn this server: " + known,
            [
                ("Database", "name", current.name, False),
                ("Host", "host", current.host, False),
                ("Port", "port", str(current.port), False),
                ("User", "user", current.user, False),
                ("Password", "password", current.password, True),
            ],
            "Connect",
        )
        values = form.result
        if not values or not values["name"].strip():
            return
        try:
            port = int(values["port"].strip() or "5432")
        except ValueError:
            self._notify("Connect to a database", "The port must be a number.", [], tone=RED)
            return
        target = Endpoint(
            user=values["user"].strip() or "nexahr", password=values["password"],
            host=values["host"].strip() or "localhost", port=port, name=values["name"].strip(),
        )
        self._run_task("Switching database", lambda s: s.switch_database(target))

    def _back_up(self) -> None:
        self._run_task("Backing up", lambda s: s.back_up())

    def _restore(self) -> None:
        session = self._session
        if not session:
            return
        folder = session.ctx.paths.root / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        chosen = filedialog.askopenfilename(
            parent=self, title="Choose a backup to restore", initialdir=str(folder),
            filetypes=[("PostgreSQL dump", "*.dump"), ("All files", "*.*")],
        )
        if not chosen:
            return
        source = Path(chosen)
        # تأییدِ صریح، چون این کار برگشت‌ناپذیر است: `--clean` هرچه در دیتابیس
        # هست را اول حذف می‌کند.
        agreed = ConfirmDialog(
            self, "Restore this backup?",
            f"Everything now in “{session.endpoint().name}” is deleted and replaced with the "
            f"contents of {source.name}. This cannot be undone.\n\n"
            "The servers stop during the restore and start again afterwards.",
            "Replace the data",
        ).agreed
        if agreed:
            self._run_task("Restoring", lambda s: s.restore_from(source))

    def _create_admin(self) -> None:
        form = FormDialog(
            self, "Create an admin account",
            "The account gets every administrative capability, and stays outside the "
            "evaluation chain — it can configure the system but sees nobody's scores.",
            [
                ("Username", "username", "", False),
                ("Display name", "full_name", "", False),
                ("Password", "password", "", True),
                ("Repeat password", "confirm", "", True),
            ],
            "Create",
        )
        values = form.result
        if not values:
            return
        problem = adminlib.validate(
            values["username"], values["full_name"], values["password"], values["confirm"]
        )
        if problem:
            self._notify("Create an admin account", problem, [], tone=RED)
            return
        self._run_task(
            "Creating the account",
            lambda s: s.create_admin(
                username=values["username"], full_name=values["full_name"], password=values["password"]
            ),
        )

    def _fix_feature(self, key: str) -> None:
        feature = next((item for item in self._features if item.key == key), None)
        if feature is None or feature.available:
            self._notify("PDF export", "This already works — nothing to fix.", [], tone=GREEN)
            return
        fix = feature.fix
        if fix is None:
            return
        if fix.package:
            self._run_task("Installing", lambda s: s.install_package(fix.package))
            return
        # چیزی که خودمان نمی‌توانیم نصب کنیم: دقیقاً همان را بگو، با نشانی.
        self._notify(fix.label, f"{fix.body}\n\n{feature.detail}", [], tone=AMBER, url=fix.url)

    def _toggle_autostart(self) -> None:
        session = self._session
        wanted = self._autostart.get()
        if not autostart.supported() or session is None:
            self._autostart.set(False)
            return
        launcher = session.ctx.paths.root / "tools" / "nexahr.pyw"
        interpreter = Path(session.ctx.python.path)
        # `pythonw.exe` و نه `python.exe`: میان‌بری که به دومی اشاره کند، در هر
        # بوت یک پنجرهٔ کنسول باز می‌کند — همان چیزی که این راه‌انداز آمده که
        # از بین ببرد.
        console_free = interpreter.with_name("pythonw.exe")
        if console_free.exists():
            interpreter = console_free
        done = autostart.enable(interpreter, launcher) if wanted else autostart.disable()
        self._autostart.set(autostart.enabled())
        if not done:
            self._notify(
                "Start with Windows",
                "The Startup shortcut could not be written. This is usually a policy that "
                "blocks changes to the Startup folder.",
                [], tone=RED,
            )
        else:
            self._append("setup", f"start with Windows: {'on' if self._autostart.get() else 'off'}")

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

    def _restart(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._set_actions(False)
        self._restart_button.configure(state="disabled")
        self._open_button.configure(state="disabled")
        self._open_button.restyle(False)
        self._phase.configure(text="restarting…", fg=AMBER)
        self._phase_dot.set(AMBER)
        for dot, label in self._chips.values():
            dot.set(MUTED)
            label.configure(fg=MUTED)
        self._notice.clear()
        self._fit()

        def run() -> None:
            self._work(restarting=True)
            self._busy = False

        threading.Thread(target=run, name="restart", daemon=True).start()

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

    def clear(self) -> None:
        if self._frame is not None:
            self._frame.destroy()
            self._frame = None

    def show(self, title: str, body: str, commands: list[str], *, tone: str = AMBER, url: str = "") -> None:
        self.clear()
        frame = tk.Frame(self._holder, bg=CARD, highlightbackground=tone, highlightthickness=1)
        frame.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(frame, bg=CARD)
        inner.pack(fill="x", padx=14, pady=12)

        tk.Label(inner, text=title, bg=CARD, fg=tone, font=_FONTS["strong"], anchor="w", justify="left").pack(fill="x")
        if body:
            tk.Label(
                inner, text=body, bg=CARD, fg=TEXT, font=_FONTS["small"],
                anchor="w", justify="left", wraplength=WIDTH - 90,
            ).pack(fill="x", pady=(4, 0))
        for command in commands:
            tk.Label(
                inner, text=command, bg=FILL, fg=TEXT, font=_FONTS["mono"],
                anchor="w", justify="left", padx=8, pady=5, wraplength=WIDTH - 110,
            ).pack(fill="x", pady=(6, 0))
        if url:
            link = tk.Label(inner, text=url, bg=CARD, fg=BLUE, font=_FONTS["small"], cursor="hand2", anchor="w")
            link.pack(fill="x", pady=(6, 0))
            link.bind("<Button-1>", lambda _e: webbrowser.open(url))
        self._frame = frame


class _Dialog(tk.Toplevel):
    """پایهٔ مشترکِ پنجره‌های کوچک: تمِ یکسان، مودال، و Escape که می‌بندد."""

    def __init__(self, parent: tk.Tk, title: str) -> None:
        super().__init__(parent)
        self.title(title)
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.body = tk.Frame(self, bg=BG)
        self.body.pack(padx=18, pady=16, fill="both", expand=True)

    def finish(self) -> None:
        self.grab_release()
        self.destroy()

    def run(self) -> None:
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.grab_set()
        self.wait_window(self)

    def _cancel(self) -> None:  # pragma: no cover - زیرکلاس‌ها بازنویسی می‌کنند
        self.finish()


class FormDialog(_Dialog):
    """چند فیلد و یک دکمهٔ تأیید. `result` بعد از بسته شدن پر است، یا `None`."""

    def __init__(
        self,
        parent: tk.Tk,
        title: str,
        explanation: str,
        fields: list[tuple[str, str, str, bool]],
        confirm: str,
    ) -> None:
        super().__init__(parent, title)
        self.result: dict[str, str] | None = None

        tk.Label(
            self.body, text=explanation, bg=BG, fg=MUTED, font=_FONTS["small"],
            wraplength=430, justify="left", anchor="w",
        ).pack(fill="x", pady=(0, 12))

        grid = tk.Frame(self.body, bg=BG)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        self._entries: dict[str, tk.Entry] = {}
        for index, (label, key, initial, secret) in enumerate(fields):
            tk.Label(grid, text=label, bg=BG, fg=TEXT, font=_FONTS["small"], anchor="w", width=15).grid(
                row=index, column=0, sticky="w", pady=4
            )
            entry = tk.Entry(
                grid, bg=CARD, fg=HEAD, font=_FONTS["body"], relief="flat",
                insertbackground=HEAD, highlightthickness=1, highlightbackground=LINE,
                highlightcolor=BRAND, show="•" if secret else "",
            )
            entry.insert(0, initial)
            entry.grid(row=index, column=1, sticky="ew", pady=4, ipady=4)
            self._entries[key] = entry

        buttons = tk.Frame(self.body, bg=BG)
        buttons.pack(fill="x", pady=(14, 0))
        pill(buttons, "Cancel", self._cancel).pack(side="right")
        pill(buttons, confirm, self._submit, primary=True).pack(side="right", padx=6)

        first = next(iter(self._entries.values()), None)
        if first:
            first.focus_set()
            first.select_range(0, "end")
        self.bind("<Return>", lambda _e: self._submit())
        self.run()

    def _submit(self) -> None:
        self.result = {key: entry.get() for key, entry in self._entries.items()}
        self.finish()

    def _cancel(self) -> None:
        self.result = None
        self.finish()


class ConfirmDialog(_Dialog):
    """تأییدِ کارِ برگشت‌ناپذیر. دکمهٔ تأیید عمداً می‌گوید چه می‌کند، نه «بله»."""

    def __init__(self, parent: tk.Tk, title: str, body: str, confirm: str) -> None:
        super().__init__(parent, title)
        self.agreed = False

        tk.Label(self.body, text=title, bg=BG, fg=RED, font=_FONTS["strong"], anchor="w").pack(fill="x")
        tk.Label(
            self.body, text=body, bg=BG, fg=TEXT, font=_FONTS["small"],
            wraplength=430, justify="left", anchor="w",
        ).pack(fill="x", pady=(6, 0))

        buttons = tk.Frame(self.body, bg=BG)
        buttons.pack(fill="x", pady=(16, 0))
        pill(buttons, "Cancel", self._cancel).pack(side="right")
        pill(buttons, confirm, self._accept, primary=True).pack(side="right", padx=6)
        self.run()

    def _accept(self) -> None:
        self.agreed = True
        self.finish()

    def _cancel(self) -> None:
        self.agreed = False
        self.finish()


class PasswordDialog(_Dialog):
    def __init__(self, parent: tk.Tk, prompt: str, deliver: Callable[[str | None], None]) -> None:
        super().__init__(parent, "PostgreSQL")
        self._deliver = deliver
        self._sent = False

        tk.Label(self.body, text=prompt, bg=BG, fg=TEXT, font=_FONTS["small"],
                 wraplength=380, justify="left", anchor="w").pack(fill="x")
        self._entry = tk.Entry(self.body, show="•", bg=CARD, fg=HEAD, font=_FONTS["body"],
                               relief="flat", insertbackground=HEAD, highlightthickness=1,
                               highlightbackground=LINE, highlightcolor=BRAND)
        self._entry.pack(fill="x", pady=(12, 12), ipady=5)
        self._entry.focus_set()

        buttons = tk.Frame(self.body, bg=BG)
        buttons.pack(fill="x")
        pill(buttons, "Skip", self._cancel).pack(side="right")
        pill(buttons, "Continue", self._submit, primary=True).pack(side="right", padx=6)
        self.bind("<Return>", lambda _e: self._submit())
        self.run()

    def _send(self, value: str | None) -> None:
        if self._sent:
            return
        self._sent = True
        self._deliver(value)
        self.finish()

    def _submit(self) -> None:
        self._send(self._entry.get() or None)

    def _cancel(self) -> None:
        self._send(None)


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
