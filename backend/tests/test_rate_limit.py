"""لایهٔ اول دفاع: محدودیت نرخ به ازای IP، روی هر مسیری که رمز حدس می‌زند.

لایهٔ دوم (قفل حساب به ازای نام کاربری) در test_login_lockout.py است.

هر تلاش عمداً نام کاربری *متفاوتی* دارد: با نام تکراری، قفلِ حساب زودتر از سقف
per-IP فعال می‌شود و آن‌وقت این تست دیگر چیزی دربارهٔ محدودیت per-IP اثبات نمی‌کند —
دقیقاً همان اتفاقی که با اضافه‌شدن قفل حساب افتاد. این شکل، دو لایه را از هم جدا
نگه می‌دارد.
"""
from tests.helpers import auth_header, make_user


def test_login_is_rate_limited_per_ip_regardless_of_username(client, db_session):
    responses = [
        client.post("/api/auth/login", json={"username": f"ghost-{i}", "password": "wrong"})
        for i in range(10)
    ]
    assert all(r.status_code == 401 for r in responses), "قفل حساب نباید این‌جا دخالت کند"

    blocked = client.post("/api/auth/login", json={"username": "ghost-11", "password": "wrong"})
    assert blocked.status_code == 429
    assert "بیش از حد مجاز" in blocked.json()["detail"]


def test_changing_a_password_is_rate_limited_too(client, db_session):
    """«کاربر از قبل وارد شده» این سقف را بی‌معنا نمی‌کند.

    کسی که یک نشستِ دزدیده‌شده دارد — توکنِ لو رفته، یا رایانه‌ای که قفل نشده —
    با این مسیر رمزِ *فعلی* را حدس می‌زند؛ و با پیدا کردنش تصاحبِ کاملِ حساب
    است، چون همین مسیر رمز را عوض می‌کند. `login` و `refresh` سقف داشتند و
    این نداشت.
    """
    user = make_user(db_session, "hr")
    db_session.commit()
    headers = auth_header(user)
    body = {"current_password": "wrong-guess", "new_password": "Brand-New-9876"}

    responses = [client.post("/api/auth/change-password", json=body, headers=headers) for _ in range(10)]
    assert all(r.status_code == 400 for r in responses), "رمزِ غلط باید ۴۰۰ بدهد، نه چیز دیگر"

    blocked = client.post("/api/auth/change-password", json=body, headers=headers)
    assert blocked.status_code == 429
    assert "بیش از حد مجاز" in blocked.json()["detail"]


def test_the_public_verify_endpoint_is_rate_limited(client):
    """تنها مسیرِ بی‌احراز‌هویتِ سامانه، و تنها دفاعش همین سقف.

    `/api/verify/{token}` عمداً با یک توکنِ تصادفی کار می‌کند و نه با
    `evaluation_code`ِ ترتیبی، تا کسی با شمارش نتواند نام و واحد و نتیجهٔ همهٔ
    پرسنل را بیرون بکشد. سقفِ نرخ نیمهٔ دومِ همان تصمیم است: بی آن، حدس‌زدنِ
    توکن فقط کندتر می‌شد، نه ناممکن.

    گارد از قبل بود و تست نداشت — یعنی حذفِ تصادفی‌اش هیچ‌جا دیده نمی‌شد.
    """
    responses = [client.get(f"/api/verify/no-such-token-{i}") for i in range(30)]
    assert all(r.status_code == 404 for r in responses), "توکنِ ناموجود باید ۴۰۴ بدهد"

    # توکنِ سی‌ویکم باز هم *متفاوت* است، و همین نکتهٔ تست است.
    #
    # گاردِ قبلی این‌جا نمی‌گرفت: `limiter.limit` سطل را بر اساسِ مسیرِ درخواست
    # می‌سازد و توکن جزوِ مسیر است، پس هر حدسِ تازه سهمیهٔ تازهٔ خودش را
    # داشت. یعنی سقف فقط جلوی بازکردنِ مکررِ *یک* سند را می‌گرفت — نه
    # حدس‌زدنِ توکن، که تنها دلیلِ وجودش بود.
    blocked = client.get("/api/verify/no-such-token-31")
    assert blocked.status_code == 429, (
        "سقفِ نرخِ این مسیر باید روی *همهٔ* توکن‌ها مشترک باشد، نه هر توکن "
        "سطلِ خودش (`shared_limit` و نه `limit`)."
    )


def test_every_public_route_carries_a_rate_limit():
    """قاعده، نه فهرستِ امروز.

    `routers/verify.py` تنها فایلی است که مسیرهایش احراز هویت ندارند. هر مسیرِ
    تازه‌ای که فردا این‌جا اضافه شود و سقف نداشته باشد، همان‌قدر قابلِ
    شمارش است که `evaluation_code` بود.
    """
    import re
    from pathlib import Path as _Path

    source = (_Path(__file__).resolve().parents[1] / "app" / "api" / "routers" / "verify.py").read_text(
        encoding="utf-8"
    )
    routes = re.findall(r"@router\.(?:get|post|put|patch|delete)\([^)]*\)\s*\n(.*?)def ", source, re.S)
    assert routes, "هیچ مسیری پیدا نشد؛ خودِ این سنجش شکسته است"
    unguarded = [block for block in routes if "@limiter.shared_limit" not in block]
    assert unguarded == [], (
        "این مسیرهای عمومی سقفِ نرخِ *مشترک* ندارند. هر چیزی در `verify.py` بی "
        "احراز هویت سرو می‌شود، و `limiter.limit`ِ ساده کافی نیست: سطلش را از "
        "مسیرِ درخواست می‌سازد، پس اگر شناسه‌ای در مسیر باشد هر مقدار سهمیهٔ "
        f"خودش را می‌گیرد. `shared_limit` لازم است: {unguarded}"
    )


def test_no_rate_limit_is_scoped_by_a_path_parameter():
    """قاعدهٔ کلیِ همان اشکال، در کلِ سامانه.

    `limiter.limit` سطلِ شمارش را از *مسیرِ درخواست* می‌سازد. تا وقتی مسیر ثابت
    است (`/api/auth/login`) این دقیقاً همان چیزی است که می‌خواهیم. ولی اگر
    مسیر پارامتر داشته باشد، هر مقدارِ تازه یک سطلِ تازه می‌گیرد و سقف عملاً
    وجود ندارد — و بدتر، *به‌نظر* وجود دارد.

    این همان چیزی بود که `/api/verify/{token}` را بی‌دفاع گذاشته بود: سقفش
    فقط جلوی بازکردنِ مکررِ یک سند را می‌گرفت و در برابر حدس‌زدنِ توکن هیچ
    کاری نمی‌کرد.

    فهرستِ امروز سنجیده نمی‌شود، خودِ قاعده: هر مسیرِ پارامتردارِ تازه‌ای که با
    `limit` بسته شود، همین‌جا می‌افتد.
    """
    import re
    from pathlib import Path as _Path

    routers = _Path(__file__).resolve().parents[1] / "app" / "api" / "routers"
    offenders = []
    for path in sorted(routers.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for route_path, block in re.findall(
            r"@router\.(?:get|post|put|patch|delete)\(\s*[\"']([^\"']*)[\"'][^)]*\)\s*\n(.*?)def ",
            source,
            re.S,
        ):
            if "{" not in route_path:
                continue
            if re.search(r"@limiter\.limit\(", block):
                offenders.append(f"{path.name}: {route_path}")

    assert offenders == [], (
        "این مسیرها پارامتر دارند و با `limiter.limit` بسته شده‌اند، یعنی هر "
        "مقدارِ پارامتر سهمیهٔ جداگانه می‌گیرد و سقف بی‌اثر است. "
        f"`limiter.shared_limit(..., scope=...)` لازم دارند: {offenders}"
    )
