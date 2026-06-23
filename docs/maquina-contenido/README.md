# Máquina de contenido — especificaciones

Specs de DEV de los motores que alimentan el tablero de contenido. Solo quedan los docs que el
código sigue citando como contrato; los demás (ingesta, agrupar+scoring, calidad del feed,
cobertura, fuentes, video-formato) se retiraron porque la fuente de verdad es el propio código
(docstrings de los módulos), no prosa que se desincroniza.

| # | Doc | Qué cubre | Código principal |
|---|-----|-----------|------------------|
| 01 | [insumos-del-dia](01-insumos-del-dia.md) | Cajones del día: captura manual de insumos | `api/insumos.py`, `dominio/recibir_parse.py` |
| 08 | [video-engine](08-video-engine.md) | Motor de edición de video (esquema/contrato del seam) | `motores/estudio_video/`, `motores/transcripcion/`, `api/video.py` |

**Dónde vive lo retirado (la verdad está en el código):**
- **Agrupar + scoring:** docstring de `dominio/agrupar/scoring.py` (modelo `mérito × confianza`,
  señales, perfiles por marca) y `dominio/agrupar/corroboracion.py`.
- **Umbral de auto-producción + calidad del feed:** `noticias_umbral.py`,
  `dominio/agrupar/promocion.py`, `dominio/ingesta.py` (filtro de entrada).
- **Motor de ingesta y fuentes:** `recolectar_daemon/`, `dominio/fuentes_presets.py`,
  `dominio/traducir.py`.
