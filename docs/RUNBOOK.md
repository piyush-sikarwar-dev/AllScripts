# Runbook: deploy and operate on one EC2 server

Step-by-step for the EC2 host (Ubuntu 24.04 LTS, x86_64). For the wider AWS design see
[DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md); for the security controls see [SECURITY.md](SECURITY.md).

---

## 0. Before you start

| Check | How |
|---|---|
| Security group: inbound **8000 only from the load balancer** (or your IP while testing); SSH only from your IP, or no SSH at all (Session Manager) | EC2 console → Security groups |
| The server reaches the archive SQL Server on 1433 | `nc -zv <sql-host> 1433` → "succeeded" |
| The server reaches the app database (RDS) on 5432 | `nc -zv <rds-endpoint> 5432` |
| Read-only SQL login exists (`legacy_viewer_ro`) | DBA. **Production will not start with a login that can write.** |

## 1. Install Docker (once)

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install docker.io docker-compose-v2 git netcat-openbsd
sudo systemctl enable --now docker
sudo usermod -aG docker $USER   # sign out and back in
```

## 2. Get the code (once)

```bash
sudo mkdir -p /srv/legacy-viewer/empty && sudo chown $USER /srv/legacy-viewer
cd /srv/legacy-viewer
git clone https://github.com/Centricity-Research/Legacy-DEC-LR-Records.git app
```

## 3. Settings and secrets (once, then on rotation)

```bash
sudo mkdir -p /etc/legacy-viewer
sudo cp /srv/legacy-viewer/app/deploy/app.env.template /etc/legacy-viewer/app.env
sudo nano /etc/legacy-viewer/app.env       # fill in every <...> value
sudo chown root:root /etc/legacy-viewer/app.env
sudo chmod 600 /etc/legacy-viewer/app.env  # only root can read it
```

- `SESSION_SECRET`: generate with `python3 -c "import secrets; print(secrets.token_urlsafe(64))"`.
- Passwords come from AWS Secrets Manager. Don't paste them into chat, tickets or the repository.
- Using PostgreSQL on this server instead of RDS? Put its password in `/etc/legacy-viewer/pg_password`
  (chmod 600) and add `--profile local-db` to the commands below. RDS is recommended.

## 4. First deploy

```bash
cd /srv/legacy-viewer/app
docker compose -f docker-compose.prod.yml build                 # builds the image (ODBC + PDF libs)
docker compose -f docker-compose.prod.yml --profile tools run --rm migrate          # create app tables
docker compose -f docker-compose.prod.yml --profile tools run --rm cli dbcheck      # archive reachable?
docker compose -f docker-compose.prod.yml --profile tools run --rm cli build-crosswalk  # EMR <-> PM links
docker compose -f docker-compose.prod.yml up -d app
curl -s http://127.0.0.1:8000/healthz      # {"status":"ok"}
curl -s http://127.0.0.1:8000/readyz       # every check "ok", sql_login "read-only"
```

If `up` fails, read the reason with `docker compose -f docker-compose.prod.yml logs app`.
In production the app refuses to start when a setting is unsafe; the log names the setting,
never its value.

## 5. Create the staff accounts

One per person. The password is typed at a prompt (minimum 12 characters) and never appears in
shell history:

```bash
docker compose -f docker-compose.prod.yml --profile tools run --rm cli create-user --email name@clinic.org --name "Full Name"
```

Other account commands: `reset-password --email …`, `deactivate-user --email …`. Deactivation ends
that person's sessions on their next request.

## 6. Update to a new version

```bash
cd /srv/legacy-viewer/app
git fetch && git checkout <release-tag-or-commit>
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml --profile tools run --rm migrate
docker compose -f docker-compose.prod.yml up -d app            # restarts with the new image
curl -s http://127.0.0.1:8000/readyz
```

**Rollback:** check out the previous tag, `build`, then `up -d app`. Migrations are additive, so an
older version runs against a newer schema.

## 7. Day-to-day

| Task | Command |
|---|---|
| Status / health | `docker compose -f docker-compose.prod.yml ps` · `curl -s http://127.0.0.1:8000/readyz` |
| Logs (no PHI: route templates, status, timings, user ids) | `docker compose -f docker-compose.prod.yml logs --tail 200 app` |
| Restart | `docker compose -f docker-compose.prod.yml restart app` |
| Rotate `SESSION_SECRET` (signs everyone out) | edit `/etc/legacy-viewer/app.env`, then `up -d app` |
| OS patches | `sudo apt update && sudo apt -y upgrade`, reboot if required; the app restarts by itself |
| Monthly image refresh (security fixes) | `docker compose -f docker-compose.prod.yml build --pull` then `up -d app` |

## 8. Scanned pages (when the share copies are available)

1. Copy or mount the shares on the host, e.g. `/srv/scans/hmscan` and `/srv/scans/legacy`.
2. Start the app with them mounted read-only:
   ```bash
   export SCAN_HOST_DIR=/srv/scans/hmscan LEGACY_SCAN_HOST_DIR=/srv/scans/legacy
   ```
3. In `app.env` set `SCAN_ROOT=/scans/hmscan` and `LEGACY_SCAN_ROOT=/scans/legacy`, then run
   `up -d app`.
4. Open a few documents in the Documents tabs and check the pages display.

(If the copies go to S3 instead, the app needs the S3 store: see DEPLOYMENT_PLAN.md §3.4.)
