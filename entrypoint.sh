#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
python << 'PY'
import os, time
import psycopg2
url = os.environ.get("DATABASE_URL_SYNC", "postgresql+psycopg2://charclamp:charclamp@db:5432/charclamp")
raw = url.replace("postgresql+psycopg2://", "")
creds, hostpart = raw.split("@", 1)
user, password = creds.split(":", 1)
hostport, db = hostpart.split("/", 1)
host, port = (hostport.split(":", 1) + ["5432"])[:2]
for i in range(60):
    try:
        conn = psycopg2.connect(host=host, port=port, dbname=db, user=user, password=password)
        conn.close()
        print("PostgreSQL is ready.")
        break
    except Exception as e:
        print(f"Waiting... ({i+1}/60) {e}")
        time.sleep(2)
else:
    raise SystemExit("PostgreSQL not available")
PY

python << 'PY'
from charclamp.infra.db import sync_create_all
from charclamp.infra.seed import seed_demo

sync_create_all()
seed_demo()
print("migrate/seed done")
PY

exec uvicorn charclamp.main:app --host 0.0.0.0 --port 8000
