"""راه‌اندازِ محیطِ توسعهٔ NexaHR.

یک پنجره به‌جای سه کنسول: پیش‌نیازها را می‌سنجد و هرچه را بشود خودش درست
می‌کند، هر دو سرور را بدونِ پنجرهٔ جداگانه بالا می‌آورد، و آدرس‌های محلی و
شبکه را نشان می‌دهد.

    python -m tools.launcher            # پنجره
    python -m tools.launcher --no-gui   # همان کار، در ترمینال
    python -m tools.launcher --check    # فقط تشخیص، بدونِ اجرا
"""

__all__ = ["ports", "environment", "steps", "supervisor", "session"]
