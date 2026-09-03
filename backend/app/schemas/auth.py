from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserRole


class LoginRequest(BaseModel):
    """ورودیِ ورود، با سقفِ طول روی هر دو میدان.

    بی سقف، Argon2 هرچه رسیده را هش می‌کند و تنها مهارِ موجود
    `client_max_body_size 20m` در nginx بود — عددی که برای *بارگذاریِ فایلِ
    دستیار* انتخاب شده و ربطی به فرمِ ورود ندارد. یعنی یک درخواستِ
    احراز‌هویت‌نشده می‌توانست چند مگابایت رمز بفرستد و پروسه را روی تابعِ
    عمداً کندِ هش نگه دارد.

    ۲۵۶ سخاوتمندانه است: از سقفِ عملیِ هر مدیرِ رمزی بیشتر است و هیچ رمزِ
    واقعی‌ای را رد نمی‌کند. سقفِ نام کاربری هم از ستونِ خودش می‌آید.
    """

    username: str = Field(max_length=150)
    password: str = Field(max_length=256)


class LoginResponse(BaseModel):
    """refresh token عمداً در بدنه پاسخ نیست؛ فقط به‌صورت کوکی HttpOnly ست می‌شود
    تا از دسترس اسکریپت‌ها (XSS) خارج باشد."""

    access_token: str
    token_type: str = "bearer"
    role: UserRole
    must_change_password: bool = False


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)


class CurrentUser(BaseModel):
    id: int
    username: str
    # نامی که در نوار بالای صفحه دیده می‌شود. اگر روی حساب ثبت نشده باشد همان
    # نام کاربری است، پس همیشه مقدار دارد و UI لازم نیست fallback بنویسد.
    display_name: str = ""
    role: UserRole
    personnel_id: int | None = None
    must_change_password: bool = False


class SessionRead(BaseModel):
    """یک نشست فعال، آن‌قدر که کاربر بتواند تشخیصش بدهد.

    jti عمداً برنمی‌گردد: شناسهٔ عددیِ ردیف برای «این یکی را ببند» کافی است، و
    خودِ jti بخشی از یک توکن زنده است که نباید در پاسخ API پخش شود.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_agent: str | None
    ip: str | None
    created_at: datetime
    last_used_at: datetime | None
    # آیا همین نشستی است که این درخواست با آن آمده؟ بدون این، کاربر نمی‌داند
    # کدام ردیف را نباید ببندد.
    is_current: bool = False
