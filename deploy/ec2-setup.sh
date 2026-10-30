#!/usr/bin/env bash
# Legacy DEC & LR Records: one-command install on an Ubuntu 24.04 EC2 server.
#
#   git clone https://github.com/Centricity-Research/Legacy-DEC-LR-Records.git /srv/legacy-viewer/app
#   cd /srv/legacy-viewer/app
#   sudo bash deploy/ec2-setup.sh                         # asks for each setting
#   sudo bash deploy/ec2-setup.sh --secret-id legacy-viewer/prod-env   # settings from Secrets Manager
#
# Steps (docs/RUNBOOK.md Parts C-E): install Docker -> write /etc/legacy-viewer/app.env (root-only)
# -> optional PostgreSQL container with TLS -> network checks -> build image -> migrate -> dbcheck
# -> build-crosswalk -> start app -> health checks -> first staff account.
# Safe to run again: existing settings, database password and data are kept.
# Never prints secrets. Only reads the archive SQL Server (dbcheck / crosswalk are SELECT-only).

set -Eeuo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ETC=/etc/legacy-viewer
ENV_FILE="$ETC/app.env"
COMPOSE_ENV="$ETC/compose.env"
SECRET_ID=""

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32mOK\033[0m %s\n' "$*"; }
warn() { printf '    \033[33mWARNING\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31mSTOPPED:\033[0m %s\n' "$*" >&2; exit 1; }
trap 'die "a command failed on line $LINENO (see the output above)."' ERR

while [[ $# -gt 0 ]]; do
  case "$1" in
    --secret-id) SECRET_ID="${2:?--secret-id needs a value}"; shift 2 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ $EUID -eq 0 ]] || die "run with sudo:  sudo bash deploy/ec2-setup.sh"
[[ -f "$APP_DIR/docker-compose.prod.yml" ]] || die "run this from the cloned repository."
. /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || warn "written for Ubuntu 24.04; this is ${PRETTY_NAME:-unknown}."

# ---------- prompts ----------
ask() {  # ask VAR "question" "default"
  local reply; read -rp "    $2${3:+ [$3]}: " reply
  printf -v "$1" '%s' "${reply:-$3}"
}
ask_secret() {  # ask_secret VAR "question"
  local reply
  while true; do
    read -rsp "    $2: " reply; echo
    [[ -n "$reply" ]] || { echo "    (cannot be empty)"; continue; }
    [[ "$reply" != *"'"* ]] || { echo "    (must not contain a single quote ')"; continue; }
    break
  done
  printf -v "$1" '%s' "$reply"
}
yes_no() {  # yes_no "question" default(Y|N)
  local reply; read -rp "    $1 [$([[ $2 == Y ]] && echo Y/n || echo y/N)]: " reply
  reply="${reply:-$2}"; [[ "$reply" =~ ^[Yy] ]]
}
env_value() {  # value of KEY in app.env, quotes removed
  sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 | sed -e "s/^'\(.*\)'$/\1/" -e 's/^"\(.*\)"$/\1/'
}
urlencode() { python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.stdin.read(),safe=""))'; }

lv() { docker compose --project-directory "$APP_DIR" -f "$APP_DIR/docker-compose.prod.yml" \
         --env-file "$COMPOSE_ENV" "$@"; }

# ---------- 1. packages ----------
say "1/9 Installing Docker, git and tools"
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
apt-get update -qq
apt-get -y -qq upgrade
apt-get -y -qq install docker.io docker-compose-v2 git netcat-openbsd openssl curl python3
systemctl enable --now docker >/dev/null
if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != root ]]; then usermod -aG docker "$SUDO_USER"; fi
docker compose version >/dev/null || die "docker compose plugin is missing."
ok "$(docker --version)"

# ---------- 2. settings ----------
say "2/9 Settings ($ENV_FILE)"
mkdir -p "$ETC" /srv/legacy-viewer/empty
chmod 700 "$ETC"
DB_MODE=""
if [[ -f "$ENV_FILE" ]] && yes_no "A settings file already exists. Keep it?" Y; then
  ok "keeping existing settings"
  grep -q '@postgres:5432/' "$ENV_FILE" && DB_MODE=local || DB_MODE=rds
elif [[ -n "$SECRET_ID" ]]; then
  command -v aws >/dev/null || snap install aws-cli --classic >/dev/null
  aws secretsmanager get-secret-value --secret-id "$SECRET_ID" --query SecretString \
      --output text > "$ENV_FILE.new" || die "could not read secret $SECRET_ID (IAM role? region?)"
  mv "$ENV_FILE.new" "$ENV_FILE"
  grep -q '@postgres:5432/' "$ENV_FILE" && DB_MODE=local || DB_MODE=rds
  ok "settings written from Secrets Manager ($(grep -c '=' "$ENV_FILE") lines)"
else
  echo "    Answer each question (Enter keeps the [default]). Passwords are not shown."
  ask DOMAIN "Web address staff will use (e.g. records.clinic.org)" ""
  [[ -n "$DOMAIN" ]] || die "a web address is needed for ALLOWED_HOSTS."
  ask CLINIC_NAME "Clinic name" ""
  ask CLINIC_TZ "Clinic time zone" "America/New_York"
  echo "    -- Archive SQL Server (use the READ-ONLY login) --"
  ask SQL_HOST "SQL Server host or IP" ""
  ask SQL_PORT "SQL Server port" "1433"
  ask SQL_USER "SQL login" "legacy_viewer_ro"
  ask_secret SQL_PASSWORD "SQL password"
  ask SQL_TRUST "Trust the server certificate without checking it? (true only for a self-signed cert)" "false"
  echo "    -- App database (users, sessions, audit log) --"
  echo "       1) Amazon RDS PostgreSQL (recommended)   2) PostgreSQL container on this server"
  ask DB_CHOICE "Choose 1 or 2" "1"
  if [[ "$DB_CHOICE" == 2 ]]; then
    DB_MODE=local
    [[ -f "$ETC/pg_password" ]] || openssl rand -hex 32 > "$ETC/pg_password"
    APP_DB_URL="postgresql+psycopg://legacy:$(tr -d '\n' < "$ETC/pg_password")@postgres:5432/legacy_viewer?sslmode=require"
  else
    DB_MODE=rds
    ask RDS_HOST "RDS endpoint" ""
    ask RDS_DB "Database name" "legacy_viewer"
    ask RDS_USER "Database user" "legacy_app"
    ask_secret RDS_PASSWORD "Database password"
    APP_DB_URL="postgresql+psycopg://${RDS_USER}:$(printf '%s' "$RDS_PASSWORD" | urlencode)@${RDS_HOST}:5432/${RDS_DB}?sslmode=require"
  fi
  # Load balancer addresses allowed to set X-Forwarded-For: this VPC's range (from instance metadata).
  TOKEN=$(curl -fs -m 2 -X PUT http://169.254.169.254/latest/api/token \
          -H "X-aws-ec2-metadata-token-ttl-seconds: 60" || true)
  MAC=$(curl -fs -m 2 -H "X-aws-ec2-metadata-token: $TOKEN" \
        http://169.254.169.254/latest/meta-data/mac || true)
  VPC_CIDR=$(curl -fs -m 2 -H "X-aws-ec2-metadata-token: $TOKEN" \
        "http://169.254.169.254/latest/meta-data/network/interfaces/macs/$MAC/vpc-ipv4-cidr-block" || true)
  ask FWD "Load balancer network range (VPC CIDR)" "${VPC_CIDR:-10.0.0.0/16}"

  umask 077
  cat > "$ENV_FILE.new" <<EOF
# Written by deploy/ec2-setup.sh on $(date -u +%F). Root-only. Never commit or print this file.
APP_ENV='production'
ALLOWED_HOSTS='${DOMAIN},localhost,127.0.0.1'
USE_FAKE_DATA='false'
COOKIE_SECURE='true'
SESSION_SECRET='$(openssl rand -hex 48)'
SQL_HOST='${SQL_HOST}'
SQL_PORT='${SQL_PORT}'
SQL_USER='${SQL_USER}'
SQL_PASSWORD='${SQL_PASSWORD}'
SQL_TRUST_SERVER_CERTIFICATE='${SQL_TRUST}'
EMR_DATABASE='EMR'
NTIER_DATABASE='Ntier_0010060'
DMZ_DATABASE='DMZ'
APP_DATABASE_URL='${APP_DB_URL}'
CLINIC_NAME='${CLINIC_NAME}'
CLINIC_TZ='${CLINIC_TZ}'
FEATURE_LEGACY_DMZ='true'
FORWARDED_ALLOW_IPS='${FWD}'
WEB_CONCURRENCY='3'
SCAN_ROOT=''
LEGACY_SCAN_ROOT=''
EOF
  cat >> "$ENV_FILE.new" <<'EOF'
SCAN_UNC_PREFIX='\\amhs-db1\hmscan'
LEGACY_SCAN_UNC_PREFIX='\\w10060-1\images'
EOF
  mv "$ENV_FILE.new" "$ENV_FILE"
  unset SQL_PASSWORD RDS_PASSWORD APP_DB_URL
  ok "settings written"
fi
chown root:root "$ENV_FILE"; chmod 600 "$ENV_FILE"

# Compose-level settings: which optional services run, where scan copies are mounted from.
if [[ ! -f "$COMPOSE_ENV" ]]; then
  cat > "$COMPOSE_ENV" <<EOF
COMPOSE_PROFILES=$([[ $DB_MODE == local ]] && echo local-db)
SCAN_HOST_DIR=/srv/legacy-viewer/empty
LEGACY_SCAN_HOST_DIR=/srv/legacy-viewer/empty
EOF
fi
chmod 600 "$COMPOSE_ENV"

# ---------- 3. local PostgreSQL (option 2 only) ----------
if [[ $DB_MODE == local ]]; then
  say "3/9 PostgreSQL container: password file and TLS certificate"
  [[ -f "$ETC/pg_password" ]] || die "$ETC/pg_password is missing but the settings point at the local database."
  mkdir -p "$ETC/pg-tls"
  if [[ ! -f "$ETC/pg-tls/server.key" ]]; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=postgres" \
      -keyout "$ETC/pg-tls/server.key" -out "$ETC/pg-tls/server.crt" 2>/dev/null
  fi
  chown -R 999:999 "$ETC/pg-tls" "$ETC/pg_password"   # uid of the postgres user in postgres:16
  chmod 600 "$ETC/pg-tls/server.key" "$ETC/pg_password"; chmod 644 "$ETC/pg-tls/server.crt"
  ok "password and certificate ready (data kept in the docker volume legacy-viewer_pgdata)"
  warn "back up this server's disk (EBS snapshots): the audit and release logs live here."
else
  say "3/9 App database: RDS (nothing to set up here)"
fi

# ---------- 4. network ----------
say "4/9 Checking network paths"
SQL_HOST_V=$(env_value SQL_HOST); SQL_PORT_V=$(env_value SQL_PORT)
if nc -z -w 5 "$SQL_HOST_V" "${SQL_PORT_V:-1433}" 2>/dev/null; then ok "archive SQL Server reachable"
else die "cannot reach the SQL Server on port ${SQL_PORT_V:-1433}. Fix the security groups (RUNBOOK B1), then run this again."; fi
if [[ $DB_MODE == rds ]]; then
  DB_HOST=$(env_value APP_DATABASE_URL | python3 -c 'import sys,urllib.parse;print(urllib.parse.urlsplit(sys.stdin.read().strip()).hostname or "")')
  if nc -z -w 5 "$DB_HOST" 5432 2>/dev/null; then ok "RDS reachable"
  else die "cannot reach the RDS database on port 5432. Fix the security groups (RUNBOOK B1), then run this again."; fi
fi

# ---------- 5. helper command ----------
say "5/9 Installing the 'legacy-viewer' command"
install -m 755 "$APP_DIR/deploy/legacy-viewer" /usr/local/bin/legacy-viewer
sed -i "s|^APP_DIR=.*|APP_DIR=\"$APP_DIR\"|" /usr/local/bin/legacy-viewer
ok "try:  legacy-viewer help"

# ---------- 6. build ----------
say "6/9 Building the image (first time takes a few minutes)"
lv build
ok "image legacy-viewer:latest built"

# ---------- 7. database tables ----------
say "7/9 Creating / updating the app's tables"
if [[ $DB_MODE == local ]]; then
  lv up -d postgres
  for _ in $(seq 1 30); do
    [[ "$(docker inspect -f '{{.State.Health.Status}}' "$(lv ps -q postgres)" 2>/dev/null)" == healthy ]] && break
    sleep 2
  done
fi
lv --profile tools run --rm -T migrate
ok "migrations applied"

# ---------- 8. archive checks + patient links ----------
say "8/9 Checking the archive login (read-only) and linking EMR <-> PM patients"
lv --profile tools run --rm -T cli dbcheck || die "dbcheck failed (message above). Usually the SQL login or password."
lv --profile tools run --rm -T cli build-crosswalk || die "build-crosswalk failed (message above)."

# ---------- 9. start ----------
say "9/9 Starting the app"
lv up -d app
for _ in $(seq 1 45); do curl -fs -m 3 http://127.0.0.1:8000/healthz >/dev/null && break; sleep 2; done
if ! curl -fs -m 3 http://127.0.0.1:8000/healthz >/dev/null; then
  lv logs --tail 40 app || true
  die "the app did not start. The log above names the setting to fix (RUNBOOK Part D table)."
fi
ok "healthz: $(curl -s http://127.0.0.1:8000/healthz)"
echo "    readyz: $(curl -s -m 30 http://127.0.0.1:8000/readyz)"

if yes_no "Create a staff sign-in account now?" Y; then
  while true; do
    ask U_EMAIL "Email" ""; ask U_NAME "Full name" ""
    lv --profile tools run --rm cli create-user --email "$U_EMAIL" --name "$U_NAME" || warn "not created (see above)"
    yes_no "Create another?" N || break
  done
fi

trap - ERR
cat <<EOF

$(printf '\033[1;32m')Done.$(printf '\033[0m') The app is running on this server at port 8000 and restarts automatically after a reboot.

  Next:
  - HTTPS: point the load balancer target group at this server, port 8000 (RUNBOOK B6).
    Staff open https://$( (env_value ALLOWED_HOSTS) | cut -d, -f1 ).
  - Test before the load balancer exists (from your laptop, AWS CLI + Session Manager plugin):
      aws ssm start-session --target <instance-id> --document-name AWS-StartPortForwardingSession \\
          --parameters portNumber=8000,localPortNumber=8000
    then open http://localhost:8000
  - Everyday commands:  legacy-viewer help
  - Sign out and back in once so your user can run docker without sudo (the helper uses sudo anyway).
EOF
