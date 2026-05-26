"""API Termometro mundial: config + generacion del posteo de galeria diario.

El Termometro mundial es el posteo de GALERIA con las 5-8 noticias internacionales
mas importantes (una por region). Esta API:

  - `GET  /api/termometro`          -> config guardada + si la skill esta instalada +
                                       marcas y regiones sugeridas (para el formulario).
  - `PUT  /api/termometro/config`   -> guarda la config (numero 5-8, regiones, hora, marca).
  - `POST /api/termometro/generar`  -> lanza la generacion EN SEGUNDO PLANO reutilizando
                                       el motor de Skills (`skills.lanzar_generacion_skill`)
                                       con la skill `termometro-mundial` (salida documento).

No bloquea: `generar` responde de inmediato con `{generacion}` (estado "ejecutando")
y el frontend sondea `GET /api/generaciones/{id}` hasta el estado terminal, igual que
"Generar copy". El cron de las 7:00 (`keni-termometro`) usa la misma config pero corre
la skill de forma sincrona (ver `consola.termometro_cli`).

SEGURIDAD: la marca se valida contra el catalogo (`skills._MARCAS_IDS`); la skill contra
el catalogo de archivos; el texto viaja como argumento de subprocess (sin shell). Errores
en espanol, sin tracebacks.
"""

from __future__ import annotations

from datetime import date

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import skills_catalogo, termometro
from .._http_json import leer_json
from . import skills

# Id de la skill que arma el termometro (vive en skills-copy/.claude/skills/).
SKILL_ID = "termometro-mundial"

# Regiones sugeridas en la UI (el reparto por defecto de la skill si no se indican otras).
REGIONES_SUGERIDAS: tuple[str, ...] = (
    "EEUU",
    "América Latina",
    "Europa",
    "Asia",
    "Medio Oriente",
    "África",
    "Oceanía",
)


def _marcas_lista() -> list[dict[str, str]]:
    """Marcas para el selector del formulario (id + nombre humano)."""
    return [{"id": mid, "nombre": nombre} for mid, nombre in skills.MARCAS]


async def obtener_config(request: Request) -> Response:
    """`GET /api/termometro` -> `{config, skill_disponible, marcas, regiones_sugeridas}`."""
    return JSONResponse(
        {
            "config": termometro.obtener(),
            "skill_disponible": skills_catalogo.existe(SKILL_ID),
            "marcas": _marcas_lista(),
            "regiones_sugeridas": list(REGIONES_SUGERIDAS),
        }
    )


async def guardar_config(request: Request) -> Response:
    """`PUT /api/termometro/config` -> guarda `{numero?, regiones?, hora?, marca?}` -> `{config}`."""
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "La configuración del termómetro no es válida."}, status_code=400)
    try:
        config = termometro.guardar(datos)
    except termometro.TermometroConfigError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"config": config})


def construir_valores(datos: dict[str, object]) -> dict[str, str]:
    """Extrae los valores de los campos de la skill desde el cuerpo (todo como texto)."""
    valores: dict[str, str] = {}
    for campo in ("noticias", "numero", "regiones", "fecha"):
        valor = datos.get(campo)
        valores[campo] = valor.strip() if isinstance(valor, str) else ""
    return valores


def titulo_termometro(fecha: str) -> str:
    """Titulo legible para el historial: 'Termómetro mundial · <fecha>'."""
    return f"Termómetro mundial · {fecha or date.today().isoformat()}"


async def generar(request: Request) -> Response:
    """`POST /api/termometro/generar` -> lanza la generacion EN SEGUNDO PLANO -> `{generacion}`.

    Cuerpo JSON: `{marca, noticias, numero?, regiones?, fecha?}`. Valida marca∈catalogo,
    que `noticias` no este vacio y que la skill `termometro-mundial` exista. Renderiza la
    invocacion y delega en `skills.lanzar_generacion_skill` (salida documento: registra el
    historial, sin auto-crear publicaciones). El frontend sondea `GET /api/generaciones/{id}`.
    """
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "El cuerpo de la petición no es válido."}, status_code=400)

    marca = datos.get("marca")
    if not isinstance(marca, str) or marca not in skills._MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)

    valores = construir_valores(datos)
    if not valores["noticias"]:
        return JSONResponse(
            {"error": "Pega las noticias internacionales del día para armar el termómetro."},
            status_code=400,
        )
    if len(valores["noticias"]) > skills._MAX_TEXTO:
        return JSONResponse(
            {"error": "El texto es demasiado largo; acórtalo e inténtalo de nuevo."}, status_code=400
        )

    skilldef = skills_catalogo.obtener(SKILL_ID)
    if skilldef is None:
        return JSONResponse(
            {
                "error": (
                    "La skill del termómetro no está instalada en este equipo. "
                    "Actualiza el plugin de skills de Keni e inténtalo de nuevo."
                )
            },
            status_code=400,
        )

    redes_ids = skills.normalizar_redes(None)
    prompt = skills_catalogo.render_invocacion(skilldef, marca, valores, redes_ids)
    gen = skills.lanzar_generacion_skill(
        skilldef=skilldef,
        marca=marca,
        prompt=prompt,
        redes_ids=redes_ids,
        titulo_base=titulo_termometro(valores["fecha"]),
    )
    return JSONResponse({"generacion": gen})


RUTAS = [
    Route("/api/termometro", obtener_config, methods=["GET"]),
    Route("/api/termometro/config", guardar_config, methods=["PUT"]),
    Route("/api/termometro/generar", generar, methods=["POST"]),
]
