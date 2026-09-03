from pydantic import BaseModel


class AppConfig(BaseModel):
    """قوانین کسب‌وکار که فرانت‌اند هم لازمشان دارد؛ از یک منبع واحد (backend) خوانده
    می‌شوند تا نسخه‌های کپی‌شده در UI با سرور واگرا نشوند."""

    evidence_min_words: int
    evidence_max_words: int
    # امتیازهایی که شواهد عینی برایشان اجباری است (پیش‌فرض [۱، ۵]).
    evidence_required_scores: list[int]
    general_section_weight: float
    specialized_section_weight: float
    # سقف امتیاز ویژه در طرح فعال؛ صفر یعنی فرم اصلاً این بخش را نشان ندهد.
    bonus_max_points: float
    # حداقل طول توضیح امتیاز ویژه؛ قاعدهٔ مشترک فرانت و سرور.
    bonus_reason_min_length: int
    #: {شناسهٔ شاخص: وزن} — شاخصِ غایب وزن ۱ دارد.
    #:
    #: بی این، پیش‌نمایشِ فرم *نمی‌توانست* درست باشد: `computePreview` هر شاخص
    #: را وزن ۱ می‌گرفت، در حالی که سرور از `rules.weight_for` استفاده می‌کند.
    #: روی هر طرحی با وزن‌های نابرابر، عددی که ارزیاب نگاه می‌کرد و تصمیمش را
    #: بر آن می‌ساخت با عددی که ثبت می‌شد یکی نبود — و «وزنِ هر شاخص» یکی از
    #: قابلیت‌های اصلیِ طرح است، نه یک گوشه.
    #:
    #: کلیدها در JSON رشته‌اند (قاعدهٔ خودِ JSON)؛ فرانت با همان `String(id)`
    #: می‌خواندشان.
    indicator_weights: dict[int, float]

    @classmethod
    def from_rules(cls, rules) -> "AppConfig":
        """`Rules` → شکلی که فرم لازم دارد.

        یک سازنده و نه دو، تا `/api/config` (طرحِ فعال) و جزئیاتِ پرونده
        (طرحِ خودِ پرونده) هرگز دو زیرمجموعهٔ متفاوت از قواعد نفرستند.
        """
        from app.core.text_limits import BONUS_REASON_MIN

        return cls(
            evidence_min_words=rules.evidence_min_words,
            evidence_max_words=rules.evidence_max_words,
            evidence_required_scores=list(rules.evidence_required_scores),
            general_section_weight=rules.general_section_weight,
            specialized_section_weight=rules.specialized_section_weight,
            bonus_max_points=rules.bonus_max_points,
            bonus_reason_min_length=BONUS_REASON_MIN,
            indicator_weights=dict(rules.indicator_weights),
        )
