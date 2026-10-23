# Deploying the Legacy Records Viewer on EC2: step-by-step guide

This guide goes from an empty AWS account to staff signing in over HTTPS, then covers day-to-day
operation. Follow the parts in order: each one depends on the one before.

**Target setup:**
- one EC2 server (t3.large, Ubuntu 24.04 LTS) running the app in Docker
- RDS PostgreSQL for the app's own data
- the existing archive SQL Server (read-only)
- an HTTPS load balancer in front

Background and reasoning: [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md). Security controls:
[SECURITY.md](SECURITY.md).

```
 Staff browser ──HTTPS──▶ ALB (certificate, IP allow-list) ──HTTP 8000──▶ EC2: Docker "app"
                                                                          │          │
                                                       TLS 1433 (read-only) │          │ TLS 5432
                                                                          ▼          ▼
                                                           Archive SQL Server   RDS PostgreSQL
```

---

## Part A: Decide and collect first (no AWS work yet)

| # | Item | Who | Notes |
|---|---|---|---|
| A1 | **AWS account** for production, with the **HIPAA BAA** accepted (AWS Artifact) | Clinic / IT | The quota request was in the *Development* account. Real PHI belongs in a BAA-covered production account. |
| A2 | **Region** | IT | Same region as the archive SQL Server (e.g. us-east-1) |
| A3 | **Where the archive SQL Server runs** (EC2 / RDS / on-prem) and its VPC | IT / DBA | Decides the network path in B1 |
| A4 | **Read-only SQL login** `legacy_viewer_ro` (script in DEPLOYMENT_PLAN.md §4) | DBA | **Production will not start with a login that can write.** |
| A5 | **Domain name** for the app, e.g. `records.<clinic>.org`, and who manages its DNS | IT | Needed for the HTTPS certificate |
| A6 | **Who may connect**: office public IP addresses, or VPN | IT | Used in the load balancer's security group |
| A7 | **5 staff names + emails**; who gets alerts | Clinic | Part E, Part G |
| A8 | Scan shares: do the files still exist? Total size and file count | IT | Part F; can be done after go-live |

---

## Part B: AWS setup

### B1. Network and security groups
Use a VPC that can reach the archive SQL Server (the same VPC, or peering / Transit Gateway).
Create four security groups:

| Security group | Inbound rule | From |
|---|---|---|
| `sg-legacy-alb` | 443 (HTTPS), 80 (redirect only) | **Office IPs only** (A6), or the VPN range |
| `sg-legacy-app` (EC2) | 8000 | `sg-legacy-alb` only |
| `sg-legacy-rds` | 5432 | `sg-legacy-app` only |
| Archive SQL Server's existing group | **add**: 1433 | `sg-legacy-app` only |

**No SSH rule:** you connect with Session Manager (B2). Never open 1433, 5432 or 8000 to
`0.0.0.0/0`.

### B2. IAM role for the EC2 server
Create role **`legacy-viewer-ec2`** (trusted entity: EC2) with:
- `AmazonSSMManagedInstanceCore`: Session Manager access, no SSH keys or open port 22
- `CloudWatchAgentServerPolicy`: logs and metrics (Part G)
- an inline policy that lets it read only its own secret:
  ```json
  {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
    "Action": "secretsmanager:GetSecretValue",
    "Resource": "arn:aws:secretsmanager:<region>:<account>:secret:legacy-viewer/prod-env-*"}]}
  ```

### B3. EC2 instance
| Setting | Value |
|---|---|
| Name | `legacy-viewer-app` |
| AMI | **Ubuntu Server 24.04 LTS**, x86_64. Not 26.04: Microsoft's ODBC driver is published for LTS releases. |
| Type | **t3.large** (2 vCPU, 8 GB). Credit specification **Unlimited**. |
| Subnet | **Private** subnet (no public IP). The ALB lives in public subnets. |
| Security group | `sg-legacy-app` |
| IAM role | `legacy-viewer-ec2` |
| Storage | 30 GB **gp3, encrypted** |
| Metadata | **IMDSv2 required** |
| Protection | Termination protection **on** |
| Key pair | None (Session Manager) |

A private subnet needs outbound HTTPS to install packages and pull images: a NAT gateway, or VPC
endpoints for SSM / Secrets Manager / CloudWatch plus a NAT for apt.

### B4. App database: RDS PostgreSQL
| Setting | Value |
|---|---|
| Engine | PostgreSQL **16** |
| Class | **db.t4g.small**, 20 GB gp3 |
| Network | Private subnets, **Public access: No**, `sg-legacy-rds` |
| Encryption | **On** (KMS) |
| Parameter group | custom, with **`rds.force_ssl = 1`** |
| Backups | 35 days; deletion protection **on** |
| Long-term | Monthly manual snapshot (or AWS Backup plan) kept **6 years**, the HIPAA retention for audit and disclosure records |
| Database / user | database `legacy_viewer`, user `legacy_app` with a generated password |

### B5. Settings secret (Secrets Manager)
Store the **whole settings file** as one secret named **`legacy-viewer/prod-env`** (plaintext type).
Start from `deploy/app.env.template` and fill in:
- `SESSION_SECRET`: generate with `python3 -c "import secrets; print(secrets.token_urlsafe(64))"`
- `SQL_HOST`, `SQL_USER=legacy_viewer_ro`, `SQL_PASSWORD` (A4)
- `APP_DATABASE_URL=postgresql+psycopg://legacy_app:<pw>@<rds-endpoint>:5432/legacy_viewer?sslmode=require`
- `ALLOWED_HOSTS=records.<clinic>.org` (A5)
- `CLINIC_NAME`, `CLINIC_TZ`, `FEATURE_LEGACY_DMZ=true`
- `FORWARDED_ALLOW_IPS=<VPC CIDR>`, e.g. `10.0.0.0/16`

Passwords live only here. Don't put them in email, chat, tickets or the repository.

### B6. HTTPS: certificate and load balancer
1. **ACM:** request a public certificate for `records.<clinic>.org` (DNS validation) and add the
   validation record to DNS.
2. **Target group** `tg-legacy-app`:
   - target type Instance, HTTP, port **8000**
   - health check path **`/healthz`**, healthy threshold 2
   - register the EC2 instance
3. **Application Load Balancer** `alb-legacy`:
   - internet-facing (or internal if staff use a VPN), public subnets in 2 AZs, `sg-legacy-alb`
   - **Idle timeout: 300 s**, because large PDF releases take time
   - listener **443** with the ACM certificate, security policy `ELBSecurityPolicy-TLS13-1-2-2021-06`, forwarding to `tg-legacy-app`
   - listener **80**: redirect to HTTPS
4. **DNS:** point `records.<clinic>.org` at the ALB (Route 53 alias, or a CNAME at your DNS host).
5. **WAF** (recommended): attach a web ACL with:
   - the AWS managed *Core rule set*, *Known bad inputs* and *SQL database* rules
   - a **rate-based rule on `/login`** (e.g. 100 requests per 5 minutes per IP)

---

## Part C: Prepare the server

### C1. Connect
EC2 console → the instance → **Connect → Session Manager → Connect**. No SSH needed.

### C2. Install Docker, git and the AWS CLI
```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install docker.io docker-compose-v2 git netcat-openbsd unzip
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu        # then: exit the session and connect again
# AWS CLI v2
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp && sudo /tmp/aws/install && aws --version
```

### C3. Check the network paths (the most common blocker)
```bash
nc -zv <sql-server-host> 1433        # must say "succeeded"
nc -zv <rds-endpoint> 5432           # must say "succeeded"
```
A **timeout** means a security group or route is missing (B1). Fix that before going further.

### C4. Get the code
On your own machine first: `git push org main`, so the org repository has the latest version.
```bash
sudo mkdir -p /srv/legacy-viewer/empty && sudo chown ubuntu /srv/legacy-viewer
cd /srv/legacy-viewer
git clone https://github.com/Centricity-Research/Legacy-DEC-LR-Records.git app
```
(For a private repository, use a read-only deploy key or a fine-grained token.)

### C5. Write the settings file from Secrets Manager
```bash
sudo mkdir -p /etc/legacy-viewer
aws secretsmanager get-secret-value --secret-id legacy-viewer/prod-env \
    --query SecretString --output text | sudo tee /etc/legacy-viewer/app.env > /dev/null
sudo chown root:root /etc/legacy-viewer/app.env && sudo chmod 600 /etc/legacy-viewer/app.env
sudo grep -c "=" /etc/legacy-viewer/app.env   # just a line count; never print the file
```

---

## Part D: First deployment

```bash
cd /srv/legacy-viewer/app
C="docker compose -f docker-compose.prod.yml"

$C build                                         # 1. build the image (ODBC driver + PDF libraries)
$C --profile tools run --rm migrate              # 2. create the app's tables in RDS
$C --profile tools run --rm cli dbcheck          # 3. archive reachable, login permissions
$C --profile tools run --rm cli build-crosswalk  # 4. link EMR <-> PM patients (a few minutes)
$C up -d app                                     # 5. start the app
curl -s http://127.0.0.1:8000/healthz            # {"status":"ok"}
curl -s http://127.0.0.1:8000/readyz             # every check "ok"; sql_login "read-only"
```

Then:
- **ALB:** the target in `tg-legacy-app` turns **healthy** within about a minute.
- **Browser:** `https://records.<clinic>.org` shows the sign-in page, with a padlock and no warnings.

**If step 5 fails**, run `$C logs app`. In production the app **refuses to start** when something
is unsafe, and the log names the setting, never its value:

| Log message mentions | Fix |
|---|---|
| `SESSION_SECRET` | 64-character random value in the secret (B5) |
| `COOKIE_SECURE` / `USE_FAKE_DATA` / `ALLOWED_HOSTS` | `true` / `false` / your domain |
| `APP_DATABASE_URL must use sslmode=require` | add `?sslmode=require` |
| `the archive SQL login must be read-only` | DBA creates `legacy_viewer_ro` (A4) and you update the secret |

After any change to the secret, repeat C5 and run `$C up -d app`.

---

## Part E: Staff accounts

One per person. The password is typed at a prompt (minimum 12 characters) and never appears in
shell history:
```bash
$C --profile tools run --rm cli create-user --email name@clinic.org --name "Full Name"
```
- `reset-password --email …`: set a new password.
- `deactivate-user --email …`: disable a leaver; their sessions end on their next click.

Each user then signs in once and opens a test patient. That check is the go-live smoke test.

---

## Part F: Scanned page images (when the share copies exist)

The database stores only the original Windows paths for scanned pages, so the files must be
reachable by the app. With one EC2 server, the simplest way is an **encrypted EBS volume**:

1. **Create** an EBS volume (gp3, **encrypted**, sized to the shares plus 20%) in the instance's
   AZ, and attach it as `/dev/sdf`.
2. **Mount** it:
   ```bash
   sudo mkfs -t ext4 /dev/nvme1n1           # check the device name with: lsblk
   sudo mkdir -p /srv/scans && sudo mount /dev/nvme1n1 /srv/scans
   echo "/dev/nvme1n1 /srv/scans ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab
   ```
3. **Copy** the shares, **keeping the folder structure exactly**, e.g. from a Windows machine that
   can read them (robocopy / AWS DataSync), into `/srv/scans/hmscan` and `/srv/scans/legacy`.
4. **Point the app at them:**
   - In the secret, set `SCAN_ROOT=/scans/hmscan` and `LEGACY_SCAN_ROOT=/scans/legacy`, then
     repeat C5.
   - Restart with the folders mounted read-only:
     ```bash
     export SCAN_HOST_DIR=/srv/scans/hmscan LEGACY_SCAN_HOST_DIR=/srv/scans/legacy
     $C up -d app
     ```
5. Open a few scanned documents in the Documents tab and check the pages display.

If the server can reach the file shares directly over SMB, they can instead be mounted read-only
with `mount -t cifs`, and no copy is needed. S3 is an option for very large shares (needs the S3
reader, DEPLOYMENT_PLAN.md §3.4).

---

## Part G: Monitoring, backups and patching

| Task | How |
|---|---|
| **App logs → CloudWatch** | Install the CloudWatch agent (or switch the compose logging driver to `awslogs`). Logs contain route templates, status, timings and user ids only, never PHI. Keep them 1 year. |
| **Alarms** (to the alert email from A7) | ALB unhealthy targets ≥ 1 · ALB 5xx count · EC2 status check failed · RDS free storage low · a metric filter on `login_failed` spikes |
| **EC2 auto-recovery** | CloudWatch alarm on *StatusCheckFailed_System* → action *Recover* |
| **Backups** | RDS: automated 35 days + monthly snapshots kept 6 years (B4). EC2 disks: a Data Lifecycle Manager policy for daily snapshots, kept 14 days; the scan volume weekly. |
| **OS patching** | SSM Patch Manager, weekly in a quiet window (the app restarts by itself), or `sudo apt update && sudo apt -y upgrade` |
| **Image refresh** (security fixes in the base image) | Monthly: `$C build --pull && $C up -d app` |
| **Security monitoring** | CloudTrail, GuardDuty and Security Hub on for the account |

---

## Part H: Go-live checklist

- [ ] BAA in place; production account (A1)
- [ ] `readyz`: every check `ok`, `sql_login` **read-only**
- [ ] HTTPS works on the real domain; HTTP redirects to HTTPS; office-only access confirmed (test from a phone on mobile data: it should **not** connect)
- [ ] WAF attached, with the `/login` rate rule
- [ ] 5 accounts created; each person signed in once
- [ ] One real records release made end to end: the PDF opens, and the Release log shows it
- [ ] Audit log has rows for those sign-ins and views
- [ ] Alarms fire to the right email (test one)
- [ ] RDS snapshot restore tested once
- [ ] [SECURITY.md](SECURITY.md) open items reviewed and signed off

---

## Part I: Updates and rollback

```bash
cd /srv/legacy-viewer/app
git fetch && git checkout <release-tag-or-commit>
$C build
$C --profile tools run --rm migrate
$C up -d app
curl -s http://127.0.0.1:8000/readyz
```

**Rollback:** check out the previous tag, then `$C build && $C up -d app`. Migrations only add, so
an older version still runs.

Later, CI/CD (GitHub Actions) builds the image, pushes it to ECR, and runs these same steps
after an approval (DEPLOYMENT_PLAN.md §5).

---

## Part J: Day-to-day commands

| Task | Command |
|---|---|
| Status | `$C ps` · `curl -s http://127.0.0.1:8000/readyz` |
| Logs | `$C logs --tail 200 app` |
| Restart | `$C restart app` |
| Rotate `SESSION_SECRET` (signs everyone out) | update the secret → C5 → `$C up -d app` |
| Disable a leaver | `$C --profile tools run --rm cli deactivate-user --email …` |

## Part K: Troubleshooting

| Symptom | Likely cause |
|---|---|
| `nc` to 1433 or 5432 times out | Security group or route missing (B1) |
| `dbcheck`: login failed | Wrong `SQL_USER` / `SQL_PASSWORD` in the secret, or the login lacks access to one of the 3 databases |
| ALB target **unhealthy** | App not running (`$C ps`), or `sg-legacy-app` doesn't allow 8000 from `sg-legacy-alb` |
| Browser shows **400 Bad Request** | `ALLOWED_HOSTS` doesn't match the domain being used |
| Browser shows **502 / 504** on big PDF releases | ALB idle timeout still 60 s: set it to 300 (B6) |
| Signed out on every click | `COOKIE_SECURE=true` but the site was opened over plain HTTP: use the HTTPS address |
| "Too many sign-in attempts" | 10 failed sign-ins from that address in 15 minutes: wait, or check for an attack in the audit log |
| Documents tab shows the yellow scans banner | Part F not done yet, or `SCAN_ROOT` is wrong |
