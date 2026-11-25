from importlib import import_module


PriceHistoryMigration = import_module("core.migrations.0014_price_history").Migration


class Migration(PriceHistoryMigration):
    dependencies = [("core", "0001_initial")]
