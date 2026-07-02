"""Daemon del MOTOR DE RECOLECCIÓN PERSISTENTE (Ola A).

PROBLEMA QUE RESUELVE
=====================
El Radar v1 descargaba feeds EN VIVO por petición y con tope (30 items/feed): cobertura a
medias. Este daemon invierte el modelo: SIEMPRE activo, sondea en background los feeds
VENCIDOS (cadencia por feed/categoría), PERSISTE cada artículo en `noticias_items` (archivo a
nivel de artículo, dedup por (fuente_id, clave)) y programa el próximo sondeo. La UI/Plan leen
del store; nadie golpea la red por request.

SEGURO POR DISEÑO
=================
  - GATEADO EN VIVO: solo sondea con `KENI_PIPELINE_RECOLECTAR=1` (def OFF para CI/tests; ON en prod).
    El hilo arranca SIEMPRE y comprueba el flag cada ciclo (toggle en caliente).
  - SOLO LECTURA EXTERNA: descarga feeds RSS públicos (guard SSRF de `http_feed`) y persiste.
    No publica, no genera, no llama a `claude -p`.
  - ESCALABLE: tope de feeds por barrido (`KENI_INGESTA_BATCH`), descargas en paralelo
    ACOTADAS (`KENI_INGESTA_WORKERS`) y cadencia por feed -> escala a cientos de feeds.
  - BACKOFF: un feed que falla incrementa `errores_seguidos` y se pausa
    `intervalo * 2^errores` (con tope). En éxito se resetea.
  - SINGLE-FLIGHT cross-proceso (advisory lock): un segundo barrido solapado (deploy, varios
    daemons) no duplica trabajo; sale sin hacer nada.
  - BEST-EFFORT: ningún feed que falle aborta el barrido; se loguea y se sigue.

La lógica de planificación (`planificar_proximo`) es PURA: decide el `proximo_sondeo`,
`errores_seguidos` y `pausado_hasta` a partir del resultado, sin reloj ni BD (testeable).

ESTRUCTURA (refactor de pura reubicación, sin cambio de comportamiento)
=======================================================================
El módulo se troceó en un paquete por áreas; este `__init__` es el FACADE que preserva la
superficie pública (mismo nombre de import `keni_consola.recolectar_daemon`):
  - `_comun`: estado/throttles compartidos y helpers (relevancia, rendimiento, actividad IA,
    clasificación de marca, fusionar un grupo).
  - `pasos/`: cada `paso_*` independiente (agrupar, rescore, fusionar_semantica,
    traducir, caducidad, agencias).
  - `_bucle`: orquestador (`ejecutar_barrido`), planificación pura y arranque del hilo
    (`iniciar_ingesta`).
"""

from __future__ import annotations

from keni_shared import marcas  # noqa: F401  (re-export de superficie pública)

from .. import (  # noqa: F401  (re-export de superficie pública)
    agencias,
    config,
    daemon_util,
    db,
    generaciones,
    noticias_umbral,
    repos,
)
from ..dominio import (  # noqa: F401  (re-export de superficie pública)
    agrupar,
    fusionar_semantica,
    http_feed,
    ingesta,
    perfil_editorial,
    traducir,
)
from ..tiempo import ahora_iso, iso_utc  # noqa: F401  (re-export de superficie pública)

# Re-export de módulos hermanos/dominio para preservar `recolectar_daemon.<modulo>` (los tests y
# otros consumidores parchean p. ej. `recolectar_daemon.repos`, `.db`, `.config`, `.ingesta`,
# `.agencias`, `.fusionar_semantica`: deben seguir siendo el MISMO objeto-módulo).
from . import _comun  # noqa: F401  (expone `recolectar_daemon._comun`; carga el estado compartido)

# Orquestador y entrypoint (`daemons.py` hace `from .recolectar_daemon import iniciar_ingesta`).
from ._bucle import (  # noqa: F401
    _intervalo_feed,
    _particion_por_plan,
    _sondear_feed,
    ejecutar_barrido,
    iniciar_ingesta,
    planificar_proximo,
)

# Helpers/estado compartidos (parcheables sobre el facade: `_registrar_actividad_ia`,
# `_fusionar_grupo`).
from ._comun import (  # noqa: F401
    _fusionar_grupo,
    _log,
    _palabras_relevancia,
    _registrar_actividad_ia,
    _rendimiento_bonus,
    _rendimiento_top_lineas,
    ia_fondo_bloqueada,
)

# Pasos (parcheables sobre el facade: el orquestador los invoca vía `_pkg.paso_*`).
from .pasos.agencias import paso_agencias  # noqa: F401
from .pasos.agrupar import paso_agrupar  # noqa: F401
from .pasos.caducidad import paso_caducidad  # noqa: F401
from .pasos.etiquetas import paso_etiquetas  # noqa: F401
from .pasos.fusionar_semantica import paso_fusionar_semantica  # noqa: F401
from .pasos.rescore import paso_rescore  # noqa: F401
from .pasos.traducir import paso_traducir  # noqa: F401

__all__ = [
    "ejecutar_barrido",
    "iniciar_ingesta",
    "ia_fondo_bloqueada",
    "planificar_proximo",
    "paso_agencias",
    "paso_caducidad",
    "paso_agrupar",
    "paso_etiquetas",
    "paso_fusionar_semantica",
    "paso_rescore",
    "paso_traducir",
]
