# core/models.py
import builtins
import random

from django.db import models
from django.utils import timezone


def gen_external_id():
    """
    Stable default used by historical migrations.
    Keep this function available permanently so that
    'default=core.models.gen_external_id' imports resolve during migrate.
    """
    ts = timezone.now().strftime("%Y%m%d%H%M%S")
    return f"AG{ts}{random.randint(100, 999)}"

CATEGORY_CHOICES = [
    ("house", "Дом"),
    ("flat", "Квартира"),
    ("room", "Комната"),
    ("commercial", "Коммерция"),
    ("land", "Земля"),
    ("garage", "Гараж"),
]

OPERATION_CHOICES = [
    ("sale", "Продажа"),
    ("rent_long", "Аренда"),
    ("rent_daily", "Посуточно"),
]

FLAT_SUBTYPE_CHOICES = [
    ("apartment", "Квартира"),
    ("studio", "Студия"),
    ("apartments", "Апартаменты"),
    ("penthouse", "Пентхаус"),
]

ROOM_SUBTYPE_CHOICES = [
    ("room", "Комната"),
    ("share", "Доля комнаты/комната в квартире"),
]

HOUSE_TYPE_CHOICES = [
    ("house", "Жилой дом"),
    ("dacha", "Дача"),
    ("townhouse", "Таунхаус"),
    ("cottage", "Коттедж"),
]

COMMERCIAL_SUBTYPE_CHOICES = [
    ("office", "Офис"),
    ("retail", "Торговая"),
    ("warehouse", "Склад"),
    ("production", "Производство"),
    ("free_purpose", "Свободное назначение"),
]

LAND_SUBTYPE_CHOICES = [
    ("izh", "ИЖС"),
    ("agriculture", "С/Х"),
    ("garden", "СНТ/садовый участок"),
]

WINDOWS_VIEW_CHOICES = [("street","На улицу"),("yard","Во двор"),("yardAndStreet","На улицу и двор")]
REPAIR_TYPE_CHOICES = [("cosmetic","Косметический"),("design","Дизайнерский"),("euro","Евроремонт"),("no","Без ремонта")]
MATERIAL_TYPE_CHOICES = [
    ("aerocreteBlock","Газобетонный блок"),("arbolit","Арболит"),("boards","Щитовой"),
    ("brick","Кирпичный"),("expandedClayConcrete","Керамзитобетон"),
    ("foamConcreteBlock","Пенобетонный блок"),("gasSilicateBlock","Газосиликатный блок"),
    ("gluedLaminatedTimber","Клееный брус"),("metalFrame","Металлокаркас"),
    ("monolith","Монолит"),("reinforcedConcretePanels","ЖБ панели"),
    ("sipPanels","СИП-панели"),("slagConcrete","Шлакобетон"),
    ("solidWood","Цельное дерево"),("wireframe","Каркасный"),("wood","Деревянный"),
]
HEATING_TYPE_CHOICES = [
    ("central", "Центральное"),
    ("gas", "Газовое"),
    ("electric", "Электро"),
    ("solid", "Твёрдое топливо"),
]
WC_LOCATION_CHOICES = [("outside", "На улице"), ("inside", "В доме")]
SEWERAGE_TYPE_CHOICES = [
    ("central", "Центральная"),
    ("septic", "Септик"),
    ("cesspool", "Выгребная яма"),
    ("none", "Нет"),
]
WATER_SUPPLY_TYPE_CHOICES = [
    ("central", "Центральное"),
    ("borehole", "Скважина"),
    ("well", "Колодец"),
    ("none", "Нет"),
]
GAS_SUPPLY_TYPE_CHOICES = [
    ("main_on_plot", "Магистральный в доме или на участке"),
    ("border", "По границе участка"),
    ("gasholder", "Газгольдер"),
    ("none", "Нет"),
]
HOUSE_CONDITION_CHOICES = [
    ("ready", "Можно жить"),
    ("needs_repair", "Нужен ремонт"),
    ("need_finish", "Нужно достроить"),
    ("needs_capital_or_demolition", "Нужен капремонт или под снос"),
]
LAND_AREA_UNIT_CHOICES = [("sotka", "Сотка"), ("sqm", "м²")]
PERMITTED_LAND_USE_CHOICES = [
    ("individualHousingConstruction","ИЖС"),("privateFarm","ЛПХ"),
    ("gardening","Садоводство"),("horticulture","Огородничество"),
    ("suburbanNonProfitPartnership","Дачное хозяйство"),("farm","Фермерское хозяйство"),
    ("other","Иное"),
]
LAND_CATEGORY_CHOICES = [("settlements","Земли населенных пунктов"),("forAgriculturalPurposes","С/Х назначения"),("other","Иное")]
CURRENCY_CHOICES = [("rur","RUB"),("usd","USD"),("eur","EUR")]
ROOM_TYPE_CHOICES = [
    ("separate", "Изолированная"),
    ("combined", "Смежная"),
    ("both", "Смежно‑изолированная"),
]
SALE_TYPE_CHOICES = [
    ("free", "Свободная"),
    ("alternative", "Альтернативная"),
]
STATUS_CHOICES = [("active", "Активен"), ("archived", "В архиве")]

class Property(models.Model):
    # Базовое
    external_id = models.CharField(
        "Внешний ID",
        max_length=100,
        unique=True,
        blank=True,
    )
    category = models.CharField(
        "Тип объекта",
        max_length=20,
        choices=CATEGORY_CHOICES,
        blank=True,
        null=True,
    )
    operation = models.CharField(
        "Тип сделки",
        max_length=20,
        choices=OPERATION_CHOICES,
        blank=True,
        null=True,
    )
    subtype = models.CharField("Подтип", max_length=30, blank=True, null=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="active",
        verbose_name="Статус",
    )

    export_to_cian = models.BooleanField(default=True, verbose_name="Экспорт в ЦИАН")
    export_to_domklik = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False, verbose_name="В архиве")

    title = models.CharField("Заголовок (внутр.)", max_length=64, blank=True)
    description = models.TextField("Описание", blank=True)

    address = models.CharField("Адрес (как на Я.Картах)", max_length=255, blank=True)
    lat = models.DecimalField("Широта", max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField("Долгота", max_digits=9, decimal_places=6, null=True, blank=True)
    cadastral_number = models.CharField("Кадастровый номер", max_length=64, blank=True)

    phone_country = models.CharField(
        "Код страны", max_length=8, blank=True, default="7"
    )
    phone_number = models.CharField("Телефон №1", max_length=32, blank=True)
    phone_number2 = models.CharField("Телефон №2 (опц.)", max_length=32, blank=True)

    # Медиа
    layout_photo_url = models.URLField("URL планировки (опц.)", blank=True)
    object_tour_url = models.URLField("URL 3D-тура (опц.)", blank=True)

    # Здание
    building_name = models.CharField("Название здания/ЖК (опц.)", max_length=128, blank=True)
    building_floors = models.PositiveIntegerField("Этажей в здании", null=True, blank=True)
    building_build_year = models.PositiveIntegerField("Год постройки", null=True, blank=True)
    building_material = models.CharField("Материал здания", max_length=64, choices=MATERIAL_TYPE_CHOICES, blank=True)
    building_ceiling_height = models.DecimalField("Высота потолков, м", max_digits=4, decimal_places=2, null=True, blank=True)
    building_passenger_lifts = models.PositiveSmallIntegerField("Пассажирских лифтов", null=True, blank=True)
    building_cargo_lifts = models.PositiveSmallIntegerField("Грузовых лифтов", null=True, blank=True)
    building_series = models.CharField("Серия дома (опц.)", max_length=64, blank=True)
    building_has_garbage_chute = models.BooleanField("Мусоропровод", default=False)
    building_parking = models.CharField("Парковка (опис.)", max_length=64, blank=True)

    # Квартира
    flat_type = models.CharField(max_length=20, choices=FLAT_SUBTYPE_CHOICES, null=True, blank=True, verbose_name="Подтип квартиры")
    room_type = models.CharField("Тип комнат", max_length=16, choices=ROOM_TYPE_CHOICES, blank=True)
    sale_type = models.CharField("Тип продажи", max_length=12, choices=SALE_TYPE_CHOICES, blank=True)
    flat_rooms_count = models.PositiveSmallIntegerField("Кол-во комнат (кв.)", null=True, blank=True)
    room_type_ext = models.CharField(max_length=30, choices=ROOM_SUBTYPE_CHOICES, null=True, blank=True, verbose_name="Подтип комнаты")
    rooms_for_sale_count = models.PositiveSmallIntegerField("Комнат продаётся", null=True, blank=True)
    is_euro_flat = models.BooleanField("Европланировка", default=False)
    is_apartments = models.BooleanField("Апартаменты (юрид.)", default=False)
    is_penthouse = models.BooleanField("Пентхаус", default=False)
    beds_count = models.PositiveSmallIntegerField("Спальных мест", null=True, blank=True)
    total_area = models.DecimalField(
        "Общая площадь, м²",
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )
    living_area = models.DecimalField(
        "Жилая площадь, м²",
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )
    kitchen_area = models.DecimalField(
        "Площадь кухни, м²",
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )
    rooms = models.PositiveSmallIntegerField("Количество комнат", null=True, blank=True)
    floor_number = models.PositiveSmallIntegerField("Этаж", null=True, blank=True)
    loggias_count = models.PositiveSmallIntegerField("Лоджии", null=True, blank=True)
    balconies_count = models.PositiveSmallIntegerField("Балконы", null=True, blank=True)
    windows_view_type = models.CharField("Куда окна", max_length=20, choices=WINDOWS_VIEW_CHOICES, blank=True)
    separate_wcs_count = models.PositiveSmallIntegerField("Раздельные с/у", null=True, blank=True)
    combined_wcs_count = models.PositiveSmallIntegerField("Совмещённые с/у", null=True, blank=True)
    repair_type = models.CharField("Ремонт", max_length=16, choices=REPAIR_TYPE_CHOICES, blank=True)

    # ЖК/корпус
    jk_id = models.PositiveIntegerField("ID ЖК (ЦИАН)", null=True, blank=True)
    jk_name = models.CharField("Название ЖК", max_length=128, blank=True)
    house_id = models.PositiveBigIntegerField("ID корпуса (ЦИАН)", null=True, blank=True)
    house_name = models.CharField("Название корпуса", max_length=128, blank=True)
    flat_number = models.CharField("Номер квартиры (не показывается)", max_length=32, blank=True)
    section_number = models.CharField("№ секции", max_length=32, blank=True)

    # Загород / участок
    house_type = models.CharField(max_length=20, choices=HOUSE_TYPE_CHOICES, null=True, blank=True, verbose_name="Подтип дома")
    bedrooms_count = models.PositiveSmallIntegerField("Количество спален", null=True, blank=True)
    wc_location = models.CharField("Санузел", max_length=12, choices=WC_LOCATION_CHOICES, blank=True)
    sewerage_type = models.CharField("Канализация", max_length=12, choices=SEWERAGE_TYPE_CHOICES, blank=True)
    has_drainage = models.BooleanField("Есть канализация", default=False)
    water_supply_type = models.CharField("Водоснабжение", max_length=12, choices=WATER_SUPPLY_TYPE_CHOICES, blank=True)
    has_water = models.BooleanField("Есть водоснабжение", default=False)
    gas_supply_type = models.CharField("Газ", max_length=16, choices=GAS_SUPPLY_TYPE_CHOICES, blank=True)
    has_gas = models.BooleanField("Есть газ", default=False)
    has_electricity = models.BooleanField("Электричество", default=False)
    house_condition = models.CharField("Состояние дома", max_length=32, choices=HOUSE_CONDITION_CHOICES, blank=True)
    has_garage = models.BooleanField("Гараж", default=False)
    heating_type = models.CharField("Отопление", max_length=20, choices=HEATING_TYPE_CHOICES, blank=True)
    land_area = models.DecimalField("Площадь участка", max_digits=8, decimal_places=2, null=True, blank=True)
    land_area_unit = models.CharField("Единица участка", max_length=10, choices=LAND_AREA_UNIT_CHOICES, blank=True)
    permitted_land_use = models.CharField("ВРИ участка", max_length=48, choices=PERMITTED_LAND_USE_CHOICES, blank=True)
    is_land_with_contract = models.BooleanField("Участок с подрядом", default=False)
    land_category = models.CharField("Категория земель", max_length=32, choices=LAND_CATEGORY_CHOICES, blank=True)
    land_type = models.CharField(max_length=20, choices=LAND_SUBTYPE_CHOICES, null=True, blank=True, verbose_name="Подтип земельного участка")
    has_terrace = models.BooleanField("Есть терраса", default=False)
    has_cellar = models.BooleanField("Есть погреб", default=False)
    has_pool = models.BooleanField("Бассейн", default=False)
    has_bathhouse = models.BooleanField("Баня", default=False)
    has_security = models.BooleanField("Охрана", default=False)

    # Коммерция / дом (частые)
    commercial_type = models.CharField(max_length=20, choices=COMMERCIAL_SUBTYPE_CHOICES, null=True, blank=True, verbose_name="Подтип коммерции")
    is_rent_by_parts = models.BooleanField("Сдаётся по частям", default=False)
    rent_by_parts_desc = models.CharField("Описание сдачи части", max_length=255, blank=True)
    ceiling_height = models.DecimalField("Высота потолков, м", max_digits=4, decimal_places=2, null=True, blank=True)
    power = models.PositiveIntegerField(
        "Выделенная мощность, кВт",
        null=True,
        blank=True,
        help_text="Для коммерческих объектов ЦИАН",
    )
    parking_places = models.PositiveIntegerField(
        "Паркомест",
        null=True,
        blank=True,
        help_text="Количество мест для коммерческих объявлений",
    )
    has_parking = models.BooleanField("Есть парковка", default=False)

    # Удобства (жилые)
    furnishing_details = models.CharField("Комплектация (опис.)", max_length=255, blank=True)
    has_internet = models.BooleanField("Интернет", default=False)
    has_furniture = models.BooleanField("Мебель", default=False)
    has_kitchen_furniture = models.BooleanField("Мебель на кухне", default=False)
    has_tv = models.BooleanField("Телевизор", default=False)
    has_washer = models.BooleanField("Стиральная машина", default=False)
    has_conditioner = models.BooleanField("Кондиционер", default=False)
    has_refrigerator = models.BooleanField("Холодильник", default=False)
    has_dishwasher = models.BooleanField("Посудомойка", default=False)
    has_shower = models.BooleanField("Душ", default=False)
    has_phone = models.BooleanField("Телефон (городской)", default=False)
    has_ramp = models.BooleanField(
        "Пандус",
        default=False,
        help_text="Наличие пандуса для коммерческого объекта",
    )
    has_bathtub = models.BooleanField("Ванна", default=False)

    # Сделка
    price = models.DecimalField("Цена", max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField("Валюта", max_length=3, choices=CURRENCY_CHOICES, default="rur")
    mortgage_allowed = models.BooleanField("Ипотека возможна", default=False)
    agent_bonus_value = models.DecimalField("Бонус агенту (число)", max_digits=10, decimal_places=2, null=True, blank=True)
    agent_bonus_is_percent = models.BooleanField("Бонус в %", default=False)
    security_deposit = models.DecimalField("Залог (аренда)", max_digits=10, decimal_places=2, null=True, blank=True)
    min_rent_term_months = models.PositiveSmallIntegerField("Мин. срок аренды (мес.)", null=True, blank=True)
    lease_term_type = models.CharField("Тип срока аренды", max_length=16, blank=True)
    prepay_months = models.PositiveSmallIntegerField("Предоплата (мес.)", null=True, blank=True)
    deposit = models.DecimalField("Залог (Deposit)", max_digits=10, decimal_places=2, null=True, blank=True)
    client_fee = models.DecimalField("Комиссия клиента", max_digits=10, decimal_places=2, null=True, blank=True)
    agent_fee = models.DecimalField("Комиссия агента", max_digits=10, decimal_places=2, null=True, blank=True)
    utilities_terms = models.CharField("Коммуналка (условия)", max_length=64, blank=True)
    bargain_allowed = models.BooleanField("Торг уместен", default=False)
    bargain_price = models.DecimalField("Цена по торгу", max_digits=12, decimal_places=2, null=True, blank=True)
    bargain_conditions = models.CharField("Условия торга", max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        base = f"{self.get_category_display()} | {self.address or ''}".strip()
        return f"{base} [{self.external_id}]"

    def save(self, *args, **kwargs):
        if not getattr(self, "external_id", None):
            for _ in range(6):
                candidate = gen_external_id()
                if not type(self).objects.filter(external_id=candidate).exists():
                    self.external_id = candidate
                    break
            else:
                raise ValueError("Не удалось сгенерировать уникальный external_id")
        super().save(*args, **kwargs)

class Photo(models.Model):
    property = models.ForeignKey(
        "Property", related_name="photos", on_delete=models.CASCADE
    )
    image = models.ImageField(
        upload_to="photos/%Y/%m/%d", null=True, blank=True
    )
    full_url = models.URLField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    sort = models.PositiveIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "sort", "id"]

    def __str__(self):
        if self.image:
            return self.image.name
        if self.full_url:
            return self.full_url
        return f"Photo #{self.pk}" if self.pk else "Photo"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        storage = getattr(self.image, "storage", None)
        name = getattr(self.image, "name", None)
        super().delete(using=using, keep_parents=keep_parents)
        try:
            if storage and name:
                storage.delete(name)
        except Exception:
            pass

    def file_size_bytes(self):
        try:
            f = self.image
            if not f:
                return None
            size = getattr(f, "size", None)
            if size is None:
                try:
                    f.open("rb")
                    size = f.size
                finally:
                    try:
                        f.close()
                    except Exception:
                        pass
            return int(size) if size is not None else None
        except Exception:
            return None

    def human_size(self):
        size = self.file_size_bytes()
        if not size:
            return "URL" if self.full_url and not self.image else ""
        units = ["Б", "КБ", "МБ", "ГБ"]
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:.0f} Б" if unit == "Б" else f"{size:.1f} {unit}"
            size = size / 1024

    @builtins.property
    def src(self):
        try:
            if self.image:
                return self.image.url
        except Exception:
            pass
        return self.full_url or ""
