"""Runs de un agente (`runs/<id>.yaml`): persistencia, indice y monitorizacion.

  - Persistencia: `_dir_runs`, `_metricas_run`, `_parsear_run`, `guardar_run`,
    `actualizar_run`, `listar_runs`, `obtener_run`.
  - Indice de runs (denormaliza coste/tokens; lo usa el monitor): `_id_indice_run`,
    `_entrada_indice_run`, `_indexar_run`, `reindexar_runs`.
  - Monitor (runs globales + agregados): `_runs_en_disco`, `_asegurar_indice_runs`,
    `listar_runs_globales`, `contar_runs_globales`, `_sumar_metrica`, `agregados_runs`.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from .. import indice
from ._comun import (
    _DIR_RUNS,
    _escribir_yaml_atomico,
    _leer_yaml,
    nuevo_run_id,
)
from ._genericos import (
    _agentes_para_runs,
    _mapa_nombres_agentes,
    carpeta_agente,
)

__all__ = [
    "_dir_runs",
    "_metricas_run",
    "_parsear_run",
    "guardar_run",
    "_id_indice_run",
    "_entrada_indice_run",
    "_indexar_run",
    "reindexar_runs",
    "actualizar_run",
    "listar_runs",
    "obtener_run",
    "_runs_en_disco",
    "_asegurar_indice_runs",
    "listar_runs_globales",
    "contar_runs_globales",
    "_sumar_metrica",
    "agregados_runs",
]


# --------------------------------------------------------------------------- #
# Runs (ejecuciones de un prompt): `runs/<id>.yaml`                            #
# --------------------------------------------------------------------------- #

# Serializa las MUTACIONES del indice de runs entre hilos del proceso (escrituras del
# sondeo en vivo y reconstrucciones del monitor conviven). Reentrante: `actualizar_run`
# lo toma para su read-modify-write y dentro llama a `guardar_run` -> `_indexar_run`, que
# vuelve a tomarlo. Sin el, `reindexar_runs` (snapshot+swap del tipo "run") puede borrar un
# `guardar_run` que cae entre el `glob` del disco y el `reemplazar_tipo`.
_LOCK_RUNS = threading.RLock()


def _dir_runs(marca_id: str) -> Path:
    """Sub-carpeta `runs/` del agente (creada si falta)."""
    carpeta = carpeta_agente(marca_id) / _DIR_RUNS
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _metricas_run(datos: dict[str, Any]) -> dict[str, Any] | None:
    """Normaliza el campo `metricas` de un run: dict no vacio o None."""
    metricas = datos.get("metricas")
    if not isinstance(metricas, dict) or not metricas:
        return None
    return metricas


def _parsear_run(datos: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Reconstruye el dict publico de un run (id implicito = nombre de fichero)."""
    return {
        "id": run_id,
        "prompt": datos.get("prompt", "") or "",
        "modo": datos.get("modo", "") or "",
        "estado": datos.get("estado", "") or "",
        "salida": datos.get("salida", "") or "",
        "motivo": datos.get("motivo", "") or "",
        "fecha_inicio": datos.get("fecha_inicio", "") or "",
        "fecha_fin": datos.get("fecha_fin", "") or "",
        "metricas": _metricas_run(datos),
    }


def guardar_run(marca_id: str, run: dict[str, Any]) -> dict[str, Any]:
    """Escribe `runs/<id>.yaml` (atomico), INDEXA el run y lo devuelve con su `id`.

    Si el run no trae `id`, se genera uno. El cuerpo YAML no repite el `id` (es
    implicito por el nombre de fichero). `metricas` (tokens/turnos/coste/duracion/
    modelo) se incluye solo si viene presente (None => ausente en el YAML). `motivo`
    (p.ej. "timeout") se incluye solo si trae valor.

    Tras escribir, hace UPSERT en el indice de runs (denormalizando coste/tokens/
    agente/fecha) para que el monitor agregue sin escanear cuerpos. El upsert por
    (tipo, id) es idempotente: el SONDEO en vivo llama a `actualizar_run` muchas veces
    y siempre refleja el ultimo estado (metricas parciales -> finales). Best-effort: si
    el indice falla, NO rompe la escritura del run (el agregado cae a disco+reindex).
    """
    run_id = run.get("id") or nuevo_run_id()
    cuerpo: dict[str, Any] = {
        "prompt": run.get("prompt", "") or "",
        "modo": run.get("modo", "") or "",
        "estado": run.get("estado", "") or "",
        "salida": run.get("salida", "") or "",
        "fecha_inicio": run.get("fecha_inicio", "") or "",
        "fecha_fin": run.get("fecha_fin", "") or "",
    }
    motivo = run.get("motivo", "") or ""
    if motivo:
        cuerpo["motivo"] = motivo
    metricas = _metricas_run(run)
    if metricas is not None:
        cuerpo["metricas"] = metricas
    ruta = _dir_runs(marca_id) / f"{run_id}.yaml"
    _escribir_yaml_atomico(ruta, cuerpo, tipo="run")
    _indexar_run(marca_id, run_id, ruta, cuerpo)
    return {"id": run_id, "motivo": motivo, **cuerpo, "metricas": metricas}


# --------------------------------------------------------------------------- #
# Indice de runs (denormaliza coste/tokens; lo usa el monitor para agregar)    #
# --------------------------------------------------------------------------- #


def _id_indice_run(agente_id: str, run_id: str) -> str:
    """Clave de indice de un run: `<agente>:<run_id>` (unica bajo tipo='run')."""
    return f"{agente_id}:{run_id}"


def _entrada_indice_run(
    agente_id: str, run_id: str, ruta: Path, cuerpo: dict[str, Any]
) -> dict[str, Any]:
    """Construye la fila de indice de un run (denormaliza coste/tokens/agente/fecha)."""
    try:
        mtime = ruta.stat().st_mtime
    except OSError:
        mtime = 0.0
    metricas = _metricas_run(cuerpo)
    fecha_inicio = cuerpo.get("fecha_inicio", "") or ""
    return {
        "id": _id_indice_run(agente_id, run_id),
        "tipo": "run",
        "marca": agente_id,
        "agente": agente_id,
        "ruta": str(ruta),
        "mtime": mtime,
        "coste_usd": _sumar_metrica(metricas, "total_cost_usd"),
        "tokens_in": int(_sumar_metrica(metricas, "tokens_in")),
        "tokens_out": int(_sumar_metrica(metricas, "tokens_out")),
        "fecha_inicio": fecha_inicio,
        "dia": fecha_inicio[:10],
    }


def _indexar_run(agente_id: str, run_id: str, ruta: Path, cuerpo: dict[str, Any]) -> None:
    """UPSERT de un run en el indice (best-effort: el error nunca rompe la escritura)."""
    try:
        with _LOCK_RUNS:
            indice.upsert(_entrada_indice_run(agente_id, run_id, ruta, cuerpo))
    except Exception:  # noqa: BLE001 -- el indice es regenerable; degradar a disco+reindex
        pass


def reindexar_runs() -> None:
    """Reconstruye en el indice TODOS los runs leyendo el disco (regenerable).

    Recorre los `runs/<id>.yaml` de cada agente (marca o generico) y reemplaza el
    tipo `run` en el indice de una tacada. Es el backfill (mirror de
    `ficheros._reindexar_tipo`) y el camino de recuperacion ante un indice vacio/stale.

    El escaneo del disco Y el `reemplazar_tipo` corren bajo `_LOCK_RUNS` para que un
    `guardar_run` concurrente no caiga en la ventana entre snapshot y swap (su upsert
    espera al lock y se reaplica tras el swap, en vez de quedar fuera y borrarse).
    """
    with _LOCK_RUNS:
        entradas: list[dict[str, Any]] = []
        for agente_id, _nombre in _agentes_para_runs():
            carpeta = carpeta_agente(agente_id, crear=False) / _DIR_RUNS
            if not carpeta.is_dir():
                continue
            for ruta in carpeta.glob("*.yaml"):
                if ruta.name.startswith(".tmp-"):
                    continue
                datos = _leer_yaml(ruta, tipo="run")
                if datos is None:
                    continue
                entradas.append(_entrada_indice_run(agente_id, ruta.stem, ruta, datos))
        indice.reemplazar_tipo("run", entradas)


def actualizar_run(marca_id: str, run_id: str, cambios: dict[str, Any]) -> dict[str, Any]:
    """Mezcla `cambios` sobre el run `runs/<id>.yaml` existente y lo reescribe ATOMICO.

    Lee el YAML actual (si falta, parte de un cuerpo vacio), aplica los `cambios` por
    clave (sobre `prompt/modo/estado/salida/motivo/fecha_inicio/fecha_fin/metricas`) y
    reescribe via `guardar_run` (que ya escribe de forma atomica). Es la primitiva del
    SONDEO en vivo: el hilo lector la usa para avanzar `estado`/`metricas` parciales y,
    al final, fijar el estado terminal. `metricas` se reemplaza por completo cuando
    viene en `cambios` (parciales o finales); las claves ausentes se conservan.

    El read-modify-write (leer + fusionar + reescribir) corre bajo `_LOCK_RUNS` para que
    dos actualizaciones concurrentes del MISMO run no se pisen (last-write-wins).
    """
    with _LOCK_RUNS:
        ruta = _dir_runs(marca_id) / f"{run_id}.yaml"
        actual = _leer_yaml(ruta, tipo="run") or {}
        fusion: dict[str, Any] = {"id": run_id, **actual, **cambios}
        return guardar_run(marca_id, fusion)


def listar_runs(marca_id: str) -> list[dict[str, Any]]:
    """Runs del agente, recientes primero (por `fecha_inicio` desc, luego id)."""
    carpeta = carpeta_agente(marca_id, crear=False) / _DIR_RUNS
    if not carpeta.is_dir():
        return []
    runs: list[dict[str, Any]] = []
    for ruta in carpeta.glob("*.yaml"):
        if ruta.name.startswith(".tmp-"):
            continue
        datos = _leer_yaml(ruta, tipo="run")
        if datos is None:
            continue
        runs.append(_parsear_run(datos, ruta.stem))
    runs.sort(key=lambda r: (r["fecha_inicio"], r["id"]), reverse=True)
    return runs


def obtener_run(marca_id: str, run_id: str) -> dict[str, Any] | None:
    """Un run del agente por id (None si no existe o su YAML no valida).

    El `run_id` se restringe al `stem` para impedir traversal por la ruta.
    """
    if not isinstance(run_id, str) or not run_id:
        return None
    # Solo el nombre base: descarta cualquier separador/`..` del id.
    seguro = Path(run_id).name
    if seguro != run_id or seguro in (".", ".."):
        return None
    ruta = (carpeta_agente(marca_id, crear=False) / _DIR_RUNS / f"{seguro}.yaml").resolve()
    base = (carpeta_agente(marca_id, crear=False) / _DIR_RUNS).resolve()
    if ruta.parent != base or not ruta.is_file():
        return None
    datos = _leer_yaml(ruta, tipo="run")
    if datos is None:
        return None
    return _parsear_run(datos, seguro)


# --------------------------------------------------------------------------- #
# Monitorizacion: runs de TODOS los agentes + agregados                       #
# --------------------------------------------------------------------------- #


def _runs_en_disco() -> bool:
    """True si HAY algun `runs/<id>.yaml` en disco (para decidir reindex perezoso)."""
    for agente_id, _nombre in _agentes_para_runs():
        carpeta = carpeta_agente(agente_id, crear=False) / _DIR_RUNS
        if carpeta.is_dir() and any(
            p.name for p in carpeta.glob("*.yaml") if not p.name.startswith(".tmp-")
        ):
            return True
    return False


def _asegurar_indice_runs() -> None:
    """Reindexa los runs si el indice esta vacio pero hay runs en disco (stale/borrado).

    Garantiza que el monitor (listado paginado + agregados) NUNCA sub-cuente por un
    indice ausente: si `contar('run')==0` y hay ficheros, se reconstruye desde disco.
    """
    if indice.contar("run", None) == 0 and _runs_en_disco():
        reindexar_runs()


def listar_runs_globales(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    """Runs de TODOS los agentes (marcas + genericos), recientes primero.

    Cada run incluye su agente (`agente`/`agente_nombre`) ademas de sus campos. No
    materializa carpetas que no existan. Orden: por `fecha_inicio` desc, luego id.

    Pagina via el INDICE de runs (`LIMIT/OFFSET`): solo se lee el cuerpo YAML de la
    pagina pedida, no de todos los runs. `limite=None` (def) devuelve todos
    (retrocompat). Si el indice esta vacio pero hay runs en disco, se reconstruye antes.
    """
    _asegurar_indice_runs()
    nombres = _mapa_nombres_agentes()
    todos: list[dict[str, Any]] = []
    for entrada in indice.listar("run", limite=limite, desplazamiento=desplazamiento):
        ruta = Path(entrada["ruta"])
        datos = _leer_yaml(ruta, tipo="run")
        if datos is None:
            continue  # YAML borrado/corrupto: se omite (degradado)
        agente_id = entrada["agente"]
        run = _parsear_run(datos, ruta.stem)
        todos.append(
            {**run, "agente": agente_id, "agente_nombre": nombres.get(agente_id, agente_id)}
        )
    return todos


def contar_runs_globales() -> int:
    """Total de runs indexados de TODOS los agentes (para el `total` de paginacion)."""
    _asegurar_indice_runs()
    return indice.contar("run", None)


def _sumar_metrica(metricas: dict[str, Any] | None, clave: str) -> float:
    """Devuelve `metricas[clave]` como numero (0 si ausente/no numerico/None)."""
    if not isinstance(metricas, dict):
        return 0.0
    valor = metricas.get(clave)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return 0.0
    return float(valor)


def agregados_runs() -> dict[str, Any]:
    """Totales de coste/tokens/runs: global, por agente y por dia (via SQL en el indice).

    - `total`: `{coste_usd, tokens, runs}` sumando TODOS los runs.
    - `por_agente`: una entrada por agente con runs (`{agente, agente_nombre, coste_usd,
      tokens, runs}`), de mayor a menor coste.
    - `por_dia`: una entrada por fecha (YYYY-MM-DD del `fecha_inicio`), recientes primero.
    Tokens = tokens_in + tokens_out de cada run con metricas.

    Agrega con SUM/GROUP BY sobre la denormalizacion del indice (sin escanear cuerpos).
    El `agente_nombre` (no denormalizado: cambia al renombrar) se resuelve aqui. Cae a
    disco+reindex si el indice esta vacio/stale para no sub-contar. Suma, orden y redondeo
    a 6 decimales coinciden con un full-scan en disco.
    """
    _asegurar_indice_runs()
    agg = indice.agregados_runs()
    nombres = _mapa_nombres_agentes()
    return {
        "total": {
            "coste_usd": round(agg["total"]["coste_usd"], 6),
            "tokens": agg["total"]["tokens"],
            "runs": agg["total"]["runs"],
        },
        "por_agente": [
            {
                "agente": e["agente"],
                "agente_nombre": nombres.get(e["agente"], e["agente"]),
                "coste_usd": round(e["coste_usd"], 6),
                "tokens": e["tokens"],
                "runs": e["runs"],
            }
            for e in agg["por_agente"]
        ],
        "por_dia": [
            {"dia": e["dia"], "coste_usd": round(e["coste_usd"], 6), "tokens": e["tokens"],
             "runs": e["runs"]}
            for e in agg["por_dia"]
        ],
    }
