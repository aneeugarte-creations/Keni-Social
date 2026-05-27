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

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import skills_catalogo
from .._http_json import leer_json
from ..dominio import jobspec, stream
from ..dominio import qa_editorial as dom_qa
from ..dominio import skills as dom_skills
from ..seguridad import autor_de_peticion
from . import skills

# Id de la skill que hace el QA (vive en skills-copy/.claude/skills/).
SKILL_ID = dom_qa.SKILL_ID

# Parseo del informe + post-procesado viven AHORA en `dominio.qa_editorial` (para que el
# worker los reconstruya sin importar de `api/`, #130 Fase 2). Se reexportan aqui por compat
# de referencias (los tests llaman a `parsear_informe`).
parsear_informe = dom_qa.parsear_informe
_construir_procesar = dom_qa.construir_procesar_qa
_VERDICTO_POR_SEMAFORO = dom_qa._VERDICTO_POR_SEMAFORO
_TIPOS = dom_qa._TIPOS
_GRAVEDADES = dom_qa._GRAVEDADES
_MAX_HALLAZGOS = dom_qa._MAX_HALLAZGOS

# Plataformas que se pueden indicar (para validar el limite de caracteres). El value es la
# etiqueta que entiende la skill / `plataformas.md`; "" = no validar ningun limite.
PLATAFORMAS: tuple[str, ...] = (
    "X / Twitter",
    "Instagram",
    "Facebook",
    "TikTok",
    "YouTube",
)


def _marcas_lista() -> list[dict[str, str]]:
    """Marcas para el selector del formulario (id + nombre humano)."""
    return [{"id": mid, "nombre": nombre} for mid, nombre in skills.MARCAS]


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
    # ENCOLA (#130 Fase 2); el worker reconstruye el parseo del informe desde el `spec`.
    autor = autor_de_peticion(request)
    gen = dom_skills._lanzar_con_procesar(
        tipo="qa-editorial",
        skill=SKILL_ID,
        marca=marca,
        prompt=prompt,
        procesar=_construir_procesar(marca, titulo, autor),
        procesar_spec=jobspec.construir_qa(marca=marca, titulo=titulo, autor=autor),
        autor=autor,
    )
    return JSONResponse({"generacion": gen})


RUTAS = [
    Route("/api/qa-editorial", opciones, methods=["GET"]),
    Route("/api/qa-editorial/revisar", revisar, methods=["POST"]),
]
