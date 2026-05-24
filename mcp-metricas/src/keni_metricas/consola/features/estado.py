"""Feature Estado: autodiagnostico del sistema en la UI, para no tecnicos.

Envuelve el `doctor` ya existente (`keni_metricas.doctor`) y lo presenta de forma
visual: una frase tranquilizadora/alerta arriba, la lista de chequeos con su icono
y color (verde/ambar/rojo), un contador "N OK N aviso N error", y el siguiente paso
concreto al final. NO reimplementa ninguna comprobacion: solo orquesta + renderiza.

El doctor solo informa de presencia/ausencia de credenciales (NUNCA imprime el
valor de un secreto), asi que esta pagina tampoco expone nada sensible.

`ejecutar_chequeos` se expone como nombre de modulo para poder inyectarlo/mockearlo
en los tests (set determinista de resultados, offline, sin tocar red ni binarios).
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route

from ... import doctor
from .. import layout
from . import Feature, RecursoEstatico, features_ordenadas

# Inyectable: los tests reasignan esto a un stub que devuelve resultados
# deterministas (OK + AVISO + ERROR), sin tocar la maquina real.
ejecutar_chequeos = doctor.ejecutar_chequeos

# Mapa Estado del doctor -> clase CSS para el color de cada fila.
_CLASE_POR_ESTADO = {
    doctor.Estado.OK: "ok",
    doctor.Estado.AVISO: "aviso",
    doctor.Estado.ERROR: "error",
}


def _clase_de(estado: object) -> str:
    """Clase CSS para un estado del doctor (cae a 'aviso' si fuese desconocido)."""
    return _CLASE_POR_ESTADO.get(estado, "aviso")


def _render_fila(r: object) -> str:
    """Una fila de la lista: icono + nombre + detalle, con color segun estado."""
    icono = escape(str(getattr(r.estado, "value", "")))
    clase = _clase_de(r.estado)
    nombre = escape(str(r.nombre))
    detalle = escape(str(r.detalle))
    return f"""
<li class="chequeo {clase}">
  <span class="icono" aria-hidden="true">{icono}</span>
  <div class="texto">
    <span class="nombre">{nombre}</span>
    <span class="detalle">{detalle}</span>
  </div>
</li>
"""


def _contador(resultados: list) -> str:
    """Contador 'N OK N aviso N error' con los iconos del propio doctor."""
    oks = sum(1 for r in resultados if r.estado is doctor.Estado.OK)
    avisos = sum(1 for r in resultados if r.estado is doctor.Estado.AVISO)
    errores = sum(1 for r in resultados if r.estado is doctor.Estado.ERROR)
    return (
        '<p class="contador" role="status">'
        f'<span class="cuenta ok">{oks} {doctor.Estado.OK.value}</span>'
        f'<span class="cuenta aviso">{avisos} {doctor.Estado.AVISO.value}</span>'
        f'<span class="cuenta error">{errores} {doctor.Estado.ERROR.value}</span>'
        "</p>"
    )


def _cuerpo() -> str:
    """Arma el contenido de la pagina ejecutando el doctor (defensivo)."""
    try:
        resultados = ejecutar_chequeos()
    except Exception:  # noqa: BLE001 -- el doctor es defensivo; aun asi, nunca un traceback crudo
        return (
            "<h1>Estado del sistema</h1>"
            '<p class="aviso-global" role="alert">No se pudo ejecutar el '
            "autodiagnóstico. Vuelve a intentarlo en un momento.</p>"
            '<p><a class="boton" href="/estado">Volver a comprobar</a></p>'
        )

    hay_error = any(r.estado is doctor.Estado.ERROR for r in resultados)
    clase_resumen = "error" if hay_error else "ok"
    resumen = escape(doctor.resumen_humano(resultados))
    cierre = escape(doctor.cierre_accionable(resultados))
    filas = "".join(_render_fila(r) for r in resultados)

    # El "siguiente paso" del doctor puede incluir comandos/rutas tecnicas: lo
    # presentamos dentro de un <details> para no abrumar a quien no es tecnico, con
    # el resumen amable siempre visible arriba.
    return f"""
<h1>Estado del sistema</h1>
<p class="intro">Esta página revisa tu equipo y te dice, en lenguaje sencillo, si todo
está listo para trabajar. Si algo falla, te indica el siguiente paso.</p>
<p class="resumen-estado {clase_resumen}" role="status">{resumen}</p>
{_contador(resultados)}
<ul class="chequeos">{filas}</ul>
<details class="cierre-detalle" open>
  <summary>¿Qué hago ahora?</summary>
  <p class="cierre-estado">{cierre}</p>
</details>
<p class="acciones-estado">
  <a class="boton primario" href="/estado">Volver a comprobar</a>
</p>
"""


async def pagina_estado(request: Request) -> Response:
    return HTMLResponse(
        layout.render_pagina(
            features=features_ordenadas(),
            activa=FEATURE.id,
            titulo="Estado",
            contenido=_cuerpo(),
            css=FEATURE.css,
        )
    )


_ESTATICOS = Path(__file__).parent.parent / "estaticos"

FEATURE = Feature(
    id="estado",
    etiqueta="Estado",
    orden=60,
    descripcion="Revisa tu equipo: si todo está listo para trabajar y, si no, qué hacer.",
    rutas=[Route("/estado", pagina_estado)],
    estaticos=[
        RecursoEstatico("estado.css", _ESTATICOS / "estado.css", "text/css; charset=utf-8"),
    ],
    css=["estado.css"],
)
