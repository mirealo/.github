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
review, and overrides. The canonical label data lives in
[.github/labels.yml](.github/labels.yml); human lifecycle rules remain in the
governance policy.

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
