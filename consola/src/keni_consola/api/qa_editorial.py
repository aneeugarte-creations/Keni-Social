"""API QA editorial: revisa el copy YA escrito por el community y devuelve un INFORME.

Ficha F3 (issue #143). NUEVO MODO de la verificacion editorial: hoy los prompts de copy
solo se auto-verifican lo que ELLOS generan; aqui aplicamos esa misma capacidad a TEXTO
AJENO (el copy que escribio el community manager) y devolvemos un veredicto 🟢/🟡/🔴 con
los hallazgos clasificados (ortografia / dato / legal / voz), cada uno con su correccion
SUGERIDA.

Frontera del producto (no negociable): Keni **SEÑALA**, el equipo **decide**. La salida es
un INFORME; puede OFRECER una correccion, pero NO la aplica ni reescribe el copy, y NUNCA
publica. Honestidad: un dato que no se puede comprobar se marca como "no verificable", no se
inventa.

  - `GET  /api/qa-editorial`          -> marcas + plataformas + si el prompt esta instalado.
  - `POST /api/qa-editorial/revisar`  (JSON `{marca, texto, plataforma?, contexto?}`) ->
    `{generacion}` (estado "ejecutando"); el frontend SONDEA `GET /api/generaciones/{id}` y,
    al completar, recoge `resultado = {informe: <reporte>}`.

Reutiliza la infra de generaciones en background (mismo sondeo que copy/verificacion) y la
Texto de Prompts (el prompt `qa-editorial` con su contexto editorial versionado).
El POST-PROCESADO parsea el bloque ```json de hallazgos que emite el prompt en un reporte
estructurado para la UI; cae con elegancia a un informe de solo-texto si no hay JSON valido.

SEGURIDAD: marca∈catalogo unico; prompt∈Texto; el texto viaja como argumento
de subprocess (sin shell). Errores en espanol, sin tracebacks.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import libtexto, marcas, repos
from .._http_json import leer_json
from ..dominio import generar as gen_dom
from ..dominio import jobspec, stream
from ..dominio import qa_editorial as dom_qa
from ..seguridad import autor_de_peticion

# Prompt base (Texto) que hace el QA + etiqueta de origen del historial.
PROMPT_ID = "prompt/qa-editorial"
ORIGEN_HISTORIAL = dom_qa.PROMPT_ID

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
# etiqueta que entiende el prompt / `plataformas.md`; "" = no validar ningun limite.
PLATAFORMAS: tuple[str, ...] = (
    "X / Twitter",
    "Instagram",
    "Facebook",
    "TikTok",
    "YouTube",
)


def _marcas_lista() -> list[dict[str, str]]:
    """Marcas para el selector del formulario (id + nombre humano)."""
    return [{"id": mid, "nombre": nombre} for mid, nombre in marcas.opciones()]


async def opciones(request: Request) -> Response:
    """`GET /api/qa-editorial` -> `{marcas, plataformas, prompt_disponible}` (para el form).

    `prompt_disponible` indica si el prompt base está instalado: viaja en la semilla
    del paquete, así que siempre está disponible (salvo borrado manual del store).
    """
    return JSONResponse(
        {
            "marcas": _marcas_lista(),
            "plataformas": list(PLATAFORMAS),
            "prompt_disponible": libtexto.cuerpo_efectivo(PROMPT_ID) is not None,
        }
    )


async def revisar(request: Request) -> Response:
    """`POST /api/qa-editorial/revisar` -> lanza el QA EN SEGUNDO PLANO -> `{generacion}`.

    Cuerpo JSON: `{marca, texto, plataforma?, contexto?}`. Valida marca∈catalogo, que `texto`
    no este vacio ni sea gigante, y que el prompt `qa-editorial` exista. Renderiza la invocacion
    y lanza el trabajo con un post-procesado propio (parsea el informe). NO bloquea: el frontend
    sondea `GET /api/generaciones/{id}` y recoge `resultado.informe` al completarse.
    """
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "El cuerpo de la petición no es válido."}, status_code=400)

    marca = datos.get("marca")
    if not gen_dom.marca_valida(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)

    texto_crudo = datos.get("texto")
    texto = texto_crudo.strip() if isinstance(texto_crudo, str) else ""
    if not texto:
        return JSONResponse(
            {"error": "Pega el copy que escribió el community manager para revisarlo."},
            status_code=400,
        )
    if len(texto) > gen_dom.MAX_TEXTO:
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

    # APROBADOR AUTOMATICO (item A): si la revision se lanza SOBRE una pieza concreta, atamos el
    # veredicto a ella (plataforma_id/contenido_id) y guardamos el hash del copy revisado para
    # invalidarlo si el copy cambia (item D). `plataforma_id` desconocido se ignora (sin atar).
    plataforma_id_crudo = datos.get("plataforma_id")
    plataforma_id = plataforma_id_crudo.strip() if isinstance(plataforma_id_crudo, str) else ""
    contenido_id = ""
    if plataforma_id:
        pieza = repos.obtener_contenido_plataforma(plataforma_id)
        if pieza is None:
            plataforma_id = ""  # pieza inexistente: revision suelta, sin atar
        else:
            contenido_id = pieza.get("contenido_id", "") or ""
    copy_hash = dom_qa.hash_copy(texto)

    cuerpo = libtexto.cuerpo_efectivo(PROMPT_ID)
    if cuerpo is None:
        return JSONResponse(
            {"error": "No está disponible el prompt de QA editorial. Reinstala la Consola."},
            status_code=400,
        )

    titulo = stream.derivar_titulo(texto)
    # Atribucion por usuario (#130 Fase 1): el QA lo dispara el usuario de la peticion.
    # ENCOLA (#130 Fase 2); el worker reconstruye el parseo del informe desde el `spec`.
    autor = autor_de_peticion(request)
    gen = gen_dom.lanzar(
        tipo="qa-editorial",
        titulo="QA editorial",
        marca=marca,
        prompt=gen_dom.componer(
            cuerpo, libtexto.editoriales_de_marca(marca), _contexto_qa(texto, plataforma, contexto)
        ),
        procesar=_construir_procesar(
            marca, titulo, autor,
            plataforma_id=plataforma_id, contenido_id=contenido_id, copy_hash=copy_hash,
        ),
        procesar_spec=jobspec.construir_qa(
            marca=marca, titulo=titulo, autor=autor,
            plataforma_id=plataforma_id, contenido_id=contenido_id, copy_hash=copy_hash,
        ),
        autor=autor,
        # QA editorial = VERIFICACIÓN de datos con SALIDA ESTRUCTURADA (se parsea a un informe
        # 🟢/🟡/🔴 con hallazgos; el usuario no ve la salida cruda). Verificar un dato puede
        # requerir LEER la fuente, así que NO se le veta la web. Queda la veta global `Bash Write
        # Edit`.
    )
    return JSONResponse({"generacion": gen})


def _contexto_qa(texto: str, plataforma: str, contexto: str) -> str:
    """Bloque de contexto del QA: plataforma + contexto + el copy a revisar."""
    partes: list[str] = []
    if plataforma:
        partes.append(f"Plataforma de destino: {plataforma}")
    if contexto:
        partes.append(f"Contexto adicional: {contexto}")
    partes.append("Copy a revisar:\n\n" + texto)
    return "\n\n".join(partes)


RUTAS = [
    Route("/api/qa-editorial", opciones, methods=["GET"]),
    Route("/api/qa-editorial/revisar", revisar, methods=["POST"]),
]
