#!/usr/bin/env python3
"""Regenerate docs/code-index.md with RAW GitHub links for every repo file."""
from __future__ import annotations

import argparse
import errno
import os
import re
import socket
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_RAW_URL = "https://raw.githubusercontent.com/isty-maker/mini-crm-realty/refs/heads/main/"
RAW_URL_PATTERN = re.compile(
    r"^https://raw\.githubusercontent\.com/isty-maker/mini-crm-realty/refs/heads/main/.+"
)
REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = REPO_ROOT / "docs" / "code-index.md"

EXCLUDE_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "venv",
    "node_modules",
}
EXCLUDE_DIR_PATHS = {
    Path(".github") / "workflows",
}


def should_skip_dir(root: Path, current: Path) -> bool:
    """Return True if the directory should be excluded from the index."""
    rel = current.relative_to(root)
    if rel in EXCLUDE_DIR_PATHS:
        return True
    return any(part in EXCLUDE_DIR_NAMES for part in rel.parts)


def iter_repo_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirpath_path = Path(dirpath)
        rel_dir = dirpath_path.relative_to(root)
        # Filter directories in-place for os.walk
        filtered_dirnames = []
        for name in sorted(dirnames):
            candidate = dirpath_path / name
            if should_skip_dir(root, candidate):
                continue
            filtered_dirnames.append(name)
        dirnames[:] = filtered_dirnames

        for filename in sorted(filenames):
            file_path = dirpath_path / filename
            rel_path = file_path.relative_to(root)
            # Skip files under excluded directories even if os.walk reached them
            if any(part in EXCLUDE_DIR_NAMES for part in rel_path.parts):
                continue
            if any(rel_path.is_relative_to(p) for p in EXCLUDE_DIR_PATHS):  # type: ignore[attr-defined]
                # Python < 3.9 compatibility fallback handled below
                continue
            files.append(rel_path)
    # Ensure deterministic order
    files.sort(key=lambda p: p.as_posix())
    return files


def is_under(path: Path, ancestor: Path) -> bool:
    try:
        path.relative_to(ancestor)
        return True
    except ValueError:
        return False


# Compatibility fallback for Python < 3.9 where Path.is_relative_to does not exist
if not hasattr(Path, "is_relative_to"):
    def _is_relative_to(self: Path, other: Path) -> bool:
        return is_under(self, other)

    Path.is_relative_to = _is_relative_to  # type: ignore[attr-defined]


def group_files(paths: Iterable[Path]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = defaultdict(list)
    for path in paths:
        parent = path.parent.as_posix()
        section = "/" if parent == "." else parent
        grouped[section].append(path.as_posix())
    for files in grouped.values():
        files.sort()
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


USER_AGENT = "mini-crm-index/1.0 (+https://github.com/isty-maker/mini-crm-realty)"
RATE_LIMIT_SECONDS = 0.05
HEAD_TIMEOUT = 4.0
GET_TIMEOUT = 6.0
MAX_RETRIES = 2
BACKOFF_INITIAL = 0.2


class ValidationState:
    VALID = "valid"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class ValidationResult:
    url: str
    state: str
    detail: str


@dataclass
class ValidationSummary:
    results: List[ValidationResult]

    @property
    def valid_count(self) -> int:
        return sum(1 for result in self.results if result.state == ValidationState.VALID)

    @property
    def skipped(self) -> List[ValidationResult]:
        return [result for result in self.results if result.state == ValidationState.SKIPPED]

    @property
    def errors(self) -> List[ValidationResult]:
        return [result for result in self.results if result.state == ValidationState.ERROR]

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    @property
    def error_count(self) -> int:
        return len(self.errors)


def _send_request(url: str, *, method: str, timeout: float, headers: Dict[str, str]) -> int:
    request = Request(url, method=method, headers=headers)
    with urlopen(request, timeout=timeout) as response:  # type: ignore[arg-type]
        status = response.status
    time.sleep(RATE_LIMIT_SECONDS)
    return status


def _request_with_retries(
    url: str,
    *,
    method: str,
    timeout: float,
    headers: Dict[str, str],
    max_retries: int = MAX_RETRIES,
) -> int:
    attempt = 0
    delay = BACKOFF_INITIAL
    while True:
        try:
            return _send_request(url, method=method, timeout=timeout, headers=headers)
        except HTTPError as exc:
            time.sleep(RATE_LIMIT_SECONDS)
            if exc.code == 429 and attempt < max_retries:
                time.sleep(delay)
                delay *= 2
                attempt += 1
                continue
            raise
        except URLError as exc:
            time.sleep(RATE_LIMIT_SECONDS)
            if _is_timeout_error(exc.reason) and attempt < max_retries:
                time.sleep(delay)
                delay *= 2
                attempt += 1
                continue
            raise


def _is_timeout_error(reason: object) -> bool:
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return True
    if isinstance(reason, OSError) and getattr(reason, "errno", None) == errno.ETIMEDOUT:
        return True
    if isinstance(reason, str) and "timed out" in reason.lower():
        return True
    return False


def validate_url(url: str) -> ValidationResult:
    if not RAW_URL_PATTERN.match(url):
        return ValidationResult(url, ValidationState.ERROR, "malformed URL pattern")

    head_headers = {"User-Agent": USER_AGENT}
    head_detail = ""
    try:
        head_status = _request_with_retries(
            url,
            method="HEAD",
            timeout=HEAD_TIMEOUT,
            headers=head_headers,
        )
    except HTTPError as exc:
        head_status = exc.code
        head_detail = f"HEAD {exc.code}"
    except URLError as exc:
        head_status = None
        head_detail = f"HEAD error: {exc.reason if exc.reason else exc}"

    fallback_needed = False
    if head_status is not None:
        if 200 <= head_status <= 399:
            return ValidationResult(url, ValidationState.VALID, f"HEAD {head_status}")
        if head_status in {405, 403, 501}:
            fallback_needed = True
        elif head_status in {404, 410}:
            detail = head_detail or f"HEAD {head_status}"
            return ValidationResult(url, ValidationState.ERROR, detail)
        elif head_status >= 400:
            detail = head_detail or f"HEAD {head_status}"
            return ValidationResult(url, ValidationState.SKIPPED, detail)
    else:
        fallback_needed = True

    if not fallback_needed:
        # If we reached here, head_status is None but fallback not required (shouldn't happen)
        return ValidationResult(url, ValidationState.SKIPPED, "HEAD unknown failure")

    get_headers = {"User-Agent": USER_AGENT, "Range": "bytes=0-0"}
    try:
        get_status = _request_with_retries(
            url,
            method="GET",
            timeout=GET_TIMEOUT,
            headers=get_headers,
        )
    except HTTPError as exc:
        get_status = exc.code
    except URLError as exc:
        reason = exc.reason if exc.reason else exc
        detail = f"{head_detail}; GET error: {reason}" if head_detail else f"GET error: {reason}"
        return ValidationResult(url, ValidationState.SKIPPED, detail)

    if get_status in {200, 206, 304}:
        detail = f"{head_detail}; GET {get_status}" if head_detail else f"GET {get_status}"
        return ValidationResult(url, ValidationState.VALID, detail)
    if get_status in {404, 410}:
        detail = f"{head_detail}; GET {get_status}" if head_detail else f"GET {get_status}"
        return ValidationResult(url, ValidationState.ERROR, detail)
    detail = f"{head_detail}; GET {get_status}" if head_detail else f"GET {get_status}"
    return ValidationResult(url, ValidationState.SKIPPED, detail)


def validate_links(urls: Iterable[str]) -> ValidationSummary:
    results = [validate_url(url) for url in urls]
    return ValidationSummary(results)


def print_validation_summary(summary: ValidationSummary) -> None:
    print(
        "[validate] Summary — VALID: {valid}, SKIPPED(blocked): {skipped}, ERROR: {errors}".format(
            valid=summary.valid_count,
            skipped=summary.skipped_count,
            errors=summary.error_count,
        )
    )

    if summary.error_count:
        print("[validate] Broken URLs (first 10):")
        for result in summary.errors[:10]:
            print(f"  - {result.url} ({result.detail})")

    if summary.skipped_count:
        print("[validate] Skipped (blocked) URLs (first 5):")
        for result in summary.skipped[:5]:
            print(f"  - {result.url} ({result.detail})")



def build_document(grouped: Dict[str, List[str]]) -> str:
    lines = ["# Repository Code Index", "", "_Generated by scripts/update_code_index.py_", ""]
    for section, files in grouped.items():
        lines.append(f"## {section}")
        lines.append("")
        for path in files:
            lines.append(f"[{path}]")
            lines.append(f"RAW: {BASE_RAW_URL}{path}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def resolve_validation_mode(args: argparse.Namespace) -> tuple[bool, str]:
    env_value = os.getenv("CODE_INDEX_VALIDATE")
    if args.validate:
        return True, "--validate"
    if args.no_validate:
        return False, "--no-validate"

    if env_value is not None:
        normalized = env_value.strip().lower()
        if normalized in {"0", "false", "no", "off"}:
            return False, f"CODE_INDEX_VALIDATE={env_value}"
        if normalized in {"1", "true", "yes", "on"}:
            return True, f"CODE_INDEX_VALIDATE={env_value}"
    return True, "default"


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate docs/code-index.md with RAW links")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--validate",
        action="store_true",
        help="Force HTTP validation of generated RAW links",
    )
    group.add_argument(
        "--no-validate",
        action="store_true",
        help="Disable HTTP validation of generated RAW links",
    )
    args = parser.parse_args()

    should_validate, reason = resolve_validation_mode(args)
    mode_label = "ENABLED" if should_validate else "DISABLED"
    print(f"[validate] Validation mode: {mode_label} ({reason})")

    files = iter_repo_files(REPO_ROOT)
    grouped = group_files(files)
    document = build_document(grouped)
    DOC_PATH.write_text(document, encoding="utf-8")
    print(f"[info] Wrote index for {len(files)} files to {DOC_PATH.relative_to(REPO_ROOT)}")

    if not should_validate:
        print("[validate] Link validation disabled; skipping network checks.")
        return

    summary = validate_links(BASE_RAW_URL + path.as_posix() for path in files)
    print_validation_summary(summary)
    if summary.error_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
