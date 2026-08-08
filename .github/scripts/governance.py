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
    return errors


def validate_repository(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        labels = validate_label_manifest(root / ".github" / "labels.yml")
    except GovernanceError as error:
        return [str(error)]
    errors.extend(validate_issue_forms(root, labels))
    errors.extend(validate_community_files(root))
    return errors
