import re
import uuid
from decimal import Decimal

import pytest
from django.urls import reverse

from core.models import Property


@pytest.fixture
def property_factory():
    def _create(**overrides):
        defaults = {
            "category": "flat",
            "operation": "sale",
            "external_id": f"DOM-{uuid.uuid4().hex[:8]}",
            "title": "Тестовый объект",
            "address": "Москва, ул. Тестовая, 1",
            "total_area": Decimal("45"),
            "floor_number": 5,
            "price": Decimal("5000000"),
            "phone_number": "+7 999 000-00-00",
            "export_to_cian": False,
            "export_to_domklik": False,
            "is_archived": False,
        }
        defaults.update(overrides)
        return Property.objects.create(**defaults)

    return _create


@pytest.mark.django_db
def test_domclick_feed_filters_only_marked(client, property_factory):
    a = property_factory(export_to_domklik=True, external_id="DOM-A")
    b = property_factory(export_to_cian=True, external_id="DOM-B")
    c = property_factory(external_id="DOM-C")
    d = property_factory(export_to_domklik=True, is_archived=True, external_id="DOM-D")

    url = reverse("export_domclick")
    resp = client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode("utf-8", errors="ignore")

    assert a.external_id in body
    assert b.external_id not in body
    assert c.external_id not in body
    assert d.external_id not in body

    assert re.search(r"<feed\b", body)
    assert re.search(r"<feed_version>2</feed_version>", body)


@pytest.mark.django_db
def test_cian_and_domclick_are_independent(client, property_factory):
    both = property_factory(
        export_to_domklik=True,
        export_to_cian=True,
        external_id="DOM-BOTH",
    )
    only_cian = property_factory(export_to_cian=True, external_id="DOM-CIAN")
    only_dom = property_factory(export_to_domklik=True, external_id="DOM-DOM")

    dom = client.get(reverse("export_domclick")).content.decode("utf-8", "ignore")
    assert only_dom.external_id in dom
    assert only_cian.external_id not in dom

    cian = client.get(reverse("export_cian")).content.decode("utf-8", "ignore")
    assert only_cian.external_id in cian
    assert only_dom.external_id not in cian

    assert both.external_id in dom
    assert both.external_id in cian
