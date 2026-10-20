# Security: controls, status and responsibilities

The Legacy Records Viewer shows PHI from a retired EHR, so a vulnerability anywhere (browser, app,
databases, network, pipeline) must not lead to disclosure, alteration or loss of records. This
document lists every control, where it is enforced, and its status:

- **Pass:** implemented in the app and covered by tests (`tests/unit/test_security.py` and others).
- **Infra:** must be provided by the AWS setup ([DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md)).
- **DBA:** must be done on the archive SQL Server.
- **Ops:** a process to run regularly.
- **Open:** not done yet.

Reviewed 2026-10-21 against CLAUDE.md §8 and the OWASP Top 10. Dependency audit (`pip-audit`, 163
locked packages): **no known vulnerabilities**.

---

## 1. What we protect and from whom

| Asset | Threats |
|---|---|
| Patient records in the archive (EMR, Ntier, DMZ) and scanned pages | Unauthorised viewing; bulk extraction; tampering with the archive |
| App database: users, sessions, **audit log**, **release log** | Account takeover; session theft; erasing evidence of access |
| Secrets: SQL login, session-signing key, DB URL | Leak through code, logs, images or CI |
| Availability for 5 clinic staff | Denial of service, broken deploys |

**Attackers considered:**
- outsiders on the internet
- a stolen or phished staff password
- a malicious or compromised document inside the archive (stored XSS)
- a compromised dependency or CI workflow
- an insider browsing records without a reason. This one is handled by the audit log and review,
  since everyone has the same role.

---

## 2. Web application

### 2.1 Authentication and sessions
| Control | Status |
|---|---|
| Every route except `/login`, `/healthz`, `/readyz` and static files requires a valid session; signed-out requests redirect to sign-in (HTMX gets `HX-Redirect`) | **Pass** |
| Passwords hashed with **argon2id**; minimum 12 characters; rehash on login when parameters change | **Pass** |
| Generic sign-in error; the same time is spent on unknown emails as on real ones (no account enumeration) | **Pass** |
| **Account lockout:** 5 failed attempts lock the account for 15 minutes | **Pass** |
| **Per-IP sign-in throttle:** 10 failures from one address in 15 minutes block further attempts, even with the right password; audited as `rate_limited` | **Pass** (new) |
| Server-side sessions; the cookie holds only a random 32-byte token, HMAC-signed; stored hashed in the DB | **Pass** |
| Session id **rotated at sign-in**; deleted at sign-out; **15-minute idle**, **8-hour absolute** timeout; disabled users are signed out on their next request | **Pass** |
| Cookie flags: `HttpOnly`, `Secure` (production), `SameSite=Lax`, `Path=/` | **Pass** |
| Tampered or forged session cookies are ignored | **Pass** (tested) |
| No self-registration and no password reset by email. Users are created and disabled from the command line by an administrator (`cli.py create-user`), so there is less to attack. | **Pass** |
| MFA | **Open.** Recommend MFA in front of the app (VPN with MFA, or AWS Verified Access / an identity provider) until in-app TOTP is added |

### 2.2 Request forgery and browser protections
| Control | Status |
|---|---|
| **CSRF token** (HMAC of the session) on every POST, including sign-in (pre-login nonce) and sign-out; missing or wrong token → 403 | **Pass** (tested) |
| **Content-Security-Policy:** `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'`. No inline scripts or styles anywhere. | **Pass** |
| `X-Frame-Options: DENY` (no clickjacking), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` | **Pass** |
| `Strict-Transport-Security` (1 year, subdomains) whenever cookies are secure | **Pass** (new) |
| `Permissions-Policy` (camera, microphone, location … off), `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy: same-origin` | **Pass** (new) |
| **Host-header check** (`ALLOWED_HOSTS`): any other host gets 400 (blocks host-header injection and DNS rebinding) | **Pass** (new) |
| `Cache-Control: no-store` on every non-static response, so PHI is never cached by the browser or proxies | **Pass** |
| HTMX: `allowEval` off, history cache 0 (no PHI in browser storage), same-origin requests only | **Pass** |
| No API docs exposed (`/docs`, `/openapi.json` disabled) | **Pass** |

### 2.3 Injection and unsafe content
| Control | Status |
|---|---|
| **SQL injection:** every query is a `.sql` file with **bound parameters** (`:name`); no SQL is built from strings anywhere (checked); `LIKE` input escaped | **Pass** |
| **HTML from the EMR** (documents, notes) is sanitised with **nh3**: no scripts, event handlers, styles, forms or images, and no link URL schemes. Only then is it rendered. | **Pass** |
| All other output goes through Jinja **autoescape**; `|safe` is used only on nh3-sanitised HTML (6 places, each reviewed) | **Pass** |
| Embedded pictures in documents: rewritten only from a strict numeric pattern produced by our own code; the image route checks the image belongs to the patient | **Pass** |
| RTF notes are converted to plain text; never rendered as HTML | **Pass** |
| Uploaded files: none (the viewer accepts no uploads) | **Pass** |
| Downloads (PDF releases, attachments): fixed `Content-Type`, `Content-Disposition: attachment`, generic file names (never the patient's name) | **Pass** |
| Path traversal on scanned files: stored UNC paths are mapped under one root; anything that resolves outside it is refused | **Pass** |
| Image decoding: Pillow with a pixel limit (decompression-bomb guard); files over 50 MB refused | **Pass** |
| No client-side `innerHTML` / `eval` in our JavaScript | **Pass** |

### 2.4 Access control and privacy
| Control | Status |
|---|---|
| Patient keys validated by regex (`EMR:\d+`, `DMZ:\d+`); unknown → 404 | **Pass** |
| **Object-level checks:** every note, document, page image, attachment, lab report and photo is fetched with the item id **and** the patient id; another patient's item → 404 | **Pass** (tested per area) |
| Pre-2010 section hidden (404) unless `FEATURE_LEGACY_DMZ` is on | **Pass** |
| **Audit log** of every sign-in (success, failure, lockout, throttle), search, chart and tab view, note / document / photo view, print and export. Append-only (no update or delete code path). No PHI in `detail`. | **Pass** |
| **Release log** of every PDF: who, when, recipient, purpose, sections, page count, SHA-256 of the file | **Pass** |
| Same role for all 5 users (by design). Least privilege comes from the network restriction, the audit log and periodic review. | **Ops:** monthly audit-log review |

### 2.5 Errors and logging
| Control | Status |
|---|---|
| Friendly 404 / 500 pages and HTMX error fragments; **no stack traces** to the browser | **Pass** |
| Unhandled errors log the exception **type and route template only** | **Pass** |
| One log line per request: request id, method, **route template** (never the path or query string, which can hold names), status, duration, user id | **Pass** (new, tested) |
| Database errors never shown or logged with host or login names (`/readyz` returns `ok` / `error` only) | **Pass** |
| Web server access logs (gunicorn / uvicorn) **turned off** in the container, because they would log query strings | **Open:** Dockerfile (Phase 11) |

### 2.6 Production fail-safes
| Control | Status |
|---|---|
| `APP_ENV=production` **refuses to start** unless: `SESSION_SECRET` ≥ 32 chars, `COOKIE_SECURE=true`, `USE_FAKE_DATA=false`, `ALLOWED_HOSTS` set, `APP_DATABASE_URL` uses `sslmode=require`. Errors name the setting, never its value. | **Pass** (new, tested) |
| **Archive login must be read-only:** at start-up the app checks its own permissions in every source database (`IS_ROLEMEMBER`, `HAS_PERMS_BY_NAME`; read-only catalog functions). If it could write, production **does not start**. `/readyz` reports `sql_login: writable` → 503. (`ALLOW_WRITABLE_SQL_LOGIN=true` is a temporary, logged override.) | **Pass** (new, tested) |
| Unverified SQL Server certificate (`SQL_TRUST_SERVER_CERTIFICATE=true`) logs a warning at start-up | **Pass** |

---

## 3. Databases

### 3.1 Archive SQL Server (EMR, Ntier_0010060, DMZ)
| Control | Owner / status |
|---|---|
| Dedicated login **`legacy_viewer_ro`**, `db_datareader` on the three databases only; no other database (never `AIE_Master`). Script in DEPLOYMENT_PLAN.md §4. | **DBA**. Today's login can write. The app now refuses to start in production until this is fixed. |
| `DENY SELECT` on the secret / SSN columns (`DEM_SSNUM`, `GUARANTOR_SSNUM`, `INS_SUBSSNUM`, `PROV_PASSWORD`, `PROV_SSNUM`, `EXTSYS_PATIENTINDEX.SSN`, `PM.Contacts.SSN`, `PM.Practitioners.SSN`, `PM.Carriers.Elig_Password`, `conv.person.ssno`, `conv.drmast.ssno / dea_num`). The app never selects them anyway. | **DBA** (recommended) |
| **App-side read-only guard:** every statement sent to a source database is checked; anything other than a single `SELECT` / `WITH … SELECT` (or containing `INSERT`, `UPDATE`, `DELETE`, `EXEC`, `INTO`, `DROP`, …) is refused before it reaches the server | **Pass** |
| Explicit column lists only (no `SELECT *`); the NEVER columns are not in any query (unit test for the DMZ queries) | **Pass** |
| Connections use `Encrypt=yes`, `ApplicationIntent=ReadOnly`, a 15 s login timeout and a 30 s query timeout | **Pass** |
| Valid TLS certificate on SQL Server, so the app can verify it (`SQL_TRUST_SERVER_CERTIFICATE=false`) | **DBA / Infra** |
| Port 1433 reachable **only from the app's security group** | **Infra** |
| SQL Server auditing of failed logins and permission changes; backups of the restored databases kept unchanged | **DBA** |
| The archive data never changes, so a periodic checksum or row-count snapshot detects tampering | **Ops** (optional) |

### 3.2 App database (PostgreSQL)
| Control | Owner / status |
|---|---|
| RDS PostgreSQL 16, **encrypted at rest (KMS)**, **TLS required** (`rds.force_ssl=1`; app uses `sslmode=require`) | **Infra** (app enforces `sslmode` in production) |
| Private subnets; 5432 only from the app security group; no public access | **Infra** |
| Separate migration user (DDL) and runtime user (DML only on app tables) | **Infra / Ops** |
| Backups: automated 35 days + **monthly snapshots kept 6 years** (HIPAA retention of audit and disclosure records) | **Infra** |
| Audit and release logs append-only in code. Optionally a DB trigger or `REVOKE UPDATE, DELETE` on `audit_log` / `release_log` for the runtime user. | **Pass** (code) / **Infra** (DB rule, recommended) |
| Session tokens stored **hashed** (a leaked table does not give usable sessions); passwords argon2id | **Pass** |

---

## 4. Infrastructure and network (AWS)

| Control | Owner |
|---|---|
| **AWS BAA** signed; only HIPAA-eligible services | Clinic / Infra |
| TLS 1.2+ only at the ALB (ACM certificate, modern security policy); HTTP redirects to HTTPS | Infra |
| **Access restricted** to the clinic: IP allow-list on the ALB / WAF, or VPN with MFA, or AWS Verified Access | Infra |
| **AWS WAF:** managed rule sets (core, known bad inputs, SQLi), **rate-based rule on `/login`**, IP reputation list | Infra |
| App in private subnets; outbound only through VPC endpoints (no open internet egress) | Infra |
| Containers: non-root user, read-only root filesystem, no SSH, minimal base image, image scanning in ECR | App (Dockerfile) + Infra |
| Secrets only in **Secrets Manager** (injected at start; never in the image, repo, logs or CI). `SESSION_SECRET` rotated yearly; SQL password rotated on staff changes. | Infra / Ops |
| Scanned page copies in S3: Block Public Access, SSE-KMS, versioning (optionally Object Lock), bucket policy allowing only the app role through the VPC endpoint | Infra |
| CloudTrail on, logs to a locked bucket; GuardDuty on; Security Hub (HIPAA controls) | Infra |
| CloudWatch alarms: 5xx spikes, `login_failed` / `rate_limited` spikes (log metric filter), unhealthy tasks, `/readyz` failing | Infra |
| Load balancer forwards the client IP; the app trusts `X-Forwarded-For` **only from the ALB** (gunicorn `forwarded_allow_ips`), so audit IPs and the throttle see real addresses | App (Dockerfile) + Infra |

---

## 5. Code, dependencies and CI/CD

| Control | Status |
|---|---|
| Every change through a pull request with review; `main` protected | **Infra** (GitHub settings) |
| CI on every PR: lint, full tests, **secret scan (gitleaks)**, **dependency audit (pip-audit)**, **image scan (Trivy)**; any failure blocks merge | **Open:** workflows (Phase 11) |
| Dependencies pinned by `uv.lock`; Dependabot / Renovate for weekly update PRs | **Open** |
| GitHub → AWS via **OIDC** roles with least privilege; no long-lived AWS keys | **Infra** |
| Same image promoted from staging to production; production deploy needs a named approver | **Open:** deploy workflow |
| **Staging uses fake data only** (no PHI outside production) | **Pass** (fake-data mode) / **Infra** |
| Never commit `.env` / filled `.env.example` (gitleaks blocks it). History checked 2026-10-21: no password or host in any commit; the SQL login name appears once in an old `DATA_MAP.md` revision. Rotate it with the new read-only login. | **Ops** |

---

## 6. Operations

| Process | Frequency |
|---|---|
| Review the audit log: sign-in failures, lockouts, throttles, unusual volumes of chart views or exports per user | Monthly |
| Review the user list; disable leavers the same day (`cli.py`), which ends their sessions on the next request | On every staff change; quarterly review |
| Patch: rebuild the image (base OS + dependencies) and redeploy | Monthly, or immediately for critical CVEs |
| Restore test of an RDS snapshot | Twice a year |
| Penetration test or external scan of the production URL | Before go-live, then yearly |
| **Incident response:** <br>1. Disable the affected accounts. <br>2. Rotate `SESSION_SECRET` (signs everyone out) and the SQL password. <br>3. Preserve the audit log and CloudTrail. <br>4. Assess breach notification (HIPAA: without unreasonable delay, ≤ 60 days). | As needed |

---

## 7. Open items (to finish before go-live)

1. **DBA:** read-only login `legacy_viewer_ro` (+ column DENYs); valid TLS certificate. Production won't start without the read-only login.
2. **Infra:** network restriction (IP allow-list or VPN with MFA), WAF with the `/login` rate rule, RDS TLS and encryption, 6-year snapshots, CloudTrail and GuardDuty, alarms.
3. **App (Phase 11):** Dockerfile (non-root, read-only filesystem, access logs off, trusted proxy only from the ALB), CI with gitleaks / pip-audit / Trivy, deploy workflow with approval.
4. **Decide on MFA:** in front of the app (VPN or IdP) now, or in-app TOTP as a follow-up.
5. External penetration test before go-live.
