# Máquina de contenido — especificaciones

Specs de los motores que alimentan el tablero de contenido (ingesta de noticias,
agrupar, verificar, video). Cada doc es autocontenido; léelos en orden para
entender la pipeline de "reutilizar lo que ya existe".

> **Modelo de máquina de contenido (Fase 1):** 1 master (`KENI_MAQUINA`) + 3 etapas, todas
> colgando del pipeline: «Crear noticias» (`KENI_PIPELINE_RECOLECTAR`, global), «Generar copy»
> (`KENI_PIPELINE_REDACTAR`) y «Generar arte» (`KENI_PIPELINE_ILUSTRAR`), estas dos con excepción por marca.
> Los daemons sueltos de auto-redactar / auto-ilustrar / auto-feed / breaking / auto-avance se
> retiraron; sus etapas viven dentro del pipeline (`pipeline_contenido.py`).

| # | Doc | Qué cubre | Código principal |
|---|-----|-----------|------------------|
| 01 | [insumos-del-dia](01-insumos-del-dia.md) | Cajones del día: captura manual de insumos | `api/insumos.py`, `dominio/insumos_parse.py` |
| 02 | [fuentes-externas](02-fuentes-externas.md) | Presets de fuentes + traducir idiomas | `dominio/fuentes_presets.py`, `dominio/traduccion.py` |
| 03 | [motor-ingesta](03-motor-ingesta.md) | Motor de ingesta persistente (núcleo de cobertura) | `ingesta_daemon.py`, `dominio/ingesta.py` |
| 05 | [cobertura-verificacion](05-cobertura-verificacion.md) | Monitor de cobertura + auto-verificación | `api/noticias.py` (`/salud`), `dominio/clustering.py` |
| 07 | [video-formato](07-video-formato.md) | Aceptar video como formato (no solo foto) | `api/media.py`, `media.py` |
| 08 | [video-engine](08-video-engine.md) | Motor de edición de video (toque RRSS) | `motores/estudio_video/`, `motores/transcripcion/`, `api/video.py` |

> **Nota de numeración:** los títulos internos conservan la etiqueta histórica "Ola N/A–G"
> con la que se escribieron (Ola 1, 4, A, B, D, E, F, G). El prefijo numérico es el orden de
> lectura; quedan huecos (04, 06) por specs retiradas. El **agrupar + scoring** (antiguo 04) y
> la **calidad del feed** (antiguo 06) ya no tienen doc en prosa: la fuente de verdad es el
> código — el docstring de `dominio/agrupar/scoring.py` (modelo `mérito × confianza`, señales,
> perfiles por marca) y `noticias_umbral.py` / `dominio/agrupar/promocion.py` (umbral). La
> antigua "Ola C" (ampliación de fuentes verificadas) se materializó en
> `dominio/fuentes_presets.py` sin doc propio.

**Feature relacionada sin spec aquí:** el endpoint MANUAL de breaking
(`api/breaking.py` + `dominio/breaking.py`) prepara borradores de breaking a demanda (lo usa
la página Cobertura). La detección automática de "breaking" de Agrupar
(`KENI_CLUSTER_BREAKING_*`) solo marca historias, sin daemon ni toggle.
