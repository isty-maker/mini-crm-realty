"""Send fixed deployment commands to an existing PythonAnywhere Bash console."""

import json
import logging
import os
import re
import secrets
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


LOG = logging.getLogger(__name__)


class DeployError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class PythonAnywhere:
    def __init__(self, username, console_id, token):
        if not re.fullmatch(r"[a-z][a-z0-9]{0,29}", username):
            raise DeployError("Invalid PA_USERNAME.")
        if not re.fullmatch(r"[1-9][0-9]{0,15}", console_id):
            raise DeployError("Invalid PA_CONSOLE_ID.")
        if not token:
            raise DeployError("Missing PA_API_TOKEN.")
        self.username = username
        self.token = token
        self.domain = f"{username}.pythonanywhere.com"
        self.console = f"consoles/{console_id}"
        self.webapp = f"webapps/{self.domain}"
        self.opener = build_opener(NoRedirect())

    def api(self, path, method="GET", form=None):
        request = Request(
            f"https://www.pythonanywhere.com/api/v0/user/{self.username}/{path}/",
            headers={"Authorization": f"Token {self.token}"},
            method=method,
            data=urlencode(form).encode() if form is not None else None,
        )
        try:
            with self.opener.open(request, timeout=20) as response:
                body = response.read(32768)
        except HTTPError as exc:
            if exc.code == 412 and path.startswith(self.console + "/"):
                raise DeployError(
                    "Console inactive (HTTP 412). Open the dedicated Bash console in "
                    "the PythonAnywhere browser dashboard and confirm Bash is idle. "
                    "If a command was already sent, inspect the private run log before retrying."
                ) from None
            raise DeployError(f"{method} {path}: HTTP {exc.code}.") from None
        except (URLError, OSError):
            raise DeployError(f"{method} {path}: transport failure; inspect before retrying.") from None
        if method == "GET":
            try:
                return json.loads(body)
            except (ValueError, UnicodeError):
                raise DeployError(f"Invalid JSON from {path}.") from None
        return None

    def console_output(self):
        payload = self.api(f"{self.console}/get_latest_output")
        if not isinstance(payload, dict) or not isinstance(payload.get("output"), str):
            raise DeployError("Unexpected console output response.")
        return payload["output"]

    def run(self, mode, sha, run_id, timeout):
        if mode not in {"dry-run", "apply", "ack"} or not re.fullmatch(
            r"[0-9a-f]{40}", sha
        ) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise DeployError("Invalid deployment command arguments.")
        # Protected launcher outside the checkout. All interpolated values are validated.
        command = (
            f"env -u API_TOKEN /bin/bash /home/{self.username}/.mini-crm-deploy/deploy "
            f"{mode} {sha} {run_id}\n"
        )
        LOG.info("Sending %s; private server log is %s.%s.log", mode, run_id, mode)
        initial_output = self.console_output()
        if not re.search(r"(?:^|\n)(?:\(venv\) )?[^\r\n]*[#$] ?$", initial_output):
            raise DeployError(
                "Dedicated console does not show an idle shell prompt. Open it in the browser, "
                "wait for a free Bash prompt, inspect any previous run, then retry."
            )
        self.api(f"{self.console}/send_input", "POST", {"input": command})
        marker = re.compile(rf"(?m)^CRM_DEPLOY {run_id} {mode} ([0-9]{{1,3}})\r?$")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            match = marker.search(self.console_output())
            if match:
                code = int(match[1])
                LOG.info("Server confirmed %s exit %s", mode, code)
                if code:
                    raise DeployError(f"Server stage {mode} exited {code}. Inspect its private log.")
                return
            time.sleep(4)
        raise DeployError("Server completion unconfirmed. Inspect the private log before retrying.")

    def verify_health(self, sha, timeout=120):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            request = Request(
                f"https://{self.domain}/healthz/?deploy={secrets.token_hex(8)}",
                headers={"Cache-Control": "no-cache"},
            )
            try:
                with self.opener.open(request, timeout=10) as response:
                    if (response.status == 200 and response.read(16) == b"ok"
                            and response.headers.get("X-App-Revision") == sha):
                        return
            except (URLError, OSError):
                pass
            time.sleep(5)
        raise DeployError("Health check did not confirm the deployed revision.")

    def deploy(self, mode, sha, run_id):
        configuration = self.api(self.webapp)
        root = f"/home/{self.username}/mini-crm-realty"
        if (
            not isinstance(configuration, dict)
            or configuration.get("source_directory") != root
            or configuration.get("virtualenv_path") != f"{root}/venv"
            or configuration.get("python_version") not in {"3.12", "python312"}
        ):
            raise DeployError("PythonAnywhere source directory, virtualenv or Python setting mismatch.")
        self.run(mode, sha, run_id, timeout=1140)
        if mode == "apply":
            LOG.info("Requesting official web app reload.")
            self.api(f"{self.webapp}/reload", "POST", {})
            self.verify_health(sha)
            LOG.info("Health and worker revision confirmed.")
            self.run("ack", sha, run_id, timeout=60)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("pa-deploy.log", mode="w")],
    )
    try:
        sha = os.environ.get("PA_TARGET_SHA", "")
        mode = os.environ.get("PA_MODE", "")
        if mode not in {"dry-run", "apply"} or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise DeployError("Invalid mode or target SHA.")
        if subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() != sha:
            raise DeployError("Runner checkout does not match target SHA.")
        client = PythonAnywhere(*(os.environ.get(key, "") for key in (
            "PA_USERNAME", "PA_CONSOLE_ID", "PA_API_TOKEN",
        )))
        LOG.info("Target %s, mode %s", sha, mode)
        client.deploy(mode, sha, secrets.token_hex(16))
    except (DeployError, subprocess.CalledProcessError) as exc:
        LOG.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
