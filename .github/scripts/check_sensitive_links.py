#!/usr/bin/env python3
from __future__ import annotations

import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import (
    HTTPRedirectHandler,
    OpenerDirector,
    Request,
    build_opener,
)

ALLOWED_HOSTS = frozenset({"github.com", "support.github.com"})
REQUEST_TIMEOUT_SECONDS = 10
MAX_REDIRECTS = 5
SENSITIVE_LINKS = (
    (
        "published security policy",
        "https://github.com/mirealo/.github/blob/main/SECURITY.md",
    ),
    (
        "published support policy",
        "https://github.com/mirealo/.github/blob/main/SUPPORT.md",
    ),
    (
        "private vulnerability reporting",
        "https://github.com/mirealo/.github/security/advisories/new",
    ),
    (
        "GitHub conduct escalation",
        "https://support.github.com/contact/report-abuse",
    ),
)


def validate_sensitive_url(url: str) -> None:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("URL has an invalid port") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        raise ValueError("URL is outside the HTTPS host allowlist")


class BoundedRedirectHandler(HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS
    max_repeats = 2

    def redirect_request(
        self,
        request,
        file_pointer,
        code,
        message,
        headers,
        new_url,
    ):
        try:
            validate_sensitive_url(new_url)
        except ValueError as error:
            raise HTTPError(
                new_url,
                code,
                "redirect target is outside the allowlist",
                headers,
                file_pointer,
            ) from error
        return super().redirect_request(
            request,
            file_pointer,
            code,
            message,
            headers,
            new_url,
        )


def check_sensitive_links(
    opener: OpenerDirector | None = None,
) -> list[str]:
    errors: list[str] = []
    active_opener = opener or build_opener(BoundedRedirectHandler())
    for name, url in SENSITIVE_LINKS:
        try:
            validate_sensitive_url(url)
            request = Request(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": "mirealo-governance-monitor/1.0",
                },
                method="GET",
            )
            with active_opener.open(
                request,
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as response:
                validate_sensitive_url(response.geturl())
                status = response.getcode()
                response.read(1)
                if status != 200:
                    errors.append(f"{name}: unexpected HTTP status {status}")
        except HTTPError as error:
            errors.append(f"{name}: HTTP {error.code}")
        except (TimeoutError, URLError, OSError, ValueError) as error:
            errors.append(f"{name}: unavailable ({type(error).__name__})")
    return errors


def main() -> int:
    errors = check_sensitive_links()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Sensitive link check passed ({len(SENSITIVE_LINKS)} URLs).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
