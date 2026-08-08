# Security policy

Security is a core requirement for every Mirealo project.

## Supported versions

The default branch and versions explicitly listed as supported by the affected
repository are eligible for security fixes. A repository-specific support
window takes precedence. Unsupported versions may still inform an assessment
but do not create a remediation commitment.

## Reporting a vulnerability

Do not open a public issue, discussion, pull request, or support request for a
suspected vulnerability.

Use the affected repository's **Report a vulnerability** option under its
Security tab. This creates a private report visible only to its security
maintainers.

If the affected repository cannot accept a private report, use the
[Mirealo central private reporting form](https://github.com/mirealo/.github/security/advisories/new)
and identify the affected repository. Use the central route only to establish a
private handoff; do not disclose unrelated private material.

## What to include

Provide, when available:

- the affected repository, component, version, or exact commit;
- realistic impact and attack prerequisites;
- minimal reproduction steps or a proof of concept;
- known mitigations or workarounds;
- whether the issue has been disclosed elsewhere;
- a safe private contact path available through the report.

Minimize personal, customer, and proprietary data. Never include production
credentials or data obtained from another person.

## Safe testing

Security research must not:

- access, alter, retain, or disclose data belonging to others;
- degrade service availability or perform denial-of-service testing;
- use social engineering, phishing, physical intrusion, or credential theft;
- test third-party systems outside the affected project's control;
- persist after demonstrating the minimum evidence needed for a report.

Stop immediately if testing reaches data or systems you did not intend to
access, and report the boundary privately.

## Response process

Maintainers will validate scope, assess impact, coordinate remediation, and
communicate through the private report. Timing depends on complexity, affected
users, upstream coordination, and safe release requirements; this policy does
not promise a public response SLA.

## Coordinated disclosure

Do not disclose the issue publicly until maintainers confirm that remediation
and affected-user communication are ready. Public advisories should credit the
reporter when requested and appropriate, document affected versions, and
describe available fixes or mitigations without exposing unnecessary exploit
detail.
