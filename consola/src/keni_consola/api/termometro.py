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

from .. import biblioteca, marcas, repos, termometro
from .._http_json import leer_json
from ..dominio import copy as dom_copy
from ..dominio import generar as gen_dom
from ..dominio import jobspec
from ..seguridad import autor_de_peticion

# Prompt base (Biblioteca) que arma el termometro + etiqueta de origen del historial.
PROMPT_ID = "prompt/termometro-mundial"
ORIGEN_HISTORIAL = "termometro-mundial"

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
    return [{"id": mid, "nombre": nombre} for mid, nombre in marcas.opciones()]


def _ultimo_resultado() -> dict[str, str] | None:
    """El último termómetro generado (fuente PERMANENTE del resultado de la página).

    El resultado del termómetro NO se persiste en el cliente: el historial es su registro
    duradero. Devuelve la entrada de historial más reciente con origen `termometro-mundial`
    (documento + id, para repintar `ResultadoDocumento`), o `None` si aún no hay ninguna.
    Un termómetro nuevo la reemplaza (queda como la más reciente); borrarla del historial la
    elimina. El listado viene recientes-primero, así que basta el primer match.
    """
    for e in repos.listar_historial_skills():
        if e.get("skill") == ORIGEN_HISTORIAL:
            return {
                "historial_id": e["id"],
                "documento": e.get("resultado", "") or "",
                "titulo": e.get("titulo", "") or "",
                "fecha": e.get("fecha", "") or "",
                "marca": e.get("marca", "") or "",
            }
    return None


async def obtener_config(request: Request) -> Response:
    """`GET /api/termometro` -> `{config, skill_disponible, marcas, regiones_sugeridas, ultimo}`.

    `skill_disponible` se conserva por compat del frontend: el prompt base viaja en la
    semilla del paquete, así que siempre está disponible (salvo borrado manual del store).
    `ultimo` es el último termómetro generado (o `null`): la página lo usa como resultado
    PERSISTENTE entre navegaciones, sin depender del estado de cliente.
    """
    return JSONResponse(
        {
            "config": termometro.obtener(),
            "skill_disponible": biblioteca.cuerpo_efectivo(PROMPT_ID) is not None,
            "marcas": _marcas_lista(),
            "regiones_sugeridas": list(REGIONES_SUGERIDAS),
            "ultimo": _ultimo_resultado(),
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
    if not gen_dom.marca_valida(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)

    valores = construir_valores(datos)
    if not valores["noticias"]:
        return JSONResponse(
            {"error": "Pega las noticias internacionales del día para armar el termómetro."},
            status_code=400,
        )
    if len(valores["noticias"]) > gen_dom.MAX_TEXTO:
        return JSONResponse(
            {"error": "El texto es demasiado largo; acórtalo e inténtalo de nuevo."}, status_code=400
        )

    cuerpo = biblioteca.cuerpo_efectivo(PROMPT_ID)
    if cuerpo is None:
        return JSONResponse(
            {"error": "No está disponible el prompt del termómetro. Reinstala la Consola."},
            status_code=400,
        )

    titulo = titulo_termometro(valores["fecha"])
    autor = autor_de_peticion(request)
    procesar_spec = jobspec.construir_documento(
        skill=ORIGEN_HISTORIAL, marca=marca, titulo_base=titulo, autor=autor
    )
    gen = gen_dom.lanzar(
        tipo="copy",
        titulo=titulo,
        marca=marca,
        prompt=gen_dom.componer(cuerpo, biblioteca.editoriales_de_marca(marca), _contexto(valores)),
        procesar=dom_copy.construir_procesar_documento(
            ORIGEN_HISTORIAL, marca, titulo_base=titulo, autor=autor
        ),
        procesar_spec=procesar_spec,
        autor=autor,
    )
    return JSONResponse({"generacion": gen})


def _contexto(valores: dict[str, str]) -> str:
    """Compone el bloque de contexto del termómetro (parámetros + noticias del día)."""
    extras: list[str] = []
    if valores["numero"]:
        extras.append(f"Número de slides: {valores['numero']}")
    if valores["regiones"]:
        extras.append(f"Regiones a cubrir: {valores['regiones']}")
    if valores["fecha"]:
        extras.append(f"Fecha: {valores['fecha']}")
    cabecera = ("\n".join(extras) + "\n\n") if extras else ""
    return f"{cabecera}Noticias del día:\n\n{valores['noticias']}"


RUTAS = [
    Route("/api/termometro", obtener_config, methods=["GET"]),
    Route("/api/termometro/config", guardar_config, methods=["PUT"]),
    Route("/api/termometro/generar", generar, methods=["POST"]),
]
