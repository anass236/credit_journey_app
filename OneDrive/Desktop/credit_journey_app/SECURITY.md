# CreditFlow security operations

This is a shared workspace with two roles. Every account can read and export the journey; only administrators can change the map, teams, or account access. Viewers can change their own password. There is no claim that this application is immune to unknown vulnerabilities.

## Running the app

Use `python app.py` in this prepared Windows workspace. It switches to the verified project-local Python 3.14.10 under `.runtime` and starts Waitress on `127.0.0.1:5001` (or the configured `PORT`). Other projects' Python installations are unchanged. The private runtime and runtime dependencies are not committed to Git. On another machine, use an up-to-date Python and install `requirements.lock` with `pip install --require-hashes -r requirements.lock`.

Keep the backend on loopback. Do not use Flask's development server or debugger for hosting. The normal entry point ignores `FLASK_DEBUG` and never enables the debugger.

## Hosting behind HTTPS

1. Create the initial administrator locally before exposing the service. Web setup only accepts loopback clients in local mode and is completely disabled in production.
2. Use Python 3.14.10 or newer, and set `CREDIT_JOURNEY_PRODUCTION=1` and `CREDIT_JOURNEY_HTTPS=1`.
3. Set `CREDIT_JOURNEY_TRUSTED_HOSTS` to exact comma-separated hostnames, such as `credit.example.org`. Wildcard and leading-dot host patterns are rejected.
4. Configure a maintained TLS reverse proxy to forward to `127.0.0.1:5001` (or your configured `PORT`), preserve the trusted Host, reject ambiguous/duplicate HTTP framing headers, and impose connection, request-size, and traffic limits. Keep the backend inaccessible from other machines. The HTTPS flag describes TLS termination at this trusted proxy; it does not encrypt the backend port itself.
5. Supply a stable, random `CREDIT_JOURNEY_SECRET` of at least 32 characters if you manage secrets externally. Otherwise a random signing secret is generated and retained in the local database. Never publish either the database or the secret.

Secure cookies and HSTS are enabled when HTTPS mode is set. Proxy forwarding headers are not trusted by default, so untrusted `X-Forwarded-For` cannot bypass login throttling. Behind the default proxy arrangement, application throttling sees the proxy IP; configure per-client abuse controls at the proxy. Do not broadly enable trusted forwarding headers to work around a rate limit.

## Accounts and sessions

- Use unique, strong passwords or passphrases of 12–128 characters. Do not share administrator accounts. Grant Viewer to people who do not need edit access.
- **Password** requires the current password and revokes every session for that account. Use **Accounts & access → Sign out** to revoke another account's sessions, or **Disable** to prevent it signing back in. The last active administrator is protected from accidental removal of its access.
- Server session tokens are random; only their SHA-256 hashes are stored in SQLite. Logout deletes the server record, so replaying the old signed cookie does not restore access. Idle expiry is eight hours and absolute expiry is 24 hours. At most ten sessions per account are retained.
- Upgrading from the old cookie-only system requires one fresh sign-in; usernames and password hashes are preserved.
- There is no email password recovery, public registration, or MFA/SSO integration. Add organizational SSO/MFA before using this for sensitive organizational or customer data.

## Data and backups

`CREDIT_JOURNEY_DB` selects the SQLite file; the existing `journey.db` is used by default to preserve this workspace. The database includes account hashes, a signing secret, session hashes, and journey content. Do not store actual customer financial documents or credentials in journey notes.

The current workspace is under OneDrive. Git ignores databases and local runtimes, but Git ignore rules do not prevent cloud sync. If organizational policy requires data to stay on the computer, stop the app, use SQLite's backup API to copy the database into a private non-synced directory, set `CREDIT_JOURNEY_DB` to that copy, verify it, and manage retained synced copies according to your data-retention policy. Do not copy an actively written SQLite file using a plain filesystem copy.

Protect database and backup folders using OS access controls and disk encryption. Keep tested, restricted backups outside the served static directory and outside the repository. This application does not configure Windows encryption, OneDrive security, your firewall, TLS certificates, or your organization's backup service.

Only four named browser assets can be served through `/static`; the database, Python source, and secret files are not downloadable application routes. The security-event API `/api/security/events` is administrator-only, returns the latest 100 events, retains approximately 20,000 events, and records action, actor ID, target ID, result, and time without recording passwords, tokens, request bodies, or raw IP addresses. It is a local diagnostic log, not a tamper-proof external audit trail.

## Limits and browser protections

The app accepts at most 64 KiB per request, 10 form parts, and 8 KiB per form field. JSON must be a UTF-8 object; duplicate keys, non-finite numbers, wrong field types, invalid IDs, and oversized values are rejected. Workspace creation is capped at 1,000 stages, 250 teams, 5,000 connections, and 250 accounts. User writes are limited to 300 per minute. Authentication is limited to 30 requests per source IP per 15 minutes, with an additional ten failed attempts per account/IP pair.

Hierarchy writes also require an administrator session, CSRF validation, and same-origin requests. Limits are 50 macro-stages, 2,000 subteams overall, and 100 subteams per parent team. Headcounts must be integers from 0 to 10,000. Subteam names are unique within each parent. Deleting a macro-stage unassigns its children without deleting stages or edges; deleting a parent team cascades its subteams and stage assignments.

Content Security Policy restricts scripts and connections to this origin, blocks framing, plugins, and base-URL injection, and limits form submissions to this origin. Inline CSS remains permitted for diagram positioning and existing visual styles; inline JavaScript and dynamic evaluation are not permitted. User text is rendered with DOM text APIs, not HTML string injection. These controls supplement parameterized SQL, authorization, and CSRF validation; they are not substitutes for them.

Application and Waitress limits reduce some resource-exhaustion risks. They do not provide network-level DDoS protection or defend a compromised administrator, operating system, browser, or cloud account.

## Verification and updates

Run `python -m unittest discover -s tests -v` in a development environment with `requirements-dev.txt` installed. JavaScript checks are driven by Python with a small DOM double; a real-browser visual and interaction smoke test is still needed when changing UI behavior.

For published dependency advisories, install `pip-audit` in an isolated development environment and run `python -m pip_audit -r requirements.lock`. For Python source review, run `python -m bandit app.py validation.py`. Review results rather than treating either tool as proof of security. Regenerate `requirements.lock` with hashes after selecting and verifying dependency updates, and retest before installing them. Update the private Python runtime separately using an official release and its published SHA-256; updating Python packages alone does not update CPython or OpenSSL.

Security controls were checked against [Flask's security guidance](https://flask.palletsprojects.com/en/stable/web-security/), [Flask configuration guidance](https://flask.palletsprojects.com/en/stable/config/), and [Waitress documentation](https://docs.pylonsproject.org/projects/waitress/en/latest/). See [SECURITY_REPORT.md](SECURITY_REPORT.md) for this review's evidence and limits.
