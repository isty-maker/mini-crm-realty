from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class APIMigrationTests(TransactionTestCase):
    def test_new_tables_preserve_existing_property_in_current_chain(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        prior = ("crm_api", "0001_initial")
        executor.migrate([("crm_api", None)])
        executor = MigrationExecutor(connection)
        executor.migrate([prior])
        existing_state = executor.loader.project_state([node for node in latest if node[0] != "crm_api"] + [prior]).apps
        existing = existing_state.get_model("core", "Property").objects.create(
            external_id="api-synthetic-migration", price=100, export_to_cian=True, export_to_domklik=False,
        )
        employee = existing_state.get_model("auth", "User").objects.create(username="migration-fixture", is_staff=True)
        old_key = existing_state.get_model("crm_api", "AccessKey").objects.create(
            user_id=employee.pk, digest="1" * 64, label="Old test key", can_write=True,
        )
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        state = executor.loader.project_state(latest).apps
        record = state.get_model("core", "Property").objects.get(pk=existing.pk)
        self.assertEqual(record.price, 100)
        self.assertTrue(record.export_to_cian)
        self.assertFalse(record.export_to_domklik)
        key = state.get_model("crm_api", "AccessKey").objects.get(pk=old_key.pk)
        self.assertFalse(key.can_identify)
        self.assertEqual(key.issued_for, "")
