# --- optional pytest guard (keeps manage.py test green without pytest) ---
try:
    import pytest  # noqa: F401
except Exception:  # pragma: no cover
    pytest = None

import unittest  # noqa: E402
if pytest is None:  # pragma: no cover
    raise unittest.SkipTest("pytest is not installed; skipping this test module")

from decimal import Decimal
from xml.etree.ElementTree import tostring

from core.cian import build_ad_xml, resolve_category
from core.models import Property


@pytest.mark.django_db
def test_flat_sale_agent_bonus_payment_type_and_currency():
    prop = Property.objects.create(
        category="flat",
        operation="sale",
        external_id="BONUS-001",
        description="Квартира с бонусом",
        address="Москва",
        price=Decimal("123456.78"),
        currency="eur",
        agent_bonus_value=Decimal("4.2"),
        agent_bonus_is_percent=True,
    )

    result = build_ad_xml(prop)
    bonus = result.element.find("./BargainTerms/AgentBonus")

    assert bonus is not None
    assert bonus.findtext("Value") == "4.2"
    assert bonus.findtext("PaymentType") == "percent"
    assert bonus.findtext("Currency") == "EUR"


@pytest.mark.django_db
def test_room_sale_uses_room_area():
    prop = Property.objects.create(
        category="room",
        operation="sale",
        external_id="ROOM-AREA-1",
        description="Комната",
        address="Москва",
        price=Decimal("2100000"),
        currency="rur",
        total_area=Decimal("4.2"),
    )

    result = build_ad_xml(prop)
    xml_text = tostring(result.element, encoding="unicode")

    assert "<RoomArea>4.2</RoomArea>" in xml_text
    assert "<TotalArea>" not in xml_text


@pytest.mark.django_db
def test_flat_rent_category_and_deposit_term():
    prop = Property.objects.create(
        category="flat",
        operation="rent_long",
        external_id="RENT-001",
        description="Аренда квартиры",
        address="Москва",
        price=Decimal("50000"),
        currency="rur",
        flat_rooms_count=1,
        total_area=Decimal("38.5"),
        floor_number=6,
        security_deposit=Decimal("10000"),
        min_rent_term_months=11,
    )

    result = build_ad_xml(prop)
    assert result.element.findtext("Category") == "flatRent"

    bargain = result.element.find("./BargainTerms")
    assert bargain is not None
    assert bargain.findtext("SecurityDeposit") == "10000"
    assert bargain.findtext("MinRentTermMonths") == "11"


@pytest.mark.django_db
def test_phones_country_code_with_plus():
    prop = Property.objects.create(
        category="flat",
        operation="sale",
        external_id="PHONE-001",
        description="Телефон",
        address="Москва",
        price=Decimal("3500000"),
        currency="rur",
        phone_country="7",
        phone_number="9161234567",
    )

    result = build_ad_xml(prop)
    schema = result.element.find("./Phones/PhoneSchema")

    assert schema is not None
    assert schema.findtext("CountryCode") == "+7"
    assert schema.findtext("Number") == "9161234567"


@pytest.mark.django_db
def test_house_sale_category_is_not_changed():
    prop = Property.objects.create(
        category="house",
        operation="sale",
        external_id="HOUSE-CAT-1",
        description="Дом",
        address="Сергиев Посад",
        price=Decimal("8000000"),
        currency="rur",
    )

    assert resolve_category(prop) == "houseSale"

    result = build_ad_xml(prop)
    assert result.element.findtext("Category") == "houseSale"
