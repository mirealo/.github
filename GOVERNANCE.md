# Governance

This policy describes how Mirealo public repositories are maintained and how
organization-wide defaults evolve. A repository-specific governance policy may
replace this default when it defines stricter or more specialized controls.

## Decision authority

Mirealo repository owners are accountable for scope, security, compatibility,
maintenance, and release decisions. Public issues and pull requests provide
evidence and invite review; they do not transfer ownership of the roadmap or
create a commitment to implement a proposal.

Material changes require a documented problem, explicit boundaries, testable
acceptance criteria, risk analysis, and validation evidence. Maintainers may
request a design discussion before implementation when a change affects public
interfaces, security boundaries, data handling, or long-term maintenance.

## Issue lifecycle

Every issue starts with `status: needs-triage`. Triage confirms that the report
is actionable, supported, safe to discuss publicly, and classified correctly.

- `status: needs-info` replaces the triage status while required information is
  outstanding.
- `status: accepted` means the direction is approved but work has not started.
- `status: in-progress` means implementation or remediation is active.
- `status: blocked` means a documented dependency or decision prevents progress.

Use at most one status and one priority label. Maintainers assign priority only
after validating impact and scope. `good first issue` and `help wanted` are
applied only when acceptance criteria and contribution boundaries are clear.

When closing work without implementation, use at most one of
`resolution: duplicate`, `resolution: not-actionable`, or
`resolution: not-planned` and explain the decision.

## Pull requests

Pull requests must remain focused, link the work they resolve, document risks,
and provide exact validation evidence. Required automated checks, signed-commit
rules, linear history, code ownership, and resolved review conversations apply
according to the effective repository rulesets.

Approval is based on evidence, not authorship. A maintainer may decline or
request changes to work that is unsafe, out of scope, insufficiently tested,
unmaintainable, or inconsistent with the repository's direction.

## Policy changes

Changes to organization defaults use the same pull-request process as product
changes. A policy change must explain its effect on repositories that inherit
the default and identify any required migration for repositories that override
it.

Published behavior is not removed silently. Deprecations and incompatible
changes require an explicit transition appropriate to the affected project.

## Security and conduct

Suspected vulnerabilities never enter public governance discussion. Follow the
[security policy](SECURITY.md) and use private reporting.

Conduct concerns follow the [code of conduct](CODE_OF_CONDUCT.md). Security and
conduct reports remain confidential to the extent reasonably possible and are
handled separately from technical disagreement.

## Repository overrides

GitHub uses these files only when an owned repository does not provide its own
supported community-health file. A local policy takes precedence and should
state why the default is insufficient. Local overrides must not weaken
organization, enterprise, legal, or security controls that apply independently
of repository content.
