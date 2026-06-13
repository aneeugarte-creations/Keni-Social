"""Persistencia — rota: config de franjas por marca (tabla `rota_config_franjas`)."""
from __future__ import annotations

from ._comun import (
    _conectar,
    ahora_iso,
)

# --------------------------------------------------------------------------- #
# Config de franjas (#185): singleton id='default'                              #
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
