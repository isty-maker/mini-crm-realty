"""Rehearse importing a synthetic passport on a disposable HTTPS CRM."""

import argparse
import json
import os
import ssl
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CRM:
    def __init__(self, origin, cafile, token):
        self.root = origin.rstrip("/") + "/api/v1/"
        self.http = build_opener(NoRedirects(), HTTPSHandler(context=ssl.create_default_context(cafile=cafile)))
        self.token = token

    def request(self, path, method="GET", data=None, *, etag=None, request_key=None):
        headers = {"Authorization": f"Bearer {self.token}"}
        if etag is not None:
            headers["If-Match"] = etag
        if request_key is not None:
            headers["Idempotency-Key"] = request_key
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.root + path, method=method, headers=headers,
                          data=json.dumps(data).encode() if data is not None else None)
        try:
            with self.http.open(request, timeout=10) as response:
                return json.load(response), response.headers.get("ETag")
        except HTTPError as error:
            raise SystemExit(f"{method} {path}: HTTP {error.code}. Re-read and review before retrying.") from None


def patch_object(api, path, data, expected, apply):
    current, etag = api.request(path)
    if expected is not None and expected != etag:
        raise SystemExit("Object version changed. Read current data and confirm a new version.")
    preview, version = api.request(path + "?dry_run=1", "PATCH", data, etag=etag)
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    if not apply:
        return current
    if preview["warnings"]:
        raise SystemExit("Review the identity warnings before using a direct PATCH.")
    saved, _ = api.request(path, "PATCH", data, etag=version)
    verified, _ = api.request(path)
    if verified["version"] != saved["version"]:
        raise SystemExit("Version moved after save. Re-read before continuing.")
    return verified


def create_passport(api, fixture, namespace, apply):
    body = {"listing": fixture["create"]}
    preview, _ = api.request("objects/?dry_run=1", "POST", body)
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    if not apply:
        return
    if preview["confirmation_required"]:
        raise SystemExit("Review duplicate warnings before explicitly confirming creation.")
    record, _ = api.request("objects/", "POST", body, request_key=namespace + "-object")
    path = f'objects/{record["id"]}/'
    patch_object(api, path, fixture["update"], None, True)
    catalog, _ = api.request("document-types/")
    types = {item["slug"]: item["id"] for item in catalog["document_types"]}
    files = {}
    for scope in ("files", "bases", "owners", "documents", "notes"):
        for index, entry in enumerate(fixture[scope]):
            data = dict(entry)
            if scope == "documents":
                data["document_type"] = types[data.pop("type")]
                if "file" in data:
                    data["original"] = files[data.pop("file")]
            _, etag = api.request(path)
            _, version = api.request(path + scope + "/?dry_run=1", "POST", data, etag=etag)
            row, _ = api.request(path + scope + "/", "POST", data, etag=version,
                                 request_key=f"{namespace}-{scope}-{index}")
            checked, _ = api.request(f'{path}{scope}/{row["id"]}/')
            if checked["version"] != row["version"]:
                raise SystemExit("Linked record changed after save.")
            if scope == "files":
                files[data["file_id"]] = row["id"]
    print(f'Verified synthetic object {record["id"]}.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--ca-file", required=True)
    candidate = parser.add_mutually_exclusive_group(required=True)
    candidate.add_argument("--create", action="store_true")
    candidate.add_argument("--object-id", type=int)
    parser.add_argument("--expected-etag", help="Quoted ETag, required when applying a refresh to an existing object.")
    parser.add_argument("--apply", action="store_true", help="Write to the disposable test database.")
    parser.add_argument("--namespace", default="synthetic-passport-v1")
    options = parser.parse_args()
    origin = urlsplit(options.origin)
    if (origin.scheme != "https" or origin.hostname not in {"127.0.0.1", "::1", "localhost"}
            or origin.username or origin.path not in ("", "/") or origin.query or origin.fragment):
        parser.error("Use only a disposable HTTPS CRM on loopback.")
    if options.object_id is not None and options.apply and not options.expected_etag:
        parser.error("--expected-etag is required when applying a refresh.")
    token = os.environ.get("CRM_TEST_API_TOKEN")
    if not token:
        parser.error("Set CRM_TEST_API_TOKEN to a disposable test key in the local environment.")
    fixture_path = Path(__file__).resolve().parents[1] / "docs" / "examples" / "crm-api-passport.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    api = CRM(options.origin, options.ca_file, token)
    if options.create:
        create_passport(api, fixture, options.namespace, options.apply)
    else:
        saved = patch_object(api, f"objects/{options.object_id}/", fixture["refresh_example"],
                             options.expected_etag, options.apply)
        print(f'ETag: "{saved["version"]}"')


if __name__ == "__main__":
    main()
