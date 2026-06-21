"""Persistencia — rota: config/plantilla de franjas por marca (tabla `rota_config_franjas`)."""
from __future__ import annotations

import json
from typing import Any

from ..estados import NOMBRE_FRANJA_MANANA_DEFAULT, NOMBRE_FRANJA_TARDE_DEFAULT
from .._db_core._comun import resolver_franjas_plantilla
from ._comun import (
    _conectar,
    ahora_iso,
)

# --------------------------------------------------------------------------- #
# Config de franjas: singleton id='default'                                   #
# --------------------------------------------------------------------------- #


_COLS_CONFIG_FRANJAS = (
    "matutino_inicio",
    "matutino_fin",
    "vespertino_inicio",
    "vespertino_fin",
    "actualizado",
)


def obtener_franjas_config(marca: str = "") -> dict[str, str]:
    """Lee la config de franjas DE UNA MARCA. Si no existe, devuelve los DEFAULTS del dominio.

    GRID POR MARCA: la config es por marca — `rota_config_franjas.id` guarda el id de la marca.
    Sin marca (vista "Todas" / legado) cae al singleton `'default'`. No SELECT-INSERT race: si
    la fila aun no esta, la crea el PATCH del admin; mientras, `mapear_franja` usa los defaults.
    """
    con = _conectar()
    try:
        fila = con.execute(
            f"SELECT {', '.join(_COLS_CONFIG_FRANJAS)} FROM rota_config_franjas "
            "WHERE id = ?",
            (marca or "default",),
        ).fetchone()
    finally:
        con.close()
    if fila is None:
        return {
            "matutino_inicio": "08:00",
            "matutino_fin": "16:00",
            "vespertino_inicio": "16:00",
            "vespertino_fin": "24:00",
            "actualizado": "",
        }
    return {col: fila[col] for col in _COLS_CONFIG_FRANJAS}


def guardar_franjas_config(
    matutino_inicio: str,
    matutino_fin: str,
    vespertino_inicio: str,
    vespertino_fin: str,
    marca: str = "",
) -> dict[str, str]:
    """Hace UPSERT de la config de franjas DE UNA MARCA. Devuelve la fila resultante.

    GRID POR MARCA: `rota_config_franjas.id` guarda el id de la marca; sin marca cae al
    singleton `'default'`. Cada marca define los rangos por defecto de su rejilla.
    """
    ahora = ahora_iso()
    clave = marca or "default"
    con = _conectar()
    try:
        # INSERT ... ON CONFLICT DO UPDATE (Postgres): si la fila existe, actualiza.
        con.execute(
            "INSERT INTO rota_config_franjas "
            "(id, matutino_inicio, matutino_fin, vespertino_inicio, vespertino_fin, "
            " actualizado) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET "
            "matutino_inicio = EXCLUDED.matutino_inicio, "
            "matutino_fin = EXCLUDED.matutino_fin, "
            "vespertino_inicio = EXCLUDED.vespertino_inicio, "
            "vespertino_fin = EXCLUDED.vespertino_fin, "
            "actualizado = EXCLUDED.actualizado",
            (
                clave,
                matutino_inicio,
                matutino_fin,
                vespertino_inicio,
                vespertino_fin,
                ahora,
            ),
        )
        con.commit()
    finally:
        con.close()
    return obtener_franjas_config(marca)


# --------------------------------------------------------------------------- #
# PLANTILLA de franjas como LISTA flexible (columna JSON `franjas`)             #
# --------------------------------------------------------------------------- #
# Modelo nuevo: la plantilla con que se siembra cada semana es una lista de N franjas
# ([{nombre,inicio,fin}, ...]), no 2 columnas fijas matutino/vespertino. Asi el equipo puede
# añadir una 3a franja (p. ej. "Nocturna"). "Descanso" no vive aqui: lo añade la siembra.


def obtener_plantilla_franjas(marca: str = "") -> dict[str, Any]:
    """Lee la PLANTILLA de franjas de una marca como `{"franjas": [{nombre,inicio,fin}], "actualizado"}`.

    Fuente de verdad: la columna JSON `franjas`. Si esta vacia (fila previa a la columna o marca
    que nunca uso el editor de lista) se DERIVA de las columnas legadas matutino/vespertino, asi
    una marca con rangos personalizados los conserva. Sin fila: defaults del dominio.
    """
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT franjas, matutino_inicio, matutino_fin, vespertino_inicio, "
            "vespertino_fin, actualizado FROM rota_config_franjas WHERE id = ?",
            (marca or "default",),
        ).fetchone()
    finally:
        con.close()
    if fila is None:
        franjas = resolver_franjas_plantilla(
            "", "08:00", "16:00", "16:00", "24:00",
            nombre_manana=NOMBRE_FRANJA_MANANA_DEFAULT,
            nombre_tarde=NOMBRE_FRANJA_TARDE_DEFAULT,
        )
        return {"franjas": franjas, "actualizado": ""}
    franjas = resolver_franjas_plantilla(
        fila["franjas"],
        fila["matutino_inicio"],
        fila["matutino_fin"],
        fila["vespertino_inicio"],
        fila["vespertino_fin"],
        nombre_manana=NOMBRE_FRANJA_MANANA_DEFAULT,
        nombre_tarde=NOMBRE_FRANJA_TARDE_DEFAULT,
    )
    return {"franjas": franjas, "actualizado": fila["actualizado"] or ""}


def guardar_plantilla_franjas(
    franjas: list[dict[str, str]],
    marca: str = "",
) -> dict[str, Any]:
    """Hace UPSERT de la PLANTILLA de franjas (lista JSON) DE UNA MARCA. Devuelve la plantilla.

    Guarda solo la columna `franjas`: las columnas legadas matutino/vespertino quedan con su
    DEFAULT en filas nuevas (vestigio para el endpoint legado `mapear_franja`). La validacion
    (horas, nombres, duplicados) la hace la API antes de llamar aqui.
    """
    ahora = ahora_iso()
    clave = marca or "default"
    crudo = json.dumps(
        [
            {"nombre": f["nombre"], "inicio": f["inicio"], "fin": f["fin"]}
            for f in franjas
        ],
        ensure_ascii=False,
    )
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO rota_config_franjas (id, franjas, actualizado) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET "
            "franjas = EXCLUDED.franjas, actualizado = EXCLUDED.actualizado",
            (clave, crudo, ahora),
        )
        con.commit()
    finally:
        con.close()
    return obtener_plantilla_franjas(marca)
