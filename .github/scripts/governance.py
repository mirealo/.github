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
FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
APPROVED_CHECKOUT_ACTION = (
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
)
EXPECTED_LABEL_COUNT = sum(
    len(names) for names in EXPECTED_NAMES_BY_CATEGORY.values()
)
EXPECTED_FORMS = (
    "01-bug-report.yml",
    "02-feature-proposal.yml",
    "03-documentation-issue.yml",
    "04-maintenance-proposal.yml",
)
EXPECTED_FORM_METADATA = {
    "01-bug-report.yml": (
        "Bug",
        ("bug", "status: needs-triage"),
    ),
    "02-feature-proposal.yml": (
        "Feature",
        ("enhancement", "status: needs-triage"),
    ),
    "03-documentation-issue.yml": (
        "Task",
        ("documentation", "status: needs-triage"),
    ),
    "04-maintenance-proposal.yml": (
        "Task",
        ("maintenance", "status: needs-triage"),
    ),
}
APPROVED_TYPES = {"Bug", "Feature", "Task"}
SUPPORTED_BODY_TYPES = {
    "markdown",
    "input",
    "textarea",
    "dropdown",
    "checkboxes",
    "upload",
}
FIELD_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
YAML_PROFILE_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
YAML_PROFILE_MAPPING_PATTERN = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_.-]*):(?: +(.*))?$"
)
YAML_PROFILE_LINE_BREAK_PATTERN = re.compile(r"\r\n|[\r\n]")
YAML_PROFILE_NONPORTABLE_LINE_CHARACTERS = {
    "\u0085": "U+0085",
    "\u2028": "U+2028",
    "\u2029": "U+2029",
}
YAML_PROFILE_RESERVED_KEYS = frozenset({"true", "false", "null"})
YAML_PROFILE_KEY_ERROR = (
    "mapping keys must use only ASCII letters, digits, _, ., and -, begin "
    "with an ASCII letter or _, and not equal true, false, or null"
)
YAML_PROFILE_BLOCK_HEADER_PATTERN = re.compile(
    r"^[|>](?:[+-][1-9]?|[1-9][+-]?)?$"
)
YAML_PROFILE_FORBIDDEN_NODE_PREFIXES = {
    "{": "flow collections are unsupported",
    "[": "flow collections are unsupported",
    "&": "anchors are unsupported",
    "*": "aliases are unsupported",
    "!": "tags are unsupported",
    "%": "directives are unsupported",
}
SECURITY_URL = "https://github.com/mirealo/.github/blob/main/SECURITY.md"
SUPPORT_URL = "https://github.com/mirealo/.github/blob/main/SUPPORT.md"
REQUIRED_COMMUNITY_FILES = (
    Path("README.md"),
    Path("profile/README.md"),
    Path("GOVERNANCE.md"),
    Path("CONTRIBUTING.md"),
    Path("SECURITY.md"),
    Path("SUPPORT.md"),
    Path("CODE_OF_CONDUCT.md"),
    Path("PULL_REQUEST_TEMPLATE.md"),
    Path(".github/CODEOWNERS"),
)
PLACEHOLDER_PATTERN = re.compile(
    r"\b(?:TBD|TODO|FIXME|XXX)\b|<<<<<<<|=======|>>>>>>>",
    re.IGNORECASE,
)
MARKDOWN_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
CODEOWNERS_WILDCARD_PATTERN = re.compile(
    r"(?m)^\*\s+@\S+(?:\s+@\S+)*\s*$"
)
REQUIRED_POLICY_HEADINGS = {
    Path("CONTRIBUTING.md"): (
        "## Before contributing",
        "## Propose substantial work",
        "## Validation evidence",
        "## Pull requests",
        "## Contribution provenance",
        "## Review and decisions",
    ),
    Path("SECURITY.md"): (
        "## Supported versions",
        "## Reporting a vulnerability",
        "## What to include",
        "## Safe testing",
        "## Response process",
        "## Coordinated disclosure",
    ),
    Path("SUPPORT.md"): (
        "## Issue tracker scope",
        "## Questions and operational support",
        "## Unsupported requests",
        "## Security and sensitive information",
    ),
    Path("CODE_OF_CONDUCT.md"): (
        "## Our standard",
        "## Unacceptable behavior",
        "## Reporting concerns",
        "## Enforcement",
        "## Scope",
    ),
    Path("PULL_REQUEST_TEMPLATE.md"): (
        "## Summary",
        "## Linked work",
        "## Changes",
        "## Validation evidence",
        "## Risk and recovery",
        "## Checklist",
    ),
}
EXPECTED_WORKFLOW_TRIGGERS = {
    "pull_request": None,
    "push": {"branches": ["main"]},
    "workflow_dispatch": None,
}
EXPECTED_CONCURRENCY = {
    "group": "governance-${{ github.workflow }}-${{ github.ref }}",
    "cancel-in-progress": True,
}
EXPECTED_RUN_SCRIPTS = (
    "python3 --version\nyq --version",
    "python3 -m unittest discover -s .github/scripts -p 'test_*.py' -v",
    "python3 .github/scripts/validate_governance.py",
)
EXPECTED_STEP_NAMES = (
    "Check out repository",
    "Report tool versions",
    "Run governance unit tests",
    "Validate governance repository",
)
EXPECTED_STEP_KEYS = (
    {"name", "uses", "with"},
    {"name", "run"},
    {"name", "run"},
    {"name", "run"},
)
EXPECTED_DEPENDABOT_UPDATE = {
    "package-ecosystem": "github-actions",
    "directory": "/",
    "schedule": {"interval": "monthly"},
    "groups": {"github-actions": {"patterns": ["*"]}},
    "open-pull-requests-limit": 5,
    "labels": ["dependencies", "status: needs-triage"],
    "commit-message": {"prefix": "ci"},
}


class GovernanceError(Exception):
    """Raised when a governance artifact violates an invariant."""


@dataclass(frozen=True)
class _YamlProfileNode:
    empty: bool
    block_scalar: bool


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


def compare_labels(
    expected: tuple[LabelDefinition, ...],
    actual: tuple[RemoteLabel, ...],
) -> LabelDrift:
    expected_by_name = {label.name: label for label in expected}
    actual_by_name = {label.name: label for label in actual}
    create = tuple(
        expected_by_name[name]
        for name in sorted(expected_by_name.keys() - actual_by_name.keys())
    )
    update = tuple(
        (expected_by_name[name], actual_by_name[name])
        for name in sorted(expected_by_name.keys() & actual_by_name.keys())
        if (
            expected_by_name[name].color.lower() != actual_by_name[name].color.lower()
            or expected_by_name[name].description != actual_by_name[name].description
        )
    )
    extra = tuple(
        actual_by_name[name]
        for name in sorted(actual_by_name.keys() - expected_by_name.keys())
    )
    return LabelDrift(create=create, update=update, extra=extra)


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


def _yaml_profile_error(path: Path, line_number: int, reason: str) -> None:
    raise GovernanceError(f"{path}:{line_number}: {reason}")


def _strip_yaml_profile_comment(value: str) -> str:
    for index, character in enumerate(value):
        if character == "#" and (index == 0 or value[index - 1] == " "):
            return value[:index].rstrip(" ")
    return value.rstrip(" ")


def _validate_yaml_profile_key(
    key: str,
    path: Path,
    line_number: int,
) -> None:
    if (
        YAML_PROFILE_KEY_PATTERN.fullmatch(key) is None
        or key.lower() in YAML_PROFILE_RESERVED_KEYS
    ):
        _yaml_profile_error(path, line_number, YAML_PROFILE_KEY_ERROR)


def _yaml_profile_mapping_entry(content: str) -> tuple[str, str] | None:
    match = YAML_PROFILE_MAPPING_PATTERN.fullmatch(content.rstrip(" "))
    if match is None:
        return None
    key, value = match.groups()
    return key, (value or "").lstrip(" ")


def _yaml_profile_mapping_separator(value: str) -> int | None:
    if value.startswith(("\"", "'")):
        return None
    value = _strip_yaml_profile_comment(value)
    for index, character in enumerate(value):
        if character == ":" and (
            index + 1 == len(value) or value[index + 1] == " "
        ):
            return index
    return None


def _validate_yaml_profile_node(
    value: str,
    path: Path,
    line_number: int,
) -> _YamlProfileNode:
    value = value.lstrip(" ")
    if not value:
        return _YamlProfileNode(empty=True, block_scalar=False)

    if value[0] in {"\"", "'"}:
        quote = value[0]
        index = 1
        escaped = False
        while index < len(value):
            character = value[index]
            if quote == "\"":
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    break
            elif character == quote:
                if index + 1 < len(value) and value[index + 1] == quote:
                    index += 2
                    continue
                break
            index += 1
        else:
            _yaml_profile_error(
                path,
                line_number,
                "multiline quoted scalars are unsupported",
            )

        tail = value[index + 1 :]
        if tail and tail[0] != " ":
            _yaml_profile_error(
                path,
                line_number,
                "content after a quoted scalar is unsupported",
            )
        tail = tail.lstrip(" ")
        if tail and not tail.startswith("#"):
            _yaml_profile_error(
                path,
                line_number,
                "content after a quoted scalar is unsupported",
            )
        return _YamlProfileNode(empty=False, block_scalar=False)

    value = _strip_yaml_profile_comment(value)
    if not value:
        return _YamlProfileNode(empty=True, block_scalar=False)
    if value[0] in YAML_PROFILE_FORBIDDEN_NODE_PREFIXES:
        _yaml_profile_error(
            path,
            line_number,
            YAML_PROFILE_FORBIDDEN_NODE_PREFIXES[value[0]],
        )
    if value[0] in {"|", ">"}:
        if YAML_PROFILE_BLOCK_HEADER_PATTERN.fullmatch(value) is None:
            _yaml_profile_error(
                path,
                line_number,
                "invalid block scalar header",
            )
        return _YamlProfileNode(empty=False, block_scalar=True)
    return _YamlProfileNode(empty=False, block_scalar=False)


def _require_yaml_profile_container(
    level_kinds: dict[int, str],
    indentation: int,
    kind: str,
    path: Path,
    line_number: int,
) -> None:
    existing = level_kinds.get(indentation)
    if existing is not None and existing != kind:
        _yaml_profile_error(
            path,
            line_number,
            "mapping and sequence entries cannot share one block container",
        )
    level_kinds[indentation] = kind


def _record_yaml_profile_key(
    scopes: list[tuple[int, set[str]]],
    indentation: int,
    key: str,
    path: Path,
    line_number: int,
    *,
    new_sequence_item: bool = False,
) -> None:
    if new_sequence_item:
        while scopes and scopes[-1][0] >= indentation:
            scopes.pop()
        keys: set[str] = set()
        scopes.append((indentation, keys))
    else:
        while scopes and scopes[-1][0] > indentation:
            scopes.pop()
        if scopes and scopes[-1][0] == indentation:
            keys = scopes[-1][1]
        else:
            keys = set()
            scopes.append((indentation, keys))
    if key in keys:
        _yaml_profile_error(
            path,
            line_number,
            f"duplicate YAML mapping key: {key}",
        )
    keys.add(key)


def _validate_yaml_profile(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise GovernanceError(f"{path}: unable to read YAML profile") from error
    lines = YAML_PROFILE_LINE_BREAK_PATTERN.split(text)
    scopes: list[tuple[int, set[str]]] = []
    level_kinds: dict[int, str] = {}
    previous_indentation: int | None = None
    permitted_deeper_indentation: set[int] = set()
    block_scalar_indentation: int | None = None

    for line_number, raw_line in enumerate(lines, start=1):
        for character, code_point in YAML_PROFILE_NONPORTABLE_LINE_CHARACTERS.items():
            if character in raw_line:
                _yaml_profile_error(
                    path,
                    line_number,
                    f"{code_point} is unsupported by the portable YAML profile",
                )
        if "\t" in raw_line:
            _yaml_profile_error(path, line_number, "tabs are unsupported")

        indentation = len(raw_line) - len(raw_line.lstrip(" "))
        if block_scalar_indentation is not None:
            if not raw_line.strip(" ") or indentation > block_scalar_indentation:
                continue
            block_scalar_indentation = None

        content = raw_line[indentation:]
        if not content or content.startswith("#"):
            continue
        if indentation % 2:
            _yaml_profile_error(
                path,
                line_number,
                "indentation must use two-space increments",
            )
        if previous_indentation is None and indentation != 0:
            _yaml_profile_error(
                path,
                line_number,
                "the first structural line must not be indented",
            )
        if (
            previous_indentation is not None
            and indentation > previous_indentation
            and indentation not in permitted_deeper_indentation
        ):
            _yaml_profile_error(
                path,
                line_number,
                "indentation skips an expected structural level",
            )

        for level in tuple(level_kinds):
            if level > indentation:
                del level_kinds[level]

        permitted_next: set[int] = set()
        is_sequence = content == "-" or content.startswith("- ")
        if is_sequence:
            _require_yaml_profile_container(
                level_kinds,
                indentation,
                "sequence",
                path,
                line_number,
            )
            logical_indentation = indentation + 2
            while scopes and scopes[-1][0] >= logical_indentation:
                scopes.pop()
            item = content[1:].lstrip(" ")
            if item == "-" or item.startswith("- "):
                _yaml_profile_error(
                    path,
                    line_number,
                    "compact nested block-sequence syntax is unsupported; "
                    "put each '-' indicator on its own line",
                )
            if item == "?" or item.startswith("? "):
                _yaml_profile_error(
                    path,
                    line_number,
                    "quoted or complex mapping keys are unsupported",
                )
            entry = _yaml_profile_mapping_entry(item)
            if entry is None:
                node = _validate_yaml_profile_node(item, path, line_number)
                separator = _yaml_profile_mapping_separator(item)
                if separator is not None:
                    key = item[:separator]
                    if key == "<<":
                        _yaml_profile_error(
                            path,
                            line_number,
                            "merge keys are unsupported",
                        )
                    _validate_yaml_profile_key(key, path, line_number)
                    _yaml_profile_error(
                        path,
                        line_number,
                        "unsupported structural YAML syntax",
                    )
                if node.empty:
                    permitted_next.add(logical_indentation)
                if node.block_scalar:
                    block_scalar_indentation = indentation
            else:
                key, value = entry
                _validate_yaml_profile_key(key, path, line_number)
                _require_yaml_profile_container(
                    level_kinds,
                    logical_indentation,
                    "mapping",
                    path,
                    line_number,
                )
                _record_yaml_profile_key(
                    scopes,
                    logical_indentation,
                    key,
                    path,
                    line_number,
                    new_sequence_item=True,
                )
                node = _validate_yaml_profile_node(value, path, line_number)
                permitted_next.add(logical_indentation)
                if node.empty:
                    permitted_next.add(logical_indentation + 2)
                if node.block_scalar:
                    block_scalar_indentation = logical_indentation
        else:
            if content.startswith(("\"", "'", "?")):
                _yaml_profile_error(
                    path,
                    line_number,
                    "quoted or complex mapping keys are unsupported",
                )
            if content.startswith("<<:"):
                _yaml_profile_error(
                    path,
                    line_number,
                    "merge keys are unsupported",
                )
            if content.startswith("%"):
                _yaml_profile_error(
                    path,
                    line_number,
                    "directives are unsupported",
                )
            if content in {"---", "..."} or content.startswith(
                ("--- ", "... ")
            ):
                _yaml_profile_error(
                    path,
                    line_number,
                    "document markers are unsupported",
                )

            entry = _yaml_profile_mapping_entry(content)
            if entry is None:
                separator = _yaml_profile_mapping_separator(content)
                if separator is not None:
                    _validate_yaml_profile_key(
                        content[:separator],
                        path,
                        line_number,
                    )
                _yaml_profile_error(
                    path,
                    line_number,
                    "unsupported structural YAML syntax",
                )
            key, value = entry
            _validate_yaml_profile_key(key, path, line_number)
            _require_yaml_profile_container(
                level_kinds,
                indentation,
                "mapping",
                path,
                line_number,
            )
            _record_yaml_profile_key(
                scopes,
                indentation,
                key,
                path,
                line_number,
            )
            node = _validate_yaml_profile_node(value, path, line_number)
            if node.empty:
                permitted_next.add(indentation + 2)
            if node.block_scalar:
                block_scalar_indentation = indentation

        previous_indentation = indentation
        permitted_deeper_indentation = permitted_next


def load_yaml(path: Path) -> object:
    _validate_yaml_profile(path)
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


def validate_issue_forms(
    root: Path,
    labels: tuple[LabelDefinition, ...],
) -> list[str]:
    errors: list[str] = []
    template_dir = root / ".github" / "ISSUE_TEMPLATE"
    actual_forms = tuple(
        sorted(
            {
                path.name
                for pattern in ("*.yml", "*.yaml", "*.md")
                for path in template_dir.glob(pattern)
                if path.name != "config.yml"
            }
        )
    )
    if actual_forms != EXPECTED_FORMS:
        errors.append(
            f".github/ISSUE_TEMPLATE: expected forms {list(EXPECTED_FORMS)}"
        )
    label_names = {label.name for label in labels}
    form_names: set[str] = set()

    for filename in actual_forms:
        path = template_dir / filename
        try:
            document = load_yaml(path)
        except GovernanceError as error:
            errors.append(str(error))
            continue
        if not isinstance(document, dict):
            errors.append(f"{path}: top level must be a mapping")
            continue
        for key in ("name", "description", "body"):
            if key not in document:
                errors.append(f"{path}: missing required top-level key: {key}")
        name = document.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{path}: name must be a non-empty string")
        elif name in form_names:
            errors.append(f"{path}: duplicate form name: {name}")
        else:
            form_names.add(name)
        description = document.get("description")
        if not isinstance(description, str) or not description.strip():
            errors.append(f"{path}: description must be a non-empty string")
        issue_type = document.get("type")
        if issue_type not in APPROVED_TYPES:
            errors.append(f"{path}: unsupported native issue type: {issue_type}")
        raw_labels = document.get("labels", [])
        if not isinstance(raw_labels, list):
            errors.append(f"{path}: labels must be a list")
        else:
            for label in raw_labels:
                if not isinstance(label, str):
                    errors.append(f"{path}: automatic label must be a string")
                elif label not in label_names:
                    errors.append(f"{path}: unknown automatic label: {label}")
        expected_metadata = EXPECTED_FORM_METADATA.get(filename)
        if expected_metadata is not None:
            expected_type, expected_labels = expected_metadata
            if issue_type != expected_type:
                errors.append(
                    f"{path}: {filename} must use native type {expected_type}"
                )
            if (
                isinstance(raw_labels, list)
                and tuple(raw_labels) != expected_labels
            ):
                errors.append(
                    f"{path}: {filename} labels must equal "
                    f"{list(expected_labels)}"
                )
        body = document.get("body")
        if not isinstance(body, list):
            errors.append(f"{path}: body must be a list")
            continue
        field_ids: set[str] = set()
        for index, element in enumerate(body):
            context = f"{path}: body[{index}]"
            if not isinstance(element, dict):
                errors.append(f"{context}: element must be a mapping")
                continue
            body_type = element.get("type")
            if (
                not isinstance(body_type, str)
                or body_type not in SUPPORTED_BODY_TYPES
            ):
                errors.append(f"{context}: unsupported body type: {body_type}")
            field_id = element.get("id")
            if body_type == "markdown" and field_id is not None:
                errors.append(f"{context}: markdown must not define an id")
            elif body_type != "markdown":
                if (
                    not isinstance(field_id, str)
                    or not FIELD_ID_PATTERN.fullmatch(field_id)
                ):
                    errors.append(f"{context}: invalid field id: {field_id}")
                elif field_id in field_ids:
                    errors.append(f"{path}: duplicate field id: {field_id}")
                else:
                    field_ids.add(field_id)
            if not isinstance(element.get("attributes"), dict):
                errors.append(f"{context}: attributes must be a mapping")
            validations = element.get("validations")
            if validations is not None and not isinstance(validations, dict):
                errors.append(f"{context}: validations must be a mapping")

    config_path = template_dir / "config.yml"
    try:
        config = load_yaml(config_path)
    except GovernanceError as error:
        errors.append(str(error))
        return errors
    if not isinstance(config, dict):
        errors.append(f"{config_path}: top level must be a mapping")
        return errors
    if config.get("blank_issues_enabled") is not False:
        errors.append(f"{config_path}: blank_issues_enabled must be false")
    links = config.get("contact_links")
    if not isinstance(links, list):
        errors.append(f"{config_path}: contact_links must be a list")
    else:
        urls = {
            link.get("url")
            for link in links
            if isinstance(link, dict) and isinstance(link.get("url"), str)
        }
        if urls != {SECURITY_URL, SUPPORT_URL}:
            errors.append(
                f"{config_path}: contact links must be exactly security and support"
            )
    return errors


def validate_automation(
    root: Path,
    labels: tuple[LabelDefinition, ...],
) -> list[str]:
    errors: list[str] = []
    workflow_path = root / ".github" / "workflows" / "governance.yml"
    dependabot_path = root / ".github" / "dependabot.yml"
    workflow_files = sorted(
        {
            path.name
            for pattern in ("*.yml", "*.yaml")
            for path in workflow_path.parent.glob(pattern)
            if path.is_file()
        }
    )
    if workflow_files != ["governance.yml"]:
        errors.append(
            f"{workflow_path.parent}: workflow files must equal "
            "['governance.yml']"
        )
    missing_errors: list[str] = []
    for path in (workflow_path, dependabot_path):
        if not path.is_file():
            missing_errors.append(
                f"missing required file: {path.relative_to(root)}"
            )
    errors.extend(missing_errors)
    if missing_errors:
        return errors

    try:
        workflow = load_yaml(workflow_path)
    except GovernanceError as error:
        return [str(error)]
    if not isinstance(workflow, dict):
        return [f"{workflow_path}: top level must be a mapping"]
    if set(workflow) != {"name", "on", "permissions", "concurrency", "jobs"}:
        errors.append(f"{workflow_path}: top-level keys must equal the approved set")
    if workflow.get("name") != "Governance":
        errors.append(f"{workflow_path}: workflow name must be Governance")
    triggers = workflow.get("on")
    if not isinstance(triggers, dict) or triggers != EXPECTED_WORKFLOW_TRIGGERS:
        errors.append(f"{workflow_path}: triggers must equal the approved set")
    if isinstance(triggers, dict) and "pull_request_target" in triggers:
        errors.append(f"{workflow_path}: pull_request_target is forbidden")
    if workflow.get("permissions") != {"contents": "read"}:
        errors.append(f"{workflow_path}: permissions must be exactly contents: read")
    if workflow.get("concurrency") != EXPECTED_CONCURRENCY:
        errors.append(f"{workflow_path}: concurrency must equal the approved policy")
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != {"validate"}:
        errors.append(f"{workflow_path}: jobs must contain only validate")
    job = jobs.get("validate") if isinstance(jobs, dict) else None
    if not isinstance(job, dict):
        errors.append(f"{workflow_path}: jobs.validate must be a mapping")
    else:
        if set(job) != {"name", "runs-on", "timeout-minutes", "steps"}:
            errors.append(
                f"{workflow_path}: validate job keys must equal the approved set"
            )
        if job.get("name") != "Governance validation":
            errors.append(f"{workflow_path}: job name must be Governance validation")
        if job.get("runs-on") != "ubuntu-24.04":
            errors.append(f"{workflow_path}: runner must be ubuntu-24.04")
        if job.get("timeout-minutes") != 5:
            errors.append(f"{workflow_path}: timeout-minutes must equal 5")
        if "permissions" in job:
            errors.append(f"{workflow_path}: job-level permissions are forbidden")
        steps = job.get("steps")
        if not isinstance(steps, list):
            errors.append(f"{workflow_path}: steps must be a list")
        else:
            if (
                len(steps) != 4
                or not all(isinstance(step, dict) for step in steps)
            ):
                errors.append(f"{workflow_path}: exactly four mapping steps are required")
            else:
                if tuple(step.get("name") for step in steps) != EXPECTED_STEP_NAMES:
                    errors.append(
                        f"{workflow_path}: step names must equal the approved sequence"
                    )
                if tuple(set(step) for step in steps) != EXPECTED_STEP_KEYS:
                    errors.append(
                        f"{workflow_path}: step keys must equal the approved sequence"
                    )
            action_steps = [
                step
                for step in steps
                if isinstance(step, dict) and "uses" in step
            ]
            if len(action_steps) != 1:
                errors.append(
                    f"{workflow_path}: exactly one action step is required"
                )
            for action_step in action_steps:
                action_reference = action_step.get("uses")
                if not isinstance(action_reference, str):
                    errors.append(
                        f"{workflow_path}: action reference must be a string"
                    )
                    continue
                repository, separator, reference = action_reference.partition("@")
                if repository != "actions/checkout":
                    errors.append(
                        f"{workflow_path}: unapproved action: {repository}"
                    )
                if not separator or not FULL_SHA_PATTERN.fullmatch(reference):
                    errors.append(
                        f"{workflow_path}: action reference must use a full SHA: "
                        f"{action_reference}"
                    )
                elif action_reference != APPROVED_CHECKOUT_ACTION:
                    errors.append(
                        f"{workflow_path}: action reference must equal the "
                        "approved checkout reference"
                    )
            checkout_steps = [
                step
                for step in steps
                if isinstance(step, dict)
                and isinstance(step.get("uses"), str)
                and step["uses"].startswith("actions/checkout@")
            ]
            if len(checkout_steps) != 1:
                errors.append(
                    f"{workflow_path}: one checkout action must appear"
                )
            else:
                checkout_with = checkout_steps[0].get("with")
                if (
                    not isinstance(checkout_with, dict)
                    or checkout_with != {"persist-credentials": False}
                ):
                    errors.append(
                        f"{workflow_path}: checkout must only disable "
                        "credential persistence"
                    )
            run_scripts = tuple(
                run_script.strip()
                for step in steps
                if isinstance(step, dict)
                and isinstance((run_script := step.get("run")), str)
            )
            if run_scripts != EXPECTED_RUN_SCRIPTS:
                errors.append(
                    f"{workflow_path}: run scripts must equal the approved commands"
                )
            for step in steps:
                if isinstance(step, dict):
                    run_script = step.get("run")
                    if isinstance(run_script, str) and "${{" in run_script:
                        errors.append(f"{workflow_path}: GitHub expression in run script")

    try:
        dependabot = load_yaml(dependabot_path)
    except GovernanceError as error:
        errors.append(str(error))
        return errors
    if not isinstance(dependabot, dict):
        errors.append(f"{dependabot_path}: top level must be a mapping")
    elif set(dependabot) != {"version", "updates"}:
        errors.append(f"{dependabot_path}: top-level keys must be version and updates")
    elif dependabot.get("version") != 2:
        errors.append(f"{dependabot_path}: version must equal 2")
    elif dependabot.get("updates") != [EXPECTED_DEPENDABOT_UPDATE]:
        errors.append(
            f"{dependabot_path}: configuration must equal the approved "
            "GitHub Actions policy"
        )
    else:
        known_labels = {label.name for label in labels}
        for label in EXPECTED_DEPENDABOT_UPDATE["labels"]:
            if label not in known_labels:
                errors.append(f"{dependabot_path}: unknown label: {label}")

    return errors


def _tracked_policy_files(root: Path) -> tuple[Path, ...]:
    paths = list(REQUIRED_COMMUNITY_FILES)
    yaml_directories = (
        root / ".github",
        root / ".github" / "ISSUE_TEMPLATE",
        root / ".github" / "workflows",
    )
    for directory in yaml_directories:
        for pattern in ("*.yml", "*.yaml"):
            paths.extend(
                path.relative_to(root)
                for path in sorted(directory.glob(pattern))
                if path.is_file()
            )
    script_directory = root / ".github" / "scripts"
    paths.extend(
        path.relative_to(root)
        for path in sorted(script_directory.glob("*.py"))
        if path.name != "test_governance.py"
    )
    return tuple(dict.fromkeys(paths))


def _validate_text_file(root: Path, relative: Path) -> list[str]:
    errors: list[str] = []
    path = root / relative
    if not path.is_file():
        return [f"missing required file: {relative.as_posix()}"]
    text = path.read_text(encoding="utf-8")
    if path.suffix != ".py" and PLACEHOLDER_PATTERN.search(text):
        errors.append(f"{relative}: placeholder or conflict marker")
    for number, line in enumerate(text.splitlines(), start=1):
        if line != line.rstrip():
            errors.append(f"{relative}:{number}: trailing whitespace")
        if "\t" in line:
            errors.append(f"{relative}:{number}: tab character")
    return errors


def _validate_markdown_links(root: Path, relative: Path) -> list[str]:
    errors: list[str] = []
    path = root / relative
    if not path.is_file() or path.suffix.lower() != ".md":
        return errors
    text = path.read_text(encoding="utf-8")
    for match in MARKDOWN_LINK_PATTERN.finditer(text):
        target = match.group(1).strip()
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        clean_target = target.split("#", 1)[0].split("?", 1)[0]
        if not clean_target:
            continue
        resolved = (path.parent / clean_target).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            errors.append(f"{relative}: link escapes repository: {target}")
            continue
        if not resolved.exists():
            errors.append(f"{relative}: broken internal link: {target}")
    return errors


def _validate_policy_headings(root: Path) -> list[str]:
    errors: list[str] = []
    for relative, headings in REQUIRED_POLICY_HEADINGS.items():
        path = root / relative
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for heading in headings:
            if heading not in lines:
                errors.append(f"{relative}: missing heading: {heading}")
    return errors


def validate_community_files(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in _tracked_policy_files(root):
        errors.extend(_validate_text_file(root, relative))
        errors.extend(_validate_markdown_links(root, relative))
    codeowners_path = root / ".github" / "CODEOWNERS"
    if codeowners_path.is_file():
        codeowners = codeowners_path.read_text(encoding="utf-8")
        if not CODEOWNERS_WILDCARD_PATTERN.search(codeowners):
            errors.append(".github/CODEOWNERS: wildcard owner is required")
    errors.extend(_validate_policy_headings(root))
    return errors


def validate_repository(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        labels = validate_label_manifest(root / ".github" / "labels.yml")
    except GovernanceError as error:
        return [str(error)]
    errors.extend(validate_issue_forms(root, labels))
    errors.extend(validate_automation(root, labels))
    errors.extend(validate_community_files(root))
    return errors
