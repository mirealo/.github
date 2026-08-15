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
and native issue fields are authoritative for issues. The canonical repository
label data lives in [.github/labels.yml](.github/labels.yml); the governance
policy defines its narrower public-projection and pull-request roles.

Labels are repository-scoped. A repository that inherits these issue forms must
also provision the referenced labels. Check a repository without making changes:

```bash
python3 .github/scripts/sync_labels.py --repo owner/name --check
```

An explicitly authorized maintainer may replace `--check` with `--apply` to
create or update labels. The command never deletes labels and refuses to mutate
when unexpected labels require a human rename decision.

## Validate a change

Run the same dependency-free checks used by CI:

```bash
python3 -m unittest discover -s .github/scripts -p 'test_*.py' -v
python3 .github/scripts/validate_governance.py
```

The validator requires Python 3.11 or newer and a compatible `yq` command. It
supports the local Python-`yq` interface and Go-`yq` v4 on GitHub-hosted runners.

## Security

Never disclose a vulnerability, credential, personal data, customer data,
proprietary information, or unsanitized diagnostic in a public issue or pull
request. Follow [SECURITY.md](SECURITY.md) to report privately.
