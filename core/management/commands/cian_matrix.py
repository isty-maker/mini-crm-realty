from django.core.management.base import BaseCommand

from core.cian import load_registry


class Command(BaseCommand):
    help = "Печатает матрицу: поле формы → тег ЦИАН → разделы"

    def handle(self, *args, **opts):
        registry = load_registry()
        common = registry.get("common", {}).get("fields", {})
        deal_terms = registry.get("deal_terms", {}).get("fields", {})
        categories = registry.get("categories", {}) or {}

        self.stdout.write("COMMON FIELDS:")
        for field_name, tag in sorted(common.items()):
            self.stdout.write(f"  {field_name:30} -> {tag}")

        self.stdout.write("\nDEAL TERMS:")
        for field_name, tag in sorted(deal_terms.items()):
            self.stdout.write(f"  {field_name:30} -> {tag}")

        self.stdout.write("\nCATEGORIES:")
        for category_name, config in sorted(categories.items()):
            self.stdout.write(f"  [{category_name}]")
            category_fields = (config.get("fields") or {}).items()
            for field_name, tag in sorted(category_fields):
                self.stdout.write(f"    {field_name:28} -> {tag}")
