from pydantic import BaseModel, ConfigDict, Field


class OrgUnitCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    #: خالی یعنی واحدی که به محل خاصی وابسته نیست.
    site: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=150)


class OrgUnitUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    site: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    is_active: bool | None = None
    #: واحدِ منابع انسانی — پروندهٔ اعضایش مرحلهٔ بررسیِ منابع انسانی ندارد.
    is_hr_unit: bool | None = None


class OrgUnitRead(BaseModel):
    id: int
    site: str | None
    name: str
    #: همان رشته‌ای که در `personnel.org_unit` می‌نشیند («محل / واحد»).
    full_name: str
    is_active: bool
    #: واحدِ منابع انسانی. تنها اثرش شکلِ زنجیرهٔ ارزیابیِ اعضای همین واحد است:
    #: پروندهٔ آن‌ها مرحلهٔ بررسیِ منابع انسانی را ندارد، چون داورِ آن مرحله
    #: هم‌تیمیِ خودشان می‌شد.
    is_hr_unit: bool = False
    display_order: int
    #: چند نفر همین حالا در این واحدند — تا «حذف» یک تصمیم کور نباشد.
    personnel_count: int
