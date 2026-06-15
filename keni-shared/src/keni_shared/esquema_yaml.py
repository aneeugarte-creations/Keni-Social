"""Versionado de esquema de los YAML del monorepo (#125): `version` por fichero.

`version: <int>` como clave top-level DENTRO de cada YAML; upgrade PEREZOSO en lectura
via un registro de migraciones por tipo, reescrito solo al siguiente guardado.

USO (cada modulo de dominio que (de)serializa YAML):
  - lector:  `datos = migrar(tipo, yaml.safe_load(texto))` tras cargar.
  - escritor: `yaml.dump(sellar(tipo, datos))` antes de volcar.

ANADIR UNA MIGRACION (cuando cambie la forma de un tipo, p.ej. de la version N a N+1):
  1. Subir `VERSIONES[tipo]` a N+1.
  2. Anadir a `MIGRACIONES[tipo]` una funcion `dict -> dict` que transforma de la version
     N a la N+1, en la posicion N-1 (la lista[0] sube 1->2, la lista[1] sube 2->3, ...).
     La 0->1 es siempre identidad (solo estampa la version), por eso NO se registra.
  3. La migracion recibe un dict ya copiado; debe devolver el dict transformado.

Capa MAS BAJA (en `keni_shared`): sin dependencias de keni-metricas ni de la consola,
para que ambos paquetes importen de la misma fuente.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

# Version de esquema ACTUAL por tipo de entidad. Subir aqui al cambiar la forma de
# un tipo (y registrar la migracion correspondiente en `MIGRACIONES`).
VERSIONES: dict[str, int] = {
    "publicacion": 1,
    "plantilla": 1,
    "fuente_rss": 1,
    "grupo_hashtags": 1,
    "historial_prompt": 1,
    "marca": 1,
    "franjas": 1,
    "rss_vistos": 1,
    "run": 1,
    "agente": 1,
    "generacion": 1,
    "prompt": 1,
}

# Registro de migraciones por tipo. `MIGRACIONES[tipo][i]` sube de la version `i+1`
# a la `i+2` (la 0->1 es identidad implicita: solo estampar). Hoy vacio: la version 1
# es la forma actual, no hay nada que transformar.
MIGRACIONES: dict[str, list[Callable[[dict[str, Any]], dict[str, Any]]]] = {
    tipo: [] for tipo in VERSIONES
}


def _version_objetivo(tipo: str) -> int:
    """Version de esquema actual de un `tipo`; lanza si el tipo es desconocido.

    Los sitios de llamada son INTERNOS (modulos de dominio que ya conocen su tipo),
    asi que un tipo no registrado es un bug de programacion: fallamos ruidosamente.
    """
    if tipo not in VERSIONES:
        raise KeyError(f"Tipo de esquema YAML desconocido: {tipo!r}")
    return VERSIONES[tipo]


def migrar(tipo: str, datos: dict[str, Any]) -> dict[str, Any]:
    """Sube `datos` a la version de esquema actual de `tipo`, aplicando migraciones.

    Lee `datos.get("version", 0)` (ausencia => 0) y aplica en orden las migraciones
    registradas para cada salto hasta `VERSIONES[tipo]`. El salto 0->1 es identidad
    (la version 1 es la forma actual): solo se estampa la version. Idempotente: un
    dict ya en la version actual se devuelve sin cambios salvo la version ya presente.
    Devuelve un dict NUEVO (no muta el de entrada). Lanza si `tipo` es desconocido.
    """
    objetivo = _version_objetivo(tipo)
    actual = datos.get("version")
    if not isinstance(actual, int) or isinstance(actual, bool):
        actual = 0
    resultado = deepcopy(datos)
    migraciones = MIGRACIONES.get(tipo, [])
    while actual < objetivo:
        # El salto de la version `actual` a `actual + 1` lo hace `migraciones[actual - 1]`
        # (la 1->2 es el indice 0, la 2->3 el indice 1, ...). El salto 0->1 es identidad
        # (no esta registrado): solo estampa la version.
        if actual >= 1 and actual - 1 < len(migraciones):
            resultado = migraciones[actual - 1](resultado)
        actual += 1
    resultado["version"] = objetivo
    return resultado


def sellar(tipo: str, datos: dict[str, Any]) -> dict[str, Any]:
    """Devuelve una COPIA de `datos` con `version` = version actual de `tipo`.

    Estampa la version como PRIMERA clave (orden de insercion = orden de diff, ya
    que los escritores usan `sort_keys=False`): asi el campo de control aparece
    arriba, separado del cuerpo editorial. Lanza si `tipo` es desconocido.
    """
    objetivo = _version_objetivo(tipo)
    # `version` primero, luego el resto del cuerpo (sin duplicar `version`).
    return {"version": objetivo, **{k: v for k, v in datos.items() if k != "version"}}
