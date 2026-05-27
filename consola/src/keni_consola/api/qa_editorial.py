"""API QA editorial: revisa el copy YA escrito por el community y devuelve un INFORME.

Ficha F3 (issue #143). NUEVO MODO de la verificacion editorial: hoy las skills de copy
solo se auto-verifican lo que ELLAS generan; aqui aplicamos esa misma capacidad a TEXTO
AJENO (el copy que escribio el community manager) y devolvemos un veredicto 🟢/🟡/🔴 con
los hallazgos clasificados (ortografia / dato / legal / voz), cada uno con su correccion
SUGERIDA.

Frontera del producto (no negociable): Keni **SEÑALA**, el equipo **decide**. La salida es
un INFORME; puede OFRECER una correccion, pero NO la aplica ni reescribe el copy, y NUNCA
publica. Honestidad: un dato que no se puede comprobar se marca como "no verificable", no se
inventa.

  - `GET  /api/qa-editorial`          -> marcas + plataformas + si la skill esta instalada.
  - `POST /api/qa-editorial/revisar`  (JSON `{marca, texto, plataforma?, contexto?}`) ->
    `{generacion}` (estado "ejecutando"); el frontend SONDEA `GET /api/generaciones/{id}` y,
    al completar, recoge `resultado = {informe: <reporte>}`.

Reutiliza la infra de generaciones en background (mismo sondeo que copy/verificacion) y el
catalogo de skills de archivos (la skill `qa-editorial` con su contexto editorial versionado).
El POST-PROCESADO parsea el bloque ```json de hallazgos que emite la skill en un reporte
estructurado para la UI; cae con elegancia a un informe de solo-texto si no hay JSON valido.

SEGURIDAD: marca∈catalogo unico; skill∈catalogo de archivos; el texto viaja como argumento
de subprocess (sin shell). Errores en espanol, sin tracebacks.
"""

from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import generaciones, repos, skills_catalogo
from .._http_json import leer_json
from ..dominio import skills as dom_skills
from ..dominio import stream
from ..seguridad import autor_de_peticion
from . import skills

# Id de la skill que hace el QA (vive en skills-copy/.claude/skills/).
SKILL_ID = "qa-editorial"

# Plataformas que se pueden indicar (para validar el limite de caracteres). El value es la
# etiqueta que entiende la skill / `plataformas.md`; "" = no validar ningun limite.
PLATAFORMAS: tuple[str, ...] = (
    "X / Twitter",
    "Instagram",
    "Facebook",
    "TikTok",
    "YouTube",
)

# Valores permitidos del informe estructurado (defensa: ignoramos cualquier otro).
_TIPOS = frozenset({"ortografia", "dato", "legal", "voz"})
_GRAVEDADES = frozenset({"error", "aviso"})

# Mapa del simbolo de semaforo (🟢/🟡/🔴) al verdicto interno estable, equivalente al
# ✅/⚠️/❌ del resto del producto (`stream._VEREDICTO_POR_SIMBOLO`).
_VERDICTO_POR_SEMAFORO = {"🟢": "listo", "🟡": "revisar", "🔴": "no_publicar"}

# Tope defensivo de hallazgos que devolvemos (evita una salida abusiva del modelo).
_MAX_HALLAZGOS = 200


def _marcas_lista() -> list[dict[str, str]]:
    """Marcas para el selector del formulario (id + nombre humano)."""
    return [{"id": mid, "nombre": nombre} for mid, nombre in skills.MARCAS]


def _verdicto_de_texto(texto: str) -> str:
    """Deriva el verdicto del informe: primero el semaforo 🟢/🟡/🔴, luego ✅/⚠️/❌.

    La skill abre con la linea de semaforo (🟢/🟡/🔴); si por lo que sea saliera con los
    simbolos clasicos, `stream.derivar_verdicto` los cubre. Devuelve "" si no hay ninguno.
    """
    for linea in texto.splitlines():
        if not linea.strip():
            continue
        for simbolo, valor in _VERDICTO_POR_SEMAFORO.items():
            if simbolo in linea:
                return valor
        return stream.derivar_verdicto(texto)
    return ""


def _hallazgo_limpio(crudo: object) -> dict[str, object] | None:
    """Normaliza un hallazgo del JSON de la skill o devuelve None si no es usable.

    Acota `tipo`/`gravedad` a los valores permitidos (un `tipo` desconocido se descarta;
    una `gravedad` desconocida cae a "aviso", la menos alarmante). Recorta los textos a un
    tope razonable. `no_verificable` solo es True para hallazgos de tipo `dato`.
    """
    if not isinstance(crudo, dict):
        return None
    tipo = crudo.get("tipo")
    if not isinstance(tipo, str) or tipo not in _TIPOS:
        return None
    gravedad = crudo.get("gravedad")
    if not isinstance(gravedad, str) or gravedad not in _GRAVEDADES:
        gravedad = "aviso"

    def _texto(clave: str) -> str:
        valor = crudo.get(clave)
        return valor.strip()[:1000] if isinstance(valor, str) else ""

    no_verificable = bool(crudo.get("no_verificable")) and tipo == "dato"
    return {
        "tipo": tipo,
        "gravedad": gravedad,
        "fragmento": _texto("fragmento"),
        "explicacion": _texto("explicacion"),
        "sugerencia": _texto("sugerencia"),
        "no_verificable": no_verificable,
    }


def parsear_informe(salida: str) -> dict[str, object]:
    """Parsea la salida de la skill en un INFORME estructurado para la UI.

    Localiza el ULTIMO bloque ```json cercado (igual criterio que `stream.parsear_salida`)
    y mapea `veredicto`/`resumen`/`hallazgos`. El `informe_texto` es el documento legible
    SIN ese bloque json y sin emojis del cuerpo (el verdicto se deriva ANTES de limpiar, asi
    no se pierde el simbolo). Degradacion robusta: si no hay JSON valido, `hallazgos=[]` y el
    informe queda como el texto completo (el QA nunca se rompe por un formato inesperado).

    Devuelve `{verdicto, resumen, hallazgos: [...], informe_texto}`.
    """
    salida = salida or ""
    verdicto = _verdicto_de_texto(salida)

    coincidencias = list(stream._RE_BLOQUE_JSON.finditer(salida))
    datos: object = None
    texto_sin_json = salida
    if coincidencias:
        ultima = coincidencias[-1]
        try:
            datos = json.loads(ultima.group(1))
        except (json.JSONDecodeError, ValueError):
            datos = None
        else:
            texto_sin_json = salida[: ultima.start()] + salida[ultima.end():]

    hallazgos: list[dict[str, object]] = []
    resumen = ""
    if isinstance(datos, dict):
        # El verdicto del JSON (semaforo) tiene prioridad si lo trae; si no, el de la 1a linea.
        v = datos.get("veredicto")
        if isinstance(v, str):
            for simbolo, valor in _VERDICTO_POR_SEMAFORO.items():
                if simbolo in v:
                    verdicto = valor
                    break
        r = datos.get("resumen")
        if isinstance(r, str):
            resumen = r.strip()[:500]
        crudos = datos.get("hallazgos")
        if isinstance(crudos, list):
            for cr in crudos[:_MAX_HALLAZGOS]:
                limpio = _hallazgo_limpio(cr)
                if limpio is not None:
                    hallazgos.append(limpio)

    return {
        "verdicto": verdicto,
        "resumen": resumen,
        "hallazgos": hallazgos,
        "informe_texto": stream.quitar_emojis(texto_sin_json).strip(),
    }


def _construir_procesar(
    marca: str, titulo: str, autor: dict[str, str] | None = None
) -> generaciones.Procesar:
    """Callback de post-procesado: parsea el informe y registra el historial (sin piezas).

    NO auto-crea publicaciones (esto SEÑALA, no publica). Devuelve `{informe, verdicto,
    historial_id, piezas: [], publicaciones: []}` para el sondeo del frontend. `autor`
    (atribucion por usuario, #130 Fase 1) se propaga al historial.
    """

    def procesar(salida: str, metricas: stream.MetricasRun | None) -> dict[str, object]:
        informe = parsear_informe(salida)
        historial_id = repos.registrar_historial_skill(
            SKILL_ID, marca, informe["informe_texto"], piezas=[], titulo=titulo,
            metricas=stream.metricas_a_dict(metricas), autor=autor,
        )
        return {
            "informe": informe,
            "verdicto": informe["verdicto"],
            "historial_id": historial_id,
            "piezas": [],
            "publicaciones": [],
        }

    return procesar


async def opciones(request: Request) -> Response:
    """`GET /api/qa-editorial` -> `{marcas, plataformas, skill_disponible}` (para el form)."""
    return JSONResponse(
        {
            "marcas": _marcas_lista(),
            "plataformas": list(PLATAFORMAS),
            "skill_disponible": skills_catalogo.existe(SKILL_ID),
        }
    )


async def revisar(request: Request) -> Response:
    """`POST /api/qa-editorial/revisar` -> lanza el QA EN SEGUNDO PLANO -> `{generacion}`.

    Cuerpo JSON: `{marca, texto, plataforma?, contexto?}`. Valida marca∈catalogo, que `texto`
    no este vacio ni sea gigante, y que la skill `qa-editorial` exista. Renderiza la invocacion
    y lanza el trabajo con un post-procesado propio (parsea el informe). NO bloquea: el frontend
    sondea `GET /api/generaciones/{id}` y recoge `resultado.informe` al completarse.
    """
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "El cuerpo de la petición no es válido."}, status_code=400)

    marca = datos.get("marca")
    if not isinstance(marca, str) or marca not in skills._MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)

    texto_crudo = datos.get("texto")
    texto = texto_crudo.strip() if isinstance(texto_crudo, str) else ""
    if not texto:
        return JSONResponse(
            {"error": "Pega el copy que escribió el community manager para revisarlo."},
            status_code=400,
        )
    if len(texto) > skills._MAX_TEXTO:
        return JSONResponse(
            {"error": "El texto es demasiado largo; acórtalo e inténtalo de nuevo."},
            status_code=400,
        )

    plataforma_crudo = datos.get("plataforma")
    plataforma = plataforma_crudo.strip() if isinstance(plataforma_crudo, str) else ""
    if plataforma and plataforma not in PLATAFORMAS:
        plataforma = ""  # ignoramos una plataforma desconocida (no es un dato de seguridad)
    contexto_crudo = datos.get("contexto")
    contexto = contexto_crudo.strip() if isinstance(contexto_crudo, str) else ""

    skilldef = skills_catalogo.obtener(SKILL_ID)
    if skilldef is None:
        return JSONResponse(
            {
                "error": (
                    "La skill de QA editorial no está instalada en este equipo. "
                    "Actualiza el plugin de skills de Keni e inténtalo de nuevo."
                )
            },
            status_code=400,
        )

    valores = {"texto": texto, "plataforma": plataforma, "contexto": contexto}
    redes_ids = skills.normalizar_redes(None)
    prompt = skills_catalogo.render_invocacion(skilldef, marca, valores, redes_ids)
    titulo = stream.derivar_titulo(texto)

    # Atribucion por usuario (#130 Fase 1): el QA lo dispara el usuario de la peticion.
    autor = autor_de_peticion(request)
    gen = dom_skills._lanzar_con_procesar(
        tipo="qa-editorial",
        skill=SKILL_ID,
        marca=marca,
        prompt=prompt,
        procesar=_construir_procesar(marca, titulo, autor),
        autor=autor,
    )
    return JSONResponse({"generacion": gen})


RUTAS = [
    Route("/api/qa-editorial", opciones, methods=["GET"]),
    Route("/api/qa-editorial/revisar", revisar, methods=["POST"]),
]
