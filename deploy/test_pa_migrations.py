"""Offline deploy tests against a temporary Git remote and synthetic SQLite."""

import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from django.db import migrations, models

from deploy.pa_client import DeployError, PythonAnywhere
from deploy.pa_server import automatic_migration, backup


REPO = Path(__file__).resolve().parent.parent
SAFE_OPERATION = """
migrations.CreateModel(
    name="DeployScratchProof",
    fields=[("id", models.AutoField(primary_key=True)), ("amount", models.IntegerField())],
)
"""


class MigrationPolicyTests(unittest.TestCase):
    def test_only_an_atomic_independent_table_is_automatic(self):
        def allowed(operation, **flags):
            migration = migrations.Migration("9999_test", "core")
            migration.operations = [operation]
            for key, value in flags.items():
                setattr(migration, key, value)
            return automatic_migration([(migration, False)])

        field = ("id", models.AutoField(primary_key=True))
        plain = migrations.CreateModel("NewTable", [field])
        self.assertTrue(allowed(plain))
        self.assertFalse(allowed(plain, atomic=False))
        self.assertFalse(allowed(plain, replaces=[("core", "old")]))
        for operation in (
            migrations.RunSQL("SELECT 1"),
            migrations.RunPython(migrations.RunPython.noop),
            migrations.DeleteModel("Property"),
            migrations.RenameModel("Property", "Elsewhere"),
            migrations.AddField("Property", "another", models.IntegerField(null=True)),
            migrations.CreateModel("NewTable", [field, ("x", models.CharField(max_length=5, default="x"))]),
            migrations.CreateModel("NewTable", [field, ("x", models.ForeignKey("core.Property", on_delete=models.CASCADE))]),
            migrations.CreateModel("NewTable", [field], options={"db_table": "core_property"}),
        ):
            with self.subTest(operation=operation):
                self.assertFalse(allowed(operation))

    def test_snapshot_rejects_foreign_key_violations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with closing(sqlite3.connect(root / "broken.sqlite3")) as database:
                database.executescript("""
                    CREATE TABLE parent (id INTEGER PRIMARY KEY);
                    CREATE TABLE child (parent_id REFERENCES parent(id));
                    INSERT INTO child VALUES (999);
                """)
            with self.assertRaisesRegex(RuntimeError, "foreign_key_check"):
                backup(root / "broken.sqlite3", root / "snapshot.sqlite3")


@unittest.skipUnless(sys.version_info[:2] == (3, 12), "Launcher requires Python 3.12")
class MigrationLauncherTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.remote = self.home / "origin"
        self.remote.mkdir()
        self.state = self.home / ".mini-crm-deploy"
        self.state.mkdir(mode=0o700)
        self.checkout = self.home / "mini-crm-realty"
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "PYTHONDONTWRITEBYTECODE": "1",
            "USE_SQUASHED_MIGRATIONS": "false",
            "AUTO_APPLY_MIGRATIONS": "0",
        }
        archive = subprocess.check_output(
            ["git", "archive", "HEAD"], cwd=REPO,
        )
        with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
            tree.extractall(self.remote, filter="data")
        shutil.copyfile(REPO / "deploy/pa_server.py", self.remote / "deploy/pa_server.py")
        self.git(self.remote, "init", "-q", "-b", "main")
        self.git(self.remote, "add", ".")
        self.git(self.remote, "commit", "-qm", "baseline fixture")
        self.base = self.git(self.remote, "rev-parse", "HEAD").strip()
        self.git(self.home, "clone", "-q", str(self.remote), str(self.checkout))
        self.git(self.checkout, "switch", "-qc", "production")
        (self.checkout / ".git/info/exclude").write_text("/.env\n/venv\n/db.sqlite3\n/media/\n/staticfiles/\n")
        if sys.prefix != sys.base_prefix:
            (self.checkout / "venv").symlink_to(sys.prefix, target_is_directory=True)
        else:
            subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", "venv"],
                           cwd=self.checkout, check=True)
        self.domain = subprocess.check_output(["id", "-un"], text=True).strip() + ".pythonanywhere.com"
        dotenv = self.checkout / ".env"
        dotenv.write_text(
            f"DEBUG=False\nALLOWED_HOSTS={self.domain}\nCSRF_TRUSTED_ORIGINS=https://{self.domain}\n"
            "YANDEX_CLIENT_KEY_ID=fixture\nYANDEX_CLIENT_SECRET_KEY=fixture\nYANDEX_STORAGE_BUCKET_NAME=fixture\n"
        )
        dotenv.chmod(0o600)
        (self.state / "last-good").write_text(self.base)
        self.db = self.checkout / "db.sqlite3"
        self.launcher = self.state / "deploy-v2"
        # Use a local origin and baseline for this fixture. No requests leave the test.
        self.launcher.write_text(
            (REPO / "deploy/deploy").read_text()
            .replace("https://github.com/isty-maker/mini-crm-realty.git", str(self.remote))
            .replace("bf6164eb52efacaa8eaaff6174c6e348778db049", self.base)
        )
        self.launcher.chmod(0o700)
        subprocess.run([str(self.checkout / "venv/bin/python"), "manage.py", "migrate", "--noinput", "-v", "0"],
                       cwd=self.checkout, env=self.env, check=True)
        with closing(sqlite3.connect(self.db)) as database:
            self.latest = database.execute(
                "SELECT name FROM django_migrations WHERE app='core' ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]

    def git(self, cwd, *args):
        return subprocess.check_output(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
            cwd=cwd, env=self.env, text=True,
        )

    def release(self, name, dependency, operation):
        path = self.remote / "core/migrations" / f"{name}.py"
        path.write_text(
            "from django.db import migrations, models\n\n"
            "class Migration(migrations.Migration):\n"
            f"    dependencies = [('core', {dependency!r})]\n"
            f"    operations = [{operation}]\n"
        )
        self.git(self.remote, "add", str(path.relative_to(self.remote)))
        self.git(self.remote, "commit", "-qm", name)
        return self.git(self.remote, "rev-parse", "HEAD").strip()

    def launch(self, mode, sha, run_id, success=True):
        result = subprocess.run(["bash", str(self.launcher), mode, sha, run_id],
                                env=self.env, capture_output=True, text=True, timeout=90)
        log = (self.state / f"{run_id}.{mode}.log").read_text()
        self.assertEqual(result.returncode == 0, success, log)
        return result.stdout, log

    def table_exists(self, database):
        with closing(sqlite3.connect(database)) as connection:
            return connection.execute(
                "SELECT 1 FROM sqlite_schema WHERE name='core_deployscratchproof'"
            ).fetchone() is not None

    def test_automatic_release_through_client_without_manual_approval(self):
        target = self.release("9999_deploy_fixture", self.latest, SAFE_OPERATION)
        db_before = self.db.read_bytes()
        _, log = self.launch("dry-run", target, "1" * 32)
        self.assertIn("Migration policy: automatic", log)
        self.assertEqual(self.db.read_bytes(), db_before)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD").strip(), self.base)
        self.assertFalse((self.state / "pending").exists())

        client = PythonAnywhere("example", "123", "fake-token")
        run_id = "2" * 32
        output = "12:34 ~ $ "
        phases = []

        def api(path, method="GET", form=None):
            nonlocal output
            if path == client.webapp:
                return {"python_version": "3.12",
                        "source_directory": "/home/example/mini-crm-realty",
                        "virtualenv_path": "/home/example/mini-crm-realty/venv"}
            if path.endswith("/get_latest_output"):
                return {"output": output}
            if path.endswith("/send_input"):
                mode = "ack" if " ack " in form["input"] else "auto-apply"
                phases.append(mode)
                output, _ = self.launch(mode, target, run_id)
                output += "12:34 ~ $ "
            elif path.endswith("/reload"):
                self.assertTrue(self.table_exists(self.db))
                self.assertTrue((self.state / "pending").exists())
                phases.append("reload")
            return None

        with patch.object(client, "api", side_effect=api), patch.object(
            client, "verify_health", side_effect=lambda sha: phases.append(("health", sha))
        ):
            client.deploy("auto-apply", target, run_id)
        self.assertEqual(phases, ["auto-apply", "reload", ("health", target), "ack"])
        self.assertTrue(self.table_exists(self.db))
        self.assertFalse(self.table_exists(self.state / f"{run_id}.sqlite3"))
        self.assertFalse((self.state / "pending").exists())
        self.assertEqual((self.state / "last-good").read_text().strip(), target)
        _, repeat = self.launch("dry-run", target, "3" * 32)
        self.assertIn("Migration policy: none", repeat)

    def test_unknown_and_failing_rehearsal_leave_live_checkout_and_db_intact(self):
        target = self.release("9999_fail_fixture", self.latest,
                              'migrations.RunSQL(["UPDATE core_property SET price=1", "INVALID SQL"])')
        db_before = self.db.read_bytes()
        _, blocked = self.launch("apply", target, "4" * 32, success=False)
        self.assertIn("require SHA-specific approval even for rehearsal", blocked)
        approval = self.state / "allow-migrations"
        approval.write_text(target + "\n")
        approval.chmod(0o600)
        _, auto_blocked = self.launch("auto-apply", target, "6" * 32, success=False)
        self.assertIn("require SHA-specific approval even for rehearsal", auto_blocked)
        _, failure = self.launch("apply", target, "5" * 32, success=False)
        self.assertIn("Migration execution failed (OperationalError)", failure)
        self.assertEqual(self.db.read_bytes(), db_before)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD").strip(), self.base)
        self.assertFalse((self.state / "pending").exists())
        self.assertEqual(list(self.state.glob("*.sqlite3")), [])
