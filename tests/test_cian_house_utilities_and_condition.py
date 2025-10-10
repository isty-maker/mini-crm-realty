from decimal import Decimal
from xml.etree.ElementTree import fromstring

import pytest

from core.cian import build_cian_feed
from core.models import Photo, Property


@pytest.mark.django_db
def test_house_sale_utilities_and_condition_export():
    prop = Property.objects.create(
        category="house",
        operation="sale",
        address="МО",
        total_area=Decimal("120"),
        land_area=Decimal("6.0"),
        land_area_unit="sotka",
        has_electricity=True,
        has_gas=True,
        gas_supply_type="main_on_plot",
        has_water=True,
        water_supply_type="borehole",
        has_drainage=True,
        sewerage_type="septic",
        house_condition="ready",
        wc_location="inside",
        price=Decimal("10000000"),
        currency="rur",
        export_to_cian=True,
    )
    Photo.objects.create(property=prop, full_url="http://example.com/h.jpg", is_default=True)

    root = fromstring(build_cian_feed([prop]).xml)
    obj = root.find("object")
    assert obj is not None
    assert obj.findtext("Category") == "houseSale"
    assert obj.findtext("HasElectricity") == "true"
    assert obj.findtext("HasGas") == "true"
    gas_node = obj.find("Gas")
    assert gas_node is not None
    assert gas_node.findtext("Type") == "main"
    assert obj.findtext("HasWater") == "true"
    water_node = obj.find("Water")
    assert water_node is not None
    assert water_node.findtext("SuburbanWaterType") == "borehole"
    assert obj.findtext("HasDrainage") == "true"
    drainage_node = obj.find("Drainage")
    assert drainage_node is not None
    assert drainage_node.findtext("Type") == "septicTank"
    assert obj.findtext("Condition") == "ready"
    assert obj.findtext("WcLocationType") == "inside"
