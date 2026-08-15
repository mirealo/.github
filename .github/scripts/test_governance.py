from __future__ import annotations

import contextlib
import importlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from governance import (
    GovernanceError,
    LabelDefinition,
    RemoteLabel,
    REQUIRED_POLICY_HEADINGS,
    compare_labels,
    load_yaml,
    validate_community_files,
    validate_issue_forms,
    validate_label_manifest,
    validate_automation,
    validate_repository,
)
from check_sensitive_links import (
    REQUEST_TIMEOUT_SECONDS,
    SENSITIVE_LINKS,
    check_sensitive_links,
    validate_sensitive_url,
)


_MISSING = object()


class _FakeResponse:
    def __init__(self, url: str, status: int = 200) -> None:
        self.url = url
        self.status = status
        self.read_sizes: list[int] = []

    def __enter__(self):
        return self

    def __exit__(self, *_arguments) -> None:
        return None

    def geturl(self) -> str:
        return self.url

    def getcode(self) -> int:
        return self.status

    def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        return b"x"


def _copy_monitor_workflow(root: Path) -> None:
    target = root / ".github" / "workflows" / "governance-monitor.yml"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        ROOT / ".github" / "workflows" / "governance-monitor.yml",
        target,
    )


def _copy_issue_form_fixture(root: Path) -> tuple[LabelDefinition, ...]:
    shutil.copytree(
        ROOT / ".github" / "ISSUE_TEMPLATE",
        root / ".github" / "ISSUE_TEMPLATE",
    )
    return validate_label_manifest(ROOT / ".github" / "labels.yml")


def _load_form_document(path: Path) -> dict[str, object]:
    document = load_yaml(path)
    if not isinstance(document, dict):
        raise AssertionError(f"test fixture must be a mapping: {path}")
    return document


def _write_form_document(path: Path, document: dict[str, object]) -> None:
    lines: list[str] = []

    def emit(value: object, indentation: int) -> None:
        prefix = " " * indentation
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise AssertionError("fixture mapping keys must be strings")
                if isinstance(item, dict):
                    if item:
                        lines.append(f"{prefix}{key}:")
                        emit(item, indentation + 2)
                    else:
                        lines.append(f"{prefix}{key}: {{}}")
                elif isinstance(item, list):
                    if item:
                        lines.append(f"{prefix}{key}:")
                        emit(item, indentation + 2)
                    else:
                        lines.append(f"{prefix}{key}: []")
                else:
                    lines.append(
                        f"{prefix}{key}: {json.dumps(item, ensure_ascii=False)}"
                    )
            return
        if isinstance(value, list):
            for item in value:
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}-")
                    emit(item, indentation + 2)
                else:
                    lines.append(
                        f"{prefix}- {json.dumps(item, ensure_ascii=False)}"
                    )
            return
        raise AssertionError("fixture root must be a mapping or list")

    emit(document, 0)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mutate_document_path(
    document: dict[str, object],
    path: tuple[str | int, ...],
    value: object,
) -> None:
    target: object = document
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    final = path[-1]
    if value is _MISSING:
        del target[final]  # type: ignore[index]
    else:
        target[final] = value  # type: ignore[index]


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
                    + (
                        "\n[Private contact](mailto:conduct@mirealo.com)"
                        if relative == "CODE_OF_CONDUCT.md"
                        else ""
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

    def test_community_read_failures_are_path_controlled(self) -> None:
        cases = (
            ("markdown policy", Path("SECURITY.md")),
            ("CODEOWNERS", Path(".github/CODEOWNERS")),
        )
        for case_name, relative in cases:
            with self.subTest(case=case_name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copytree(
                    ROOT,
                    root,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(
                        ".git",
                        ".superpowers",
                        "__pycache__",
                    ),
                )
                (root / relative).write_bytes(b"\xff\xfe\x80")

                try:
                    errors = validate_community_files(root)
                except (OSError, UnicodeError) as error:
                    self.fail(
                        f"{relative.as_posix()} raised {type(error).__name__} "
                        "instead of returning a controlled diagnostic"
                    )

                self.assertEqual(
                    errors,
                    [f"{relative.as_posix()}: unable to read as UTF-8"],
                )

    def test_conduct_policy_requires_the_confidential_contact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(
                ROOT,
                root,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".git", "__pycache__"),
            )
            conduct = root / "CODE_OF_CONDUCT.md"
            conduct.write_text(
                conduct.read_text(encoding="utf-8").replace(
                    "mailto:conduct@mirealo.com",
                    "#missing-contact",
                ),
                encoding="utf-8",
            )

            self.assertIn(
                "CODE_OF_CONDUCT.md: confidential conduct contact is required",
                validate_community_files(root),
            )


class PolicyStructureTests(unittest.TestCase):
    def test_repository_policies_have_required_sections(self) -> None:
        errors = validate_community_files(ROOT)
        policy_errors = [
            error for error in errors if "missing heading:" in error
        ]
        self.assertEqual(policy_errors, [])

    def test_solo_maintainer_and_issue_authority_are_explicit(self) -> None:
        governance = (ROOT / "GOVERNANCE.md").read_text(encoding="utf-8")
        normalized_governance = " ".join(governance.split())
        for statement in (
            "Native Issue Type",
            "The native Priority field is the sole public priority authority.",
            "`Urgent`, `High`, `Medium`, and `Low`",
            "Native close reasons replace resolution labels.",
            "Required human approvals, code-owner review, and",
            "last-push approval remain at zero",
            "must require one approving review, code-owner review, and",
            "described as independent human approval.",
        ):
            with self.subTest(statement=statement):
                self.assertIn(statement, normalized_governance)

        conduct = (ROOT / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
        for statement in (
            "mailto:conduct@mirealo.com",
            "does not promise a response or resolution deadline",
            "no second maintainer who can provide independent internal",
            "not a Mirealo appeal or a promise of action",
        ):
            with self.subTest(statement=statement):
                self.assertIn(statement, conduct)


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

    def test_load_yaml_rejects_duplicate_workflow_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "governance.yml"
            path.write_text(
                """
name: Governance
on:
  pull_request:
on:
  workflow_dispatch:
""".lstrip(),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(GovernanceError, "duplicate YAML mapping key: on"):
                load_yaml(path)

    def test_load_yaml_rejects_duplicate_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "governance.yml"
            path.write_text(
                """
permissions:
  contents: read
permissions:
  contents: write
""".lstrip(),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                GovernanceError,
                "duplicate YAML mapping key: permissions",
            ):
                load_yaml(path)

    def test_load_yaml_rejects_duplicate_key_after_plain_apostrophe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "governance.yml"
            path.write_text(
                "owner: maintainer's team\npermissions: write\npermissions: read\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                GovernanceError,
                "duplicate YAML mapping key: permissions",
            ):
                load_yaml(path)

    def test_load_yaml_rejects_duplicate_checkout_mapping_keys(self) -> None:
        fixtures = {
            "with": """
steps:
  - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
    with:
      persist-credentials: false
    with:
      persist-credentials: true
""".lstrip(),
            "persist-credentials": """
steps:
  - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
    with:
      persist-credentials: false
      persist-credentials: true
""".lstrip(),
        }
        with tempfile.TemporaryDirectory() as directory:
            for key, contents in fixtures.items():
                with self.subTest(key=key):
                    path = Path(directory) / f"{key}.yml"
                    path.write_text(contents, encoding="utf-8")
                    with self.assertRaisesRegex(
                        GovernanceError,
                        f"duplicate YAML mapping key: {key}",
                    ):
                        load_yaml(path)

    def test_load_yaml_allows_block_scalar_content_and_existing_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.yml"
            path.write_text(
                """
run: |
  on:
  permissions:
  with:
    persist-credentials: true
""".lstrip(),
                encoding="utf-8",
            )
            self.assertEqual(
                load_yaml(path),
                {
                    "run": "on:\npermissions:\nwith:\n  persist-credentials: true\n",
                },
            )
        self.assertIsInstance(
            load_yaml(ROOT / ".github" / "workflows" / "governance.yml"),
            dict,
        )

    def test_load_yaml_allows_block_scalar_header_forms_and_bodies(self) -> None:
        fixtures = {
            "literal": ("|", "duplicate:\nduplicate:\n", ""),
            "folded": (">", "duplicate: duplicate:\n", ""),
            "strip": ("|-", "duplicate:\nduplicate:", ""),
            "keep": (">+", "duplicate: duplicate:\n\n", "\n"),
            "indent": ("|2", "duplicate:\nduplicate:\n", ""),
            "indent-strip": (">2-", "duplicate: duplicate:", ""),
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, (header, expected, trailing) in fixtures.items():
                with self.subTest(header=header):
                    path = Path(directory) / f"{name}.yml"
                    path.write_text(
                        (
                            f"value: {header}\n"
                            "  duplicate:\n"
                            "  duplicate:\n"
                            f"{trailing}"
                        ),
                        encoding="utf-8",
                    )
                    self.assertEqual(load_yaml(path), {"value": expected})

    def assert_yaml_profile_error(
        self,
        contents: str,
        line: int,
        reason: str,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.yml"
            path.write_text(contents, encoding="utf-8")
            with self.assertRaises(GovernanceError) as caught:
                load_yaml(path)
            message = str(caught.exception)
            self.assertIn(f"{path}:{line}:", message)
            self.assertIn(reason, message)

    def test_load_yaml_rejects_duplicate_key_after_plain_colon_apostrophe(
        self,
    ) -> None:
        self.assert_yaml_profile_error(
            "owner: maintainer:'s-team\n"
            "permissions: write\n"
            "permissions: read\n",
            3,
            "duplicate YAML mapping key: permissions",
        )

    def test_yaml_profile_allows_same_keys_in_distinct_sequence_items(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.yml"
            path.write_text(
                "items:\n"
                "  - name: first\n"
                "    permissions: write\n"
                "  - name: second\n"
                "    permissions: read\n",
                encoding="utf-8",
            )
            self.assertEqual(
                load_yaml(path),
                {
                    "items": [
                        {"name": "first", "permissions": "write"},
                        {"name": "second", "permissions": "read"},
                    ]
                },
            )

    def test_yaml_profile_preserves_supported_scalar_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.yml"
            path.write_text(
                "owner: maintainer:'s-team\n"
                "url: https://github.com/mirealo/.github/issues?q=is%3Aopen\n"
                "concurrency: governance-${{ github.workflow }}-${{ github.ref }}\n"
                'quoted: "{literal: [value]}"\n'
                'markdown: "[link](https://example.com)"\n'
                "single: 'maintainer''s # team'\n"
                "note: value # real comment\n",
                encoding="utf-8",
            )
            self.assertEqual(
                load_yaml(path),
                {
                    "owner": "maintainer:'s-team",
                    "url": "https://github.com/mirealo/.github/issues?q=is%3Aopen",
                    "concurrency": (
                        "governance-${{ github.workflow }}-${{ github.ref }}"
                    ),
                    "quoted": "{literal: [value]}",
                    "markdown": "[link](https://example.com)",
                    "single": "maintainer's # team",
                    "note": "value",
                },
            )

    def test_yaml_profile_rejects_every_unsupported_syntax_family(self) -> None:
        fixtures = {
            "flow mapping": (
                "value: {one: 1}\n",
                1,
                "flow collections are unsupported",
            ),
            "flow sequence": (
                "value: [one, two]\n",
                1,
                "flow collections are unsupported",
            ),
            "multiline double quote": (
                'value: "first\n  second"\n',
                1,
                "multiline quoted scalars are unsupported",
            ),
            "multiline single quote": (
                "value: 'first\n  second'\n",
                1,
                "multiline quoted scalars are unsupported",
            ),
            "quoted key": (
                '"name": value\n',
                1,
                "quoted or complex mapping keys are unsupported",
            ),
            "complex key": (
                "? name\n: value\n",
                1,
                "quoted or complex mapping keys are unsupported",
            ),
            "merge key": (
                "item:\n  <<: inherited\n",
                2,
                "merge keys are unsupported",
            ),
            "anchor": (
                "value: &shared one\n",
                1,
                "anchors are unsupported",
            ),
            "alias": (
                "value: *shared\n",
                1,
                "aliases are unsupported",
            ),
            "tag": (
                "value: !custom one\n",
                1,
                "tags are unsupported",
            ),
            "directive": (
                "%YAML 1.2\nname: value\n",
                1,
                "directives are unsupported",
            ),
            "document start": (
                "---\nname: value\n",
                1,
                "document markers are unsupported",
            ),
            "document end": (
                "name: value\n...\n",
                2,
                "document markers are unsupported",
            ),
            "tab": (
                "root:\n\tchild: value\n",
                2,
                "tabs are unsupported",
            ),
            "odd indentation": (
                "root:\n   child: value\n",
                2,
                "indentation must use two-space increments",
            ),
            "skipped indentation": (
                "root:\n    child: value\n",
                2,
                "indentation skips an expected structural level",
            ),
            "invalid block header": (
                "value: |0\n  content\n",
                1,
                "invalid block scalar header",
            ),
        }
        for name, (contents, line, reason) in fixtures.items():
            with self.subTest(name=name):
                self.assert_yaml_profile_error(contents, line, reason)

    def test_yaml_profile_rejects_before_invoking_yq(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.yml"
            path.write_text("value: {one: 1}\n", encoding="utf-8")
            with patch("governance.subprocess.run") as run:
                with self.assertRaisesRegex(
                    GovernanceError,
                    "flow collections are unsupported",
                ):
                    load_yaml(path)
            run.assert_not_called()

    def test_yaml_profile_rejects_inline_sequence_merge_before_invoking_yq(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.yml"
            path.write_text(
                "items:\n  - <<: inherited\n",
                encoding="utf-8",
            )
            responses = [
                subprocess.CompletedProcess(
                    ["yq", "--version"], 0, "yq 3.4.3\n", ""
                ),
                subprocess.CompletedProcess(
                    ["yq", ".", str(path)],
                    0,
                    '{"items":[{"<<":"inherited"}]}\n',
                    "",
                ),
            ]
            with patch("governance.subprocess.run", side_effect=responses) as run:
                with self.assertRaises(GovernanceError) as caught:
                    load_yaml(path)
            message = str(caught.exception)
            self.assertIn(f"{path}:2:", message)
            self.assertIn("merge keys are unsupported", message)
            run.assert_not_called()

    def test_yaml_profile_rejects_inline_sequence_complex_key_before_invoking_yq(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.yml"
            path.write_text(
                "items:\n  - ? name\n",
                encoding="utf-8",
            )
            responses = [
                subprocess.CompletedProcess(
                    ["yq", "--version"], 0, "yq 3.4.3\n", ""
                ),
                subprocess.CompletedProcess(
                    ["yq", ".", str(path)],
                    0,
                    '{"items":[{"name":null}]}\n',
                    "",
                ),
            ]
            with patch("governance.subprocess.run", side_effect=responses) as run:
                with self.assertRaises(GovernanceError) as caught:
                    load_yaml(path)
            message = str(caught.exception)
            self.assertIn(f"{path}:2:", message)
            self.assertIn(
                "quoted or complex mapping keys are unsupported",
                message,
            )
            run.assert_not_called()

    def test_yaml_profile_allows_plain_sequence_scalar_starting_with_question_mark(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.yml"
            path.write_text(
                "items:\n  - ?name\n",
                encoding="utf-8",
            )
            self.assertEqual(load_yaml(path), {"items": ["?name"]})

    def test_yaml_profile_rejects_unsupported_inline_sequence_mapping_keys_before_yq(
        self,
    ) -> None:
        fixtures = {
            "space": (
                "bad key",
                '{"items":[{"bad key":"value"}]}\n',
            ),
            "slash": (
                "bad/key",
                '{"items":[{"bad/key":"value"}]}\n',
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, (key, yq_output) in fixtures.items():
                with self.subTest(name=name):
                    path = Path(directory) / f"{name}.yml"
                    path.write_text(
                        f"items:\n  - {key}: value\n",
                        encoding="utf-8",
                    )
                    responses = [
                        subprocess.CompletedProcess(
                            ["yq", "--version"], 0, "yq 3.4.3\n", ""
                        ),
                        subprocess.CompletedProcess(
                            ["yq", ".", str(path)],
                            0,
                            yq_output,
                            "",
                        ),
                    ]
                    with patch(
                        "governance.subprocess.run",
                        side_effect=responses,
                    ) as run:
                        with self.assertRaises(GovernanceError) as caught:
                            load_yaml(path)
                    message = str(caught.exception)
                    self.assertIn(f"{path}:2:", message)
                    self.assertIn(
                        "mapping keys must use only ASCII letters, digits, "
                        "_, ., and -",
                        message,
                    )
                    run.assert_not_called()

    def test_yaml_profile_rejects_compact_nested_sequences_before_yq(
        self,
    ) -> None:
        fixtures = {
            "flow mapping": ("{}", '{"items":[[{}]]}\n'),
            "flow sequence": (
                "[one, two]",
                '{"items":[[["one","two"]]]}\n',
            ),
            "tagged scalar": ("!!str one", '{"items":[["one"]]}\n'),
        }
        reason = (
            "compact nested block-sequence syntax is unsupported; "
            "put each '-' indicator on its own line"
        )
        with tempfile.TemporaryDirectory() as directory:
            for name, (item, yq_output) in fixtures.items():
                with self.subTest(name=name):
                    path = Path(directory) / f"{name.replace(' ', '-')}.yml"
                    path.write_text(
                        f"items:\n  - - {item}\n",
                        encoding="utf-8",
                    )
                    responses = [
                        subprocess.CompletedProcess(
                            ["yq", "--version"], 0, "yq 3.4.3\n", ""
                        ),
                        subprocess.CompletedProcess(
                            ["yq", ".", str(path)],
                            0,
                            yq_output,
                            "",
                        ),
                    ]
                    with patch(
                        "governance.subprocess.run",
                        side_effect=responses,
                    ) as run:
                        with self.assertRaises(GovernanceError) as caught:
                            load_yaml(path)
                    self.assertEqual(
                        str(caught.exception),
                        f"{path}:2: {reason}",
                    )
                    run.assert_not_called()

    def test_yaml_profile_allows_expanded_nested_sequence_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.yml"
            path.write_text(
                "items:\n  -\n    - one\n",
                encoding="utf-8",
            )
            self.assertEqual(load_yaml(path), {"items": [["one"]]})

    def test_yaml_profile_allows_negative_integer_sequence_scalar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.yml"
            path.write_text(
                "items:\n  - -1\n",
                encoding="utf-8",
            )
            self.assertEqual(load_yaml(path), {"items": [-1]})

    def test_yaml_profile_allows_merge_like_plain_sequence_scalar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.yml"
            path.write_text(
                "items:\n  - <<:literal\n",
                encoding="utf-8",
            )
            try:
                actual = load_yaml(path)
            except GovernanceError as error:
                self.fail(f"unexpected GovernanceError: {error}")
            self.assertEqual(actual, {"items": ["<<:literal"]})

    def test_yaml_profile_rejects_implicit_scalar_mapping_keys_before_yq(
        self,
    ) -> None:
        key_reason = (
            "mapping keys must use only ASCII letters, digits, _, ., and -, "
            "begin with an ASCII letter or _, and not equal true, false, or null"
        )
        fixtures = (
            ("top-level digit", "1key: value\n", 1),
            ("top-level hyphen", "-key: value\n", 1),
            ("top-level dot", ".key: value\n", 1),
            ("nested digit", "root:\n  1key: value\n", 2),
            ("nested hyphen", "root:\n  -key: value\n", 2),
            ("nested dot", "root:\n  .key: value\n", 2),
            ("inline digit", "items:\n  - 1key: value\n", 2),
            ("inline hyphen", "items:\n  - -key: value\n", 2),
            ("inline dot", "items:\n  - .key: value\n", 2),
            ("true lowercase", "true: value\n", 1),
            ("true uppercase nested", "root:\n  TRUE: value\n", 2),
            ("true mixed inline", "items:\n  - TrUe: value\n", 2),
            ("false lowercase", "false: value\n", 1),
            ("false uppercase nested", "root:\n  FALSE: value\n", 2),
            ("false mixed inline", "items:\n  - FaLsE: value\n", 2),
            ("null lowercase", "null: value\n", 1),
            ("null uppercase nested", "root:\n  NULL: value\n", 2),
            ("null mixed inline", "items:\n  - NuLl: value\n", 2),
            ("leading-zero integer", "1: first\n01: second\n", 1),
            ("radix integer", "0x10: first\n16: second\n", 1),
            (
                "boolean integer float equality",
                "true: boolean\n1: integer\n1.0: float\n",
                1,
            ),
            ("decimal exponent float", "1.0: decimal\n1e0: exponent\n", 1),
            (
                "infinity variants",
                ".inf: lower\n.Inf: title\n.INF: upper\n",
                1,
            ),
            (
                "nan variants",
                ".nan: lower\n.NaN: title\n.NAN: upper\n",
                1,
            ),
            ("positive infinity JSON names", ".inf: first\nInfinity: second\n", 1),
            (
                "negative infinity JSON names",
                "-.inf: first\n-Infinity: second\n",
                1,
            ),
            ("nan JSON names", ".nan: first\nNaN: second\n", 1),
        )
        mocked_result = subprocess.CompletedProcess(
            ["yq"],
            0,
            "{}\n",
            "",
        )
        with tempfile.TemporaryDirectory() as directory:
            for name, contents, line in fixtures:
                with self.subTest(name=name):
                    path = Path(directory) / f"{name.replace(' ', '-')}.yml"
                    path.write_text(contents, encoding="utf-8")
                    with patch(
                        "governance.subprocess.run",
                        return_value=mocked_result,
                    ) as run:
                        with self.assertRaises(GovernanceError) as caught:
                            load_yaml(path)
                    self.assertEqual(
                        str(caught.exception),
                        f"{path}:{line}: {key_reason}",
                    )
                    run.assert_not_called()

            path = Path(directory) / "valid-string-keys.yml"
            path.write_text(
                "on: trigger\n"
                "_meta: metadata\n"
                "field.id: field\n"
                "key-1: dash\n",
                encoding="utf-8",
            )
            self.assertEqual(
                load_yaml(path),
                {
                    "on": "trigger",
                    "_meta": "metadata",
                    "field.id": "field",
                    "key-1": "dash",
                },
            )

    def test_yaml_profile_uses_only_ascii_yaml_separation(self) -> None:
        key_reason = (
            "mapping keys must use only ASCII letters, digits, _, ., and -, "
            "begin with an ASCII letter or _, and not equal true, false, or null"
        )
        unicode_spaces = (
            ("no-break space", "\u00a0"),
            ("em space", "\u2003"),
        )
        mocked_result = subprocess.CompletedProcess(
            ["yq"],
            0,
            "{}\n",
            "",
        )
        with tempfile.TemporaryDirectory() as directory:
            for space_name, space in unicode_spaces:
                rejected = (
                    (
                        "non-ASCII key before hash",
                        f"na\u00efve: value{space}# literal\n",
                        1,
                        key_reason,
                    ),
                    (
                        "flow node before hash",
                        f"value: {{one: 1}}{space}# literal\n",
                        1,
                        "flow collections are unsupported",
                    ),
                    (
                        "duplicate before hash",
                        f"name: first{space}# literal\nname: second\n",
                        2,
                        "duplicate YAML mapping key: name",
                    ),
                    (
                        "Unicode-only structural line after block",
                        f"value: |\n{space}\n",
                        2,
                        "unsupported structural YAML syntax",
                    ),
                )
                for name, contents, line, reason in rejected:
                    with self.subTest(space=space_name, rejected=name):
                        path = Path(directory) / (
                            f"{space_name.replace(' ', '-')}-"
                            f"{name.replace(' ', '-')}.yml"
                        )
                        path.write_text(contents, encoding="utf-8")
                        with patch(
                            "governance.subprocess.run",
                            return_value=mocked_result,
                        ) as run:
                            with self.assertRaises(GovernanceError) as caught:
                                load_yaml(path)
                        self.assertEqual(
                            str(caught.exception),
                            f"{path}:{line}: {reason}",
                        )
                        run.assert_not_called()

                accepted = (
                    (
                        "colon remains scalar data",
                        f"items:\n  - value:{space}literal\n",
                        {"items": [f"value:{space}literal"]},
                    ),
                    (
                        "Unicode-prefixed flow text remains scalar data",
                        f"items:\n  - {space}[one]\n",
                        {"items": [f"{space}[one]"]},
                    ),
                    (
                        "hash remains scalar data",
                        f"items:\n  - value{space}#literal\n",
                        {"items": [f"value{space}#literal"]},
                    ),
                )
                for name, contents, expected in accepted:
                    with self.subTest(space=space_name, accepted=name):
                        path = Path(directory) / (
                            f"accepted-{space_name.replace(' ', '-')}-"
                            f"{name.replace(' ', '-')}.yml"
                        )
                        path.write_text(contents, encoding="utf-8")
                        self.assertEqual(load_yaml(path), expected)

            controls = (
                (
                    "ASCII-space comments",
                    "note: value # real comment\n"
                    "items:\n"
                    "  - scalar # real comment\n",
                    {"note": "value", "items": ["scalar"]},
                ),
                (
                    "single-line quoted scalar",
                    'value: "{literal: [value]} # data"\n',
                    {"value": "{literal: [value]} # data"},
                ),
                (
                    "opaque block scalar body",
                    "value: |\n"
                    "  na\u00efve: value\n"
                    "  nested: [flow]\n"
                    "  duplicate:\n"
                    "  duplicate:\n"
                    "  \u00a0\n",
                    {
                        "value": (
                            "na\u00efve: value\n"
                            "nested: [flow]\n"
                            "duplicate:\n"
                            "duplicate:\n"
                            "\u00a0\n"
                        )
                    },
                ),
            )
            for name, contents, expected in controls:
                with self.subTest(control=name):
                    path = Path(directory) / f"control-{name.replace(' ', '-')}.yml"
                    path.write_text(contents, encoding="utf-8")
                    self.assertEqual(load_yaml(path), expected)

    def test_yaml_profile_enforces_portable_line_character_contract(self) -> None:
        forbidden = (
            ("U+0085", "\u0085"),
            ("U+2028", "\u2028"),
            ("U+2029", "\u2029"),
        )
        contexts = (
            (
                "double quoted scalar",
                lambda character: f'value: "left{character}right"\n',
                1,
            ),
            (
                "single quoted scalar",
                lambda character: f"value: 'left{character}right'\n",
                1,
            ),
            (
                "plain scalar",
                lambda character: f"value: left{character}right\n",
                1,
            ),
            (
                "content after quoted scalar",
                lambda character: f'value: "ok"{character}next: fine\n',
                1,
            ),
            (
                "comment",
                lambda character: f"value: ok # left{character}right\n",
                1,
            ),
            (
                "block scalar body",
                lambda character: f"value: |\n  left{character}right\n",
                2,
            ),
        )
        physical_breaks = (
            ("LF", b"name: first\nname: second\n"),
            ("CRLF", b"name: first\r\nname: second\r\n"),
            ("CR", b"name: first\rname: second\r"),
        )
        mocked_result = subprocess.CompletedProcess(
            ["yq"],
            0,
            "{}\n",
            "",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for code_point, character in forbidden:
                for context, fixture, line in contexts:
                    with self.subTest(
                        code_point=code_point,
                        context=context,
                    ):
                        path = root / (
                            f"{code_point.lower()}-{context.replace(' ', '-')}.yml"
                        )
                        path.write_text(fixture(character), encoding="utf-8")
                        with patch(
                            "governance.subprocess.run",
                            return_value=mocked_result,
                        ) as run:
                            with self.assertRaises(GovernanceError) as caught:
                                load_yaml(path)
                        self.assertEqual(
                            str(caught.exception),
                            f"{path}:{line}: {code_point} is unsupported by "
                            "the portable YAML profile",
                        )
                        run.assert_not_called()

            for index, (name, contents) in enumerate(physical_breaks):
                with self.subTest(line_break=name):
                    path = root / f"physical-{index}.yml"
                    path.write_bytes(contents)
                    with patch(
                        "governance.subprocess.run",
                        return_value=mocked_result,
                    ) as run:
                        with self.assertRaises(GovernanceError) as caught:
                            load_yaml(path)
                    self.assertEqual(
                        str(caught.exception),
                        f"{path}:2: duplicate YAML mapping key: name",
                    )
                    run.assert_not_called()

    def test_load_yaml_wraps_profile_read_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid_utf8 = root / "invalid-utf8.yml"
            invalid_utf8.write_bytes(b"value: \xff\n")
            fixtures = (
                ("missing", root / "missing.yml", OSError),
                ("invalid UTF-8", invalid_utf8, UnicodeError),
            )
            for name, path, cause_type in fixtures:
                with self.subTest(name=name):
                    with patch("governance.subprocess.run") as run:
                        with self.assertRaises(GovernanceError) as caught:
                            load_yaml(path)
                    self.assertEqual(
                        str(caught.exception),
                        f"{path}: unable to read YAML profile",
                    )
                    self.assertIsInstance(caught.exception.__cause__, cause_type)
                    run.assert_not_called()

    def test_every_governed_repository_yaml_conforms_to_profile(self) -> None:
        paths = (
            ROOT / ".github" / "labels.yml",
            ROOT / ".github" / "dependabot.yml",
            ROOT / ".github" / "workflows" / "governance-monitor.yml",
            ROOT / ".github" / "workflows" / "governance.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "01-bug-report.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "02-feature-proposal.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "03-documentation-issue.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "04-maintenance-proposal.yml",
        )
        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsInstance(load_yaml(path), dict)


class LabelManifestTests(unittest.TestCase):
    def test_repository_manifest_is_exact_and_valid(self) -> None:
        labels = validate_label_manifest(ROOT / ".github" / "labels.yml")
        self.assertEqual(len(labels), 12)
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
                "good first issue",
                "help wanted",
            },
        )
        self.assertEqual(
            {label.category for label in labels},
            {"work", "status", "contribution"},
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
                    "Pull request addressing a defect; issues use the native Bug type.",
                    "work",
                ),
                (
                    "documentation",
                    "0075ca",
                    "Documentation subtype for Task issues and related pull requests.",
                    "work",
                ),
                (
                    "enhancement",
                    "a2eeef",
                    "Pull request implementing a feature; issues use the native Feature type.",
                    "work",
                ),
                (
                    "maintenance",
                    "5319e7",
                    "Maintenance subtype for Task issues and related pull requests.",
                    "work",
                ),
                (
                    "dependencies",
                    "0366d6",
                    "Dependency maintenance for issues and pull requests.",
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

    def test_manifest_rejects_description_over_github_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.yml"
            manifest = (ROOT / ".github" / "labels.yml").read_text(
                encoding="utf-8"
            )
            path.write_text(
                manifest.replace(
                    "Pull request addressing a defect; issues use the native Bug type.",
                    "A" * 100 + ".",
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                GovernanceError,
                "description must be a complete trimmed sentence of at most 100 characters",
            ):
                validate_label_manifest(path)


class AutomationPolicyTests(unittest.TestCase):
    def test_repository_automation_is_minimal_and_pinned(self) -> None:
        labels = validate_label_manifest(ROOT / ".github" / "labels.yml")
        self.assertEqual(validate_automation(ROOT, labels), [])

    def test_different_full_sha_checkout_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = root / ".github" / "workflows" / "governance.yml"
            workflow.parent.mkdir(parents=True)
            _copy_monitor_workflow(root)
            workflow.write_text(
                (ROOT / ".github" / "workflows" / "governance.yml")
                .read_text(encoding="utf-8")
                .replace(
                    "3d3c42e5aac5ba805825da76410c181273ba90b1",
                    "0000000000000000000000000000000000000000",
                ),
                encoding="utf-8",
            )
            dependabot = root / ".github" / "dependabot.yml"
            dependabot.write_text(
                (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            labels = validate_label_manifest(ROOT / ".github" / "labels.yml")
            errors = validate_automation(root, labels)
            self.assertTrue(
                any(
                    "action reference must equal the approved checkout reference"
                    in error
                    for error in errors
                )
            )

    def test_unpinned_action_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = root / ".github" / "workflows" / "governance.yml"
            workflow.parent.mkdir(parents=True)
            _copy_monitor_workflow(root)
            workflow.write_text(
                """
name: Governance
on:
  pull_request:
  push:
    branches:
      - main
  workflow_dispatch:
permissions:
  contents: read
jobs:
  validate:
    name: Governance validation
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - run: python3 .github/scripts/validate_governance.py
""".lstrip(),
                encoding="utf-8",
            )
            dependabot = root / ".github" / "dependabot.yml"
            dependabot.write_text(
                """
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: monthly
    labels:
      - dependencies
      - "status: needs-triage"
""".lstrip(),
                encoding="utf-8",
            )
            (workflow.parent / "unexpected.yml").write_text(
                "name: Unexpected\n",
                encoding="utf-8",
            )
            labels = (
                LabelDefinition("dependencies", "0366d6", "Dependencies.", "work"),
                LabelDefinition(
                    "status: needs-triage",
                    "d4c5f9",
                    "Triage.",
                    "status",
                ),
            )
            errors = validate_automation(root, labels)
            self.assertTrue(any("action reference must use a full SHA" in error for error in errors))
            self.assertTrue(
                any("workflow files must equal" in error for error in errors)
            )

    def test_expression_in_run_script_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = root / ".github" / "workflows" / "governance.yml"
            workflow.parent.mkdir(parents=True)
            _copy_monitor_workflow(root)
            workflow.write_text(
                """
name: Governance
on:
  pull_request:
  push:
    branches:
      - main
  workflow_dispatch:
permissions:
  contents: read
jobs:
  validate:
    name: Governance validation
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          persist-credentials: false
      - run: echo "${{ github.event.pull_request.title }}"
""".lstrip(),
                encoding="utf-8",
            )
            dependabot = root / ".github" / "dependabot.yml"
            dependabot.write_text(
                """
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: monthly
    labels:
      - dependencies
      - "status: needs-triage"
""".lstrip(),
                encoding="utf-8",
            )
            labels = (
                LabelDefinition("dependencies", "0366d6", "Dependencies.", "work"),
                LabelDefinition(
                    "status: needs-triage",
                    "d4c5f9",
                    "Triage.",
                    "status",
                ),
            )
            errors = validate_automation(root, labels)
            self.assertTrue(any("GitHub expression in run script" in error for error in errors))

    def test_monitor_rejects_non_main_or_write_enabled_variants(self) -> None:
        cases = (
            (
                "missing event-ref guard",
                "    if: github.ref == 'refs/heads/main'\n",
                "",
            ),
            ("non-main checkout", "ref: main", "ref: feature"),
            ("write permission", "issues: read", "issues: write"),
            (
                "pull request trigger",
                "  workflow_dispatch:",
                "  pull_request:\n  workflow_dispatch:",
            ),
        )
        for case_name, old, new in cases:
            with self.subTest(case=case_name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copytree(
                    ROOT / ".github" / "workflows",
                    root / ".github" / "workflows",
                )
                shutil.copy(
                    ROOT / ".github" / "dependabot.yml",
                    root / ".github" / "dependabot.yml",
                )
                monitor = (
                    root
                    / ".github"
                    / "workflows"
                    / "governance-monitor.yml"
                )
                monitor.write_text(
                    monitor.read_text(encoding="utf-8").replace(old, new, 1),
                    encoding="utf-8",
                )
                labels = validate_label_manifest(
                    ROOT / ".github" / "labels.yml"
                )

                errors = validate_automation(root, labels)

                self.assertTrue(
                    any(
                        "main-only read-only monitoring policy" in error
                        for error in errors
                    )
                )


class SensitiveLinkTests(unittest.TestCase):
    def test_sensitive_link_allowlist_is_fixed_and_https_only(self) -> None:
        self.assertEqual(len(SENSITIVE_LINKS), 4)
        for _name, url in SENSITIVE_LINKS:
            with self.subTest(url=url):
                validate_sensitive_url(url)

        for url in (
            "http://github.com/mirealo/.github",
            "https://example.com/report",
            "https://user@github.com/mirealo/.github",
            "https://github.com:444/mirealo/.github",
        ):
            with self.subTest(rejected=url), self.assertRaises(ValueError):
                validate_sensitive_url(url)

    def test_check_is_bounded_and_reads_only_one_byte(self) -> None:
        responses = [
            _FakeResponse(url)
            for _name, url in SENSITIVE_LINKS
        ]
        opener = MagicMock()
        opener.open.side_effect = responses

        errors = check_sensitive_links(opener)

        self.assertEqual(errors, [])
        self.assertEqual(opener.open.call_count, len(SENSITIVE_LINKS))
        for link, invocation, response in zip(
            SENSITIVE_LINKS,
            opener.open.call_args_list,
            responses,
            strict=True,
        ):
            _name, expected_url = link
            request = invocation.args[0]
            self.assertEqual(request.full_url, expected_url)
            self.assertEqual(
                invocation.kwargs["timeout"],
                REQUEST_TIMEOUT_SECONDS,
            )
            self.assertEqual(response.read_sizes, [1])

    def test_unavailable_sensitive_link_returns_a_controlled_error(self) -> None:
        responses = [
            _FakeResponse(url, status=503 if index == 0 else 200)
            for index, (_name, url) in enumerate(SENSITIVE_LINKS)
        ]
        opener = MagicMock()
        opener.open.side_effect = responses

        errors = check_sensitive_links(opener)

        self.assertEqual(
            errors,
            ["published security policy: unexpected HTTP status 503"],
        )


class IssueFormTests(unittest.TestCase):
    def test_repository_requires_four_ordered_forms(self) -> None:
        labels = validate_label_manifest(ROOT / ".github" / "labels.yml")
        errors = validate_issue_forms(ROOT, labels)
        self.assertEqual(errors, [])

    def test_native_bug_and_feature_types_are_not_duplicated_by_labels(self) -> None:
        cases = (
            ("01-bug-report.yml", "Bug"),
            ("02-feature-proposal.yml", "Feature"),
        )
        for filename, issue_type in cases:
            with self.subTest(filename=filename):
                form = load_yaml(
                    ROOT / ".github" / "ISSUE_TEMPLATE" / filename
                )
                self.assertIsInstance(form, dict)
                self.assertEqual(form.get("type"), issue_type)
                self.assertEqual(
                    form.get("labels"),
                    ["status: needs-triage"],
                )

    def test_issue_form_schema_rejects_empty_or_markdown_only_body(self) -> None:
        with self.subTest(body="empty"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            labels = _copy_issue_form_fixture(root)
            form_path = (
                root / ".github" / "ISSUE_TEMPLATE" / "01-bug-report.yml"
            )
            document = _load_form_document(form_path)
            document["body"] = []
            _write_form_document(form_path, document)

            errors = validate_issue_forms(root, labels)

            self.assertTrue(
                any(
                    str(form_path) in error
                    and "flow collections are unsupported" in error
                    for error in errors
                )
            )

        with self.subTest(body="markdown-only"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            labels = _copy_issue_form_fixture(root)
            form_path = (
                root / ".github" / "ISSUE_TEMPLATE" / "01-bug-report.yml"
            )
            document = _load_form_document(form_path)
            body = document["body"]
            self.assertIsInstance(body, list)
            document["body"] = [body[0]]
            _write_form_document(form_path, document)

            errors = validate_issue_forms(root, labels)

            self.assertIn(
                f"{form_path}: body must contain at least one non-markdown field",
                errors,
            )

    def test_issue_form_schema_rejects_invalid_type_specific_attributes(self) -> None:
        cases: list[
            tuple[str, tuple[str | int, ...], object, str]
        ] = [
            (
                "markdown missing value",
                ("body", 0, "attributes"),
                {"description": "Context without a value."},
                "{path}: body[0]: markdown value must be a non-empty string",
            ),
            (
                "markdown non-string value",
                ("body", 0, "attributes", "value"),
                7,
                "{path}: body[0]: markdown value must be a non-empty string",
            ),
            (
                "markdown empty value",
                ("body", 0, "attributes", "value"),
                "",
                "{path}: body[0]: markdown value must be a non-empty string",
            ),
        ]
        for body_type, index in (
            ("input", 2),
            ("textarea", 7),
            ("dropdown", 4),
            ("checkboxes", 1),
            ("upload", 13),
        ):
            cases.extend(
                (
                    (
                        f"{body_type} missing label",
                        ("body", index, "attributes", "label"),
                        _MISSING,
                        f"{{path}}: body[{index}]: {body_type} label must be a non-empty string",
                    ),
                    (
                        f"{body_type} non-string label",
                        ("body", index, "attributes", "label"),
                        7,
                        f"{{path}}: body[{index}]: {body_type} label must be a non-empty string",
                    ),
                    (
                        f"{body_type} empty label",
                        ("body", index, "attributes", "label"),
                        "",
                        f"{{path}}: body[{index}]: {body_type} label must be a non-empty string",
                    ),
                )
            )
        cases.extend(
            (
                (
                    "dropdown missing options",
                    ("body", 4, "attributes", "options"),
                    _MISSING,
                    "{path}: body[4]: dropdown options must be a non-empty list of distinct strings",
                ),
                (
                    "dropdown empty options",
                    ("body", 4, "attributes", "options"),
                    [],
                    "{path}:55: flow collections are unsupported",
                ),
                (
                    "dropdown non-string option",
                    ("body", 4, "attributes", "options"),
                    ["One", 2],
                    "{path}: body[4]: dropdown options must be a non-empty list of distinct strings",
                ),
                (
                    "dropdown duplicate options",
                    ("body", 4, "attributes", "options"),
                    ["Repeated", "Repeated"],
                    "{path}: body[4]: dropdown options must be a non-empty list of distinct strings",
                ),
                (
                    "dropdown non-Boolean multiple",
                    ("body", 4, "attributes", "multiple"),
                    "false",
                    "{path}: body[4]: dropdown multiple must be a Boolean",
                ),
                (
                    "dropdown Boolean default",
                    ("body", 4, "attributes", "default"),
                    True,
                    "{path}: body[4]: dropdown default must be a valid non-Boolean option index",
                ),
                (
                    "dropdown non-integer default",
                    ("body", 4, "attributes", "default"),
                    1.5,
                    "{path}: body[4]: dropdown default must be a valid non-Boolean option index",
                ),
                (
                    "dropdown negative default",
                    ("body", 4, "attributes", "default"),
                    -1,
                    "{path}: body[4]: dropdown default must be a valid non-Boolean option index",
                ),
                (
                    "dropdown out-of-range default",
                    ("body", 4, "attributes", "default"),
                    4,
                    "{path}: body[4]: dropdown default must be a valid non-Boolean option index",
                ),
                (
                    "checkboxes missing options",
                    ("body", 1, "attributes", "options"),
                    _MISSING,
                    "{path}: body[1]: checkboxes options must be a non-empty list of mappings",
                ),
                (
                    "checkboxes empty options",
                    ("body", 1, "attributes", "options"),
                    [],
                    "{path}:18: flow collections are unsupported",
                ),
                (
                    "checkboxes non-mapping option",
                    ("body", 1, "attributes", "options"),
                    ["not a mapping"],
                    "{path}: body[1]: checkboxes options must be a non-empty list of mappings",
                ),
                (
                    "checkbox option missing label",
                    ("body", 1, "attributes", "options", 0, "label"),
                    _MISSING,
                    "{path}: body[1]: checkbox option labels must be non-empty distinct strings",
                ),
                (
                    "checkbox option non-string label",
                    ("body", 1, "attributes", "options", 0, "label"),
                    7,
                    "{path}: body[1]: checkbox option labels must be non-empty distinct strings",
                ),
                (
                    "checkbox option empty label",
                    ("body", 1, "attributes", "options", 0, "label"),
                    "",
                    "{path}: body[1]: checkbox option labels must be non-empty distinct strings",
                ),
                (
                    "checkbox option duplicate label",
                    ("body", 1, "attributes", "options", 1, "label"),
                    "I searched the existing issues and relevant documentation.",
                    "{path}: body[1]: checkbox option labels must be non-empty distinct strings",
                ),
                (
                    "checkbox option non-Boolean required",
                    ("body", 1, "attributes", "options", 0, "required"),
                    "true",
                    "{path}: body[1]: checkbox option required must be a Boolean",
                ),
                (
                    "checkbox option unpermitted key",
                    ("body", 1, "attributes", "options", 0, "unexpected"),
                    True,
                    "{path}: body[1]: checkbox option keys must be limited to label and required",
                ),
                (
                    "upload non-string accept",
                    ("body", 13, "validations"),
                    {"accept": 7},
                    "{path}: body[13]: upload accept must be a string",
                ),
                (
                    "unpermitted element key",
                    ("body", 2, "unexpected"),
                    True,
                    "{path}: body[2]: unsupported element key: unexpected",
                ),
                (
                    "unpermitted input attribute key",
                    ("body", 2, "attributes", "unexpected"),
                    True,
                    "{path}: body[2]: unsupported input attribute key: unexpected",
                ),
                (
                    "unpermitted input validation key",
                    ("body", 2, "validations", "unexpected"),
                    True,
                    "{path}: body[2]: unsupported input validation key: unexpected",
                ),
                (
                    "duplicate non-Markdown field labels",
                    ("body", 3, "attributes", "label"),
                    "Affected component",
                    "{path}: duplicate field label: Affected component",
                ),
                (
                    "markdown id",
                    ("body", 0, "id"),
                    "context",
                    "{path}: body[0]: markdown must not define an id",
                ),
                (
                    "markdown validations",
                    ("body", 0, "validations"),
                    {"required": True},
                    "{path}: body[0]: markdown must not define validations",
                ),
            )
        )
        for body_type, index, attribute in (
            ("input", 2, "description"),
            ("input", 2, "placeholder"),
            ("input", 2, "value"),
            ("textarea", 7, "description"),
            ("textarea", 7, "placeholder"),
            ("textarea", 7, "value"),
            ("textarea", 7, "render"),
            ("dropdown", 4, "description"),
            ("checkboxes", 1, "description"),
            ("upload", 13, "description"),
        ):
            cases.append(
                (
                    f"{body_type} non-string {attribute}",
                    ("body", index, "attributes", attribute),
                    7,
                    f"{{path}}: body[{index}]: {body_type} attribute {attribute} must be a string",
                )
            )

        for case_name, mutation_path, value, expected_template in cases:
            with self.subTest(case=case_name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                labels = _copy_issue_form_fixture(root)
                form_path = (
                    root
                    / ".github"
                    / "ISSUE_TEMPLATE"
                    / "01-bug-report.yml"
                )
                document = _load_form_document(form_path)
                _mutate_document_path(document, mutation_path, value)
                _write_form_document(form_path, document)

                errors = validate_issue_forms(root, labels)

                self.assertIn(
                    expected_template.format(path=form_path),
                    errors,
                )

    def test_issue_forms_enforce_boolean_required_and_required_field_contracts(self) -> None:
        with self.subTest(required="quoted yes"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            labels = _copy_issue_form_fixture(root)
            form_path = (
                root / ".github" / "ISSUE_TEMPLATE" / "01-bug-report.yml"
            )
            document = _load_form_document(form_path)
            _mutate_document_path(
                document,
                ("body", 2, "validations", "required"),
                "yes",
            )
            _write_form_document(form_path, document)

            errors = validate_issue_forms(root, labels)

            self.assertIn(
                f"{form_path}: body[2]: validations.required must be a Boolean",
                errors,
            )

        required_ids = {
            "01-bug-report.yml": {
                "component", "version", "impact", "regression",
                "reproducibility", "expected_behavior", "actual_behavior",
                "reproduction_steps", "minimal_reproduction", "environment",
            },
            "02-feature-proposal.yml": {
                "problem", "users_and_use_case", "desired_outcome",
                "acceptance_criteria", "scope_and_non_goals", "workaround",
                "alternatives", "implications",
            },
            "03-documentation-issue.yml": {
                "location", "category", "audience", "problem",
                "expected_content", "references",
            },
            "04-maintenance-proposal.yml": {
                "problem", "outcome", "scope", "acceptance_criteria",
                "implications", "validation", "alternatives",
            },
        }
        for filename, field_ids in required_ids.items():
            for field_id in sorted(field_ids):
                with self.subTest(filename=filename, field_id=field_id), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    labels = _copy_issue_form_fixture(root)
                    form_path = (
                        root / ".github" / "ISSUE_TEMPLATE" / filename
                    )
                    document = _load_form_document(form_path)
                    body = document["body"]
                    self.assertIsInstance(body, list)
                    field = next(
                        element
                        for element in body
                        if isinstance(element, dict)
                        and element.get("id") == field_id
                    )
                    validations = field["validations"]
                    self.assertIsInstance(validations, dict)
                    validations["required"] = False
                    _write_form_document(form_path, document)

                    errors = validate_issue_forms(root, labels)

                    self.assertIn(
                        f"{form_path}: required field {field_id} must exist "
                        "and set validations.required to true",
                        errors,
                    )

    def test_issue_chooser_scope_includes_every_public_form_category(self) -> None:
        config = load_yaml(ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml")
        self.assertIsInstance(config, dict)
        support_links = [
            link
            for link in config.get("contact_links", [])
            if isinstance(link, dict)
            and link.get("url")
            == "https://github.com/mirealo/.github/blob/main/SUPPORT.md"
        ]
        self.assertEqual(len(support_links), 1)
        about = support_links[0].get("about")
        self.assertIsInstance(about, str)
        for category in ("bugs", "features", "documentation", "maintenance"):
            with self.subTest(category=category):
                self.assertIn(category, about.casefold())

    def test_maintenance_form_requires_complete_privacy_acknowledgement(self) -> None:
        form = load_yaml(
            ROOT
            / ".github"
            / "ISSUE_TEMPLATE"
            / "04-maintenance-proposal.yml"
        )
        self.assertIsInstance(form, dict)
        prerequisites = [
            element
            for element in form.get("body", [])
            if isinstance(element, dict) and element.get("id") == "prerequisites"
        ]
        self.assertEqual(len(prerequisites), 1)
        attributes = prerequisites[0].get("attributes")
        self.assertIsInstance(attributes, dict)
        options = attributes.get("options")
        self.assertIsInstance(options, list)
        acknowledgements = [
            option.get("label")
            for option in options
            if isinstance(option, dict)
            and option.get("required") is True
            and isinstance(option.get("label"), str)
            and option["label"].startswith("I removed ")
        ]
        self.assertEqual(len(acknowledgements), 1)
        acknowledgement = acknowledgements[0].casefold()
        for category in (
            "secrets",
            "personal data",
            "customer data",
            "proprietary information",
            "sensitive diagnostics",
        ):
            with self.subTest(category=category):
                self.assertIn(category, acknowledgement)

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
                    "['status: needs-triage']" in error
                    for error in errors
                )
            )


class LabelDriftTests(unittest.TestCase):
    def test_classifies_create_update_and_extra(self) -> None:
        expected = (
            LabelDefinition("bug", "d73a4a", "Defect.", "work"),
            LabelDefinition("maintenance", "5319e7", "Upkeep.", "work"),
        )
        actual = (
            RemoteLabel("bug", "ffffff", "Old description."),
            RemoteLabel("unexpected", "000000", "Unexpected."),
        )
        drift = compare_labels(expected, actual)
        self.assertEqual([label.name for label in drift.create], ["maintenance"])
        self.assertEqual(
            [(wanted.name, current.name) for wanted, current in drift.update],
            [("bug", "bug")],
        )
        self.assertEqual([label.name for label in drift.extra], ["unexpected"])
        self.assertFalse(drift.clean)

    def test_matching_labels_are_clean(self) -> None:
        expected = (
            LabelDefinition("bug", "d73a4a", "Defect.", "work"),
        )
        actual = (
            RemoteLabel("bug", "D73A4A", "Defect."),
        )
        self.assertTrue(compare_labels(expected, actual).clean)


class SyncCliContractTests(unittest.TestCase):
    def _sync_module(self):
        try:
            return importlib.import_module("sync_labels")
        except ModuleNotFoundError:
            self.fail("sync_labels CLI module is missing")

    @staticmethod
    def _remote_json(labels: tuple[LabelDefinition, ...]) -> str:
        return json.dumps(
            [
                {
                    "name": label.name,
                    "color": label.color,
                    "description": label.description,
                }
                for label in labels
            ]
        )

    def test_repository_argument_is_required_and_validated(self) -> None:
        sync_labels = self._sync_module()
        invalid = (
            None,
            "owner",
            "owner/repo/extra",
            "-owner/repo",
            "owner--name/repo",
            "owner/..",
            "owner/repo name",
            "https://github.com/owner/repo",
        )
        for repository in invalid:
            argv = ["sync_labels.py"]
            if repository is not None:
                argv.extend(("--repo", repository))
            with (
                self.subTest(repository=repository),
                patch.object(sys, "argv", argv),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                sync_labels.parse_arguments()
            self.assertEqual(raised.exception.code, 2)

        with patch.object(
            sys,
            "argv",
            [
                "sync_labels.py",
                "--repo",
                "mirealo/.github",
                "--check",
            ],
        ):
            arguments = sync_labels.parse_arguments()
        self.assertEqual(arguments.repo, "mirealo/.github")
        self.assertTrue(arguments.check)

    def test_check_is_read_only_and_targets_requested_repository(self) -> None:
        sync_labels = self._sync_module()
        expected = validate_label_manifest(ROOT / ".github" / "labels.yml")
        list_command = [
            "label",
            "list",
            "--repo",
            "mirealo/example",
            "--limit",
            "1000",
            "--json",
            "name,color,description",
        ]
        with (
            patch.object(
                sync_labels,
                "run_gh",
                return_value=self._remote_json(expected),
            ) as run_gh,
            patch.object(
                sys,
                "argv",
                [
                    "sync_labels.py",
                    "--repo",
                    "mirealo/example",
                    "--check",
                ],
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = sync_labels.main()

        self.assertEqual(result, 0)
        self.assertEqual(run_gh.call_args_list, [call(list_command)])

    def test_check_returns_nonzero_for_drift_without_mutation(self) -> None:
        sync_labels = self._sync_module()
        expected = validate_label_manifest(ROOT / ".github" / "labels.yml")
        list_command = [
            "label",
            "list",
            "--repo",
            "mirealo/example",
            "--limit",
            "1000",
            "--json",
            "name,color,description",
        ]
        with (
            patch.object(
                sync_labels,
                "run_gh",
                return_value=self._remote_json(expected[1:]),
            ) as run_gh,
            patch.object(
                sys,
                "argv",
                [
                    "sync_labels.py",
                    "--repo",
                    "mirealo/example",
                    "--check",
                ],
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = sync_labels.main()

        self.assertEqual(result, 1)
        self.assertEqual(run_gh.call_args_list, [call(list_command)])

    def test_default_mode_reports_drift_without_mutation(self) -> None:
        sync_labels = self._sync_module()
        expected = validate_label_manifest(ROOT / ".github" / "labels.yml")
        list_command = [
            "label",
            "list",
            "--repo",
            "mirealo/example",
            "--limit",
            "1000",
            "--json",
            "name,color,description",
        ]
        with (
            patch.object(
                sync_labels,
                "run_gh",
                return_value=self._remote_json(expected[1:]),
            ) as run_gh,
            patch.object(
                sys,
                "argv",
                ["sync_labels.py", "--repo", "mirealo/example"],
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = sync_labels.main()

        self.assertEqual(result, 0)
        self.assertEqual(run_gh.call_args_list, [call(list_command)])

    def test_apply_refuses_extras_without_mutation(self) -> None:
        sync_labels = self._sync_module()
        expected = validate_label_manifest(ROOT / ".github" / "labels.yml")
        remote = json.loads(self._remote_json(expected))
        remote.append(
            {
                "name": "unexpected",
                "color": "000000",
                "description": "Unexpected.",
            }
        )
        list_command = [
            "label",
            "list",
            "--repo",
            "mirealo/example",
            "--limit",
            "1000",
            "--json",
            "name,color,description",
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(sync_labels, "run_gh", return_value=json.dumps(remote))
            as run_gh,
            patch.object(
                sys,
                "argv",
                [
                    "sync_labels.py",
                    "--repo",
                    "mirealo/example",
                    "--apply",
                ],
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            result = sync_labels.main()
        self.assertEqual(result, 2)
        self.assertEqual(run_gh.call_args_list, [call(list_command)])
        self.assertEqual(
            stderr.getvalue(),
            "ERROR: refusing --apply while unexpected labels exist; "
            "review explicit renames first.\n",
        )

    def test_apply_creates_updates_and_verifies_without_delete(self) -> None:
        sync_labels = self._sync_module()
        expected = validate_label_manifest(ROOT / ".github" / "labels.yml")
        missing = expected[0]
        changed = expected[1]
        remote = json.loads(self._remote_json(expected[1:]))
        remote[0]["color"] = "ffffff"
        remote[0]["description"] = "Old description."
        list_command = [
            "label",
            "list",
            "--repo",
            "mirealo/example",
            "--limit",
            "1000",
            "--json",
            "name,color,description",
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(
                sync_labels,
                "run_gh",
                side_effect=[
                    json.dumps(remote),
                    "",
                    "",
                    self._remote_json(expected),
                ],
            ) as run_gh,
            patch.object(
                sys,
                "argv",
                [
                    "sync_labels.py",
                    "--repo",
                    "mirealo/example",
                    "--apply",
                ],
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            result = sync_labels.main()
        self.assertEqual(result, 0)
        self.assertEqual(
            run_gh.call_args_list,
            [
                call(list_command),
                call(
                    [
                        "label",
                        "create",
                        missing.name,
                        "--repo",
                        "mirealo/example",
                        "--color",
                        missing.color,
                        "--description",
                        missing.description,
                    ]
                ),
                call(
                    [
                        "label",
                        "edit",
                        changed.name,
                        "--repo",
                        "mirealo/example",
                        "--color",
                        changed.color,
                        "--description",
                        changed.description,
                    ]
                ),
                call(list_command),
            ],
        )
        self.assertEqual(stderr.getvalue(), "")
        self.assertTrue(
            stdout.getvalue().endswith("Labels match the canonical manifest.\n")
        )


if __name__ == "__main__":
    unittest.main()
