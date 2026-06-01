# keni-consola

**Consola Keni**: capa de gestion web **LOCAL** para equipo NO tecnico. Una app
con sidebar (páginas de trabajo diario + ajustes) que envuelve a Claude Code y al
servidor de métricas. El catálogo de páginas vivo está en el sidebar de la app
(`frontend/src/components/layout/navegacion.ts` / `router.tsx`); no se enumera aquí
para que no se desfase.

Corre **solo en `127.0.0.1`** (nunca expuesta a la red) y arranca con datos de
muestra. Es una capa de gestión: el motor que hace el trabajo sigue siendo
Claude Code y `keni-metricas`.

## Instalación (local, editable)

La consola **depende de `keni-shared`** (capa más baja: catálogo de marca,
límites de plataforma, `io_atomico`, `engagement_pct`) **y de `keni-metricas`**.
Instala primero las dependencias y luego la consola (las rutas son las del
monorepo, así pip resuelve los paquetes locales):

```
pip install -e ./keni-shared
pip install -e ./mcp-metricas
pip install -e ./consola          # o ./consola[dev] para los tests
```

Con `uv` también puedes instalarla como herramienta desde la ruta del paquete:

```
uv tool install ./consola
# o ejecutarla sin instalar:
uvx --from ./consola keni-consola
```

## Postgres (obligatorio, ADR 0004)

La operacional (tareas, comercial, rota, usuarios, sesiones, cola de jobs) vive en
**Postgres**: ya no hay backend SQLite. Antes de arrancar la consola necesitas un
Postgres corriendo y `DATABASE_URL` apuntandole.

En desarrollo NO se usa Postgres local: la ejecución y validación se hacen en el
server (CI Woodpecker / hosted `social.kenitech.io`). Si aun así necesitas correr la
consola en tu máquina, provee tu propio Postgres y exporta su URL, p. ej.:

```
export DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/keni_social
```

Tú gestionas ese Postgres (instalación, arranque, datos): el monorepo ya no trae un
compose de conveniencia para dev.

Si arrancas la consola SIN `DATABASE_URL`, el back falla con un mensaje claro. La
privacidad del perfil local se preserva (un Postgres local no expone datos fuera de
la maquina); lo que se pierde es el "cero-config".

## Arranque

```
keni-consola
```

(o el equivalente `python -m keni_consola`). Abre `http://127.0.0.1:8765`. El
puerto se cambia con `KENI_CONSOLA_PORT`, p. ej. `KENI_CONSOLA_PORT=9000 keni-consola`.

## Autenticación (token de sesión, #134)

El bind a `127.0.0.1` **no es control de acceso**: cualquier web abierta en el
navegador del operador podría hacer POST a la API local. Por eso la API (`/api/...`)
exige un **token de sesión** y verifica el `Origin`/`Referer` en las mutaciones
(POST/PUT/PATCH/DELETE) como protección **CSRF**.

- Fíjalo con `KENI_CONSOLA_TOKEN=<tu-token> keni-consola` (recomendado: estable).
- Si no lo defines, se **genera uno al arrancar** y se imprime en el log/terminal con
  la URL `http://127.0.0.1:8765/?token=…`. Ábrela una vez: el servidor siembra la
  cookie del token y el SPA autentica solo a partir de ahí (el modo local sigue
  usable sin configurar nada).
- El SPA y sus estáticos se sirven sin token (hay que poder cargar la página); solo
  `/api/...` exige token.

Esto es una barrera mínima local; la auth multiusuario real es otra pieza (#130).

Guía de usuario completa: [`../docs/consola.md`](../docs/consola.md).
