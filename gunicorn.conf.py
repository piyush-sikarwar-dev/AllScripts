"""Gunicorn settings for production (Dockerfile CMD); tune with environment variables.

- Access logs are OFF: they would record full URLs, and search query strings can hold patient
  names. The app writes its own request log (route template, status, duration, user id only).
- Client IPs are taken from X-Forwarded-For only when the request comes from FORWARDED_ALLOW_IPS
  (the load balancer's addresses), so audit rows and the sign-in throttle see real addresses.
"""

import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = int(os.getenv("WEB_CONCURRENCY", "3"))
worker_class = "uvicorn_worker.UvicornWorker"
timeout = int(os.getenv("GUNICORN_TIMEOUT", "300"))  # large PDF releases can take minutes
graceful_timeout = 30
keepalive = 310  # longer than the ALB idle timeout (300 s) so the ALB never reuses a closed socket
forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1")
max_requests = 2000  # recycle workers now and then (releases memory from big PDF exports)
max_requests_jitter = 200

accesslog = None
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")

logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "formatter": "plain",
            "stream": "ext://sys.stdout",
        }
    },
    "root": {"level": "INFO", "handlers": ["stdout"]},
    "loggers": {
        "uvicorn.access": {"level": "WARNING", "propagate": False, "handlers": []},
        "gunicorn.access": {"level": "WARNING", "propagate": False, "handlers": []},
    },
}
