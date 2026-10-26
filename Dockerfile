# Legacy DEC & LR Records: production image.
# - Python 3.12 on Debian 12, Microsoft ODBC Driver 18 for SQL Server, WeasyPrint system libraries.
# - Dependencies installed from uv.lock (exact versions), no dev tools.
# - Runs as a non-root user; works with a read-only root filesystem (writes only under /tmp).
# - No secrets in the image: all settings come from the environment at run time.

FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    XDG_CACHE_HOME=/tmp/cache \
    HOME=/tmp

# System packages: ODBC driver (Microsoft repository, signed), WeasyPrint (Pango, HarfBuzz,
# fontconfig) and a fallback font. Package lists are removed afterwards to keep the image small.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg; \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
      | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg; \
    curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list \
      -o /etc/apt/sources.list.d/mssql-release.list; \
    apt-get update; \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
      msodbcsql18 unixodbc \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 libfontconfig1 \
      fonts-dejavu-core; \
    apt-get purge -y --auto-remove curl gnupg; \
    rm -rf /var/lib/apt/lists/*

# uv (pinned) only to install the locked dependencies.
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first (cached layer while only the code changes).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project && rm /usr/local/bin/uv

# Application code. tests/fakes is included only for staging's fake-data mode (no PHI).
COPY app ./app
COPY config ./config
COPY alembic ./alembic
COPY alembic.ini cli.py gunicorn.conf.py ./
COPY tests/__init__.py ./tests/__init__.py
COPY tests/fakes ./tests/fakes

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser \
    && python -m compileall -q /app/app
USER 10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)" || exit 1

CMD ["gunicorn", "app.main:app", "-c", "gunicorn.conf.py"]
