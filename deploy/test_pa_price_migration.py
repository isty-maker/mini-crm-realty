"""Reproduce issue #189 against an exact, locally available PR #188 revision."""

import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from deploy.pa_server import backup


REPO = Path(__file__).resolve().parent.parent
PRICE_REF = os.environ.get("PA_PRICE_HISTORY_TEST_REF")


@unittest.skipUnless(PRICE_REF, "Set PA_PRICE_HISTORY_TEST_REF to the reviewed local PR #188 SHA")
class ReviewedPriceMigrationTests(unittest.TestCase):
    def test_both_migration_chains_with_old_and_concurrent_writers(self):
        archive = subprocess.check_output(["git", "archive", PRICE_REF], cwd=REPO)
        sha = subprocess.check_output(["git", "rev-parse", PRICE_REF], cwd=REPO, text=True).strip()
        for alternate in (False, True):
            with self.subTest(alternate=alternate), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
                    tree.extractall(root, filter="data")
                shutil.copyfile(REPO / "deploy/pa_server.py", root / "deploy/pa_server.py")
                self.exercise_snapshot(root, sha, alternate)

    def exercise_snapshot(self, root, sha, alternate):
        domain = "fixture.pythonanywhere.com"
        env = {
            "PATH": os.defpath,
            "DEBUG": "False",
            "ALLOWED_HOSTS": domain,
            "CSRF_TRUSTED_ORIGINS": "https://" + domain,
            "YANDEX_CLIENT_KEY_ID": "fixture",
            "YANDEX_CLIENT_SECRET_KEY": "fixture",
            "YANDEX_STORAGE_BUCKET_NAME": "fixture",
            "USE_SQUASHED_MIGRATIONS": "true" if alternate else "false",
        }

        def run(*args, success=True):
            result = subprocess.run([sys.executable, *args], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
            return result

        previous = "0001_initial" if alternate else "0013_merge_20260927_1839"
        run("manage.py", "migrate", "-v", "0")
        run("manage.py", "migrate", "core", previous, "-v", "0")
        run("manage.py", "shell", "-c", f"""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
schema = MigrationExecutor(connection).loader.project_state([('core', {previous!r})])
property_model = schema.apps.get_model('core', 'Property')
for index, price in enumerate((100, None, 0), start=1):
    property_model.objects.create(id=index, external_id=f'fixture-{{index}}', price=price)
""")
        database = root / "db.sqlite3"
        snapshot = root / "rehearsal.sqlite3"
        plan = root / "plan.json"
        with closing(sqlite3.connect(database)) as writer:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("PRAGMA foreign_keys=ON")
            backup(database, snapshot)

            def stage(mode, file, approval="no"):
                return ["deploy/pa_server.py", mode, str(file), str(plan), domain, sha, approval]

            run(*stage("rehearse", snapshot))
            self.assertEqual(json.loads(plan.read_text())["policy"], "price-history")
            with closing(sqlite3.connect(snapshot)) as rehearsed:
                self.assertEqual(rehearsed.execute(
                    "SELECT new_price FROM core_pricehistory ORDER BY property_id"
                ).fetchall(), [(100,), (None,), (0,)])
            run(*stage("verify", database))
            rejected = run(*stage("apply", database), success=False)
            self.assertIn("requires explicit SHA approval", rejected.stderr)
            self.assertIsNone(writer.execute(
                "SELECT name FROM sqlite_schema WHERE name='core_pricehistory'"
            ).fetchone())

            # A write committed after the rehearsal must appear in the live backfill.
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("UPDATE core_property SET price=110 WHERE id=1")
            with subprocess.Popen([sys.executable, *stage("apply", database, "yes")],
                                  cwd=root, env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True) as process:
                time.sleep(0.4)
                self.assertIsNone(process.poll())
                writer.commit()
                stdout, stderr = process.communicate(timeout=60)
                self.assertEqual(process.returncode, 0, stdout + stderr)

            writer.execute("UPDATE core_property SET price=120 WHERE id=1")
            writer.commit()
            writer.execute("UPDATE core_property SET price=130 WHERE id=1")
            writer.rollback()
            self.assertEqual(writer.execute("SELECT price FROM core_property WHERE id=1").fetchone(), (120,))
            self.assertEqual(writer.execute(
                "SELECT kind, previous_price, new_price FROM core_pricehistory WHERE property_id=1 ORDER BY id"
            ).fetchall(), [("baseline", None, 110), ("change", 110, 120)])

            # A worker unaware of the new ORM relation does not cascade this delete.
            writer.execute("DELETE FROM core_property WHERE id=1")
            with self.assertRaises(sqlite3.IntegrityError):
                writer.commit()
            writer.rollback()
            self.assertEqual(writer.execute("PRAGMA foreign_key_check").fetchall(), [])
