from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from governance import (
    GovernanceError,
    LabelDefinition,
    REQUIRED_POLICY_HEADINGS,
    load_yaml,
    validate_community_files,
    validate_issue_forms,
    validate_label_manifest,
    validate_repository,
)


class CommunityFileTests(unittest.TestCase):
    def test_repository_requires_governance_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            required = (
                "README.md",
                "profile/README.md",
                "CONTRIBUTING.md",
                "SECURITY.md",
                "SUPPORT.md",
                "CODE_OF_CONDUCT.md",
                "PULL_REQUEST_TEMPLATE.md",
                ".github/CODEOWNERS",
            )
            for relative in required:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                contents = (
                    "* @example\n"
                    if relative.endswith("CODEOWNERS")
                    else "# Policy\n\n"
                    + "\n".join(
                        REQUIRED_POLICY_HEADINGS.get(Path(relative), ())
                    )
                    + "\n"
                )
                path.write_text(contents, encoding="utf-8")
            errors = validate_community_files(root)
            self.assertEqual(errors, ["missing required file: GOVERNANCE.md"])

    def test_broken_internal_markdown_link_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            required = (
                "README.md",
                "GOVERNANCE.md",
                "CONTRIBUTING.md",
                "SECURITY.md",
                "SUPPORT.md",
                "CODE_OF_CONDUCT.md",
                "PULL_REQUEST_TEMPLATE.md",
            )
            for relative in required:
                path = root / relative
                path.write_text("# Policy\n", encoding="utf-8")
            profile = root / "profile" / "README.md"
            profile.parent.mkdir()
            profile.write_text(
                "# Profile\n\nSee [missing](../MISSING.md).\n",
                encoding="utf-8",
            )
            errors = validate_community_files(root)
            self.assertTrue(
                any("broken internal link: ../MISSING.md" in error for error in errors)
            )

    def test_placeholder_and_conflict_marker_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            required = (
                "README.md",
                "GOVERNANCE.md",
                "CONTRIBUTING.md",
                "SECURITY.md",
                "SUPPORT.md",
                "CODE_OF_CONDUCT.md",
                "PULL_REQUEST_TEMPLATE.md",
            )
            for relative in required:
                path = root / relative
                path.write_text("# Policy\n", encoding="utf-8")
            profile = root / "profile" / "README.md"
            profile.parent.mkdir()
            profile.write_text("# Profile\n\nTBD\n<<<<<<< branch\n", encoding="utf-8")
            errors = validate_community_files(root)
            self.assertTrue(any("placeholder or conflict marker" in error for error in errors))

    def test_codeowners_requires_an_effective_wildcard_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            required = (
                "README.md",
                "GOVERNANCE.md",
                "CONTRIBUTING.md",
                "SECURITY.md",
                "SUPPORT.md",
                "CODE_OF_CONDUCT.md",
                "PULL_REQUEST_TEMPLATE.md",
                "profile/README.md",
            )
            for relative in required:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Policy\n", encoding="utf-8")
            codeowners = root / ".github" / "CODEOWNERS"
            codeowners.parent.mkdir(parents=True, exist_ok=True)
            codeowners.write_text("/docs/ @example\n", encoding="utf-8")
            errors = validate_community_files(root)
            self.assertIn(
                ".github/CODEOWNERS: wildcard owner is required",
                errors,
            )


class PolicyStructureTests(unittest.TestCase):
    def test_repository_policies_have_required_sections(self) -> None:
        errors = validate_community_files(ROOT)
        policy_errors = [
            error for error in errors if "missing heading:" in error
        ]
        self.assertEqual(policy_errors, [])


class YamlAdapterTests(unittest.TestCase):
    def test_load_yaml_uses_python_yq_json_interface(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.yml"
            path.write_text("name: example\n", encoding="utf-8")
            responses = [
                subprocess.CompletedProcess(
                    ["yq", "--version"], 0, "yq 3.4.3\n", ""
                ),
                subprocess.CompletedProcess(
                    ["yq", ".", str(path)], 0, '{"name":"example"}\n', ""
                ),
            ]
            with patch("governance.subprocess.run", side_effect=responses) as run:
                self.assertEqual(load_yaml(path), {"name": "example"})
            self.assertEqual(run.call_args_list[1].args[0], ["yq", ".", str(path)])

    def test_load_yaml_uses_go_yq_v4_json_interface(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.yml"
            path.write_text("name: example\n", encoding="utf-8")
            responses = [
                subprocess.CompletedProcess(
                    ["yq", "--version"],
                    0,
                    "yq (https://github.com/mikefarah/yq/) version v4.53.3\n",
                    "",
                ),
                subprocess.CompletedProcess(
                    ["yq", "-o=json", ".", str(path)],
                    0,
                    '{"name":"example"}\n',
                    "",
                ),
            ]
            with patch("governance.subprocess.run", side_effect=responses) as run:
                self.assertEqual(load_yaml(path), {"name": "example"})
            self.assertEqual(
                run.call_args_list[1].args[0],
                ["yq", "-o=json", ".", str(path)],
            )

    def test_load_yaml_rejects_invalid_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.yml"
            path.write_text("name: example\n", encoding="utf-8")
            responses = [
                subprocess.CompletedProcess(
                    ["yq", "--version"], 0, "yq 3.4.3\n", ""
                ),
                subprocess.CompletedProcess(
                    ["yq", ".", str(path)], 0, "not-json\n", ""
                ),
            ]
            with patch("governance.subprocess.run", side_effect=responses):
                with self.assertRaisesRegex(
                    GovernanceError, "did not produce valid JSON"
                ):
                    load_yaml(path)


class LabelManifestTests(unittest.TestCase):
    def test_repository_manifest_is_exact_and_valid(self) -> None:
        labels = validate_label_manifest(ROOT / ".github" / "labels.yml")
        self.assertEqual(len(labels), 19)
        self.assertEqual(
            {label.name for label in labels},
            {
                "bug",
                "documentation",
                "enhancement",
                "maintenance",
                "dependencies",
                "status: needs-triage",
                "status: needs-info",
                "status: accepted",
                "status: in-progress",
                "status: blocked",
                "priority: critical",
                "priority: high",
                "priority: medium",
                "priority: low",
                "good first issue",
                "help wanted",
                "resolution: duplicate",
                "resolution: not-actionable",
                "resolution: not-planned",
            },
        )
        self.assertEqual(
            {label.category for label in labels},
            {"work", "status", "priority", "contribution", "resolution"},
        )
        self.assertEqual(
            [
                (
                    label.name,
                    label.color,
                    label.description,
                    label.category,
                )
                for label in labels
            ],
            [
                (
                    "bug",
                    "d73a4a",
                    "Reproducible defect in a supported version or exact commit.",
                    "work",
                ),
                (
                    "documentation",
                    "0075ca",
                    "Incorrect, missing, unclear, or outdated documentation.",
                    "work",
                ),
                (
                    "enhancement",
                    "a2eeef",
                    "Proposed product or engineering improvement with a clear user benefit.",
                    "work",
                ),
                (
                    "maintenance",
                    "5319e7",
                    "Technical, automation, policy, or repository upkeep that is not a feature or defect.",
                    "work",
                ),
                (
                    "dependencies",
                    "0366d6",
                    "Dependency-only updates, including controlled automated upgrades.",
                    "work",
                ),
                (
                    "status: needs-triage",
                    "d4c5f9",
                    "Awaiting initial maintainer review and classification.",
                    "status",
                ),
                (
                    "status: needs-info",
                    "fbca04",
                    "Waiting for information required to continue triage or implementation.",
                    "status",
                ),
                (
                    "status: accepted",
                    "0e8a16",
                    "Approved for implementation but not yet started.",
                    "status",
                ),
                (
                    "status: in-progress",
                    "1d76db",
                    "Implementation or remediation is actively underway.",
                    "status",
                ),
                (
                    "status: blocked",
                    "b60205",
                    "Cannot proceed until a documented dependency or decision is resolved.",
                    "status",
                ),
                (
                    "priority: critical",
                    "b60205",
                    "Immediate attention required because of severe operational or user impact.",
                    "priority",
                ),
                (
                    "priority: high",
                    "d93f0b",
                    "High-impact work that should precede normal-priority items.",
                    "priority",
                ),
                (
                    "priority: medium",
                    "fbca04",
                    "Normal planned priority after maintainer triage.",
                    "priority",
                ),
                (
                    "priority: low",
                    "c5def5",
                    "Useful work with limited impact or urgency.",
                    "priority",
                ),
                (
                    "good first issue",
                    "7057ff",
                    "Well-scoped work suitable for a first contribution.",
                    "contribution",
                ),
                (
                    "help wanted",
                    "008672",
                    "Maintainers welcome a community contribution for this work.",
                    "contribution",
                ),
                (
                    "resolution: duplicate",
                    "cfd3d7",
                    "Closed because equivalent work is already tracked elsewhere.",
                    "resolution",
                ),
                (
                    "resolution: not-actionable",
                    "cfd3d7",
                    "Closed because the report is incomplete, unsupported, or outside scope.",
                    "resolution",
                ),
                (
                    "resolution: not-planned",
                    "cfd3d7",
                    "Closed because the requested work is not planned.",
                    "resolution",
                ),
            ],
        )

    def test_manifest_rejects_duplicate_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.yml"
            path.write_text(
                """
version: 1
labels:
  - name: bug
    color: d73a4a
    description: First definition.
    category: work
  - name: bug
    color: d73a4a
    description: Duplicate definition.
    category: work
""".lstrip(),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(GovernanceError, "duplicate label: bug"):
                validate_label_manifest(path)

    def test_manifest_rejects_an_unapproved_label_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.yml"
            manifest = (ROOT / ".github" / "labels.yml").read_text(encoding="utf-8")
            path.write_text(
                manifest.replace("  - name: bug\n", "  - name: defect\n", 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                GovernanceError,
                "work labels must equal the approved names",
            ):
                validate_label_manifest(path)

    def test_manifest_rejects_uppercase_color(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.yml"
            manifest = (ROOT / ".github" / "labels.yml").read_text(encoding="utf-8")
            path.write_text(
                manifest.replace("color: d73a4a", "color: D73A4A", 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                GovernanceError,
                "color must be six lowercase hex digits",
            ):
                validate_label_manifest(path)


class IssueFormTests(unittest.TestCase):
    def test_repository_requires_four_ordered_forms(self) -> None:
        labels = validate_label_manifest(ROOT / ".github" / "labels.yml")
        errors = validate_issue_forms(ROOT, labels)
        self.assertEqual(errors, [])

    def test_unknown_automatic_label_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / ".github" / "ISSUE_TEMPLATE"
            template.mkdir(parents=True)
            for filename in (
                "01-bug-report.yml",
                "02-feature-proposal.yml",
                "03-documentation-issue.yml",
                "04-maintenance-proposal.yml",
            ):
                (template / filename).write_text(
                    """
name: Example
description: Example form.
labels:
  - missing-label
type: Task
body:
  - type: textarea
    id: outcome
    attributes:
      label: Outcome
    validations:
      required: true
""".lstrip(),
                    encoding="utf-8",
                )
            (template / "config.yml").write_text(
                "blank_issues_enabled: false\ncontact_links: []\n",
                encoding="utf-8",
            )
            labels = (
                LabelDefinition("maintenance", "5319e7", "Maintenance.", "work"),
            )
            errors = validate_issue_forms(root, labels)
            self.assertTrue(
                any("unknown automatic label: missing-label" in error for error in errors)
            )

    def test_duplicate_field_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / ".github" / "ISSUE_TEMPLATE"
            template.mkdir(parents=True)
            content = """
name: Example
description: Example form.
labels:
  - maintenance
type: Task
body:
  - type: textarea
    id: repeated
    attributes:
      label: First
  - type: input
    id: repeated
    attributes:
      label: Second
""".lstrip()
            for filename in (
                "01-bug-report.yml",
                "02-feature-proposal.yml",
                "03-documentation-issue.yml",
                "04-maintenance-proposal.yml",
            ):
                (template / filename).write_text(content, encoding="utf-8")
            (template / "config.yml").write_text(
                "blank_issues_enabled: false\ncontact_links: []\n",
                encoding="utf-8",
            )
            labels = (
                LabelDefinition("maintenance", "5319e7", "Maintenance.", "work"),
            )
            errors = validate_issue_forms(root, labels)
            self.assertTrue(any("duplicate field id: repeated" in error for error in errors))

    def test_filename_contract_rejects_wrong_type_and_labels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / ".github" / "ISSUE_TEMPLATE"
            template.mkdir(parents=True)
            metadata = {
                "01-bug-report.yml": ("Bug report", "Task", ["maintenance"]),
                "02-feature-proposal.yml": (
                    "Feature proposal",
                    "Feature",
                    ["enhancement", "status: needs-triage"],
                ),
                "03-documentation-issue.yml": (
                    "Documentation issue",
                    "Task",
                    ["documentation", "status: needs-triage"],
                ),
                "04-maintenance-proposal.yml": (
                    "Maintenance proposal",
                    "Task",
                    ["maintenance", "status: needs-triage"],
                ),
            }
            for filename, (name, issue_type, automatic_labels) in metadata.items():
                labels_yaml = "\n".join(
                    f'  - "{label}"' if ":" in label else f"  - {label}"
                    for label in automatic_labels
                )
                (template / filename).write_text(
                    (
                        f"name: {name}\n"
                        "description: Example form.\n"
                        f"labels:\n{labels_yaml}\n"
                        f"type: {issue_type}\n"
                        "body:\n"
                        "  - type: textarea\n"
                        "    id: outcome\n"
                        "    attributes:\n"
                        "      label: Outcome\n"
                    ),
                    encoding="utf-8",
                )
            (template / "config.yml").write_text(
                """
blank_issues_enabled: false
contact_links:
  - name: Security
    url: https://github.com/mirealo/.github/blob/main/SECURITY.md
    about: Report privately.
  - name: Support
    url: https://github.com/mirealo/.github/blob/main/SUPPORT.md
    about: Read the support policy.
""".lstrip(),
                encoding="utf-8",
            )
            labels = (
                LabelDefinition("bug", "d73a4a", "Bug.", "work"),
                LabelDefinition("enhancement", "a2eeef", "Enhancement.", "work"),
                LabelDefinition(
                    "documentation", "0075ca", "Documentation.", "work"
                ),
                LabelDefinition(
                    "maintenance", "5319e7", "Maintenance.", "work"
                ),
                LabelDefinition(
                    "status: needs-triage",
                    "d4c5f9",
                    "Needs triage.",
                    "status",
                ),
            )
            errors = validate_issue_forms(root, labels)
            self.assertTrue(
                any(
                    "01-bug-report.yml must use native type Bug" in error
                    for error in errors
                )
            )
            self.assertTrue(
                any(
                    "01-bug-report.yml labels must equal "
                    "['bug', 'status: needs-triage']" in error
                    for error in errors
                )
            )


if __name__ == "__main__":
    unittest.main()
