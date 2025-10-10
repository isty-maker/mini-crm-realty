from decimal import Decimal
from xml.etree.ElementTree import fromstring

import pytest

from core.cian import build_cian_feed
from core.models import Photo, Property


@pytest.mark.django_db
def test_flat_rent_beds_and_terms():
    prop = Property.objects.create(
        category="flat",
        operation="rent_long",
        address="Москва",
        total_area=Decimal("33.5"),
        floor_number=7,
        flat_rooms_count=2,
        beds_count=3,
        lease_term_type="longTerm",
        prepay_months=1,
        deposit=Decimal("55000"),
        price=Decimal("55000"),
        currency="rur",
        export_to_cian=True,
    )
    Photo.objects.create(
        property=prop,
        full_url="https://example.com/rent.jpg",
        is_default=True,
    )

    feed = build_cian_feed([prop])
    root = fromstring(feed.xml)
    obj = root.find("object")
    assert obj is not None
    bargain_terms = obj.find("BargainTerms")
    assert bargain_terms is not None
    assert obj.findtext("Category") == "flatRent"
    assert obj.findtext("BedsCount") == "3"
    assert bargain_terms.findtext("LeaseTermType") == "longTerm"
    assert bargain_terms.findtext("PrepayMonths") == "1"
    assert bargain_terms.findtext("Deposit") == "55000"
