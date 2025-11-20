#!/usr/bin/env bash
set -euo pipefail

cd /home/sammy/work/BAHATI/bahati_service
source venv/bin/activate

git fetch --all
git checkout main
git pull --ff-only

pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput

sudo systemctl restart bahati
echo "✅ deployed. quick check:"
curl -sSI http://127.0.0.1:8001/healthz | sed -n '1p'
