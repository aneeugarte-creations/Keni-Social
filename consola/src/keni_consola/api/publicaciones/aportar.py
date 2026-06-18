"""Handler de la PUERTA CREATIVA del equipo (`/api/publicaciones/aportar`).

Un miembro del equipo "postea" material ORIGINAL (foto/nota/idea/url/clip) con marca y
eso enciende el pipeline de auto-generación. Ver el docstring de `aportar`.
"""

from __future__ import annotations

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ...dominio import extraccion_url
from ...tiempo import hoy_utc
from ._comun import (
    _MAX_TEXTO,
    _MAX_TITULO,
    ORIGEN_EQUIPO,
    _contenido_a_dict,
    _red_valida,
    _validar_marca,
    auto_responsable,
    autogen_redactar,
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

# Rotulo de la idea en el feed cuando el equipo NO da titulo: la 1a linea no vacia del
# material, acotada (un material entero como titulo gritaria en la cabecera del feed).
# Mismo criterio que el alta directa (`post_directo._titulo_desde_copy`).
_MAX_TITULO_DERIVADO = 120


def _primera_linea(texto: str) -> str:
    """Primera linea no vacia de `texto`, acotada, como titulo derivado."""
    primera = next((ln.strip() for ln in texto.splitlines() if ln.strip()), "")
    return primera[:_MAX_TITULO_DERIVADO]


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
    """POST /api/publicaciones/aportar (multipart): el EQUIPO sube material ORIGINAL.

    Es la PUERTA CREATIVA (Fase 1): un miembro del equipo "postea" material crudo (foto/
    nota/idea/url) con marca, y eso ENCIENDE el pipeline automaticamente. Crea un item del
    tablero con `origen='equipo'`, que el daemon de auto-generacion (`autogen_redactar`, gateado
    por `KENI_AUTOGEN`) recoge IGUAL que a una fuente externa para escribir el copy solo
    (sin que el equipo pulse nada). El gate humano sigue intacto: el borrador para en la cola
    de revision.

    Campos (form multipart):
      - `titulo` (opcional): de que va la pieza. El auto-copy lo usa como nota base. Si falta,
        se DERIVA (titulo de la pagina extraida de `url` > 1a linea del `material` > foto). Se
        EXIGE titulo O algun contenido (material/url/imagen/clip): un alta vacia no genera nada.
      - `marca` (OBLIGATORIO): sin marca no hay voz/tropicalizacion, asi que la auto-gen no
        arrancaria; aqui se EXIGE (a diferencia de `crear`, donde es opcional).
      - `material` (opcional): texto/nota/idea cruda -> `descripcion` (entra en la nota del
        auto-copy junto al titulo).
      - `url` (opcional): enlace de la fuente. Se VALIDA (SSRF guard) y se EXTRAE su texto
        legible EN EL SERVIDOR (`dominio.extraccion_url`, mismo camino que «copy desde nota»);
        ese texto se pliega al `material` como NOTA NO verificada para que el auto-copy redacte
        desde el contenido real del enlace (la auto-gen lee titulo+descripcion, NO descarga la
        URL por su cuenta). El enlace queda ademas como `imagen_fuente` de cada red. Si el
        enlace es de video/streaming o no se puede leer y es lo UNICO aportado, se rechaza con
        un mensaje claro; si hay otro material/foto, se sigue sin el texto del enlace.
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

    # El titulo es OPCIONAL: si falta se deriva (de la pagina extraida, del material o de la
    # foto) mas abajo. Aqui solo acotamos su longitud si vino.
    titulo_crudo = form.get("titulo")
    titulo = titulo_crudo.strip() if isinstance(titulo_crudo, str) else ""
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
    # CATEGORÍA del plan (mx/internacional/entretenimiento/evergreen…): el alta «Crear post»
    # la EXIGE para que la pieza case con una franja y se programe sola tras aprobarse. Texto
    # libre (mismo dominio que el resto): se persiste tal cual en el contenido padre.
    categoria = _texto("categoria")

    redes_objetivo = _redes_desde_form(form.get("redes"))
    if not redes_objetivo:
        # Por defecto, las redes del FORMATO foto (Instagram/X/Facebook): una galería aportada
        # es una pieza de imagen, NUNCA va a YouTube/TikTok (redes de vídeo).
        redes_objetivo = list(redes.redes_de_formato(redes.FORMATO_FOTO))

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
    # nota NO verificada. Asi entra al auto-copy igual que una nota escrita (autogen_redactar lee
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

    # Enlace de la fuente (opcional): se VALIDA (guard SSRF) y se EXTRAE su texto legible EN EL
    # SERVIDOR, plegandolo al `material` como nota NO verificada (mismo dominio que «copy desde
    # nota»). Asi el auto-copy redacta desde el contenido REAL del enlace, no desde la URL a
    # secas (la auto-gen lee titulo+descripcion, NO descarga la pagina). El enlace queda ademas
    # como `imagen_fuente` de cada red. Si no se puede leer (video/streaming, muro de pago, sin
    # texto) y es lo UNICO aportado, se rechaza con mensaje claro; si hay otro material/foto, se
    # sigue sin el texto del enlace (queda como fuente).
    url = ""
    titulo_pagina = ""
    url_crudo = form.get("url")
    if isinstance(url_crudo, str) and url_crudo.strip():
        url_limpia, err_url = extraccion_url.validar_url(url_crudo)
        if err_url is not None or url_limpia is None:
            return JSONResponse({"error": err_url or "La URL no es válida."}, status_code=400)
        url = url_limpia
        try:
            titulo_pagina, cuerpo = extraccion_url.extraer_texto(url)
        except extraccion_url.ExtraccionError as e:
            if not material and not foto:
                return JSONResponse({"error": str(e)}, status_code=400)
            titulo_pagina = ""
        else:
            nota = extraccion_url.componer_nota_no_verificada(url, titulo_pagina, cuerpo)
            material = f"{material}\n\n{nota}".strip()[:_MAX_TEXTO] if material else nota[:_MAX_TEXTO]

    # Titulo derivado si el equipo no lo dio: titulo real de la pagina > 1a linea del material
    # > generico de foto. Exigimos titulo O algun contenido (material/url/imagen/clip): un alta
    # del todo vacia no tiene de que generar copy.
    if not titulo:
        titulo = titulo_pagina.strip()[:_MAX_TITULO_DERIVADO] or _primera_linea(material)
    if not titulo and foto:
        titulo = "Foto del equipo"
    if not titulo:
        return JSONResponse(
            {"error": "Aporta un título, un texto, un enlace o una imagen."},
            status_code=400,
        )

    # «La lista» (reparto PULL, todas las marcas): la pieza nace LIBRE y el equipo la coge
    # desde «Por cubrir». `responsable_automatico` devuelve None hoy (el gancho de un futuro
    # PUSH por marca vive en él, no aquí).
    responsable = auto_responsable.responsable_automatico(marca)

    item = repos.crear_publicacion(
        clase="contenido",
        flujo=flujo,
        titulo=titulo,
        descripcion=material,
        marca=marca,
        prioridad="media",
        fecha_objetivo=hoy_utc().isoformat(),
        autor=autor_de_peticion(request),
        responsable=responsable,
        origen=ORIGEN_EQUIPO,
        # El equipo trae la imagen de fuera => tipo "galeria" (foto propia), no IA ni fuente.
        tipo_contenido="galeria",
        categoria=categoria,
    )

    # Una fila por red, con la checklist "pendientes": el auto-copy rellenara `copy`
    # (falta_copy -> 0) y el Flujo B el arte sobre la `foto`. `falta_imagen` arranca segun
    # haya foto aportada o no (con foto, queda la materia prima; el arte por red es paso B).
    for red in redes_objetivo:
        repos.crear_pieza_fila(
            publicacion_id=item["id"],
            red=red,
            falta_copy=True,
            falta_imagen=True,
            foto=foto,
            imagen_fuente=url,
        )

    # Generacion de copy en SEGUNDO PLANO, mismo camino que Radar/Breaking/usar-noticia
    # (`autogen_redactar.lanzar_para_topic`): compone la nota desde el tema, infiere redes y
    # encola un `claude -p` cuyo borrador rellena estas piezas (verificacion + voz de marca).
    # BEST-EFFORT: si la skill o la cola fallan, NO rompe el alta; la etapa de Redactar del
    # pipeline lo recoge en el siguiente barrido (red de seguridad, ya que origen='equipo').
    genero = False
    if marca:
        try:
            genero = autogen_redactar.lanzar_para_topic(item) is not None
        except Exception:  # noqa: BLE001 -- la generacion es opcional; nunca tumba el alta
            genero = False

    plataformas = repos.listar_piezas_fila(item["id"])
    return JSONResponse(
        {"contenido": _contenido_a_dict(item, plataformas), "copy_en_proceso": genero}
    )
