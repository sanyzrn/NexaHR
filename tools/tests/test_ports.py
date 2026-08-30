"""تست‌های انتخابِ پورت.

اینها رفتارِ ویندوز را روی لینوکس شبیه‌سازی می‌کنند، چون همان‌جاست که مسئله رخ
می‌دهد و CI ویندوز ندارد. چیزی که سنجیده می‌شود منطقِ تصمیم است: با هر یک از سه
حالتِ شکست چه اتفاقی می‌افتد، و مهم‌تر از آن، چه *نمی‌افتد* — پروسه‌ای که مالِ ما
نیست هیچ‌وقت کشته نمی‌شود.
"""
from __future__ import annotations

import socket
from pathlib import Path

import pytest

from tools.launcher import ports

# ── تجزیهٔ خروجیِ netstat ────────────────────────────────────────────────

NETSTAT = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1084
  TCP    0.0.0.0:8000           0.0.0.0:0              LISTENING       23188
  TCP    127.0.0.1:8001         0.0.0.0:0              LISTENING       4020
  TCP    192.168.1.20:139       0.0.0.0:0              LISTENING       4
  TCP    [::]:8000              [::]:0                 LISTENING       23188
  TCP    127.0.0.1:5173         127.0.0.1:63122        ESTABLISHED     9900
"""


def test_the_listening_pid_is_read_from_netstat():
    assert ports.pids_from_netstat(NETSTAT, 8000) == [23188]
    assert ports.pids_from_netstat(NETSTAT, 8001) == [4020]


def test_a_port_that_is_only_connected_to_is_not_a_listener():
    # سطرِ ۵۱۷۳ حالتش ESTABLISHED است، نه LISTENING. اگر این را جدا نکنیم،
    # هر تبِ بازِ مرورگر مثل «پورت اشغال است» دیده می‌شود.
    assert ports.pids_from_netstat(NETSTAT, 5173) == []


def test_a_port_that_appears_in_an_address_but_not_as_the_port_is_ignored():
    # «192.168.1.20:139» نباید برای پورتِ ۱۹۲ یا ۲۰ چیزی برگرداند.
    assert ports.pids_from_netstat(NETSTAT, 20) == []
    assert ports.pids_from_netstat(NETSTAT, 139) == [4]


# ── بازه‌های رزروشدهٔ ویندوز ─────────────────────────────────────────────

NETSH = """
Protocol tcp Port Exclusion Ranges

Start Port    End Port
----------    --------
      1029        1128
      7998        8097
     50000       50059     *

* - Administered port exclusions.
"""


def test_excluded_ranges_are_read_as_start_and_end():
    # هر دو ستون خودِ شمارهٔ پورت‌اند. خواندنشان به‌صورتِ «شروع و تعداد» بازه‌ها
    # را ده‌ها برابر بزرگ می‌کند و آن‌وقت پورت‌های کاملاً سالم هم «رزروشده»
    # اعلام می‌شوند.
    assert ports.parse_excluded_ranges(NETSH) == [(1029, 1128), (7998, 8097), (50000, 50059)]


def test_the_asterisk_on_administered_ranges_does_not_hide_them():
    # ستاره یعنی بازه‌ای که مدیر خودش ثبت کرده — دقیقاً همان بازه‌ای که کاربر
    # بعد از خواندنِ راهنمای ما ساخته. از قلم افتادنش یعنی راه‌انداز نمی‌فهمد
    # چرا پورت آزاد نیست.
    assert (50000, 50059) in ports.parse_excluded_ranges(NETSH)


def test_lines_that_are_not_ranges_are_ignored():
    assert ports.parse_excluded_ranges("Start Port    End Port\n----------    --------\n") == []
    # بازهٔ معکوس یعنی سطر اصلاً بازه نبوده.
    assert ports.parse_excluded_ranges("      9000        8000\n") == []


def test_a_reserved_range_is_matched_against_the_port():
    ranges = [(7998, 8097), (50000, 50059)]
    assert ports.covering_range(8000, ranges) == (7998, 8097)
    assert ports.covering_range(9000, ranges) is None


# ── «مالِ ما»، که شرطِ کشتن است ─────────────────────────────────────────

ROOT = Path("C:/Users/sany/DbsPulse_v3")


def test_the_venv_interpreter_counts_as_ours():
    owner = ports.Owner(pid=1, name="python.exe", path=r"C:\Users\sany\DbsPulse_v3\backend\.venv\Scripts\python.exe")
    assert ports.belongs_to(owner, ROOT)


def test_a_node_outside_the_project_still_counts_when_it_runs_our_code():
    # `npm run dev` در نهایت یک node.exe سراسری است؛ تنها ردِ پروژه در خطِ
    # فرمانش است. بدونِ این شرط، هر بار پورت ۵۱۷۳ را رها می‌کردیم و روی ۵۱۷۴
    # بالا می‌آمدیم و بازماندهٔ اجرای قبلی برای همیشه می‌ماند.
    owner = ports.Owner(
        pid=2, name="node.exe", path=r"C:\Program Files\nodejs\node.exe",
        cmdline=r"node C:\Users\sany\DbsPulse_v3\frontend\node_modules\vite\bin\vite.js",
    )
    assert ports.belongs_to(owner, ROOT)


def test_an_unrelated_program_is_never_ours():
    for owner in (
        ports.Owner(pid=3, name="node.exe", path=r"C:\Program Files\nodejs\node.exe", cmdline="node server.js"),
        ports.Owner(pid=4, name="Docker Desktop.exe", path=r"C:\Program Files\Docker\Docker Desktop.exe"),
        ports.Owner(pid=5, name="python.exe", path=r"C:\Python311\python.exe", cmdline="python -m http.server 8000"),
    ):
        assert not ports.belongs_to(owner, ROOT)


def test_ownership_ignores_slash_direction_and_letter_case():
    owner = ports.Owner(pid=6, name="python.exe", path="c:/users/sany/dbspulse_v3/backend/.venv/scripts/python.exe")
    assert ports.belongs_to(owner, ROOT)


def test_an_empty_root_never_matches_anything():
    # گاردِ همان اشتباهی که یک بار کافی است: ریشهٔ خالی، `"" in haystack` را
    # همیشه درست می‌کند و راه‌انداز شروع می‌کرد به کشتنِ هر پروسه‌ای.
    owner = ports.Owner(pid=7, name="python.exe", path=r"C:\Python311\python.exe")
    assert not ports.belongs_to(owner, Path(""))


# ── انتخابِ پورت ────────────────────────────────────────────────────────

def fake_prober(states: dict[int, ports.Verdict]):
    """پروبی که هر پورت را همان‌طور گزارش می‌کند که تست خواسته."""
    def probe(port: int, host: str = "0.0.0.0") -> ports.Probe:
        return ports.Probe(port, states.get(port, ports.Verdict.FREE))
    return probe


def test_a_free_port_is_taken_as_is():
    choice = ports.choose(8000, prober=fake_prober({}), root=ROOT)
    assert choice.port == 8000
    assert not choice.moved
    assert choice.story == []


def test_a_port_held_by_a_stranger_is_left_alone_and_the_next_one_is_used(monkeypatch):
    monkeypatch.setattr(ports, "owner_of", lambda port: ports.Owner(pid=99, name="Docker Desktop.exe"))
    killed: list[int] = []
    monkeypatch.setattr(ports, "reclaim", lambda owner, timeout=8.0: killed.append(owner.pid))

    choice = ports.choose(8000, prober=fake_prober({8000: ports.Verdict.IN_USE}), root=ROOT)

    assert killed == []          # این مهم‌ترین ادعای این فایل است
    assert choice.port == 8001
    assert choice.moved
    assert "Docker Desktop.exe" in " ".join(choice.story)


def test_our_own_leftover_process_is_closed_and_the_port_reused(monkeypatch):
    ours = ports.Owner(pid=42, name="python.exe", path=str(ROOT / "backend/.venv/Scripts/python.exe"))
    monkeypatch.setattr(ports, "owner_of", lambda port: ours)
    killed: list[int] = []
    monkeypatch.setattr(ports, "reclaim", lambda owner, timeout=8.0: killed.append(owner.pid))
    monkeypatch.setattr(ports, "wait_until_free", lambda port, host="0.0.0.0", timeout=8.0: True)

    # بعد از کشتن، پروب باید پورت را آزاد ببیند. یک پروبِ حالت‌دار همین را
    # می‌سازد: بارِ اول اشغال، بارهای بعد آزاد.
    seen: list[int] = []

    def probe(port: int, host: str = "0.0.0.0") -> ports.Probe:
        seen.append(port)
        occupied = port == 8000 and seen.count(8000) == 1
        return ports.Probe(port, ports.Verdict.IN_USE if occupied else ports.Verdict.FREE)

    choice = ports.choose(8000, prober=probe, root=ROOT)

    assert killed == [42]
    assert choice.port == 8000   # پورت پس گرفته شد، نه این‌که رهایش کنیم
    assert not choice.moved


def test_a_windows_reserved_port_moves_on_without_trying_to_kill_anything(monkeypatch):
    monkeypatch.setattr(ports, "excluded_ranges", lambda: [(7998, 8097)])
    monkeypatch.setattr(ports, "owner_of", lambda port: pytest.fail("no owner lookup for a reserved port"))

    choice = ports.choose(8000, prober=fake_prober({8000: ports.Verdict.RESERVED}), root=ROOT)

    assert choice.port == 8001
    story = " ".join(choice.story)
    assert "reserved" in story and "7998-8097" in story
    # و راهِ پس‌گرفتنِ خودِ ۸۰۰۰ هم گفته می‌شود، برای کسی که بخواهد.
    assert any("winnat" in line for line in choice.advice)


def test_a_whole_blocked_range_is_reported_rather_than_looping_forever():
    blocked = {port: ports.Verdict.RESERVED for port in range(8000, 8100)}
    choice = ports.choose(8000, prober=fake_prober(blocked), root=ROOT, span=20)

    assert choice.port is None
    assert not choice.ok
    assert "No free port" in " ".join(choice.story)


def test_the_search_stops_at_the_first_free_port():
    states = {8000: ports.Verdict.IN_USE, 8001: ports.Verdict.IN_USE, 8002: ports.Verdict.RESERVED}
    choice = ports.choose(8000, prober=fake_prober(states), root=ROOT)
    assert choice.port == 8003


# ── پروبِ واقعی ────────────────────────────────────────────────────────

def test_probe_reports_a_really_occupied_port_as_in_use():
    """این یکی سوکتِ واقعی می‌سازد: مسئله دقیقاً همین بود که پروبِ قدیمی
    (`connect`) به سؤالِ دیگری جواب می‌داد."""
    holder = socket.socket()
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    try:
        assert ports.probe(port, "127.0.0.1").verdict is ports.Verdict.IN_USE
    finally:
        holder.close()


def test_probe_reports_an_unused_port_as_free():
    scratch = socket.socket()
    scratch.bind(("127.0.0.1", 0))
    port = scratch.getsockname()[1]
    scratch.close()
    assert ports.probe(port, "127.0.0.1").free
