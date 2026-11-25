"""Staff-only property facts. The public listing continues to live on Property."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Finding(models.TextChoices):
    UNKNOWN = "unknown", "Неизвестно"
    YES = "yes", "Да"
    NO = "no", "Нет"


class PropertyWorkspace(models.Model):
    class WorkStatus(models.TextChoices):
        UNKNOWN = "unknown", "Не определён"
        PREPARING = "preparing", "Подготовка"
        ACTIVE = "active", "В работе"
        PAUSED = "paused", "Приостановлен"
        DEPOSIT = "deposit", "Аванс или задаток"
        CLOSING = "closing", "Оформление сделки"
        SOLD = "sold", "Продан"
        LET = "let", "Сдан"
        RENEWAL = "renewal", "Ожидание продления договора"
        EXPIRED = "expired", "Договор истёк"
        TERMINATED = "terminated", "Договор расторгнут"

    class Occupancy(models.TextChoices):
        UNKNOWN = "unknown", "Неизвестно"
        OWNERS = "owners", "Собственники"
        TENANTS = "tenants", "Арендаторы"
        VACANT = "vacant", "Никто"

    class Keys(models.TextChoices):
        UNKNOWN = "unknown", "Неизвестно"
        AGENT = "agent", "У агента"
        OWNER = "owner", "У собственника"
        OTHER = "other", "Другое"

    class Furnishing(models.TextChoices):
        UNKNOWN = "unknown", "Не согласовано"
        ALL = "all", "Остаётся всё"
        PART = "part", "Остаётся часть"
        NONE = "none", "Ничего"

    class Ownership(models.TextChoices):
        UNKNOWN = "unknown", "Неизвестно"
        SOLE = "sole", "Единоличная"
        JOINT = "joint", "Совместная"
        SHARED = "shared", "Долевая"

    class Encumbrances(models.TextChoices):
        UNKNOWN = "unknown", "Не проверены"
        CLEAR = "clear", "Не выявлены по указанному источнику"
        FOUND = "found", "Выявлены"

    class Alterations(models.TextChoices):
        UNKNOWN = "unknown", "Не проверена"
        NONE = "none", "Отсутствует"
        LEGAL = "legal", "Узаконена"
        UNCONFIRMED = "unconfirmed", "Согласование не подтверждено"

    property = models.OneToOneField("core.Property", on_delete=models.CASCADE, related_name="staff_workspace")
    work_status = models.CharField("Рабочий статус", max_length=12, choices=WorkStatus.choices, default=WorkStatus.UNKNOWN)
    status_reason = models.CharField("Причина статуса", max_length=255, blank=True)
    status_date = models.DateField("Дата статуса", null=True, blank=True)
    status_comment = models.TextField("Комментарий к статусу", blank=True)
    status_changed_at = models.DateTimeField(null=True, blank=True, editable=False)
    status_changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                          null=True, blank=True, editable=False, related_name="+")
    occupancy = models.CharField("Проживание", max_length=12, choices=Occupancy.choices, default=Occupancy.UNKNOWN)
    registered_people = models.TextField("Зарегистрированные лица и условия снятия", blank=True)
    release_date = models.DateField("Срок освобождения", null=True, blank=True)
    release_terms = models.TextField("Условия освобождения", blank=True)
    keys_available = models.CharField("Наличие ключей", max_length=12, choices=Finding.choices, default=Finding.UNKNOWN)
    keys_location = models.CharField("Место ключей (без кодов доступа)", max_length=12,
                                     choices=Keys.choices, default=Keys.UNKNOWN)
    furnishing = models.CharField("Мебель и техника", max_length=12, choices=Furnishing.choices, default=Furnishing.UNKNOWN)
    furnishing_comment = models.TextField("Пояснение к комплектации", blank=True)
    payment_methods = models.TextField("Способы расчёта", blank=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                 limit_choices_to={"is_staff": True, "is_active": True}, related_name="+")
    facts_current_on = models.DateField("Дата актуальности сведений", null=True, blank=True)
    documented_area = models.DecimalField("Площадь по документу, м²", max_digits=8, decimal_places=2,
                                          null=True, blank=True)
    documented_area_source = models.CharField("Источник площади по документу", max_length=255, blank=True)
    documented_area_checked_on = models.DateField("Когда проверена площадь по документу", null=True, blank=True)
    ownership = models.CharField("Вид собственности", max_length=12, choices=Ownership.choices, default=Ownership.UNKNOWN)
    owner_count = models.PositiveSmallIntegerField("Количество собственников", null=True, blank=True)
    encumbrances = models.CharField("Обременения", max_length=12, choices=Encumbrances.choices, default=Encumbrances.UNKNOWN)
    encumbrance_source = models.CharField("Источник проверки обременений", max_length=255, blank=True)
    encumbrance_checked_on = models.DateField("Дата проверки обременений", null=True, blank=True)
    encumbrance_comment = models.TextField("Пояснение об обременениях", blank=True)
    minor_owners = models.CharField("Несовершеннолетние собственники", max_length=12,
                                    choices=Finding.choices, default=Finding.UNKNOWN)
    registered_minors = models.CharField("Зарегистрированные несовершеннолетние", max_length=12,
                                         choices=Finding.choices, default=Finding.UNKNOWN)
    alterations = models.CharField("Перепланировка", max_length=15,
                                   choices=Alterations.choices, default=Alterations.UNKNOWN)
    legal_comments = models.TextField("Юридические ограничения и нюансы", blank=True)
    drive_folder_id = models.CharField("ID папки Google Drive", max_length=255, blank=True)

    class Meta:
        verbose_name = "Рабочий паспорт объекта"
        verbose_name_plural = "Рабочие паспорта объектов"

    def __str__(self):
        return str(self.property)

    def clean(self):
        errors = {}
        if self.encumbrances != self.Encumbrances.UNKNOWN:
            if not self.encumbrance_source.strip():
                errors["encumbrance_source"] = "Укажите источник проверки."
            if self.encumbrance_checked_on is None:
                errors["encumbrance_checked_on"] = "Укажите дату проверки."
        if self.documented_area is not None:
            if self.documented_area < 0:
                errors["documented_area"] = "Площадь не может быть отрицательной."
            if not self.documented_area_source.strip():
                errors["documented_area_source"] = "Укажите источник площади."
            if self.documented_area_checked_on is None:
                errors["documented_area_checked_on"] = "Укажите дату проверки площади."
        if errors:
            raise ValidationError(errors)


class WorkspaceRecord(models.Model):
    is_current = models.BooleanField("Актуальна", default=True, editable=False)

    class Meta:
        abstract = True


class OwnershipBasis(WorkspaceRecord):
    class Kind(models.TextChoices):
        UNKNOWN = "unknown", "Неизвестно"
        PURCHASE = "purchase", "Купля-продажа"
        INHERITANCE = "inheritance", "Наследство"
        GIFT = "gift", "Дарение"
        PRIVATIZATION = "privatization", "Приватизация"
        PARTICIPATION = "participation", "ДДУ"
        OTHER = "other", "Другое"

    workspace = models.ForeignKey(PropertyWorkspace, on_delete=models.CASCADE, related_name="ownership_bases")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.UNKNOWN)
    document_date = models.DateField("Дата основания", null=True, blank=True)
    source = models.CharField("Источник", max_length=255, blank=True)


class PropertyOwner(WorkspaceRecord):
    workspace = models.ForeignKey(PropertyWorkspace, on_delete=models.CASCADE, related_name="owners")
    name = models.CharField("Имя собственника", max_length=255)
    share_numerator = models.PositiveIntegerField("Числитель доли", null=True, blank=True)
    share_denominator = models.PositiveIntegerField("Знаменатель доли", null=True, blank=True)

    def clean(self):
        numerator, denominator = self.share_numerator, self.share_denominator
        if (numerator is None) != (denominator is None) or (
            numerator is not None and denominator is not None and not (0 < numerator <= denominator)
        ):
            raise ValidationError("Укажите оба числа доли. Числитель и знаменатель должны быть положительными.")


class DriveFile(WorkspaceRecord):
    workspace = models.ForeignKey(PropertyWorkspace, on_delete=models.CASCADE, related_name="drive_files")
    file_id = models.CharField("ID файла", max_length=255, unique=True)
    name = models.CharField("Название файла", max_length=255)
    url = models.URLField("Защищённая ссылка", max_length=1000, blank=True)
    modified_at = models.DateTimeField("Время изменения файла", null=True, blank=True)
    synced_at = models.DateTimeField("Время синхронизации", null=True, blank=True)

    def clean(self):
        if self.url and not self.url.startswith("https://"):
            raise ValidationError({"url": "Используйте HTTPS-ссылку на оригинал."})

    def __str__(self):
        return self.name


class PropertyDocumentType(models.Model):
    slug = models.SlugField(unique=True)
    title = models.CharField("Название", max_length=140)

    def __str__(self):
        return self.title


class PropertyDocument(WorkspaceRecord):
    class Applicability(models.TextChoices):
        UNKNOWN = "unknown", "Не выяснено"
        NOT_NEEDED = "not_needed", "Не требуется"
        REQUIRED = "required", "Требуется"

    class Availability(models.TextChoices):
        UNKNOWN = "unknown", "Неизвестно"
        MISSING = "missing", "Отсутствует"
        PRESENT = "present", "Имеется"

    class Review(models.TextChoices):
        UNKNOWN = "unknown", "Не проверено"
        CHECKED = "checked", "Проверено"
        ISSUES = "issues", "Имеются замечания"

    workspace = models.ForeignKey(PropertyWorkspace, on_delete=models.CASCADE, related_name="documents")
    document_type = models.ForeignKey(PropertyDocumentType, on_delete=models.PROTECT)
    applicability = models.CharField(max_length=12, choices=Applicability.choices, default=Applicability.UNKNOWN)
    availability = models.CharField(max_length=12, choices=Availability.choices, default=Availability.UNKNOWN)
    verification = models.CharField(max_length=12, choices=Review.choices, default=Review.UNKNOWN)
    document_date = models.DateField("Дата документа", null=True, blank=True)
    checked_on = models.DateField("Дата проверки", null=True, blank=True)
    source = models.CharField("Источник", max_length=255, blank=True)
    comment = models.TextField("Комментарий", blank=True)
    original = models.ForeignKey(DriveFile, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")

    def clean(self):
        errors = {}
        if self.original_id and self.original.workspace_id != self.workspace_id:
            errors["original"] = "Выберите файл этого объекта."
        if self.availability == self.Availability.MISSING and self.verification == self.Review.CHECKED:
            errors["verification"] = "Отсутствующий документ нельзя отметить проверенным. Для замечания укажите результат поиска."
        if self.availability == self.Availability.MISSING and self.original_id:
            errors["original"] = "У отсутствующего документа не может быть привязан оригинал."
        if self.original_id and not self.original.is_current and self.is_current:
            errors["original"] = "Выберите актуальный файл этого объекта."
        if self.verification != self.Review.UNKNOWN and self.checked_on is None:
            errors["checked_on"] = "Укажите дату проверки."
        if errors:
            raise ValidationError(errors)


class PropertyNote(WorkspaceRecord):
    workspace = models.ForeignKey(PropertyWorkspace, on_delete=models.CASCADE, related_name="notes")
    text = models.TextField("Оперативная заметка")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class MarketplaceListing(models.Model):
    class Platform(models.TextChoices):
        CIAN = "cian", "ЦИАН"
        DOMKLIK = "domklik", "Домклик"
        AVITO = "avito", "Авито"

    class Publication(models.TextChoices):
        UNKNOWN = "unknown", "Не проверена"
        PUBLISHED = "published", "Опубликовано"
        NOT_PUBLISHED = "not_published", "Не опубликовано"
        REJECTED = "rejected", "Отклонено"

    workspace = models.ForeignKey(PropertyWorkspace, on_delete=models.CASCADE, related_name="marketplace_listings")
    platform = models.CharField(max_length=12, choices=Platform.choices)
    external_id = models.CharField("ID объявления", max_length=255, blank=True)
    url = models.URLField("Ссылка на объявление", max_length=1000, blank=True)
    publication = models.CharField(max_length=16, choices=Publication.choices, default=Publication.UNKNOWN)
    checked_on = models.DateTimeField("Последняя проверка", null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("workspace", "platform"), name="workspace_platform_unique")]

    def clean(self):
        if self.publication != self.Publication.UNKNOWN and self.checked_on is None:
            raise ValidationError({"checked_on": "Укажите время проверки объявления."})


class PropertyChange(models.Model):
    property = models.ForeignKey("core.Property", on_delete=models.CASCADE, related_name="staff_changes")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    source = models.CharField(max_length=24)
    scope = models.CharField(max_length=32)
    record_id = models.PositiveBigIntegerField(null=True)
    fields = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
