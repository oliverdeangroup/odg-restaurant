# Gunicorn settings for ODG-RESTAURANT on the cPanel server.
# Listens only inside the server; LiteSpeed forwards the website to it.
# Port 8001 is used by ODG-SCHOOL on the same server.
import multiprocessing
from pathlib import Path

base = Path(__file__).resolve().parent.parent

bind = "127.0.0.1:8002"
# The live POS screens poll every few seconds: threads keep that cheap.
workers = min(3, multiprocessing.cpu_count() + 1)
worker_class = "gthread"
threads = 6
timeout = 120
graceful_timeout = 30
keepalive = 5
pidfile = str(base / "run" / "gunicorn.pid")
accesslog = str(base / "run" / "access.log")
errorlog = str(base / "run" / "error.log")
# Don't log every poll of the live screens
access_log_format = '%(h)s %(t)s "%(r)s" %(s)s %(b)s %(M)sms'
forwarded_allow_ips = "127.0.0.1"
# NGINX + LiteSpeed both add scheme headers; trust only the one Django uses,
# otherwise Gunicorn rejects plain-http requests ("Contradictory scheme headers").
secure_scheme_headers = {"X-FORWARDED-PROTO": "https"}
limit_request_line = 8190
