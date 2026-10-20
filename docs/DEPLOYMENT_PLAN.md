# Deployment, infrastructure and CI/CD plan

How the Legacy Records Viewer goes from this repository to a production service on AWS, what the
infrastructure has to provide, and how changes reach production. It covers what the infra team
builds, what the app side builds (Phase 11), and the open decisions.

The data is PHI. Every choice below assumes HIPAA:
- a signed AWS BAA
- HIPAA-eligible services only
- encryption in transit and at rest
- least-privilege access
- no PHI in logs

---

## 1. What runs

| Piece | What it is | Notes |
|---|---|---|
| **App container** | FastAPI app served by `gunicorn -k uvicorn.workers.UvicornWorker`, Python 3.12, Microsoft ODBC Driver 18, WeasyPrint libraries (Pango, Cairo, fonts) | Stateless: sessions, audit and release logs live in the app database. In-memory caches are per process and safe to lose. |
| **Source SQL Server** | The restored Allscripts databases `EMR`, `Ntier_0010060`, `DMZ` on one instance | The app reads only, with explicit column lists. It needs a **read-only login** (§4). |
| **App database** | PostgreSQL 16: users, sessions, audit log, release log, export selections, patient crosswalk | Small (MB to low GB). Alembic migrations. Audit and release logs are append-only and must be kept long term. |
| **Scanned page files** | Copies of `\\amhs-db1\hmscan` (EMR, ~626k documents) and `\\w10060-1\images` (pre-2010, ~171k TIFF/JPEG) | Today the Documents tabs list metadata only. Pages display once these files are reachable (§3.4). |
| **One-off jobs** | `alembic upgrade head`, `cli.py create-user`, `cli.py build-crosswalk`, `cli.py dbcheck` | Run as one-off tasks from the same image. |

Users: 5 clinic staff, one role. Expected load is a handful of concurrent users, so the stack is
sized for reliability, not scale.

---

## 2. Target architecture (AWS)

```
 Clinic staff (browser) ──HTTPS──▶ Route 53 ──▶ ALB (ACM certificate, WAF, IP allow-list)
                                                  │  private subnets only below this line
                                                  ▼
                                   ECS Fargate service: app (2 tasks, 2 AZs)
                                    │            │              │
                    TCP 1433, TLS   │            │ TLS 5432     │ HTTPS (VPC endpoint)
                                    ▼            ▼              ▼
                         SQL Server (archive)   RDS PostgreSQL   S3: scan copies (+ export temp?)
                         read-only login        (app database)   SSE-KMS, private, versioned
                                    │
          Secrets Manager (SQL login, session secret, DB URL) · CloudWatch Logs + alarms · ECR (images)
```

**Recommended services** (all HIPAA-eligible): ECS on Fargate, ECR, ALB, ACM, Route 53, WAF,
RDS for PostgreSQL, S3, KMS, Secrets Manager, CloudWatch, VPC endpoints.

**Smaller alternative:** a single EC2 instance running Docker behind the ALB. It's cheaper but you
patch the OS yourself, so Fargate is recommended.

---

## 3. What the infrastructure must provide

### 3.1 Network
- **VPC** with private subnets in **2 AZs** for the app and RDS, and public subnets only for the ALB.
- **App → SQL Server on TCP 1433.** If SQL Server is on EC2 or RDS in another VPC or account, set up
  VPC peering or a Transit Gateway. Its security group allows 1433 **only from the app's security group**.
- **App → RDS on 5432**, allowed from the app security group only.
- **Outbound:** S3, Secrets Manager, ECR, CloudWatch and SSM through **VPC endpoints**, so no internet
  egress is needed. If a NAT gateway is used instead, restrict it.
- **Inbound:** only the ALB on 443. Port 80 redirects to 443.

### 3.2 Who can reach it
The app has its own sign-in:
- argon2 password hashes
- lockout after 5 failed attempts
- 15-minute idle and 8-hour absolute session timeout

Because it holds PHI, the network should also limit who can reach it. Pick one:
- **ALB security group / WAF IP allow-list** for the clinic's office IPs. This is the simplest.
- **VPN** (AWS Client VPN or the clinic's existing VPN) with an internal ALB. This is the strongest,
  and works when staff are remote.
- **AWS Verified Access** in front of the ALB.

### 3.3 Compute (ECS Fargate)
| Setting | Value |
|---|---|
| Tasks | 2 (one per AZ); min 1, max 2 |
| Size | 1 vCPU, **4 GB** memory per task. PDF releases with many scanned pages are the memory-heavy part. |
| Workers | `gunicorn -w 3`, timeout **300 s** |
| ALB idle timeout | **300 s**. Large PDF exports can take longer than the 60 s default. |
| Health check | `GET /healthz` (no database access). `GET /readyz` checks all four databases; use it for monitoring, not ALB health. |
| Logs | stdout → CloudWatch Logs. The app logs request id, route template, status, duration and user id only; never names, DOBs, note text or search text. |
| Filesystem | Read-only root filesystem except `/tmp`; non-root user |

### 3.4 Scanned page files: recommended S3
1. **Copy** both shares into one private S3 bucket using AWS DataSync from the on-prem / EC2 file
   server (or `robocopy` + `aws s3 sync`). Keep the folder structure: the app maps the stored UNC
   prefix (`\\amhs-db1\hmscan\…`, `\\w10060-1\images\…`) to an S3 prefix.
2. Bucket settings:
   - Block Public Access
   - SSE-KMS
   - versioning
   - optionally Object Lock for immutability
   - access only from the app task role, through a VPC endpoint
3. **App side (Phase 11):** finish the `S3Store` in `app/documents/store.py`, which is a stub today.
   Settings will be `SCAN_STORE=s3`, `SCAN_S3_BUCKET`, `SCAN_S3_PREFIX`, and the same for the
   legacy share.

   Alternative: mount the copies on **EFS** and set `SCAN_ROOT` / `LEGACY_SCAN_ROOT`. This works
   today with no code change, but costs more per GB and is harder to make immutable.

Please share the **total size and file count** of both shares. That decides DataSync timing and cost.

### 3.5 App database (RDS PostgreSQL 16)
| Setting | Value |
|---|---|
| Instance | db.t4g.small (or micro); Multi-AZ recommended for production |
| Storage | 20 GB gp3, encrypted (KMS) |
| TLS | `rds.force_ssl = 1`; the app connects with `sslmode=require` |
| Backups | Automated 35 days, plus a **monthly snapshot kept 6 years**. HIPAA requires keeping audit and disclosure records 6 years, and `audit_log` and `release_log` are those records. |
| Users | One app user (DDL only for migrations), or a separate migration user and a runtime user without DDL |

### 3.6 Secrets and configuration
**Secrets Manager** (injected into the task as environment variables, never in the image or repo):

| Secret | Used for |
|---|---|
| `SQL_USER`, `SQL_PASSWORD` | Read-only archive login |
| `APP_DATABASE_URL` | `postgresql+psycopg://…?sslmode=require` |
| `SESSION_SECRET` | Signs the session cookie: a random 64-byte value, rotated yearly |

**Plain environment** (task definition):

| Variable | Production value |
|---|---|
| `APP_ENV` | `production`: turns on the fail-closed start-up checks ([SECURITY.md](SECURITY.md) §2.6) |
| `ALLOWED_HOSTS` | the site's host name, e.g. `records.<clinic>.org` |
| `USE_FAKE_DATA` | `false` |
| `SQL_HOST`, `SQL_PORT` | archive endpoint, 1433 |
| `SQL_TRUST_SERVER_CERTIFICATE` | `false` (needs a valid cert on SQL Server; see §6) |
| `EMR_DATABASE`, `NTIER_DATABASE`, `DMZ_DATABASE` | `EMR`, `Ntier_0010060`, `DMZ` |
| `COOKIE_SECURE` | `true` |
| `CLINIC_NAME`, `CLINIC_TZ` | the clinic's name; `America/New_York` (confirm) |
| `FEATURE_LEGACY_DMZ` | `true` to show the Pre-2010 records section |
| `SCAN_*`, `LEGACY_SCAN_*` | per §3.4 |

### 3.7 Monitoring and alerts
- CloudWatch alarms:
  - ALB 5xx rate
  - unhealthy targets
  - task restarts
  - RDS CPU, storage and connections
  - `/readyz` failures (a scheduled synthetic check)
- Log retention: app logs 1 year. Audit and release logs live in RDS and are covered by the 6-year
  snapshots.
- Alert destination: an email or SNS topic for the people on call.

### 3.8 Environments
| Environment | Data | Purpose |
|---|---|---|
| **Local** | Fake data (`USE_FAKE_DATA=true`), or the real archive from a developer machine on VPN | Development |
| **Staging** | **Fake data only**. No PHI, so it can be looser (e.g. reviewers outside the clinic). | Review every change before production |
| **Production** | Real archive, read-only | Clinic staff |

Do **not** point staging at the real archive unless staging gets the same controls as production.

---

## 4. Database access the app needs (DBA task)

Today's SQL login can **write** ([DATA_MAP.md](DATA_MAP.md) §7). Production must use a login that
can only read, and only the three databases. The DBA runs this (example):

```sql
-- On the archive SQL Server, as an administrator. Replace the password; store it in Secrets Manager.
CREATE LOGIN legacy_viewer_ro WITH PASSWORD = '<generated>', CHECK_POLICY = ON;
USE EMR;            CREATE USER legacy_viewer_ro FOR LOGIN legacy_viewer_ro; ALTER ROLE db_datareader ADD MEMBER legacy_viewer_ro;
USE Ntier_0010060;  CREATE USER legacy_viewer_ro FOR LOGIN legacy_viewer_ro; ALTER ROLE db_datareader ADD MEMBER legacy_viewer_ro;
USE DMZ;            CREATE USER legacy_viewer_ro FOR LOGIN legacy_viewer_ro; ALTER ROLE db_datareader ADD MEMBER legacy_viewer_ro;
-- No access to AIE_Master or any other database. Optionally deny the SSN / password columns too:
USE EMR; DENY SELECT ON HPSITE.DEMOGRAPHICS (DEM_SSNUM) TO legacy_viewer_ro;
```

The app connects with `ApplicationIntent=ReadOnly`, `Encrypt=yes`, a 15 s login timeout and a
30 s query timeout. The app's code is read-only too (`assert_read_only` guard), but the login is the
real safety net.

---

## 5. CI/CD (GitHub Actions, `Centricity-Research/Legacy-DEC-LR-Records`)

### 5.1 On every pull request (`ci.yml`)
1. `uv sync --frozen`
2. `ruff check .` and `ruff format --check .`
3. `pytest -m "not integration"`, on fake data with no database. The runner installs the
   WeasyPrint system libraries so the PDF tests run instead of being skipped.
4. **Secret scan** (gitleaks) on the diff. This blocks commits that contain credentials, such as a
   filled-in `.env.example`.
5. Dependency audit (`pip-audit`) and **image scan** (Trivy) of the built Docker image.
6. Required to pass before merge; `main` is protected (PR + 1 review).

### 5.2 On merge to `main` (`deploy.yml`)
1. Build the image once and tag it with the commit SHA. Push to **ECR** (image scanning on).
2. **Deploy to staging:**
   - run the migration one-off task (`alembic upgrade head`)
   - update the ECS service
   - wait for steady state
   - smoke test: `/healthz` 200, `/login` renders, sign in with a staging test user
3. **Manual approval** (a GitHub Environment `production` with required reviewers).
4. **Deploy the same image to production:** migration task → ECS rolling update → `/readyz` check
   → automatic rollback if the service doesn't stabilise.

### 5.3 AWS access from GitHub
- **OIDC federation**, so no long-lived AWS keys are stored in GitHub.
- A deploy role per environment, allowed only to:
  - push to ECR
  - register task definitions
  - update the ECS service
  - run the migration task
- Secrets stay in Secrets Manager. GitHub only holds role ARNs and the AWS region.

### 5.4 Not in CI
Integration tests against the real archive (`pytest -m integration`) need network access to SQL
Server and touch PHI. Run them manually from inside the VPC (an SSM session or a one-off ECS task)
after infrastructure changes. Don't run them on GitHub-hosted runners.

### 5.5 Infrastructure as code
Define the AWS resources in **Terraform** (or CDK) in a separate infra repo, so staging and
production are identical and every change is reviewed. The app repo only holds the task definition
template and the workflows.

---

## 6. Go-live checklist

| # | Step | Owner |
|---|---|---|
| 1 | AWS BAA signed; account / region chosen | Clinic / infra |
| 2 | VPC, subnets, security groups, endpoints | Infra |
| 3 | Network path app → SQL Server 1433 tested (`cli.py dbcheck` from a one-off task) | Infra + app |
| 4 | Read-only SQL login created (§4); valid TLS certificate on SQL Server, or an explicit decision to use `SQL_TRUST_SERVER_CERTIFICATE=true` inside the VPC | DBA |
| 5 | RDS PostgreSQL created, TLS on, backups + 6-year snapshots | Infra |
| 6 | Secrets in Secrets Manager | Infra |
| 7 | ECR, ECS cluster / service, ALB + ACM certificate + DNS name | Infra |
| 8 | GitHub OIDC roles, environments (staging, production), branch protection | Infra + app |
| 9 | First deploy to staging (fake data); review screens | App |
| 10 | Production deploy; migrations; `cli.py build-crosswalk`; `cli.py create-user` for the 5 staff | App + clinic |
| 11 | Scan files copied to S3; `S3Store` switched on; spot-check pages | Infra + app |
| 12 | Security checklist (`docs/SECURITY.md`) all pass; access restricted (§3.2) | App + infra |
| 13 | Staff walkthrough; first real release done end to end | Clinic |

---

## 7. What the app side builds (Phase 11)

- `Dockerfile`:
  - python:3.12-slim
  - msodbcsql18
  - WeasyPrint libs and fonts
  - non-root user
  - gunicorn
  - healthcheck on `/healthz`
- `docker-compose.yml` app service for local runs; an entrypoint that runs migrations as a separate
  command.
- **`S3Store`** for scanned pages, with tests (if §3.4 chooses S3).
- `.github/workflows/ci.yml` and `deploy.yml` (§5); ECS task definition template.
- Friendly 404 / 500 pages for every route, including HTMX fragments. Request id in logs only.
- **Performance pass on real data:** chart open < 1.5 s, each tab < 1 s; timings reported.
- `docs/SECURITY.md`: CLAUDE.md §8 checklist with pass / fail per item.
- README: setup, settings, first user, crosswalk, deploy and runbook.

---

## 8. Information needed to start

| # | Question | Why |
|---|---|---|
| 1 | Where is the restored SQL Server: EC2, RDS for SQL Server, or on-prem? Which AWS account / VPC / region? | Network design (§3.1) |
| 2 | Can the DBA create the read-only login (§4)? Who is the DBA contact? | Production must not use a write-capable login |
| 3 | Does SQL Server have a valid TLS certificate? | `Encrypt=yes` without trusting any certificate |
| 4 | Is the AWS BAA signed for this account? | HIPAA |
| 5 | Domain name for the app (e.g. `records.<clinic>.org`) and who manages DNS | ALB + ACM certificate |
| 6 | How staff reach it: office IPs (list), VPN, or remote access needed? | §3.2 |
| 7 | Size and file count of `\\amhs-db1\hmscan` and `\\w10060-1\images`; can DataSync reach them? | §3.4 |
| 8 | S3 (recommended) or EFS for scans? | Decides whether `S3Store` is built |
| 9 | Terraform or CDK, and does an infra repo already exist? | §5.5 |
| 10 | Names and emails of the 5 staff users; who receives alerts | `create-user`, §3.7 |
| 11 | Clinic name and time zone as they should appear | `CLINIC_NAME`, `CLINIC_TZ` |
| 12 | Show the Pre-2010 records section in production? | `FEATURE_LEGACY_DMZ` |
