# Mirealo organization standards

This public repository is the source of organization-wide community health
defaults and contribution standards for repositories owned by
[Mirealo](https://github.com/mirealo).

Mirealo is private-first. This repository publishes governance material only;
it does not expose private products, roadmaps, customer information, or
operational support channels.

## Inherited defaults

GitHub uses a supported file from this repository when an owned repository does
not define its own version.

| Area | Default |
| --- | --- |
| Governance | [GOVERNANCE.md](GOVERNANCE.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Security | [SECURITY.md](SECURITY.md) |
| Support | [SUPPORT.md](SUPPORT.md) |
| Conduct | [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) |
| Pull requests | [PULL_REQUEST_TEMPLATE.md](PULL_REQUEST_TEMPLATE.md) |
| Issue intake | [.github/ISSUE_TEMPLATE](.github/ISSUE_TEMPLATE) |

A repository-local policy takes precedence when a project requires stricter or
more specialized guidance. If a repository defines any file in its own
`.github/ISSUE_TEMPLATE` directory, GitHub does not inherit the default issue
template directory.

## Operating model

The [governance policy](GOVERNANCE.md) defines decision authority, triage,
review, the honest single-maintainer bootstrap, and overrides. Native Issue Type
and native issue fields are authoritative for issues. The public native Priority
field and native close reasons replace priority and resolution labels. The
canonical repository label data lives in
[.github/labels.yml](.github/labels.yml); the governance policy defines its
workflow, contribution, and pull-request roles.

`CODEOWNERS` is repository-local and is not inherited from this community-health
repository. Every repository must provision its own ownership file. The
governance policy also defines continuity and the permanent, pull-request-only
`OrganizationAdmin` recovery capability without publishing recovery material.
That capability cannot authorize direct pushes or bypass the repository's
validation and CodeQL gates.

Labels are repository-scoped. A repository that inherits these issue forms must
also provision the referenced labels. Check a repository without making changes:

```bash
python3 .github/scripts/sync_labels.py --repo owner/name --check
```

An explicitly authorized maintainer may replace `--check` with ordinary
`--apply` to create or update labels. Ordinary `--apply` never deletes labels
and refuses to mutate when unexpected labels require a human rename decision.

The one-time native-metadata migration for this repository is deliberately
separate from normal synchronization:

```bash
python3 .github/scripts/sync_labels.py --repo mirealo/.github --apply \
  --retire-obsolete-v1
```

That bounded mode can retire only the seven frozen legacy labels after proving
zero issue and pull-request use, exact historical definitions, and an otherwise
clean 12-label state. It rejects every other repository or extra label. GitHub
does not provide an atomic search-and-delete transaction, so run the authorized
migration during a quiet maintenance window and stop if repository activity
changes. If an interrupted run deleted only the expected prefix, rerun the same
command: it resumes from that exact state and obtains fresh proof before the
next deletion. On any command failure, reported drift, unexpected label, or
out-of-band change, stop and investigate instead of renaming or deleting labels
manually. Success performs a final readback and exits zero only when the remote
inventory exactly matches the canonical 12-label manifest and all seven legacy
labels are absent.

## Validate a change

Run the same dependency-free checks used by CI:

```bash
python3 -m unittest discover -s .github/scripts -p 'test_*.py' -v
python3 .github/scripts/validate_governance.py
```

The validator requires Python 3.11 or newer and a compatible `yq` command. It
supports the local Python-`yq` interface and Go-`yq` v4 on GitHub-hosted runners.
The root `.gitattributes` explicitly classifies direct governance scripts as
detectable, non-vendored Python rather than documentation. CodeQL default setup
now analyzes GitHub Actions and Python, and successful extraction covered all
five operational scripts under `.github/scripts`. A repository ruleset with no
bypass actors targets the default branch and is configured at `errors` and
`medium_or_higher`. For eligible pull requests, qualifying findings block merge
only when every affected line is present in the pull request diff. GitHub does
not apply this protection to merge queue groups or Dependabot pull requests
analyzed by default setup. These controls apply only to this public repository;
they do not claim organization-wide or private-repository coverage, or any paid
entitlement.

The read-only Governance monitor runs weekly and on manual dispatch from `main`.
It compares remote labels with the published manifest and checks a fixed,
bounded allowlist of sensitive external links. It never runs on pull requests
and has no permission to change labels, issue fields, or linked resources.

## Security

Never disclose a vulnerability, credential, personal data, customer data,
proprietary information, or unsanitized diagnostic in a public issue or pull
request. Follow [SECURITY.md](SECURITY.md) to report privately.
