import io
import os
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from deploy.pa_client import DeployError, PythonAnywhere, idle_bash
from deploy.pa_server import backup


SHA = "a" * 40
RUN = "b" * 32


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.client = PythonAnywhere("example", "123", "mock-token")
        self.config = {
            "python_version": "3.12",
            "source_directory": "/home/example/mini-crm-realty",
            "virtualenv_path": "/home/example/mini-crm-realty/venv",
        }

    def test_apply_only_reloads_after_matching_marker_then_checks_and_acknowledges(self):
        events = []

        def api(path, method="GET", form=None):
            events.append((path.rsplit("/", 1)[-1], method))
            if path == self.client.webapp:
                return self.config
            if path.endswith("/send_input"):
                mode = "ack" if " ack " in form["input"] else "apply"
                self.assertEqual(
                    form["input"],
                    'if [ -x /home/example/.mini-crm-deploy/deploy-v2 ] && '
                    '[ "$(env -u API_TOKEN -u BASH_ENV /bin/bash /home/example/.mini-crm-deploy/deploy-v2 '
                    '--protocol-version)" = 2 ]; then '
                    'env -u API_TOKEN -u BASH_ENV /bin/bash /home/example/.mini-crm-deploy/deploy-v2 '
                    f"{mode} {SHA} {RUN}; else printf '\\nCRM_DEPLOY %s %s 127\\n' {RUN} {mode}; fi\n",
                )
                output.append(f"\r\nCRM_DEPLOY {RUN} {mode} 0\r\n13:24 ~ $ ")
            if path.endswith("/get_latest_output"):
                return {"output": output[-1]}

        output = ["13:24 ~ $ "]
        with patch.object(self.client, "api", side_effect=api), patch.object(
            self.client, "verify_health", side_effect=lambda sha: events.append((sha, "health"))
        ):
            self.client.deploy("apply", SHA, RUN)
        self.assertEqual(
            events[1:],
            [("get_latest_output", "GET"), ("send_input", "POST"),
             ("get_latest_output", "GET"), ("reload", "POST"), (SHA, "health"),
             ("get_latest_output", "GET"), ("send_input", "POST"),
             ("get_latest_output", "GET")],
        )

    def test_recognizes_colored_bash_prompt_with_terminal_line_endings(self):
        for prompt in (
            "\x1b[32m13:24 ~ $ \x1b[0;0m\r",
            "previous output\r\n(venv) 13:24 ~/repo (main) $  \x1b[0m\r\n",
            "\x1b[?2004huser@host:~$ \t",
            "previous output\rbash-5.2$ ",
            "13:24 ~/repo (main)$ ",
        ):
            with self.subTest(prompt=prompt):
                self.assertTrue(idle_bash(prompt))

    def test_rejects_busy_and_interactive_console_tails(self):
        for output in (
            "13:24 ~ $ echo waiting", "13:24 waiting $ ", "previous command $ ", "$ ", ">>> ",
            "Password: ", "sqlite> ", "> ", "13:24 ~ $ \nworking...",
            "13:24 ~\x1b[2K $ ", "13:24 ~ $ \n\n",
        ):
            with self.subTest(output=output):
                self.assertFalse(idle_bash(output))

    def test_waits_for_complete_marker_with_exact_nonce_and_stage(self):
        marker = f"CRM_DEPLOY {RUN} apply 0"
        output = [
            "13:24 ~ $ ",
            marker,  # truncated output, no line ending
            "log: " + marker + "\n",
            marker + "0 more\r",
            marker.replace(RUN, "c" * 32) + "\r\n",
            marker.replace("apply", "ack") + "\r",
            "\x1b[32m" + marker + "\x1b[0;0m  \r13:24 ~ $ ",
        ]
        with patch.object(self.client, "console_output", side_effect=output) as read, patch.object(
            self.client, "api"
        ) as api, patch("deploy.pa_client.time.sleep"):
            self.client.run("apply", SHA, RUN, 1)
        self.assertEqual(read.call_count, len(output))
        api.assert_called_once()

    def test_missing_v2_launcher_never_reloads(self):
        with patch.object(self.client, "api", side_effect=[
            self.config, {"output": "13:24 ~ $ "}, None, {"output": f"CRM_DEPLOY {RUN} apply 127\r"},
        ]) as api:
            with self.assertRaisesRegex(DeployError, "Launcher v2 unavailable"):
                self.client.deploy("apply", SHA, RUN)
        self.assertEqual(api.call_count, 4)

    def test_inactive_preflight_sends_nothing(self):
        def failure(request, timeout):
            raise HTTPError(request.full_url, 412, "Precondition Failed", {}, io.BytesIO(b""))

        with patch.object(self.client.opener, "open", side_effect=failure) as request:
            with self.assertRaisesRegex(DeployError, "Open the dedicated Bash console"):
                self.client.run("apply", SHA, RUN, 1)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[0].method, "GET")

    def test_post_412_fails_without_reload_or_retry(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"output":"13:24 ~ $ "}'
        error = HTTPError("", 412, "Precondition Failed", {}, io.BytesIO(b""))
        with patch.object(self.client.opener, "open", side_effect=[response, error]) as request:
            with self.assertRaisesRegex(DeployError, "Console inactive"):
                self.client.run("apply", SHA, RUN, 1)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.args[0].method, "POST")

    def test_http_success_and_stale_marker_do_not_confirm_deploy(self):
        with patch.object(self.client, "api", side_effect=[
            self.config, {"output": "13:24 ~ $ "}, None, {"output": f"CRM_DEPLOY {RUN} ack 0\n"},
        ]) as api, patch("deploy.pa_client.time.monotonic", side_effect=[0, 0, 1531]), patch(
            "deploy.pa_client.time.sleep"
        ):
            with self.assertRaisesRegex(DeployError, "completion unconfirmed"):
                self.client.deploy("apply", SHA, RUN)
        self.assertEqual(api.call_count, 4)

    def test_server_failure_stops_before_reload(self):
        with patch.object(self.client, "api", side_effect=[
            self.config, {"output": "13:24 ~ $ "}, None, {"output": f"CRM_DEPLOY {RUN} apply 1\n"},
        ]) as api:
            with self.assertRaisesRegex(DeployError, "exited 1"):
                self.client.deploy("apply", SHA, RUN)
        self.assertEqual(api.call_count, 4)

    def test_reload_failure_skips_health_and_ack(self):
        with patch.object(self.client, "api", side_effect=[
            self.config, DeployError("reload failed"),
        ]), patch.object(self.client, "run") as run, patch.object(
            self.client, "verify_health"
        ) as health:
            with self.assertRaisesRegex(DeployError, "reload failed"):
                self.client.deploy("apply", SHA, RUN)
        run.assert_called_once_with("apply", SHA, RUN, timeout=1530)
        health.assert_not_called()

    def test_health_failure_leaves_server_pending(self):
        with patch.object(self.client, "api", side_effect=[self.config, None]), patch.object(
            self.client, "run"
        ) as run, patch.object(self.client, "verify_health", side_effect=DeployError("health")):
            with self.assertRaisesRegex(DeployError, "health"):
                self.client.deploy("apply", SHA, RUN)
        run.assert_called_once_with("apply", SHA, RUN, timeout=1530)

    def test_health_requires_worker_revision_and_sends_no_api_token(self):
        response = Mock(status=200, headers={"X-App-Revision": "old"})
        response.read.return_value = b"ok"
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(self.client.opener, "open", return_value=response) as opened, patch(
            "deploy.pa_client.time.monotonic", side_effect=[0, 0, 121]
        ), patch("deploy.pa_client.time.sleep"):
            with self.assertRaisesRegex(DeployError, "did not confirm"):
                self.client.verify_health(SHA)
            request = opened.call_args.args[0]
            self.assertRegex(request.full_url, r"^https://example\.pythonanywhere\.com/healthz/")
            self.assertIsNone(request.get_header("Authorization"))

    def test_accepts_documented_python312_format(self):
        self.config["python_version"] = "python312"
        with patch.object(self.client, "api", return_value=self.config):
            with patch.object(self.client, "run") as run:
                self.client.deploy("dry-run", SHA, RUN)
        run.assert_called_once_with("dry-run", SHA, RUN, timeout=1530)

    def test_console_output_without_idle_prompt_does_not_send_input(self):
        with patch.object(self.client, "console_output", return_value="previous command running") as output, patch.object(
            self.client, "api"
        ) as api:
            with self.assertRaisesRegex(DeployError, "idle shell prompt"):
                self.client.run("apply", SHA, RUN, 1)
        output.assert_called_once()
        api.assert_not_called()

    def test_dry_run_never_reloads(self):
        with patch.object(self.client, "api", return_value=self.config) as api, patch.object(
            self.client, "run"
        ) as run:
            self.client.deploy("dry-run", SHA, RUN)
        api.assert_called_once_with(self.client.webapp)
        run.assert_called_once_with("dry-run", SHA, RUN, timeout=1530)

    def test_rejects_mismatched_settings_and_shell_input(self):
        with patch.object(self.client, "api", return_value={}) as api:
            with self.assertRaisesRegex(DeployError, "setting mismatch"):
                self.client.deploy("apply", SHA, RUN)
            with self.assertRaisesRegex(DeployError, "Invalid deployment command"):
                self.client.run("apply", SHA + "; id", RUN, 1)
        api.assert_called_once()


class LauncherTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name)
        self.state = self.home / ".mini-crm-deploy"
        self.state.mkdir(mode=0o700)
        self.checkout = self.home / "mini-crm-realty"
        self.git("init", "-q", "-b", "production", str(self.checkout), cwd=self.home)
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.com",
                 "commit", "-q", "--allow-empty", "-m", "baseline")
        self.git("remote", "add", "origin", "https://github.com/isty-maker/mini-crm-realty.git")
        self.head = self.git("rev-parse", "HEAD").strip()
        (self.state / "last-good").write_text(self.head + "\n")

    def git(self, *args, cwd=None):
        return subprocess.check_output(["git", *args], text=True, cwd=cwd or self.checkout)

    def launch(self, mode, sha=SHA):
        launcher = Path(__file__).with_name("deploy").resolve()
        return subprocess.run(
            ["bash", str(launcher), mode, sha, RUN],
            env={**os.environ, "HOME": str(self.home)},
            text=True,
            capture_output=True,
        )

    def test_dirty_checkout_is_rejected_before_environment_or_fetch(self):
        (self.checkout / "server_only_migration.py").touch()
        result = self.launch("apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"CRM_DEPLOY {RUN} apply 1", result.stdout)
        self.assertIn("Dirty checkout", (self.state / f"{RUN}.apply.log").read_text())
        self.assertFalse((self.state / "pending").exists())

    def test_pending_apply_blocks_another_apply_until_matching_ack(self):
        (self.state / "pending").write_text(f"{RUN} {self.head} ready\n")
        result = self.launch("apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("previous apply requires verification", (self.state / f"{RUN}.apply.log").read_text())
        result = self.launch("ack", self.head)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"CRM_DEPLOY {RUN} ack 0", result.stdout)
        self.assertFalse((self.state / "pending").exists())
        self.assertEqual((self.state / "last-good").read_text().strip(), self.head)


class BackupTests(unittest.TestCase):
    def test_backup_reads_committed_wal_data_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "production.sqlite3"
            target = Path(directory) / "backup.sqlite3"
            with closing(sqlite3.connect(source)) as database:
                database.execute("PRAGMA journal_mode=WAL")
                database.execute("CREATE TABLE test (value INTEGER)")
                database.execute("INSERT INTO test VALUES (42)")
                database.commit()
                self.assertTrue(Path(str(source) + "-wal").is_file())
                backup(source, target)
                database.execute("INSERT INTO test VALUES (13)")
                database.commit()
                with self.assertRaises(FileExistsError):
                    backup(source, target)
            with closing(sqlite3.connect(target)) as snapshot:
                self.assertEqual(snapshot.execute("SELECT value FROM test").fetchall(), [(42,)])
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_missing_source_does_not_create_database(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "missing.sqlite3"
            target = Path(directory) / "backup.sqlite3"
            with self.assertRaises(RuntimeError):
                backup(source, target)
            self.assertFalse(source.exists())
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
