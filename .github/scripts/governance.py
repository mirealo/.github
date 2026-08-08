from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

EXPECTED_NAMES_BY_CATEGORY = {
    "work": frozenset(
        {"bug", "documentation", "enhancement", "maintenance", "dependencies"}
    ),
    "status": frozenset(
        {
            "status: needs-triage",
            "status: needs-info",
            "status: accepted",
            "status: in-progress",
            "status: blocked",
        }
    ),
    "priority": frozenset(
        {
            "priority: critical",
            "priority: high",
            "priority: medium",
            "priority: low",
        }
    ),
    "contribution": frozenset({"good first issue", "help wanted"}),
    "resolution": frozenset(
        {
            "resolution: duplicate",
            "resolution: not-actionable",
            "resolution: not-planned",
        }
    ),
}
ALLOWED_CATEGORIES = set(EXPECTED_NAMES_BY_CATEGORY)
COLOR_PATTERN = re.compile(r"^[0-9a-f]{6}$")
EXPECTED_LABEL_COUNT = sum(
    len(names) for names in EXPECTED_NAMES_BY_CATEGORY.values()
)


class GovernanceError(Exception):
    """Raised when a governance artifact violates an invariant."""


@dataclass(frozen=True)
class LabelDefinition:
    name: str
    color: str
    description: str
    category: str


@dataclass(frozen=True)
class RemoteLabel:
    name: str
    color: str
    description: str


@dataclass(frozen=True)
class LabelDrift:
    create: tuple[LabelDefinition, ...]
    update: tuple[tuple[LabelDefinition, RemoteLabel], ...]
    extra: tuple[RemoteLabel, ...]

    @property
    def clean(self) -> bool:
        return not (self.create or self.update or self.extra)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise GovernanceError(f"required command is unavailable: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip() or "unknown error"
        raise GovernanceError(
            f"command failed ({' '.join(command)}): {detail}"
        ) from error


def load_yaml(path: Path) -> object:
    version_result = _run(["yq", "--version"])
    version = f"{version_result.stdout}\n{version_result.stderr}".lower()
    if "mikefarah" in version or "version v4" in version:
        command = ["yq", "-o=json", ".", str(path)]
    else:
        command = ["yq", ".", str(path)]
    result = _run(command)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise GovernanceError(
            f"{path}: yq did not produce valid JSON: {error.msg}"
        ) from error


def _require_exact_keys(
    value: dict[str, object],
    expected: set[str],
    context: str,
) -> None:
    actual = set(value)
    if actual != expected:
        raise GovernanceError(
            f"{context}: expected keys {sorted(expected)}, got {sorted(actual)}"
        )


def validate_label_manifest(path: Path) -> tuple[LabelDefinition, ...]:
    document = load_yaml(path)
    if not isinstance(document, dict):
        raise GovernanceError(f"{path}: top level must be a mapping")
    _require_exact_keys(document, {"version", "labels"}, str(path))
    if document["version"] != 1:
        raise GovernanceError(f"{path}: version must equal 1")
    raw_labels = document["labels"]
    if not isinstance(raw_labels, list):
        raise GovernanceError(f"{path}: labels must be a list")

    labels: list[LabelDefinition] = []
    names: set[str] = set()
    for index, raw_label in enumerate(raw_labels):
        context = f"{path}: labels[{index}]"
        if not isinstance(raw_label, dict):
            raise GovernanceError(f"{context}: entry must be a mapping")
        _require_exact_keys(
            raw_label,
            {"name", "color", "description", "category"},
            context,
        )
        if not all(isinstance(raw_label[key], str) for key in raw_label):
            raise GovernanceError(f"{context}: every value must be a string")
        label = LabelDefinition(
            name=raw_label["name"],
            color=raw_label["color"],
            description=raw_label["description"],
            category=raw_label["category"],
        )
        if (
            label.name != label.name.lower()
            or label.name != label.name.strip()
            or not label.name
        ):
            raise GovernanceError(f"{context}: name must be non-empty lowercase")
        if label.name in names:
            raise GovernanceError(f"{path}: duplicate label: {label.name}")
        if not COLOR_PATTERN.fullmatch(label.color):
            raise GovernanceError(f"{context}: color must be six lowercase hex digits")
        if label.category not in ALLOWED_CATEGORIES:
            raise GovernanceError(f"{context}: unknown category: {label.category}")
        if (
            label.description != label.description.strip()
            or len(label.description) < 2
            or not label.description[0].isupper()
            or not label.description.endswith(".")
        ):
            raise GovernanceError(
                f"{context}: description must be a complete trimmed sentence"
            )
        names.add(label.name)
        labels.append(label)

    if len(labels) != EXPECTED_LABEL_COUNT:
        raise GovernanceError(
            f"{path}: expected {EXPECTED_LABEL_COUNT} labels, got {len(labels)}"
        )
    for category, expected_names in EXPECTED_NAMES_BY_CATEGORY.items():
        actual_names = {
            label.name for label in labels if label.category == category
        }
        if actual_names != expected_names:
            raise GovernanceError(
                f"{path}: {category} labels must equal the approved names "
                f"{sorted(expected_names)}, got {sorted(actual_names)}"
            )
    return tuple(labels)


def validate_repository(root: Path) -> list[str]:
    try:
        validate_label_manifest(root / ".github" / "labels.yml")
    except GovernanceError as error:
        return [str(error)]
    return []
