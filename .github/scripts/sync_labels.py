#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from governance import (
    GovernanceError,
    LabelDefinition,
    LabelDrift,
    RemoteLabel,
    compare_labels,
    validate_label_manifest,
)

REPOSITORY_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/"
    r"[A-Za-z0-9._-]{1,100}$"
)
REMOTE_LABEL_LIMIT = 1000


def repository_name(value: str) -> str:
    if (
        REPOSITORY_PATTERN.fullmatch(value) is None
        or "--" in value.partition("/")[0]
        or value.partition("/")[2] in {".", ".."}
    ):
        raise argparse.ArgumentTypeError(
            "repository must be a valid owner/name identifier"
        )
    return value


def run_gh(arguments: list[str]) -> str:
    command = ["gh", *arguments]
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise GovernanceError("required command is unavailable: gh") from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip() or "unknown error"
        raise GovernanceError(f"GitHub command failed: {detail}") from error
    return result.stdout


def read_remote_labels(repository: str) -> tuple[RemoteLabel, ...]:
    output = run_gh(
        [
            "label",
            "list",
            "--repo",
            repository,
            "--limit",
            str(REMOTE_LABEL_LIMIT),
            "--json",
            "name,color,description",
        ]
    )
    try:
        values = json.loads(output)
    except json.JSONDecodeError as error:
        raise GovernanceError("gh label list returned invalid JSON") from error
    if not isinstance(values, list):
        raise GovernanceError("gh label list did not return a list")
    labels: list[RemoteLabel] = []
    for value in values:
        if not isinstance(value, dict):
            raise GovernanceError("gh label list returned a non-object entry")
        labels.append(
            RemoteLabel(
                name=str(value.get("name", "")),
                color=str(value.get("color", "")).lower(),
                description=str(value.get("description") or ""),
            )
        )
    return tuple(labels)


def report(drift: LabelDrift) -> None:
    for label in drift.create:
        print(f"CREATE {label.name}")
    for expected, actual in drift.update:
        print(
            f"UPDATE {expected.name}: "
            f"{actual.color}/{actual.description!r} -> "
            f"{expected.color}/{expected.description!r}"
        )
    for label in drift.extra:
        print(f"EXTRA {label.name}")
    if drift.clean:
        print("Labels match the canonical manifest.")


def create_label(repository: str, label: LabelDefinition) -> None:
    run_gh(
        [
            "label",
            "create",
            label.name,
            "--repo",
            repository,
            "--color",
            label.color,
            "--description",
            label.description,
        ]
    )


def update_label(repository: str, label: LabelDefinition) -> None:
    run_gh(
        [
            "label",
            "edit",
            label.name,
            "--repo",
            repository,
            "--color",
            label.color,
            "--description",
            label.description,
        ]
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare or synchronize repository labels with the manifest."
    )
    parser.add_argument(
        "--repo",
        required=True,
        type=repository_name,
        metavar="OWNER/NAME",
        help="Repository whose labels will be inspected.",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when repository labels drift.",
    )
    modes.add_argument(
        "--apply",
        action="store_true",
        help="Create or update labels, then verify. Never delete.",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    root = Path(__file__).resolve().parents[2]
    try:
        expected = validate_label_manifest(root / ".github" / "labels.yml")
    except GovernanceError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    try:
        drift = compare_labels(expected, read_remote_labels(arguments.repo))
        report(drift)
        if arguments.check:
            return 0 if drift.clean else 1
        if not arguments.apply:
            return 0
        if drift.extra:
            print(
                "ERROR: refusing --apply while unexpected labels exist; "
                "review explicit renames first.",
                file=sys.stderr,
            )
            return 2
        for label in drift.create:
            create_label(arguments.repo, label)
        for label, _current in drift.update:
            update_label(arguments.repo, label)
        verified = compare_labels(
            expected,
            read_remote_labels(arguments.repo),
        )
        report(verified)
        return 0 if verified.clean else 2
    except GovernanceError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
