"""قواعد نمره‌دهیِ جاری، برای فرم امتیازدهی در فرانت‌اند.

از طرح *فعال* خوانده می‌شود، نه از ثابت‌ها (P1-04). بدون این، HR می‌توانست
حداقل کلمات شواهد را عوض کند و فرم همچنان قاعدهٔ قدیمی را اعتبارسنجی کند —
یعنی کاربر تیک سبز می‌گرفت و بعد سرور ثبت را رد می‌کرد.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.common import AppConfig
from app.services.scoring_scheme import current_rules

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=AppConfig)
def get_config(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AppConfig:
    return AppConfig.from_rules(current_rules(db))
