# CreditFlow security review — 8 November 2026

Scope: the Python application, native JavaScript/CSS/templates, account/session design, local server configuration, runtime dependencies, and local HTTP behavior. Tests use synthetic accounts and temporary databases. No third-party systems were scanned. This review cannot discover every vulnerability, establish the absence of zero-days, or certify a future hosting environment.

## Findings and changes

| Finding | Change | Evidence |
| --- | --- | --- |
| Signed cookie replay remained possible after sign-out | Random server-backed sessions, hashed token storage, expiry, and deletion on API/form logout | Regression tests replay the old cookie after both logout paths and receive 401 |
| Throttling could be bypassed by rotating usernames | Persistent IP-wide authentication budget plus account/IP attempts; forwarded IP headers ignored | Repeated attempts with different usernames and spoofed forwarding headers are throttled |
| Accounts had no reliable compromise-response controls | Password change revokes all devices; admins can revoke sessions or disable accounts; last active admin protected | Multi-device, disabled-login, privilege, and lockout regression tests |
| First-run administrator setup was available to any visitor | Loopback-only local setup; production setup disabled; production fails closed without an existing administrator | Remote setup and hosted-mode tests |
| Host-header and browser-origin protections were missing | Exact trusted hosts; origin/fetch-metadata validation; CSRF remains required | Evil-host, hostile-origin, null-origin, and cross-site request tests |
| JSON and field types could trigger server exceptions or ambiguous parsing | Bounded UTF-8 objects, duplicate-key/NaN rejection, strict IDs/types/ranges, numeric route bounds, atomic validation and rollback | Malformed, deeply nested, oversized, wrong-type, huge-integer, and rollback tests |
| Browser hardening was incomplete | CSP, anti-framing, nosniff, permissions policy, referrer policy, cross-origin isolation headers; secure cookies/HSTS in HTTPS mode | Response/header and hosted-cookie tests |
| HTML construction could become a future XSS sink | Removed runtime HTML-string insertion; use DOM text APIs; removed third-party fonts | Malicious stored text tests and source review. No pre-existing SQL injection or stored-XSS exploit was reproduced |
| Development server and broad dependency ranges were unsuitable for hosting | Bounded Waitress server, no debugger, fixed runtime versions, hash-locked transitive dependencies, static asset allowlist | Source/configuration review, package audit, static-path tests, and HTTP checks |
| The default interpreter was Python 3.11.9 | Prepared a project-local official Python 3.14.10 runtime and locked runtime dependencies without modifying other Python installations | Runtime archive SHA-256 verification; tests run under 3.14.10 |

The runtime archive was obtained from [Python's official 3.14.10 release](https://www.python.org/downloads/release/python-31410/) and matched the published SHA-256 `90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159`. This is a security release; using an updated runtime addresses interpreter/library fixes even when no exploit of those components was demonstrated in this app.

## Verification results

- 48 regression tests passed under Python 3.14.10, with no failures, errors, or skips. These include the existing account/diagram behavior, native JavaScript logic, the security regression suite, and a real Waitress/HTTP authentication, permissions, assets, and logout check.
- `pip-audit` found no published vulnerabilities in the eight packages in the locked runtime dependency set at the time checked. This does not audit unknown vulnerabilities, the operating system, every bundled native component, or development-only tooling.
- Bandit reported one LOW/MEDIUM-confidence B606 finding on the deliberate process replacement used to select `.runtime/python.exe`. Review: the interpreter and script are fixed paths in this project, no shell is used, and no HTTP input selects a program or command. This is an intended startup operation, not a reproduced injection vulnerability. No findings were suppressed. Raw scanner results are retained locally under `security-scan-results/`.
- Existing accounts and journey content are preserved. Existing browser sessions must sign in again once because cookie-only authentication is no longer accepted.
- A consistent SQLite backup was saved under `%LOCALAPPDATA%\CreditFlow\Backups` before migration. Post-migration digests match the original journey tables and the original account IDs, usernames, password hashes, and roles. The live server is one loopback-only Waitress process using the verified private runtime.

## Remaining deployment responsibilities

The app currently stays on loopback. Internet deployment still requires a maintained TLS reverse proxy, certificate management, request-framing and network abuse controls, an exact trusted-host configuration, and restricted backups. HTTPS flags do not create TLS by themselves. Organizational MFA/SSO, recovery workflows, external tamper-resistant logging, and formal penetration testing remain outside this implementation.

The project is stored in a OneDrive folder. Local database/backup access, cloud sync policy, disk encryption, OS/browser updates, and access to the developer account still matter. Git ignore rules and an HTTP allowlist do not encrypt data or undo copies already synced or exported. Consult [SECURITY.md](SECURITY.md) before hosting or using sensitive data.

No assessment can honestly guarantee protection from all future zero-days. The result is a hardened application with tested controls and a recorded review, not a guarantee of invulnerability.
