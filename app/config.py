"""Application settings, read from environment variables or `.env`."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Source SQL Server: one instance, one read-only login, one engine per database.
    sql_host: str = ""
    sql_port: int = 1433
    sql_user: str = ""
    sql_password: SecretStr = SecretStr("")
    sql_driver: str = "ODBC Driver 18 for SQL Server"
    sql_trust_server_certificate: bool = False
    sql_login_timeout: int = 15
    sql_query_timeout: int = 30
    emr_database: str = "EMR"
    ntier_database: str = "Ntier_0010060"
    dmz_database: str = "DMZ"

    # App database (PostgreSQL).
    app_database_url: str = "postgresql+psycopg://legacy:legacy@localhost:5432/legacy_viewer"

    # Sessions / cookies.
    session_secret: SecretStr = SecretStr("")
    cookie_secure: bool = True

    # Clinic.
    clinic_name: str = "Example Clinic"
    clinic_tz: str = "America/New_York"

    # Scanned documents. Unset SCAN_ROOT = metadata only + warning banner.
    scan_root: str | None = None
    scan_unc_prefix: str = r"\\amhs-db1\hmscan"
    scan_store: str = "file"  # "file" (SCAN_ROOT mount) | "s3" (stub)
    # Pre-2010 (DMZ) scans live on a different share; unset = metadata only + warning banner.
    legacy_scan_root: str | None = None
    legacy_scan_unc_prefix: str = r"\\w10060-1\images"

    # Per-patient source-data cache (memory only; the archive never changes). 0 disables it.
    source_cache_ttl_seconds: int = 600
    source_cache_max_items: int = 500

    # PDF export: folder with the Pango/GTK DLLs on Windows dev machines (e.g. MSYS2 ucrt64in).
    # Not needed in Docker / Linux.
    weasyprint_dll_directories: str = ""

    # Security (docs/SECURITY.md). APP_ENV=production turns on fail-closed start-up checks.
    app_env: str = "development"
    allowed_hosts: str = ""  # comma-separated host names; empty = any (development only)
    allow_writable_sql_login: bool = False  # temporary override; never leave on
    login_ip_max_failures: int = 10
    login_ip_window_minutes: int = 15

    # Features.
    feature_legacy_dmz: bool = False
    use_fake_data: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
