"""Persistencia — rota: config/plantilla de franjas por marca (tabla `rota_config_franjas`)."""
from __future__ import annotations

import json
from typing import Any

from ...estados import NOMBRE_FRANJA_MANANA_DEFAULT, NOMBRE_FRANJA_TARDE_DEFAULT
from ..._db_core._comun import resolver_franjas_plantilla
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
    """Lee la PLANTILLA de franjas de una marca como `{"franjas", "mostrar_horas_equipo", "actualizado"}`.

    `franjas` es la lista `[{nombre,inicio,fin}]`. Fuente de verdad: la columna JSON `franjas`;
    si esta vacia (fila previa a la columna o marca que nunca uso el editor de lista) se DERIVA
    de las columnas legadas matutino/vespertino, asi una marca con rangos personalizados los
    conserva. `mostrar_horas_equipo` (bool, default False) decide si el calendario muestra el
    rango horario en la vista "Equipo". Sin fila: defaults del dominio + toggle apagado.
    """
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT franjas, matutino_inicio, matutino_fin, vespertino_inicio, "
            "vespertino_fin, mostrar_horas_equipo, tiempo_libre_activo, actualizado "
            "FROM rota_config_franjas WHERE id = ?",
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
        return {
            "franjas": franjas,
            "mostrar_horas_equipo": False,
            "tiempo_libre_activo": True,
            "actualizado": "",
        }
    franjas = resolver_franjas_plantilla(
        fila["franjas"],
        fila["matutino_inicio"],
        fila["matutino_fin"],
        fila["vespertino_inicio"],
        fila["vespertino_fin"],
        nombre_manana=NOMBRE_FRANJA_MANANA_DEFAULT,
        nombre_tarde=NOMBRE_FRANJA_TARDE_DEFAULT,
    )
    return {
        "franjas": franjas,
        "mostrar_horas_equipo": bool(fila["mostrar_horas_equipo"]),
        "tiempo_libre_activo": bool(fila["tiempo_libre_activo"]),
        "actualizado": fila["actualizado"] or "",
    }


def guardar_plantilla_franjas(
    franjas: list[dict[str, str]] | None = None,
    marca: str = "",
    *,
    mostrar_horas_equipo: bool | None = None,
    tiempo_libre_activo: bool | None = None,
) -> dict[str, Any]:
    """Hace UPSERT PARCIAL de la PLANTILLA de franjas DE UNA MARCA. Devuelve la plantilla.

    Actualiza SOLO los campos provistos:
      - `franjas` (lista JSON): si es None no toca la columna `franjas`.
      - `mostrar_horas_equipo` (bool): si es None no toca esa columna.
      - `tiempo_libre_activo` (bool): si es None no toca esa columna.
    En el UPSERT, ON CONFLICT actualiza solo las columnas provistas; si la fila no existe aun,
    se crea con la plantilla derivada/por defecto (de `franjas` o de las columnas legadas) y el
    toggle apagado para el campo que no llegue. Las columnas legadas matutino/vespertino quedan
    con su DEFAULT en filas nuevas (vestigio para `mapear_franja`). La validacion (horas,
    nombres, duplicados) la hace la API antes de llamar aqui.
    """
    ahora = ahora_iso()
    clave = marca or "default"
    crudo = None
    if franjas is not None:
        crudo = json.dumps(
            [
                {"nombre": f["nombre"], "inicio": f["inicio"], "fin": f["fin"]}
                for f in franjas
            ],
            ensure_ascii=False,
        )
    # Columnas a insertar (fila nueva) y a actualizar (ON CONFLICT). `actualizado` siempre.
    columnas = ["id"]
    valores: list[Any] = [clave]
    set_conflicto = ["actualizado = EXCLUDED.actualizado"]
    if crudo is not None:
        columnas.append("franjas")
        valores.append(crudo)
        set_conflicto.append("franjas = EXCLUDED.franjas")
    if mostrar_horas_equipo is not None:
        columnas.append("mostrar_horas_equipo")
        valores.append(mostrar_horas_equipo)
        set_conflicto.append("mostrar_horas_equipo = EXCLUDED.mostrar_horas_equipo")
    if tiempo_libre_activo is not None:
        columnas.append("tiempo_libre_activo")
        valores.append(tiempo_libre_activo)
        set_conflicto.append("tiempo_libre_activo = EXCLUDED.tiempo_libre_activo")
    columnas.append("actualizado")
    valores.append(ahora)
    marcadores = ", ".join("?" for _ in columnas)
    con = _conectar()
    try:
        con.execute(
            f"INSERT INTO rota_config_franjas ({', '.join(columnas)}) "  # noqa: S608 -- columnas fijas de allowlist
            f"VALUES ({marcadores}) "
            f"ON CONFLICT (id) DO UPDATE SET {', '.join(set_conflicto)}",
            tuple(valores),
        )
        con.commit()
    finally:
        con.close()
    return obtener_plantilla_franjas(marca)
