"""Feature Configuracion: ver y cambiar la fuente y el alcance desde la UI.

Pensada para el equipo NO tecnico: muestra, en lenguaje sencillo, que FUENTE de
datos esta activa (muestra/real), que marcas/cuentas hay configuradas, que ALCANCE
gestiona esta persona, y permite cambiar la fuente y el alcance sin tocar el TOML a
mano. Los cambios se escriben a `~/.config/keni-metricas/config.toml` de forma
ATOMICA y segura, REUTILIZANDO la serializacion/escritura del asistente.

NO se editan tokens por el navegador en esta version. Solo se muestra la PRESENCIA
o AUSENCIA de credenciales por plataforma (jamas el valor de un secreto) y una nota
que apunta al asistente CLI / docs para conectar cuentas reales.

Esta feature solo IMPORTA de `keni_metricas.config` y `keni_metricas.asistente`
(no los edita). Toda la logica de serializacion, merge y escritura atomica vive
alli; aqui solo se orquesta + renderiza.
"""

from __future__ import annotations

import dataclasses
from html import escape
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from ... import asistente
from ...config import (
    FUENTES_VALIDAS,
    ConfigInvalida,
    cargar_config,
    construir_fuente,
    ruta_config,
)
from .. import layout, marcas
from .._http_json import leer_json
from . import Feature, RecursoEstatico, features_ordenadas

_ESTATICOS = Path(__file__).parent.parent / "estaticos"

# Bloques de credenciales que el sistema reconoce (mismo mapa que el asistente),
# en orden estable para mostrarlos siempre igual. Cada bloque cubre una o mas
# plataformas; aqui solo informamos presencia/ausencia, nunca el valor.
_BLOQUES_CREDENCIALES: tuple[tuple[str, str], ...] = (
    ("meta", "Meta (Facebook + Instagram)"),
    ("youtube", "YouTube"),
    ("x", "X (Twitter)"),
    ("tiktok", "TikTok"),
)

# Etiquetas humanas de la fuente para los radios.
_ETIQUETA_FUENTE: dict[str, str] = {
    "muestra": "Muestra (datos de ejemplo, sin conexión)",
    "real": "Real (datos de tus plataformas; requiere credenciales)",
}

# Texto amable de cara al usuario: nada de comandos ni rutas en la frase principal.
_NOTA_CREDENCIALES = (
    "Para conectar tus cuentas reales necesitas el asistente de configuración. "
    "Tus tokens nunca se editan ni se muestran desde el navegador."
)

# Detalle tecnico (comando y docs) escondido en un <details> para quien lo necesite.
_NOTA_CREDENCIALES_TECNICA = (
    "Ejecuta el asistente de configuración en una terminal: "
    "<code>python -m keni_metricas.asistente</code>. "
    "Más detalle en <code>docs/credenciales.md</code>."
)


# --------------------------------------------------------------------------- #
# Lectura del estado actual                                                    #
# --------------------------------------------------------------------------- #


def _marcas_disponibles(cfg) -> list[tuple[str, str]]:  # noqa: ANN001 -- Config del paquete
    """Marcas elegibles para el alcance: las declaradas en el config + las de la
    fuente activa. Devuelve pares (id, nombre) sin duplicados, orden estable.

    Asi el selector tiene opciones aunque el usuario aun no haya declarado ninguna
    cuenta (caso tipico en modo muestra: salen las marcas de ejemplo).
    """
    pares: list[tuple[str, str]] = []
    vistos: set[str] = set()

    for c in cfg.cuentas:
        if c.id not in vistos:
            vistos.add(c.id)
            pares.append((c.id, c.nombre))

    # Construimos la fuente SIN el alcance actual (marcas=[]): si ya hay un alcance
    # acotado, `construir_fuente(cfg)` devolveria solo esas marcas y el usuario no
    # podria ampliarlo. Con el alcance vacio listamos TODAS las marcas de la fuente.
    try:
        cfg_sin_alcance = dataclasses.replace(cfg, marcas=[])
        fuente = construir_fuente(cfg_sin_alcance)
        for c in fuente.cuentas():
            if c.id not in vistos:
                vistos.add(c.id)
                pares.append((c.id, c.nombre))
    except Exception:  # noqa: BLE001 -- sin fuente valida seguimos con lo del config
        pass

    return pares


def _presencia_credenciales(cfg) -> list[tuple[str, str, bool]]:  # noqa: ANN001
    """Por cada bloque conocido: (etiqueta, bloque, tiene_token_real).

    `tiene_token_real` es True si el bloque trae el campo de token principal con un
    valor que NO es vacio ni el placeholder del asistente. Nunca se devuelve el
    valor; solo presencia/ausencia.
    """
    creds = cfg.credenciales if isinstance(cfg.credenciales, dict) else {}
    salida: list[tuple[str, str, bool]] = []
    for bloque, etiqueta in _BLOQUES_CREDENCIALES:
        valores = creds.get(bloque) if isinstance(creds.get(bloque), dict) else {}
        campo = asistente.CAMPO_TOKEN.get(bloque)
        token = valores.get(campo) if campo else None
        presente = bool(token) and token != asistente.PLACEHOLDER_TOKEN
        salida.append((etiqueta, bloque, presente))
    return salida


# --------------------------------------------------------------------------- #
# Render                                                                       #
# --------------------------------------------------------------------------- #


def _render_fuente(fuente_activa: str) -> str:
    """Radios para elegir la fuente, con la activa marcada."""
    opciones = []
    for valor in sorted(FUENTES_VALIDAS):
        etiqueta = _ETIQUETA_FUENTE.get(valor, valor)
        marcado = " checked" if valor == fuente_activa else ""
        opciones.append(
            f'<label class="opcion-fuente">'
            f'<input type="radio" name="fuente" value="{escape(valor)}"{marcado}> '
            f"{escape(etiqueta)}</label>"
        )
    return "\n".join(opciones)


def _etiqueta_humana(marca_id: str, nombre: str) -> str:
    """Nombre legible (con acentos) de una marca para mostrar en la UI.

    Prioriza la etiqueta canonica de `marcas` (fuente unica de verdad, con acentos);
    si la marca no esta en ese catalogo, cae al nombre declarado en el config y, en
    ultimo termino, al propio id. NUNCA mostramos el id crudo entre parentesis.
    """
    marca = marcas.marca_por_id(marca_id)
    if marca is not None:
        return marca.etiqueta
    return nombre or marca_id


def _render_alcance(disponibles: list[tuple[str, str]], alcance: list[str]) -> str:
    """Checkboxes de marcas para el alcance. Vacio (ninguna marcada) = todas.

    Cada marca se muestra con su etiqueta HUMANA (con acentos). El id tecnico solo
    viaja en `title=` para quien lo necesite, nunca como texto visible.
    """
    if not disponibles:
        return (
            '<p class="ayuda">Todavía no hay marcas configuradas. Conecta tus cuentas con '
            "el asistente de configuración para poder acotar tu alcance.</p>"
        )
    activas = set(alcance)
    filas = []
    for marca_id, nombre in disponibles:
        marcado = " checked" if marca_id in activas else ""
        etiqueta = _etiqueta_humana(marca_id, nombre)
        filas.append(
            f'<label class="opcion-marca" title="{escape(marca_id)}">'
            f'<input type="checkbox" name="marca" value="{escape(marca_id)}"{marcado}> '
            f"{escape(etiqueta)}</label>"
        )
    return "\n".join(filas)


def _render_credenciales(presencia: list[tuple[str, str, bool]]) -> str:
    """Lista de bloques con su estado de conexion (solo presencia/ausencia)."""
    filas = []
    for etiqueta, bloque, presente in presencia:
        clase = "ok" if presente else "aviso"
        texto = "conectada" if presente else "sin conectar"
        # (textos cortos, ya legibles; el detalle tecnico vive en el <details> de la pagina)
        filas.append(
            f'<li class="credencial {clase}" data-bloque="{escape(bloque)}">'
            f'<span class="nombre">{escape(etiqueta)}</span>'
            f'<span class="estado-cred">{texto}</span></li>'
        )
    return "".join(filas)


def _alcance_texto(alcance: list[str]) -> str:
    """Resumen humano del alcance actual, con etiquetas legibles (con acentos)."""
    if not alcance:
        return "todas las marcas"
    return ", ".join(marcas.etiqueta_por_id(mid) for mid in alcance)


def _fuente_legible(fuente: str) -> str:
    """Nombre corto y humano de la fuente activa (sin jerga) para el resumen."""
    return {"muestra": "Muestra", "real": "Real"}.get(fuente, fuente)


def _cuerpo(error: str | None = None) -> str:
    """Arma el contenido de la pagina leyendo el estado actual del config."""
    cuerpo: list[str] = [
        "<h1>Configuración</h1>",
        '<p class="intro">Elige de dónde salen los datos (de muestra o reales) y qué marcas '
        "gestionas. Los cambios se guardan en tu equipo; tus credenciales no se "
        "tocan desde aquí.</p>",
    ]

    if error:
        cuerpo.append(f'<p class="aviso-global" role="alert">{escape(error)}</p>')

    try:
        cfg = cargar_config()
    except ConfigInvalida as e:
        cuerpo.append(
            '<p class="aviso-global" role="alert">'
            f"No se pudo leer tu configuración: {escape(str(e))}</p>"
        )
        return layout.render_pagina(
            features=features_ordenadas(),
            activa=FEATURE.id,
            titulo="Configuración",
            contenido="".join(cuerpo),
            css=FEATURE.css,
            js=FEATURE.js,
        )

    disponibles = _marcas_disponibles(cfg)
    presencia = _presencia_credenciales(cfg)
    ruta = ruta_config()

    cuerpo.append(
        f"""
<section class="estado-actual">
  <h2>Estado actual</h2>
  <ul class="resumen-config">
    <li><span class="clave">Fuente activa</span>
        <span class="valor fuente-{escape(cfg.fuente)}">{escape(_fuente_legible(cfg.fuente))}</span></li>
    <li><span class="clave">Marcas configuradas</span>
        <span class="valor">{escape(str(len(disponibles)))}</span></li>
    <li><span class="clave">Tu alcance</span>
        <span class="valor">{escape(_alcance_texto(cfg.marcas))}</span></li>
  </ul>
</section>

<form id="form-config" class="form-config">
  <fieldset class="campo-fuente">
    <legend>Fuente de datos</legend>
    {_render_fuente(cfg.fuente)}
  </fieldset>

  <fieldset class="campo-alcance">
    <legend>Alcance (qué marcas gestionas)</legend>
    <p class="ayuda">Marca las que gestionas. Si no marcas ninguna, gestionas todas.</p>
    {_render_alcance(disponibles, cfg.marcas)}
  </fieldset>

  <div class="acciones">
    <button type="submit" class="boton primario">Guardar cambios</button>
    <span class="estado" role="status" aria-live="polite"></span>
  </div>
</form>

<section class="estado-credenciales">
  <h2>Credenciales</h2>
  <p class="ayuda">Estado de conexión por plataforma (solo si está conectada o no; nunca se muestran tokens).</p>
  <ul class="credenciales">{_render_credenciales(presencia)}</ul>
  <p class="nota-credenciales">{escape(_NOTA_CREDENCIALES)}</p>
  <details class="detalle-tecnico">
    <summary>Detalles técnicos (para personas técnicas)</summary>
    <p class="nota-tecnica">{_NOTA_CREDENCIALES_TECNICA}</p>
    <p class="ruta-config">Tu configuración se guarda en: <code>{escape(str(ruta))}</code></p>
  </details>
</section>
"""
    )

    return layout.render_pagina(
        features=features_ordenadas(),
        activa=FEATURE.id,
        titulo="Configuración",
        contenido="".join(cuerpo),
        css=FEATURE.css,
        js=FEATURE.js,
    )


# --------------------------------------------------------------------------- #
# Escritura: reutiliza la logica del asistente (merge + escritura atomica)     #
# --------------------------------------------------------------------------- #


def _guardar_fuente_y_marcas(ruta: Path, fuente: str, marcas: list[str]) -> None:
    """Escribe SOLO `fuente` y `marcas` preservando el resto del config.

    Lee el TOML existente, lo fusiona con un dict que cambia unicamente `fuente` y
    `marcas`, y lo reescribe de forma atomica (tmp + os.replace + 0600) usando las
    funciones del asistente. Las credenciales y las cuentas declaradas se preservan
    porque el merge solo toca las claves que pasamos.
    """
    existente = asistente.leer_config_existente(ruta)
    nuevo: dict = {"fuente": fuente}
    # `marcas` vacio = "todas": no queremos dejar una lista vacia en el TOML, asi
    # que la borramos del config existente para que vuelva al comportamiento "todas".
    if marcas:
        nuevo["marcas"] = list(marcas)
    fusionado = asistente.fusionar_config(existente, nuevo)
    if not marcas:
        fusionado.pop("marcas", None)
    asistente.escribir_config_atomico(ruta, fusionado)


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def pagina_config(request: Request) -> Response:
    return HTMLResponse(_cuerpo())


async def api_guardar(request: Request) -> Response:
    datos = await leer_json(request)

    fuente = datos.get("fuente")
    if not isinstance(fuente, str) or fuente not in FUENTES_VALIDAS:
        validas = ", ".join(sorted(FUENTES_VALIDAS))
        return JSONResponse(
            {"error": f"Fuente inválida. Usa una de: {validas}."},
            status_code=400,
        )

    marcas_crudas = datos.get("marcas", [])
    if not isinstance(marcas_crudas, list) or not all(
        isinstance(m, str) for m in marcas_crudas
    ):
        return JSONResponse(
            {"error": "El alcance debe ser una lista de marcas."}, status_code=400
        )

    # Las marcas elegidas deben existir entre las disponibles (declaradas o de la
    # fuente activa). Cualquier id desconocido se rechaza con un mensaje claro.
    try:
        cfg = cargar_config()
    except ConfigInvalida as e:
        return JSONResponse(
            {"error": f"No se pudo leer tu configuración: {e}"}, status_code=400
        )
    ids_validos = [mid for mid, _ in _marcas_disponibles(cfg)]
    alcance_ids = asistente.normalizar_alcance(marcas_crudas, ids_validos=ids_validos)
    desconocidas = [m for m in marcas_crudas if m.strip() and m.strip() not in ids_validos]
    if desconocidas:
        # Mostramos la etiqueta humana de cada marca desconocida (cae al id si no se conoce).
        etiquetas = ", ".join(marcas.etiqueta_por_id(m) for m in desconocidas)
        return JSONResponse(
            {"error": f"Marcas desconocidas: {etiquetas}."},
            status_code=400,
        )

    try:
        _guardar_fuente_y_marcas(ruta_config(), fuente, alcance_ids)
    except OSError as e:
        return JSONResponse(
            {"error": f"No se pudo guardar la configuración: {e}"}, status_code=400
        )

    # En el mensaje de exito mostramos etiquetas humanas (con acentos), no ids crudos.
    alcance = (
        ", ".join(marcas.etiqueta_por_id(mid) for mid in alcance_ids)
        if alcance_ids
        else "todas las marcas"
    )
    return JSONResponse(
        {"mensaje": f"Configuración guardada. Fuente: {_fuente_legible(fuente)}. Alcance: {alcance}."}
    )


FEATURE = Feature(
    id="config",
    etiqueta="Configuración",
    orden=70,
    descripcion="Elige la fuente de datos y qué marcas gestionas, sin tocar archivos a mano.",
    rutas=[
        Route("/config", pagina_config),
        Route("/api/config/guardar", api_guardar, methods=["POST"]),
    ],
    estaticos=[
        RecursoEstatico("config.css", _ESTATICOS / "config.css", "text/css; charset=utf-8"),
        RecursoEstatico(
            "config.js", _ESTATICOS / "config.js", "application/javascript; charset=utf-8"
        ),
    ],
    css=["config.css"],
    js=["config.js"],
)
