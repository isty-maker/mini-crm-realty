from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_property_room_area"),
    ]

    operations = [
        migrations.AlterField(
            model_name="property",
            name="building_material",
            field=models.CharField(
                "Материал здания",
                max_length=64,
                choices=[
                    ("aerocreteBlock", "Газобетонный блок"),
                    ("arbolit", "Арболит"),
                    ("boards", "Щитовой"),
                    ("brick", "Кирпичный"),
                    ("expandedClayConcrete", "Керамзитобетон"),
                    ("foamConcreteBlock", "Пенобетонный блок"),
                    ("gasSilicateBlock", "Газосиликатный блок"),
                    ("gluedLaminatedTimber", "Клееный брус"),
                    ("metalFrame", "Металлокаркас"),
                    ("monolith", "Монолитный"),
                    ("reinforcedConcretePanels", "Железобетонные панели"),
                    ("sipPanels", "Сип-панели"),
                    ("slagConcrete", "Шлакобетон"),
                    ("solidWood", "Цельное дерево (брус, бревно)"),
                    ("wireframe", "Каркасный"),
                    ("wood", "Деревянный"),
                ],
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="property",
            name="heating_type",
            field=models.CharField(
                "Отопление",
                max_length=20,
                choices=[
                    ("autonomousGas", "Автономное газовое"),
                    ("centralCoal", "Центральное угольное"),
                    ("centralGas", "Центральное газовое"),
                    ("diesel", "Дизельное"),
                    ("electric", "Электрическое"),
                    ("fireplace", "Камин"),
                    ("no", "Нет"),
                    ("solidFuelBoiler", "Твердотопливный котел"),
                    ("stove", "Печь"),
                ],
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="property",
            name="house_condition",
            field=models.CharField(
                "Состояние дома",
                max_length=32,
                choices=[
                    ("interiorDecorationRequired", "Без внутренней отделки"),
                    (
                        "majorRepairsRequired",
                        "Требует капитального ремонта или под снос",
                    ),
                    ("ready", "Готов к проживанию"),
                    ("unfinished", "Недостроенный"),
                ],
                blank=True,
            ),
        ),
    ]
