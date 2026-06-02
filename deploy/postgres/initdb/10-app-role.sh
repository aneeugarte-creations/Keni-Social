#!/bin/bash
# Crea el ROL DE APLICACION de minimo privilegio `keni_app` en el PRIMER arranque del
# cluster (cuando el data dir esta vacio: postgres solo ejecuta /docker-entrypoint-initdb.d
# en ese caso). El backend conecta como `keni_app` via DATABASE_URL, NUNCA como el
# bootstrap superuser `keni` (POSTGRES_USER). `keni_app` NO es superusuario: puede DML y
# crear/alterar su propio esquema (es dueno de las tablas que crea al arrancar la app),
# pero no puede ALTER SYSTEM, leer otras BD, COPY a ficheros del host, etc.
#
# En un cluster YA EXISTENTE este script NO corre (data dir no vacio); alli el rol se creo
# en su dia (migracion manual). Idempotente por si acaso (IF NOT EXISTS / ALTER).
set -euo pipefail

if [ -z "${APP_DB_PASSWORD:-}" ]; then
  echo "ERROR initdb: APP_DB_PASSWORD no definido; no se crea el rol keni_app." >&2
  exit 1
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'keni_app') THEN
    CREATE ROLE keni_app LOGIN PASSWORD '${APP_DB_PASSWORD}';
  ELSE
    ALTER ROLE keni_app LOGIN PASSWORD '${APP_DB_PASSWORD}';
  END IF;
END
\$\$;
GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO keni_app;
GRANT USAGE, CREATE ON SCHEMA public TO keni_app;
EOSQL

echo "initdb: rol keni_app (minimo privilegio) listo."
