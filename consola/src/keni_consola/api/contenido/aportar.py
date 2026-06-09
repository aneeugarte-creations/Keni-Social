"""Handler de la PUERTA CREATIVA del equipo (`/api/contenido/aportar`).

Un miembro del equipo "postea" material ORIGINAL (foto/nota/idea/url/clip) con marca y
eso enciende el pipeline de auto-generación. Ver el docstring de `aportar`.
"""

from __future__ import annotations

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ...tiempo import hoy_utc
from ._comun import (
    _MAX_TEXTO,
    _MAX_TITULO,
    ORIGEN_EQUIPO,
    _contenido_a_dict,
    _red_valida,
    _validar_marca,
    auto_responsable,
    autor_de_peticion,
    media,
    redes,
    repos,
    transcripcion,
)

# La intencion editorial que el equipo opcionalmente declara al aportar material,
# mapeada al `flujo` del tablero. "breaking" => importante (de hoy), "evergreen" =>
# evergreen, "hilo" => importante (un hilo es contenido del momento). Ausente => "".
_INTENCION_A_FLUJO: dict[str, str] = {
    "breaking": "importante",
    "evergreen": "evergreen",
    "hilo": "importante",
}


def _redes_desde_form(valor: object) -> list[str]:
    """Lee `redes` de un form multipart: lista, o cadena separada por comas.

    El cliente puede mandar `redes` repetido (varias entradas con el mismo nombre) o una
    sola cadena "instagram,x". Devuelve solo redes canonicas validas, sin duplicados.
    """
    crudas: list[str] = []
    if isinstance(valor, list):
        for v in valor:
            if isinstance(v, str):
                crudas.extend(p.strip() for p in v.split(","))
    elif isinstance(valor, str):
        crudas = [p.strip() for p in valor.split(",")]
    vistas = dict.fromkeys(r for r in crudas if r and _red_valida(r))
    return list(vistas)


async def aportar(request: Request) -> Response:
    """POST /api/contenido/aportar (multipart): el EQUIPO sube material ORIGINAL.

    Es la PUERTA CREATIVA (Fase 1): un miembro del equipo "postea" material crudo (foto/
    nota/idea/url) con marca, y eso ENCIENDE el pipeline automaticamente. Crea un item del
    tablero con `origen='equipo'`, que el daemon de auto-generacion (`autogen_copy`, gateado
    por `KENI_AUTOGEN`) recoge IGUAL que a una fuente externa para escribir el copy solo
    (sin que el equipo pulse nada). El gate humano sigue intacto: el borrador para en la cola
    de revision.

    Campos (form multipart):
      - `titulo` (OBLIGATORIO): de que va la pieza. El auto-copy lo usa como nota base.
      - `marca` (OBLIGATORIO): sin marca no hay voz/tropicalizacion, asi que la auto-gen no
        arrancaria; aqui se EXIGE (a diferencia de `crear`, donde es opcional).
      - `material` (opcional): texto/nota/idea cruda -> `descripcion` (entra en la nota del
        auto-copy junto al titulo).
      - `url` (opcional): enlace de la fuente del material -> `imagen_fuente` de cada red.
      - `intencion` (opcional): 'breaking'|'evergreen'|'hilo' -> mapea el `flujo`.
      - `redes` (opcional): redes objetivo (lista o "instagram,x"); por defecto, las canonicas.
      - `imagen` (opcional): la FOTO que el equipo trae de fuera (la IA NO la genera). Se sube
        al almacen de media y se adjunta como `foto` (foto cruda de fondo) de cada red; el
        arte/marca/formatos los aplica luego el Flujo B sobre esa foto.
      - `clip` (opcional): un VIDEO/AUDIO que el equipo graba (declaración, jugada, idea hablada).
        Se TRANSCRIBE EN LOCAL (whisper.cpp, mismo camino que la skill clip-a-copy: el audio NO
        sale de la máquina) y el texto se anexa al `material` como NOTA NO verificada (igual que
        cualquier nota cruda): el auto-copy lo redacta y el borrador para en la cola de revisión.
        El clip NO se guarda como media (v1 = solo su transcripción alimenta el copy).

    -> `{contenido}` | 400.
    """
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 -- multipart malformado => mensaje claro, sin traza
        return JSONResponse({"error": "Formulario inválido."}, status_code=400)

    titulo = form.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "El material necesita un título."}, status_code=400)
    if len(titulo) > _MAX_TITULO:
        return JSONResponse({"error": "El título es demasiado largo."}, status_code=400)

    # La marca es OBLIGATORIA en la puerta creativa: sin voz de marca no hay auto-generacion.
    marca, err = _validar_marca(form.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)
    if not marca:
        return JSONResponse(
            {"error": "Elige una marca: sin marca no se puede generar el copy."},
            status_code=400,
        )

    intencion = form.get("intencion")
    flujo = _INTENCION_A_FLUJO.get(intencion if isinstance(intencion, str) else "", "")

    def _texto(clave: str) -> str:
        v = form.get(clave)
        return v.strip()[:_MAX_TEXTO] if isinstance(v, str) else ""

    material = _texto("material")
    url = ""
    url_crudo = form.get("url")
    if isinstance(url_crudo, str) and url_crudo.strip():
        url = url_crudo.strip()[:_MAX_TEXTO]

    redes_objetivo = _redes_desde_form(form.get("redes"))
    if not redes_objetivo:
        # Por defecto, todas las redes canonicas (mismo defecto que el auto-copy).
        redes_objetivo = list(redes.ids())

    # Imagen aportada (opcional): el equipo trae la foto de fuera; la subimos al almacen.
    foto = ""
    archivo = form.get("imagen")
    if isinstance(archivo, UploadFile) and (archivo.filename or ""):
        try:
            foto = await media.guardar_subida(archivo)
        except media.MediaError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
            return JSONResponse({"error": "No se pudo guardar la imagen."}, status_code=500)

    # Clip de video/audio (opcional): se TRANSCRIBE EN LOCAL (whisper.cpp; el audio no sale de
    # la maquina, mismo camino que la skill clip-a-copy) y el texto se anexa al `material` como
    # nota NO verificada. Asi entra al auto-copy igual que una nota escrita (autogen_copy lee
    # titulo+descripcion). El clip NO se guarda; solo su transcripcion alimenta el copy.
    clip = form.get("clip")
    if isinstance(clip, UploadFile) and (clip.filename or ""):
        try:
            texto = await transcripcion.transcribir_subida(clip)
        except transcripcion.TranscripcionError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
            return JSONResponse({"error": "No se pudo transcribir el clip."}, status_code=500)
        if texto:
            # Etiqueta de procedencia: el copy debe saber que esto sale del audio del equipo
            # (no verificado), no de una fuente. Se concatena al material existente.
            bloque = f"Transcripción del clip aportado (sin verificar): {texto}"
            material = f"{material}\n\n{bloque}".strip()[:_MAX_TEXTO] if material else bloque[:_MAX_TEXTO]

    # Reparto automatico de responsable desde la rota del dia (mismo patron que `crear`):
    # el equipo solo aporta; el reparto es automatico. Degrada a None sin romper.
    responsable = auto_responsable.responsable_automatico(marca)

    item = repos.crear_contenido(
        clase="contenido",
        flujo=flujo,
        titulo=titulo.strip(),
        descripcion=material,
        marca=marca,
        prioridad="media",
        fecha_objetivo=hoy_utc().isoformat(),
        autor=autor_de_peticion(request),
        responsable=responsable,
        origen=ORIGEN_EQUIPO,
        # El equipo trae la imagen de fuera => tipo "galeria" (foto propia), no IA ni fuente.
        tipo_contenido="galeria",
    )

    # Una fila por red, con la checklist "pendientes": el auto-copy rellenara `copy`
    # (falta_copy -> 0) y el Flujo B el arte sobre la `foto`. `falta_imagen` arranca segun
    # haya foto aportada o no (con foto, queda la materia prima; el arte por red es paso B).
    for red in redes_objetivo:
        repos.crear_contenido_plataforma(
            contenido_id=item["id"],
            red=red,
            falta_copy=True,
            falta_imagen=True,
            foto=foto,
            imagen_fuente=url,
        )

    plataformas = repos.listar_contenido_plataforma(item["id"])
    return JSONResponse({"contenido": _contenido_a_dict(item, plataformas)})
