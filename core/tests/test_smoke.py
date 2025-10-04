import os

import django
from django.test import TestCase

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "realcrm.settings")
django.setup()

from core.models import Property


class FlagsExistenceTests(TestCase):
    def test_domklik_flag_exists_and_defaults(self):
        prop = Property.objects.create(
            title="T",
            category="flat",
            operation="sale",
            external_id="AGTEST_FLAG",
        )
        self.assertTrue(hasattr(prop, "export_to_domklik"))
        self.assertIs(prop.export_to_domklik, False)
