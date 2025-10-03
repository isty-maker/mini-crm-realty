# core/views.py
from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import render, get_object_or_404, redirect
from xml.etree.ElementTree import Element, SubElement, tostring
from django.utils.encoding import smart_str

from .models import Property, Photo
from .forms import PropertyForm, PhotoForm
from .guards import shared_key_required

@shared_key_required
def panel_list(request):
    q = request.GET.get("q", "").strip()
    props = Property.objects.all()
    if q:
        props = props.filter(
            Q(title__icontains=q) |
            Q(city__icontains=q) |
            Q(external_id__icontains=q)
        )
    props = props.order_by("-updated_at", "-id")
    return render(request, "core/panel_list.html", {"props": props, "q": q})

def panel_edit(request, pk):
    """
    Редактирование существующего объекта (без фото-логики).
    """
    prop = get_object_or_404(Property, pk=pk)
    if request.method == "POST":
        form = PropertyForm(request.POST, instance=prop)
        if form.is_valid():
            form.save()
            # остаёмся на этой же странице
            return redirect(f"/panel/edit/{prop.pk}/")
    else:
        form = PropertyForm(instance=prop)
    # пока без фактических фото — отдадим пустой список для шаблона
    return render(request, "core/panel_edit.html", {"form": form, "prop": prop, "photos": []})

def photo_add(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    prop = get_object_or_404(Property, pk=pk)
    f = PhotoForm(request.POST)
    if f.is_valid():
        p = f.save(commit=False)
        p.prop = prop
        if p.is_default:
            prop.photos.update(is_default=False)
        p.save()
    return redirect("core:panel_edit", pk=pk)

def photo_delete(request, pk, photo_id):
    if request.method not in ("POST","GET"):
        return HttpResponseNotAllowed(["POST","GET"])
    prop = get_object_or_404(Property, pk=pk)
    photo = get_object_or_404(Photo, pk=photo_id, prop=prop)
    photo.delete()
    return redirect("core:panel_edit", pk=pk)

# -------- Экспорт ЦИАН (Feed_Version=2) --------
def _add_text(parent, tag, value, always=False):
    if value in (None, "", False) and not always:
        return None
    el = SubElement(parent, tag)
    if value is True: el.text = "true"
    elif value is False: el.text = "false"
    else: el.text = smart_str(value)
    return el

def _add_decimal(parent, tag, value):
    if value is None: return None
    el = SubElement(parent, tag)
    el.text = str(value).replace(",", ".")
    return el

def export_cian(request):
    root = Element("Feed")
    SubElement(root, "Feed_Version").text = "2"

    for prop in Property.objects.all().order_by("id"):
        obj = SubElement(root, "Object")
        _add_text(obj, "Category", prop.category, always=True)
        _add_text(obj, "ExternalId", prop.external_id, always=True)

        _add_text(obj, "Description", prop.description)
        _add_text(obj, "Address", prop.address)
        if prop.lat is not None and prop.lng is not None:
            coords = SubElement(obj, "Coordinates")
            _add_decimal(coords, "Lat", prop.lat)
            _add_decimal(coords, "Lng", prop.lng)
        _add_text(obj, "CadastralNumber", prop.cadastral_number)

        if prop.phone_number or prop.phone_number2:
            phones = SubElement(obj, "Phones")
            if prop.phone_number:
                ph = SubElement(phones, "PhoneSchema")
                _add_text(ph, "CountryCode", prop.phone_country or "7")
                _add_text(ph, "Number", prop.phone_number)
            if prop.phone_number2:
                ph = SubElement(phones, "PhoneSchema")
                _add_text(ph, "CountryCode", prop.phone_country or "7")
                _add_text(ph, "Number", prop.phone_number2)

        if any([prop.building_name, prop.building_floors, prop.building_build_year,
                prop.building_material, prop.building_ceiling_height,
                prop.building_passenger_lifts, prop.building_cargo_lifts]):
            b = SubElement(obj, "Building")
            _add_text(b, "Name", prop.building_name)
            _add_text(b, "FloorsCount", prop.building_floors)
            _add_text(b, "BuildYear", prop.building_build_year)
            _add_text(b, "MaterialType", prop.building_material)
            _add_decimal(b, "CeilingHeight", prop.building_ceiling_height)
            _add_text(b, "PassengerLiftsCount", prop.building_passenger_lifts)
            _add_text(b, "CargoLiftsCount", prop.building_cargo_lifts)

        if prop.layout_photo_url:
            lp = SubElement(obj, "LayoutPhoto")
            _add_text(lp, "FullUrl", prop.layout_photo_url, always=True)
            _add_text(lp, "IsDefault", True, always=True)
        if prop.object_tour_url:
            t = SubElement(obj, "ObjectTour")
            _add_text(t, "FullUrl", prop.object_tour_url, always=True)

        if prop.photos.exists():
            photos = SubElement(obj, "Photos")
            for p in prop.photos.all():
                ph = SubElement(photos, "PhotoSchema")
                _add_text(ph, "FullUrl", p.full_url, always=True)
                if p.is_default:
                    _add_text(ph, "IsDefault", True, always=True)

        _add_text(obj, "RoomType", prop.room_type)
        _add_text(obj, "FlatRoomsCount", prop.flat_rooms_count)
        _add_text(obj, "IsEuroFlat", prop.is_euro_flat)
        _add_text(obj, "IsApartments", prop.is_apartments)
        _add_text(obj, "IsPenthouse", prop.is_penthouse)

        _add_decimal(obj, "TotalArea", prop.total_area)
        _add_decimal(obj, "LivingArea", prop.living_area)
        _add_decimal(obj, "KitchenArea", prop.kitchen_area)
        _add_text(obj, "FloorNumber", prop.floor_number)
        _add_text(obj, "LoggiasCount", prop.loggias_count)
        _add_text(obj, "BalconiesCount", prop.balconies_count)
        _add_text(obj, "WindowsViewType", prop.windows_view_type)
        _add_text(obj, "SeparateWcsCount", prop.separate_wcs_count)
        _add_text(obj, "CombinedWcsCount", prop.combined_wcs_count)
        _add_text(obj, "RepairType", prop.repair_type)

        if any([prop.jk_id, prop.jk_name, prop.house_id, prop.house_name, prop.flat_number, prop.section_number]):
            jk = SubElement(obj, "JKSchema")
            _add_text(jk, "Id", prop.jk_id)
            _add_text(jk, "Name", prop.jk_name)
            if prop.house_id or prop.house_name:
                house = SubElement(jk, "House")
                _add_text(house, "Id", prop.house_id)
                _add_text(house, "Name", prop.house_name)
            if prop.flat_number or prop.section_number:
                flat = SubElement(jk, "Flat")
                _add_text(flat, "FlatNumber", prop.flat_number)
                _add_text(flat, "SectionNumber", prop.section_number)

        _add_text(obj, "HeatingType", prop.heating_type)
        if any([prop.land_area, prop.land_area_unit, prop.permitted_land_use, prop.is_land_with_contract]):
            land = SubElement(obj, "Land")
            _add_decimal(land, "Area", prop.land_area)
            _add_text(land, "AreaUnitType", prop.land_area_unit)
            _add_text(land, "PermittedLandUseType", prop.permitted_land_use)
            _add_text(land, "IsLandWithContract", prop.is_land_with_contract)
        _add_text(obj, "LandCategory", prop.land_category)
        _add_text(obj, "HasTerrace", prop.has_terrace)
        _add_text(obj, "HasCellar", prop.has_cellar)

        _add_text(obj, "IsRentByParts", prop.is_rent_by_parts)
        _add_text(obj, "RentByPartsDescription", prop.rent_by_parts_desc)
        _add_decimal(obj, "CeilingHeight", prop.ceiling_height)
        _add_text(obj, "ElectricityPower", prop.power)
        _add_text(obj, "HasParking", prop.has_parking)
        _add_text(obj, "ParkingPlaces", prop.parking_places)

        for tag, flag in [
            ("HasInternet", prop.has_internet),
            ("HasFurniture", prop.has_furniture),
            ("HasKitchenFurniture", prop.has_kitchen_furniture),
            ("HasTv", prop.has_tv),
            ("HasWasher", prop.has_washer),
            ("HasConditioner", prop.has_conditioner),
            ("HasPhone", prop.has_phone),
            ("HasRamp", prop.has_ramp),
            ("HasBathtub", prop.has_bathtub),
        ]:
            _add_text(obj, tag, flag)

        if any([prop.price is not None, prop.mortgage_allowed, prop.agent_bonus_value is not None,
                prop.security_deposit is not None, prop.min_rent_term_months is not None]):
            bt = SubElement(obj, "BargainTerms")
            _add_decimal(bt, "Price", prop.price)
            _add_text(bt, "Currency", prop.currency or "rur")
            _add_text(bt, "MortgageAllowed", prop.mortgage_allowed)
            if prop.agent_bonus_value is not None:
                ab = SubElement(bt, "AgentBonus")
                _add_decimal(ab, "Value", prop.agent_bonus_value)
                _add_text(ab, "PaymentType", "percent" if prop.agent_bonus_is_percent else "fixed")
                if not prop.agent_bonus_is_percent:
                    _add_text(ab, "Currency", prop.currency or "rur")
            _add_decimal(bt, "SecurityDeposit", prop.security_deposit)
            _add_text(bt, "MinRentTerm", prop.min_rent_term_months)

    xml_bytes = tostring(root, encoding="utf-8", xml_declaration=True)
    return HttpResponse(xml_bytes, content_type="application/xml; charset=utf-8")
