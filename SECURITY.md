# Security policy

## Reporting a vulnerability

Please do not disclose suspected vulnerabilities in a public issue. Use the repository's private security-advisory channel. If private advisories are unavailable, contact the repository owner through a private channel and include only the minimum reproduction details needed.

Do not send real credentials, production metadata, personal data, or customer query text. Redact tokens and replace production URNs with safe examples.

## Supported version

Security fixes are applied to the current `main` branch. This pre-1.0 project does not promise fixes for older snapshots.

## Security model

- Replay is the default and performs no external writes.
- Service credentials are server-side settings and are excluded from the public capability response.
- GitHub and DataHub mutations require explicit feature flags, a separate admin approval token, passing artifacts, and allowlisted targets.
- Artifact paths are confined, SQL/YAML are parsed, exact hashes are verified, and generated code is not executed.
- The browser renders generated content as text.
- HTTP requests have a 16 KiB boundary and responses receive restrictive browser security headers.
- The release container runs as an unprivileged user with a read-only root filesystem under Compose.

## Deployment responsibilities

Operators should terminate TLS, add edge rate limiting and access logs with credential redaction, rotate tokens, scope integrations to one demo repository/namespace, back up the persistent run ledger, and monitor partial-publication failures. Do not enable public writeback or PR creation on an unrestricted internet endpoint.

See [docs/architecture.md](docs/architecture.md) for trust boundaries and [README.md](README.md) for the minimum integration access.
