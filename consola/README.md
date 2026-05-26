# keni-consola

**Consola Keni**: capa de gestion web **LOCAL** para equipo NO tecnico. Una app
con pestañas (Proyectos, Métricas, Generar copy, Tareas, Nueva carpeta,
Configuración, Estado) que envuelve a Claude Code y al servidor de métricas.

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

## Arranque

```
keni-consola
```

(o el equivalente `python -m keni_consola`). Abre `http://127.0.0.1:8765`. El
puerto se cambia con `KENI_CONSOLA_PORT`, p. ej. `KENI_CONSOLA_PORT=9000 keni-consola`.

Guía de usuario completa: [`../docs/consola.md`](../docs/consola.md).
