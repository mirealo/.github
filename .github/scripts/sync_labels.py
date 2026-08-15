#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
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
GITHUB_HOSTNAME = "github.com"
RETIREMENT_REPOSITORY = "mirealo/.github"
RETIREMENT_STEP_LIMIT_V1 = 7
OBSOLETE_LABELS_V1 = (
    RemoteLabel(
        "priority: critical",
        "b60205",
        "Public projection of native Priority Urgent; the native field is authoritative.",
    ),
    RemoteLabel(
        "priority: high",
        "d93f0b",
        "Public projection of native Priority High; the native field is authoritative.",
    ),
    RemoteLabel(
        "priority: medium",
        "fbca04",
        "Public projection of native Priority Medium; the native field is authoritative.",
    ),
    RemoteLabel(
        "priority: low",
        "c5def5",
        "Public projection of native Priority Low; the native field is authoritative.",
    ),
    RemoteLabel(
        "resolution: duplicate",
        "cfd3d7",
        "Closed because equivalent work is already tracked elsewhere.",
    ),
    RemoteLabel(
        "resolution: not-actionable",
        "cfd3d7",
        "Closed because the report is incomplete, unsupported, or outside scope.",
    ),
    RemoteLabel(
        "resolution: not-planned",
        "cfd3d7",
        "Closed because the requested work is not planned.",
    ),
)


@dataclass(frozen=True)
class LabelUsageV1:
    label: RemoteLabel
    issues: int
    pull_requests: int


@dataclass(frozen=True)
class RetirementUsageProofV1:
    repository: str
    results: tuple[LabelUsageV1, ...]


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


def retirement_repository_target(repository: str) -> str:
    if repository != RETIREMENT_REPOSITORY:
        raise GovernanceError("refusing an unapproved label retirement")
    return f"{GITHUB_HOSTNAME}/{repository}"


def read_retirement_labels_v1(repository: str) -> tuple[RemoteLabel, ...]:
    return read_remote_labels(retirement_repository_target(repository))


def _read_retirement_label_use_count_v1(
    label: RemoteLabel,
    item_type: str,
) -> int:
    if label not in OBSOLETE_LABELS_V1 or item_type not in {"issue", "pr"}:
        raise GovernanceError("refusing an unapproved label-usage query")
    output = run_gh(
        [
            "api",
            "--hostname",
            GITHUB_HOSTNAME,
            "--method",
            "GET",
            "/search/issues",
            "--header",
            "X-GitHub-Api-Version: 2026-03-10",
            "--field",
            (
                f'q=repo:{RETIREMENT_REPOSITORY} is:{item_type} '
                f'label:"{label.name}"'
            ),
            "--field",
            "per_page=1",
            "--jq",
            "{total_count, incomplete_results}",
        ]
    )
    try:
        result = json.loads(output)
    except json.JSONDecodeError as error:
        raise GovernanceError(
            "GitHub label-usage search returned invalid JSON"
        ) from error
    if not isinstance(result, dict):
        raise GovernanceError(
            "GitHub label-usage search did not return an object"
        )
    count = result.get("total_count")
    if (
        set(result) != {"total_count", "incomplete_results"}
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        or result.get("incomplete_results") is not False
    ):
        raise GovernanceError(
            "GitHub label-usage search returned an ambiguous result"
        )
    return count


def prove_retirement_labels_unused_v1(
    repository: str,
) -> RetirementUsageProofV1:
    retirement_repository_target(repository)
    results: list[LabelUsageV1] = []
    for label in OBSOLETE_LABELS_V1:
        usage = LabelUsageV1(
            label=label,
            issues=_read_retirement_label_use_count_v1(label, "issue"),
            pull_requests=_read_retirement_label_use_count_v1(label, "pr"),
        )
        if usage.issues or usage.pull_requests:
            raise GovernanceError(
                f"refusing to retire {label.name!r}: used by "
                f"{usage.issues} issue(s) and "
                f"{usage.pull_requests} pull request(s)"
            )
        results.append(usage)
    return RetirementUsageProofV1(repository, tuple(results))


def _validate_retirement_usage_proof_v1(
    proof: object,
) -> tuple[LabelUsageV1, ...]:
    error = "refusing deletion without a complete zero-use proof"
    if not isinstance(proof, RetirementUsageProofV1):
        raise GovernanceError(error)
    if not isinstance(proof.results, tuple) or not all(
        isinstance(result, LabelUsageV1) for result in proof.results
    ):
        raise GovernanceError(error)
    expected = tuple(OBSOLETE_LABELS_V1)
    actual = tuple(result.label for result in proof.results)
    counts_are_zero = all(
        type(count) is int and count == 0
        for result in proof.results
        for count in (result.issues, result.pull_requests)
    )
    if (
        proof.repository != RETIREMENT_REPOSITORY
        or actual != expected
        or not counts_are_zero
    ):
        raise GovernanceError(error)
    return proof.results


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


def validate_retirement_state(
    expected: tuple[LabelDefinition, ...],
    remote: tuple[RemoteLabel, ...],
) -> tuple[str, ...]:
    if len(remote) >= REMOTE_LABEL_LIMIT:
        raise GovernanceError(
            "remote label inventory may be truncated; refusing retirement"
        )
    remote_names = [label.name for label in remote]
    if len(remote_names) != len({name.casefold() for name in remote_names}):
        raise GovernanceError("remote labels contain duplicate names")

    drift = compare_labels(expected, remote)
    if drift.create or drift.update:
        raise GovernanceError(
            "refusing retirement until all retained labels match the manifest"
        )

    frozen_by_name = {label.name: label for label in OBSOLETE_LABELS_V1}
    unexpected = [
        label.name for label in drift.extra if label.name not in frozen_by_name
    ]
    if unexpected:
        raise GovernanceError(
            "refusing retirement while unexpected labels exist: "
            + ", ".join(sorted(unexpected))
        )

    for actual in drift.extra:
        frozen = frozen_by_name[actual.name]
        if (
            actual.color.lower() != frozen.color
            or actual.description != frozen.description
        ):
            raise GovernanceError(
                f"refusing retirement because {actual.name!r} no longer "
                "matches its historical definition"
            )
    present_names = {label.name for label in drift.extra}
    return tuple(
        label.name
        for label in OBSOLETE_LABELS_V1
        if label.name in present_names
    )


def delete_next_retirement_label_v1(
    expected: tuple[LabelDefinition, ...],
    current_remote: tuple[RemoteLabel, ...],
    proof: object,
) -> str:
    results = _validate_retirement_usage_proof_v1(proof)
    present = validate_retirement_state(expected, current_remote)
    if not present:
        raise GovernanceError("no frozen label remains to retire")

    next_name = present[0]
    proven_names = tuple(result.label.name for result in results)
    if next_name not in proven_names:
        raise GovernanceError(
            "retirement state is incompatible with the zero-use proof"
        )
    run_gh(
        [
            "label",
            "delete",
            next_name,
            "--repo",
            retirement_repository_target(RETIREMENT_REPOSITORY),
            "--yes",
        ]
    )
    return next_name


def validate_retirement_preflight_v1(
    expected: tuple[LabelDefinition, ...],
    remote: tuple[RemoteLabel, ...],
) -> tuple[str, ...]:
    present = validate_retirement_state(expected, remote)
    missing = [
        label.name for label in OBSOLETE_LABELS_V1 if label.name not in present
    ]
    if missing:
        raise GovernanceError(
            "retirement preflight is missing frozen labels: "
            + ", ".join(missing)
        )
    return present


def _validate_retirement_progress_v1(
    expected: tuple[LabelDefinition, ...],
    remote: tuple[RemoteLabel, ...],
) -> tuple[str, ...]:
    present = validate_retirement_state(expected, remote)
    frozen_names = tuple(label.name for label in OBSOLETE_LABELS_V1)
    deleted_count = len(frozen_names) - len(present)
    if present != frozen_names[deleted_count:]:
        raise GovernanceError(
            "retirement progress is not an exact deleted prefix"
        )
    return present


def _retirement_inventory_signature_v1(
    remote: tuple[RemoteLabel, ...],
) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        sorted(
            (label.name, label.color.lower(), label.description)
            for label in remote
        )
    )


def retire_obsolete_labels_v1(
    repository: str,
    expected: tuple[LabelDefinition, ...],
) -> LabelDrift:
    retirement_repository_target(repository)
    frozen_names = tuple(label.name for label in OBSOLETE_LABELS_V1)
    successful_steps = 0
    current = read_retirement_labels_v1(repository)

    while True:
        present = _validate_retirement_progress_v1(expected, current)
        if not present:
            final = compare_labels(expected, current)
            if not final.clean:
                raise GovernanceError(
                    "final label inventory does not match the manifest"
                )
            return final
        if successful_steps >= RETIREMENT_STEP_LIMIT_V1:
            raise GovernanceError("label retirement exceeded seven steps")
        if successful_steps == 0 and present == frozen_names:
            validate_retirement_preflight_v1(expected, current)

        proof = prove_retirement_labels_unused_v1(repository)
        confirmed = read_retirement_labels_v1(repository)
        confirmed_present = _validate_retirement_progress_v1(
            expected,
            confirmed,
        )
        if _retirement_inventory_signature_v1(
            confirmed
        ) != _retirement_inventory_signature_v1(current):
            raise GovernanceError(
                "label inventory changed after the zero-use proof"
            )

        delete_next_retirement_label_v1(expected, confirmed, proof)
        successful_steps += 1
        advanced = read_retirement_labels_v1(repository)
        advanced_present = _validate_retirement_progress_v1(expected, advanced)
        if advanced_present != confirmed_present[1:]:
            raise GovernanceError(
                "label retirement did not remove exactly the next label"
            )
        current = advanced


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
