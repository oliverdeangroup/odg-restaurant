#!/bin/bash
# Update ODG-RESTAURANT on the server from GitHub. Run as the cPanel user:
#   cd ~/odg-restaurant && ./deploy.sh
# Your data (database, uploads in DATA_DIR, .env) is never touched.
set -euo pipefail
cd "$(dirname "$0")"

echo "→ Backup of all data"
.venv/bin/python manage.py shell -c "from core.updater import backup; print(*backup('deploy'))"

echo "→ Getting the latest code"
git fetch --quiet origin
git reset --hard origin/main

echo "→ Python packages"
.venv/bin/pip install --quiet -r requirements.txt

echo "→ Database upgrade (adds new tables/fields, keeps all data)"
.venv/bin/python manage.py migrate --noinput

echo "→ Demo restaurant (rebuilt so it matches the new version)"
.venv/bin/python manage.py demo_build || echo "   (demo build failed — the real restaurant is not affected)"

echo "→ Static files"
.venv/bin/python manage.py collectstatic --noinput --verbosity 0

echo "→ Reloading the app"
mkdir -p run
if [ -f run/gunicorn.pid ]; then
  kill -HUP "$(cat run/gunicorn.pid)"
else
  echo "   Gunicorn is not running. Ask root to run: systemctl start odg-restaurant"
fi
echo "✓ ODG-RESTAURANT $(cat VERSION) is live."
