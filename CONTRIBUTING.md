# Contributing

Thank you for helping improve a Mirealo project. Repository-specific guidance
takes precedence when it defines stricter or more specialized requirements.

## Before contributing

1. Read the target repository's README, license, governance, security, and local
   contribution guidance.
2. Search existing issues and pull requests to avoid duplicate work.
3. Choose the issue form that matches the work.
4. Remove secrets, personal data, customer data, proprietary material, and
   unrelated generated files.

## Propose substantial work

Open an issue before substantial implementation unless maintainers have already
accepted the direction. Describe the problem, affected users, explicit
boundaries, testable acceptance criteria, alternatives, and material security,
privacy, compatibility, migration, or maintenance implications.

Acceptance of an issue approves a direction, not every implementation detail.
Keep the proposal current when evidence changes.

## Validation evidence

Behavior changes require tests at the narrowest useful level and any broader
integration evidence needed to prove the user-visible outcome. Documentation,
configuration, and policy changes require their applicable linters, parsers,
link checks, or rendered review.

Report exact commands and results. Do not describe a check as passing unless it
was run against the proposed commit.

## Pull requests

- Keep one independently reviewable concern per pull request.
- Link the issue or decision the change resolves.
- Explain the chosen approach, important alternatives, and scope boundaries.
- Include compatibility, security, privacy, migration, rollout, and recovery
  considerations when applicable.
- Keep the branch current and resolve every review conversation before final
  review.
- Use clear, focused commits that satisfy the repository's signature and
  history rules.

## Contribution provenance

Submit only material you have the right to license to the project. You remain
responsible for generated or assisted content: review it, test it, verify its
licenses and provenance, and never provide confidential information to an
unapproved tool.

## Review and decisions

Maintainers evaluate correctness, safety, scope, test evidence, compatibility,
and long-term maintenance cost. They may request changes or close work that is
unsafe, unsupported, out of scope, insufficiently tested, or inconsistent with
the project's direction.

Participate according to the [code of conduct](CODE_OF_CONDUCT.md) and report
suspected vulnerabilities through the [security policy](SECURITY.md), never in
public review.
