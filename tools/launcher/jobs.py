"""تضمینِ آخر: اگر راه‌انداز بمیرد، سرورها هم می‌میرند.

چرا لازم است
------------
`Supervisor.stop()` وقتی کار می‌کند که راه‌انداز فرصتِ اجرایش را داشته باشد —
یعنی کاربر پنجره را ببندد. ولی حالتی که این پروژه را آزار داده دقیقاً آن یکی
است: پروسه بدونِ خداحافظی می‌میرد (Task Manager، خطای خودِ راه‌انداز، ری‌استارتِ
ناگهانی). آن‌وقت `uvicorn --reload` و `node` زنده می‌مانند، پورت را نگه می‌دارند،
و اجرای بعدی با «پورت ۸۰۰۰ اشغال است» شروع می‌شود بی‌آنکه چیزی روی صفحه باشد که
آن را توضیح دهد.

Job Object پاسخِ خودِ ویندوز به همین مسئله است: پروسه‌ها به یک «شغل» وصل
می‌شوند و با پرچمِ `KILL_ON_JOB_CLOSE`، وقتی آخرین دستگیرهٔ آن شغل بسته شد —
که با مرگِ راه‌انداز، هرطور که باشد، اتفاق می‌افتد — سیستم‌عامل کلِ مجموعه را
می‌بندد. این دیگر ادبِ برنامه نیست، قاعدهٔ هسته است.

روی لینوکس و مک این کلاس یک پوستهٔ خالی است؛ آن‌جا `start_new_session` و
`killpg` کارِ خودشان را می‌کنند و مسیرِ عادیِ توقف کافی است.

هر شکستی این‌جا بی‌صداست و کشنده نیست: نبودنِ این تضمین بدتر از قبل نمی‌کند.
"""
from __future__ import annotations

import ctypes
import subprocess
import sys

WINDOWS = sys.platform.startswith("win")

_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JobObjectExtendedLimitInformation = 9


if WINDOWS:  # pragma: no cover - فقط روی ویندوز معنا دارد
    from ctypes import wintypes

    class _BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


class ProcessGroup:
    """مجموعه‌ای از پروسه‌ها که عمرشان به عمرِ این پروسه گره خورده است."""

    def __init__(self) -> None:
        self._handle = None
        if not WINDOWS:
            return
        try:  # pragma: no cover - مسیرِ ویندوز
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.CreateJobObjectW(None, None)
            if not handle:
                return
            limits = _ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            ok = kernel32.SetInformationJobObject(
                handle, _JobObjectExtendedLimitInformation,
                ctypes.byref(limits), ctypes.sizeof(limits),
            )
            if not ok:
                kernel32.CloseHandle(handle)
                return
            self._kernel32 = kernel32
            self._handle = handle
        except (OSError, AttributeError):
            self._handle = None

    @property
    def active(self) -> bool:
        return self._handle is not None

    def adopt(self, process: subprocess.Popen) -> bool:
        """پروسه را به این مجموعه اضافه کن. `False` یعنی تضمین برقرار نشد."""
        if self._handle is None:
            return False
        try:  # pragma: no cover - مسیرِ ویندوز
            return bool(self._kernel32.AssignProcessToJobObject(self._handle, int(process._handle)))
        except (OSError, AttributeError, ValueError):
            return False
