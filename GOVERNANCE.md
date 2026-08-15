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

## Issue authority and labels

GitHub-native metadata is authoritative for issues. Labels provide public
workflow context and pull-request categorization; they do not override native
issue metadata.

| Concern | Authority | Label role |
| --- | --- | --- |
| Issue classification | Native Issue Type | `bug` and `enhancement` classify pull requests only; `documentation` and `maintenance` may refine native Task issues and related pull requests. |
| Priority | Native Priority field | `Urgent`, `High`, `Medium`, and `Low` are the only public priority values. Labels never duplicate them. |
| Other planning data | Native issue fields | Labels do not replace Effort, Start date, Target date, or future native fields. |
| Public workflow | Repository policy | At most one `status:*` label publishes the triage or implementation state. |
| Closure reason | Native issue state reason | Use `Completed`, `Duplicate`, or `Not planned`, with a concise explanation when context is not self-evident. |

The native Priority field is the sole public priority authority. Governance
automation compares label definitions (name, color, and description) in the
manifest with repository labels. It does not inspect or mutate native fields.

## Issue lifecycle

Issues opened through the provided forms start with `status: needs-triage`.
Maintainers apply that status to issues created through another permitted path.
Triage confirms that the report is actionable, supported, safe to discuss
publicly, and classified correctly.

- `status: needs-info` replaces the triage status only while an open issue is
  waiting for information.
- `status: accepted` means the direction is approved but work has not started.
- `status: in-progress` means implementation or remediation is active.
- `status: blocked` means a documented dependency or decision prevents progress.

Use at most one public status. Maintainers set native Priority to `Urgent`,
`High`, `Medium`, or `Low` only after validating impact and scope. `good first
issue` and `help wanted` are applied only when acceptance criteria and
contribution boundaries are clear.

Close delivered or otherwise resolved work as `Completed`. Close equivalent
work as `Duplicate` and link the canonical issue. Close declined, unsupported,
out-of-scope, or otherwise not-actionable work as `Not planned` and explain the
decision. Native close reasons replace resolution labels.

## Solo-maintainer bootstrap

Mirealo currently has one trusted maintainer. Repository rulesets still require
pull requests, successful required checks, signed commits, linear history, and
resolved review conversations. Required human approvals, code-owner review, and
last-push approval remain at zero because there is no second person who can
provide them.

`CODEOWNERS` identifies accountability in this mode; it does not create
independent review. A self-review, automated check, or tool-assisted review must
not be described as independent human approval.

The `.github/CODEOWNERS` file applies only to this repository. GitHub does not
inherit `CODEOWNERS` as a default community-health file. Every future
repository must provision and maintain its own local ownership rules.

## Ownership continuity

Mirealo's target operating state has at least two trusted organization owners.
When a second trusted maintainer is ready, verify that person's identity and
secure 2FA out of band, add and test their organization access, promote them to
owner, and move repository ownership to a maintainer team. Each repository must
then update its local `CODEOWNERS` file.

The solo-maintainer bootstrap ends before the second maintainer participates in
governance merges. Effective rulesets must then require one approving review,
code-owner review, and approval of the most recent push by someone other than
its author. This transition creates human redundancy; automation never does.

Each owner maintains at least two independent secure 2FA methods and a current
set of recovery codes stored offline in a separate failure domain. Device
identifiers, credentials, recovery codes, storage locations, and private
successor contact details must never appear in repository content, issues,
pull requests, Actions secrets, or public audit evidence.

Owners periodically confirm, without consuming or rotating credentials merely
for evidence, that each authentication method remains available, recovery codes
remain readable, and successor access still matches policy. Succession transfers
roles and verified access, never personal authentication material.

## Break-glass changes

Normal pull requests remain the preferred path. Break-glass changes are limited
to incident containment, recovery of organization control, or repair of broken
merge controls. They must use the smallest separately authorized settings or
repository change for the shortest practical period. Mirealo does not maintain
a permanent emergency bypass.

Record the timestamp, reason, exact settings before and after, signed change,
tests, and restoration evidence in the appropriate audit trail. Restore normal
rules before ordinary work resumes. Put vulnerability details, credentials, or
other sensitive incident facts in a private security advisory rather than a
public issue or pull request. A solo-owner emergency action is not independent
review.

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
