"""API Rota · exports .csv / .xlsx (transicion desde el Excel manual)."""
from __future__ import annotations

import csv
import io
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import repos
from ... import rota as dominio
from ...estados import (
    TIPO_COBERTURA_NO_CUBRIR,
)
from ._comun import (
    _equipo,
    _franjas_de_semana,
    _lunes_param,
    _marca_param,
    _nombres_equipo,
)
from .ausencias import _ausencias_dominio
from .turnos import _turnos_semana

# Media types oficiales de un .xlsx (Open XML) y un CSV.
_MEDIA_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MEDIA_CSV = "text/csv; charset=utf-8"

# Cabeceras de la parrilla exportada: mismas columnas que el Excel de Elías.
_CABECERAS_EXPORT = ("Fecha", "Día", "Hora", "Evento / transmisión", "Qué sacar", "Persona", "Estado")
_DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")


def _filas_export(
    lunes_iso: str, marca: str | None = None
) -> tuple[list[str], list[list[str]]]:
    """Devuelve `(titulo, filas)` de la cobertura DERIVADA de la semana, lista para xlsx/CSV.

    Una fila por (evento, miembro cubridor). Eventos sin cubridores aparecen con `Persona`
    vacia (Elias detecta huecos al exportar). Cobertura DERIVADA: cruza eventos × turnos ×
    franjas vivas de la semana. GRID POR MARCA: `marca` acota a esa rejilla (None = todas).
    """
    if not lunes_iso:
        return "Rota", []
    inicio, fin = dominio.rango_semana(lunes_iso)
    eventos = repos.listar_eventos_rota(desde=inicio, hasta=fin, marca=marca)
    eventos = [
        e for e in eventos
        if (e.get("tipo_cobertura") or "transmision") != TIPO_COBERTURA_NO_CUBRIR
    ]
    turnos = repos.listar_turnos_rota(semana=lunes_iso, marca=marca)
    nombres = _nombres_equipo()
    franjas_lista, _por_id = _franjas_de_semana(lunes_iso, marca)
    filas: list[list[str]] = []
    from datetime import date as _date

    for e in eventos:
        fecha = e.get("fecha", "") or ""
        try:
            dia = _DIAS[_date.fromisoformat(fecha).weekday()] if fecha else ""
        except ValueError:
            dia = ""
        cubridores = dominio.cobertura_de_evento(e, turnos, franjas_lista)
        if not cubridores:
            filas.append(
                [
                    fecha,
                    dia,
                    e.get("hora", "") or "",
                    e.get("titulo", "") or "",
                    e.get("contenido", "") or "",
                    "",  # sin cubridor
                    "sin cubrir",
                ]
            )
            continue
        for t in cubridores:
            override = " (override)" if t.get("override") else ""
            filas.append(
                [
                    fecha,
                    dia,
                    e.get("hora", "") or "",
                    e.get("titulo", "") or "",
                    e.get("contenido", "") or "",
                    nombres.get(t["miembro_id"], t.get("miembro_nombre", "")),
                    f"{t['estado']}{override}",
                ]
            )
    titulo = f"Rota {inicio} a {fin}" if inicio else "Rota"
    return titulo, filas


def _nombre_descarga(lunes_iso: str, ext: str) -> str:
    sufijo = lunes_iso or "semana"
    return f"rota-{sufijo}.{ext}"


def _grid_horario(
    lunes_iso: str, marca: str | None = None
) -> tuple[str, list[str], list[list[str]]]:
    """Construye `(titulo, cabeceras, filas)` del horario persona×día de la semana.

    Cabeceras = ["Persona", Lun..Dom]; cada fila es un miembro con su franja por día
    (el `nombre` de la franja viva, "Ausente" si una ausencia cubre ese día, "—" si no
    hay turno asignado). Reutiliza `_turnos_semana` y las ausencias para marcar la
    indisponibilidad. GRID POR MARCA: `marca` acota a esa rejilla (None = todas).
    """
    turnos_payload = _turnos_semana(lunes_iso, marca)
    dias = turnos_payload["dias"]
    equipo = _equipo()
    ausencias = _ausencias_dominio()
    # Indexa el turno por (miembro, fecha) para llenar el grid.
    por_celda: dict[tuple[str, str], dict[str, Any]] = {
        (t["miembro_id"], t["fecha"]): t for t in turnos_payload["turnos"]
    }
    cabeceras = ["Persona", *(_DIAS[i] for i in range(len(dias)))]
    filas: list[list[str]] = []
    for m in sorted(equipo, key=lambda x: x.nombre.lower()):
        fila = [m.nombre]
        for fecha in dias:
            if dominio.miembro_ausente(ausencias, m.id, fecha):
                fila.append("Ausente")
                continue
            turno = por_celda.get((m.id, fecha))
            if turno is None:
                fila.append("—")
            else:
                etiqueta = turno.get("franja_nombre") or "Turno"
                if turno["override"]:
                    etiqueta += " (override)"
                fila.append(etiqueta)
        filas.append(fila)
    titulo = (
        f"Horario equipo {turnos_payload['inicio']} a {turnos_payload['fin']}"
        if turnos_payload["inicio"]
        else "Horario equipo"
    )
    return titulo, cabeceras, filas


async def export_csv(request: Request) -> Response:
    """GET /api/rota/export.csv[?lunes&marca]: descarga la rota de la semana en CSV."""
    lunes = _lunes_param(request)
    marca, error = _marca_param(request)
    if error is not None:
        return error
    _, filas = _filas_export(lunes, marca)
    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(_CABECERAS_EXPORT)
    escritor.writerows(filas)
    cabecera = f'attachment; filename="{_nombre_descarga(lunes, "csv")}"'
    # BOM para que Excel abra el UTF-8 con acentos correctamente.
    return Response(
        "﻿" + buffer.getvalue(),
        media_type=_MEDIA_CSV,
        headers={"Content-Disposition": cabecera},
    )


async def export_xlsx(request: Request) -> Response:
    """GET /api/rota/export.xlsx[?lunes]: descarga la rota de la semana en .xlsx.

    Usa `xlsxwriter` (ya presente vía python-pptx; no añade dependencia). Si no
    estuviera disponible, degrada con un 500 accionable (sin traceback crudo).
    """
    lunes = _lunes_param(request)
    marca, error = _marca_param(request)
    if error is not None:
        return error
    titulo, filas = _filas_export(lunes, marca)
    try:
        import xlsxwriter
    except ImportError:
        return JSONResponse(
            {"error": "Falta xlsxwriter para el .xlsx. Usa la exportación CSV mientras tanto."},
            status_code=500,
        )

    buffer = io.BytesIO()
    libro = xlsxwriter.Workbook(buffer, {"in_memory": True})
    fmt_titulo = libro.add_format({"bold": True, "font_size": 14})
    fmt_cabecera = libro.add_format({"bold": True, "bg_color": "#EEEEEE", "border": 1})

    # Hoja 1: cobertura de eventos (la parrilla histórica; columnas del Excel de Elías).
    hoja = libro.add_worksheet("Rota")
    hoja.write(0, 0, titulo, fmt_titulo)
    for col, encabezado in enumerate(_CABECERAS_EXPORT):
        hoja.write(2, col, encabezado, fmt_cabecera)
    for i, fila in enumerate(filas, start=3):
        for col, valor in enumerate(fila):
            hoja.write(i, col, valor)
    anchos = (12, 11, 12, 30, 40, 18, 16)
    for col, ancho in enumerate(anchos):
        hoja.set_column(col, col, ancho)

    # Hoja 2: horario de trabajo del equipo (grid persona×día) — gestión de turnos.
    titulo_h, cabeceras_h, filas_h = _grid_horario(lunes, marca)
    hoja_h = libro.add_worksheet("Horario equipo")
    hoja_h.write(0, 0, titulo_h, fmt_titulo)
    for col, encabezado in enumerate(cabeceras_h):
        hoja_h.write(2, col, encabezado, fmt_cabecera)
    for i, fila in enumerate(filas_h, start=3):
        for col, valor in enumerate(fila):
            hoja_h.write(i, col, valor)
    hoja_h.set_column(0, 0, 18)
    hoja_h.set_column(1, max(len(cabeceras_h) - 1, 1), 12)

    libro.close()

    cabecera = f'attachment; filename="{_nombre_descarga(lunes, "xlsx")}"'
    return Response(
        buffer.getvalue(),
        media_type=_MEDIA_XLSX,
        headers={"Content-Disposition": cabecera},
    )
