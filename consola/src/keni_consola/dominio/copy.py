"""Post-procesado de generaciones de COPY/DOCUMENTO (parseo + artefactos), NEUTRO.

Estas fábricas convierten la salida cruda de `claude -p` en los ARTEFACTOS de la Consola
(piezas por red, publicaciones-borrador, historial, imágenes previsualizadas). Son DOMINIO
PURO: dependen de `stream` (parseo), `repos` (historial), `dominio.publicaciones` (handoff
A→C de borradores), `redes` y `media`. NO dependen del catálogo de skills.

`jobspec.reconstruir_procesar` los reconstruye en el worker desde el `spec`.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from .. import limites_plataforma, patrones_marca, redes, repos
from . import publicaciones as contrato_publicaciones
from . import stream

if TYPE_CHECKING:
    # `generaciones` solo se usa en anotaciones (`-> generaciones.Procesar`). Mantener el
    # dominio NEUTRO: no importa de `generaciones` en runtime (invariante de `dominio/`).
    from .. import generaciones

_log = logging.getLogger("keni_consola.copy")

# --------------------------------------------------------------------------- #
# Recolección de IMAGENES de salida (skills/prompts de imagen)                     #
# --------------------------------------------------------------------------- #

# Extensiones de imagen que reconocemos en la salida.
_EXT_IMAGEN = ("png", "jpg", "jpeg", "webp", "gif")

# Ruta a un archivo de imagen dentro del texto (absoluta o relativa con separadores).
_RE_RUTA_IMAGEN = re.compile(
    r"(/?(?:[^\s\"'`<>|]+/)+[^\s\"'`<>|]+\.(?:" + "|".join(_EXT_IMAGEN) + r"))",
    re.IGNORECASE,
)

# Tope defensivo de imagenes que importamos de una sola salida.
_MAX_IMAGENES = 12


def _rutas_imagen_en_texto(salida: str) -> list[str]:
    """Extrae rutas de archivos de imagen mencionadas en la salida (orden, sin duplicar)."""
    if not salida:
        return []
    vistas: list[str] = []
    for m in _RE_RUTA_IMAGEN.finditer(salida):
        ruta = m.group(1)
        if ruta not in vistas:
            vistas.append(ruta)
    return vistas


def recolectar_imagenes(salida: str) -> list[dict[str, str]]:
    """Importa al almacen de media las imagenes que la salida menciona por ruta.

    Tolerante: una ruta inexistente o no importable se OMITE (la previsualizacion es un
    extra, nunca rompe la generacion). Limita a `_MAX_IMAGENES`.
    """
    from .. import media

    imagenes: list[dict[str, str]] = []
    for ruta in _rutas_imagen_en_texto(salida):
        if len(imagenes) >= _MAX_IMAGENES:
            break
        try:
            nombre = media.importar_imagen(ruta)
        except media.MediaError:
            continue
        except Exception:  # noqa: BLE001 -- la previsualizacion nunca rompe la generacion
            continue
        imagenes.append({"nombre": nombre, "url": f"/api/media/{nombre}"})
    return imagenes


# --------------------------------------------------------------------------- #
# Validacion de piezas ANTES de persistir (no crear borradores rotos)          #
# --------------------------------------------------------------------------- #

# Tuit de un HILO dentro de `texto` (contrato del prompt de copy): linea que ABRE con la
# numeracion "1/n ", "2/n "… Ver `instruccion_redes` y `copy-desde-nota.md` §Bloque final.
_RE_TUIT_HILO = re.compile(r"^\d{1,2}/\d{1,2}(?:\s|$)")

# Separador de SLIDES de un CARRUSEL dentro de `texto`: una linea con solo `---`.
_RE_SEPARADOR_SLIDE = re.compile(r"^\s*---\s*$")


def _intervalos_publicables(texto: str) -> list[str]:
    """Intervalos del `texto` de una pieza a validar contra el limite tecnico de su red.

    CONTRATO DE PIEZAS COMPUESTAS: un hilo viaja numerado dentro de `texto` (cada tuit abre
    con "1/n ") y un carrusel con las slides separadas por una linea `---`; el limite de la
    red aplica a CADA intervalo (tuit/slide), no al texto entero. Pieza simple = un unico intervalo.
    """
    lineas = texto.splitlines()
    inicios = [i for i, ln in enumerate(lineas) if _RE_TUIT_HILO.match(ln.strip())]
    if len(inicios) >= 2:  # un hilo de verdad tiene 2+ tuits numerados
        intervalos = [
            "\n".join(lineas[ini:fin]).strip()
            for ini, fin in zip(inicios, [*inicios[1:], len(lineas)], strict=True)
        ]
        return [t for t in intervalos if t]
    if any(_RE_SEPARADOR_SLIDE.match(ln) for ln in lineas):
        partes: list[list[str]] = [[]]
        for ln in lineas:
            if _RE_SEPARADOR_SLIDE.match(ln):
                partes.append([])
            else:
                partes[-1].append(ln)
        intervalos = ["\n".join(p).strip() for p in partes]
        return [t for t in intervalos if t]
    return [texto]


def _motivo_invalida(pieza: dict[str, object]) -> str | None:
    """Motivo por el que una pieza NO debe convertirse en borrador, o None si es valida.

    Valida red conocida (`redes.es_red`), texto no vacio y longitud dentro del limite
    tecnico de la red (`limites_plataforma`, la misma fuente que ancla el prompt).
    """
    red = pieza.get("red")
    if not isinstance(red, str) or not redes.es_red(red):
        return f"red desconocida ({red!r})"
    contenido = pieza.get("contenido")
    if not isinstance(contenido, str) or not contenido.strip():
        return f"{red}: texto vacío"
    intervalos = _intervalos_publicables(contenido)
    if not intervalos:  # solo separadores/numeración sin texto: equivale a vacío
        return f"{red}: texto vacío"
    limite = limites_plataforma.limite_de(red)
    if limite is not None:
        mas_largo = max(len(t) for t in intervalos)
        if mas_largo > limite:
            return f"{red}: {mas_largo} caracteres (límite {limite})"
    return None


_RE_HASHTAG = re.compile(r"#(\w+)", re.UNICODE)


def _inyectar_hashtags(texto: str, tags: list[str], *, red: str) -> str:
    """Añade al FINAL del copy los hashtags de la línea que NO estén ya, sin pasarse del límite
    técnico de la red.

    - Dedup case-insensitive contra los hashtags YA presentes en el texto (la IA pudo ponerlos).
    - Respeta `limites_plataforma`: añade los que QUEPAN (mide el intervalo más largo, igual que
      `_motivo_invalida`); si alguno no cabe, lo salta. Si ninguno cabe, deja el texto igual
      (el badge marcará «Faltan hashtags» y el equipo lo ajusta en revisión).
    - Inline al final (separado por espacio): compacto y seguro para el límite de X.
    """
    if not tags:
        return texto
    presentes = {m.lower() for m in _RE_HASHTAG.findall(texto)}
    faltan = [t for t in tags if t.lower() not in presentes]
    if not faltan:
        return texto
    limite = limites_plataforma.limite_de(red)
    resultado = texto.rstrip()
    for tag in faltan:
        candidato = f"{resultado} #{tag}" if resultado else f"#{tag}"
        if limite is not None:
            intervalos = _intervalos_publicables(candidato)
            mas_largo = max((len(t) for t in intervalos), default=len(candidato))
            if mas_largo > limite:
                continue  # este hashtag no cabe; probamos el siguiente
        resultado = candidato
    return resultado


def _avisar_piezas_descartadas(motivos: list[str], *, contenido_id: str, marca: str) -> None:
    """Deja rastro de las piezas descartadas: WARN + nota en el tema (si lo hay).

    Sigue el patron de avisos en `contenido.notas` (ver `pipeline_contenido._admitir`).
    Best-effort: nunca rompe el post-procesado (las piezas validas del lote ya se crearon).
    """
    detalle = "; ".join(motivos)
    _log.warning(
        "copy: %d pieza(s) descartada(s) tema=%s marca=%s: %s",
        len(motivos), contenido_id or "-", marca, detalle,
    )
    if not contenido_id:
        return
    aviso = f"⚠ Copy descartado (pieza inválida): {detalle}."
    try:
        tema = repos.obtener_contenido(contenido_id)
        if tema is None:
            return
        previas = str(tema.get("notas") or "").strip()
        repos.actualizar_contenido(
            contenido_id, {"notas": f"{previas}\n{aviso}" if previas else aviso}
        )
    except Exception:  # noqa: BLE001 -- el aviso es un extra; nunca rompe el post-procesado
        _log.warning("copy: no se pudo anotar el tema %s", contenido_id, exc_info=True)


# --------------------------------------------------------------------------- #
# Verificacion de VOZ (lint de patrones reales de la marca)                    #
# --------------------------------------------------------------------------- #


def verificar_voz(
    marca: str, piezas: list[dict[str, object]], verdicto: str, *, copy_unico: bool = True
) -> tuple[str, list[str]]:
    """Contrasta las piezas generadas contra el PERFIL DE PATRONES real de la marca.

    Devuelve `(verdicto_efectivo, avisos)`. El lint es determinista y ADVISORY: nunca
    descarta piezas ni bloquea; si hay avisos y el modelo dijo `listo`, el revision se
    DEGRADA a `revisar` (el humano decide con los avisos delante). Cualquier otro
    revision (`revisar`, `no_publicar`, vacio/heredado) ya pide ojos humanos y se
    respeta. Best-effort: un fallo del lint nunca rompe el post-procesado.
    """
    try:
        avisos = patrones_marca.avisos_de_piezas(marca, piezas, copy_unico=copy_unico)
    except Exception:  # noqa: BLE001 -- el lint es un extra; jamas rompe la generacion
        _log.warning("verificacion de voz fallo para %s", marca, exc_info=True)
        return verdicto, []
    if avisos and verdicto == "listo":
        return "revisar", avisos
    return verdicto, avisos


def _avisar_voz(avisos: list[str], *, contenido_id: str, marca: str) -> None:
    """Deja rastro de los avisos de voz: WARN + nota en el tema (si lo hay).

    Mismo patron best-effort que `_avisar_piezas_descartadas`: el aviso acompana a la
    revision humana, nunca rompe el post-procesado.
    """
    detalle = "; ".join(avisos)
    _log.warning("copy: voz fuera de patron tema=%s marca=%s: %s", contenido_id or "-", marca, detalle)
    if not contenido_id:
        return
    nota = f"⚠ Verificación de voz (patrones medidos de la marca): {detalle}."
    try:
        tema = repos.obtener_contenido(contenido_id)
        if tema is None:
            return
        previas = str(tema.get("notas") or "").strip()
        repos.actualizar_contenido(
            contenido_id, {"notas": f"{previas}\n{nota}" if previas else nota}
        )
    except Exception:  # noqa: BLE001 -- la nota es un extra; nunca rompe el post-procesado
        _log.warning("copy: no se pudo anotar la voz en el tema %s", contenido_id, exc_info=True)


# --------------------------------------------------------------------------- #
# Creacion de publicaciones (borrador) por pieza                              #
# --------------------------------------------------------------------------- #

# `tipo` de catalogo de la foto ORIGINAL del articulo (RSS de marca propia). La Biblioteca
# (Galeria de Artes) la agrupa en su carpeta "Originales".
TIPO_ARTE_ORIGINAL = "original"


def _descargar_original_a_biblioteca(
    imagen_fuente: str, *, marca: str, titulo: str, autor: dict[str, str] | None
) -> str:
    """Descarga la foto ORIGINAL del articulo, la CATALOGA en la Biblioteca y devuelve su key.

    La foto de una fuente PROPIA se baja a S3, se promueve a la carpeta protegida `artes` y se
    registra en el catalogo (`tipo="original"`, por marca): asi APARECE en la Galeria de Artes
    bajo su carpeta "Originales", el GC no la borra y la pieza nace con ESA key auto-inyectada
    al feed. Tolerante: "" si la descarga falla (la pieza cae a `imagen_fuente`); si solo falla
    el catalogo, se devuelve igualmente la key promovida (la imagen sirve en la pieza).
    """
    from .. import almacen_media
    from . import extraccion_url

    try:
        objeto = extraccion_url.descargar_imagen_a_media(imagen_fuente)
    except Exception:  # noqa: BLE001 -- la descarga es un extra; nunca rompe la generacion
        return ""
    try:
        objeto = almacen_media.promover_objeto(objeto, "artes")
        repos.crear_media_catalogo(
            objeto=objeto, tipo=TIPO_ARTE_ORIGINAL, marca=marca or "",
            titulo=titulo or "", autor=autor,
        )
    except Exception:  # noqa: BLE001 -- sin fila de catalogo la imagen sigue sirviendo en la pieza
        pass
    return objeto


def _componer_slide_real(marca: str, titular: str, foto_url: str) -> str:
    """HORNEA la placa de UN slide del carrusel editorial; devuelve su key de media ("" si falla).

    Compone la plantilla de estudio EFECTIVA de la marca (la MISMA del editor/portada) con el
    `titular` del slide como texto-en-imagen y, si la sub-historia traía foto propia, esa foto
    de fondo. El PNG va CONTENT-ADDRESSED a la carpeta protegida `artes` (el GC no la borra:
    los slides viven en el campo `carrusel` de la pieza, fuera del catálogo regenerable).
    Sin plantilla de estudio (marca sin placa), cae a la foto cruda promovida a `artes` (mismo
    criterio que la portada sin receta); sin foto NI plantilla, "" (el slide se omite).
    NUNCA lanza: el carrusel es un extra del copy, no debe romper el post-procesado.
    """
    if not (titular or "").strip() and not (foto_url or "").strip():
        return ""
    from .. import almacen_media, media
    from . import estudio_imagen, render_pieza

    # Foto de la sub-historia (si la trae): se baja a media; el PNG horneado la lleva dentro,
    # así que no hace falta catalogarla ni protegerla por separado.
    foto_key = ""
    if (foto_url or "").strip():
        try:
            from . import extraccion_url

            foto_key = extraccion_url.descargar_imagen_a_media(foto_url.strip())
        except Exception:  # noqa: BLE001 -- sin foto, el slide sale como placa de solo texto
            foto_key = ""
    try:
        plantilla = render_pieza._plantilla_efectiva({"marca": marca})
    except Exception:  # noqa: BLE001 -- sin plantilla legible, tratamos como marca sin placa
        plantilla = None
    if plantilla is not None:
        try:
            datos = estudio_imagen.componer_desde_plantilla_bytes(
                plantilla.get("documento") or "{}",
                copy_in=(titular or "").strip(),
                foto=foto_key,
            )
            return media.guardar_bytes_contenido(datos, ext="png", categoria="artes")
        except Exception:  # noqa: BLE001 -- render best-effort: este slide se omite
            _log.warning("copy: no se pudo componer el slide «%s»", (titular or "")[:60], exc_info=True)
            return ""
    # Marca sin plantilla de estudio: el slide solo vale si la sub-historia traía foto.
    if foto_key:
        try:
            return almacen_media.promover_objeto(foto_key, "artes")
        except Exception:  # noqa: BLE001 -- sin promoción, mejor omitir que arriesgar el GC
            return ""
    return ""


# Seam INYECTABLE (los tests lo parchean): la composición real corre el renderer Node.
_COMPONER_SLIDE = _componer_slide_real


def crear_publicaciones_desde_piezas(
    piezas: list[dict[str, object]],
    *,
    marca: str,
    titulo: str,
    verdicto: str,
    origen: str,
    redes_filtro: set[str] | None = None,
    autor: dict[str, str] | None = None,
    contenido_id: str = "",
    atomico: bool = False,
    imagen_fuente: str = "",
    tipo_contenido: str = "",
    slides_carrusel: list[dict[str, str]] | None = None,
    sugiere_carrusel: bool = False,
) -> list[dict[str, object]]:
    """Crea UNA publicacion (borrador) por pieza y devuelve sus dicts serializados.

    HANDOFF A->C (ADR 0005 §Seams #1): cada pieza se deposita como BORRADOR por la
    funcion-contrato `dominio.publicaciones.crear_borrador` (nace `borrador`). Si
    `redes_filtro` no es None, solo se crean las piezas cuya red este en el filtro.

    NIDO BAJO EL TEMA (lista viva): si `contenido_id` apunta a un tema del tablero existente,
    cada pieza se ADJUNTA a ESE `contenido` (via `crear_borrador_en`) en vez de crear su
    propio padre, de modo que el borrador cuelga de la tarjeta del tema. Sin `contenido_id`
    (default ""), o si el tema no existe, es EXACTAMENTE el comportamiento de hoy.

    `atomico` (default False): TODO-O-NADA. La capa de datos persiste cada borrador por su
    cuenta (sin transacción cross-fila); con `atomico=True`, si la creación de una pieza
    falla a mitad, se BORRAN las ya creadas y se RELANZA, para no dejar publicaciones rotas.
    Lo usa el "Guardar como publicación" del termómetro; el auto-copy lo deja en False
    (best-effort, no debe abortar toda la generación por una pieza).

    VALIDACIÓN PRE-PERSISTENCIA: una pieza con red desconocida, texto vacío o que excede el
    límite técnico de su red (`limites_plataforma`; en hilos/carruseles, por intervalo) NO crea
    borrador. Se descarta SOLO esa pieza (las válidas del lote se crean igual), se loguea
    WARN y, si hay tema (`contenido_id`), se deja una nota en él.

    `slides_carrusel` (pipeline, output CARRUSEL elegido por el modelo): slides EDITORIALES
    `[{titular, foto}, …]` —una tarjeta por SUB-HISTORIA, `foto` la URL de la nota o ""—.
    Solo aplica NIDADO bajo un tema (`contenido_id`): cada slide se HORNEA como placa de la
    marca (plantilla efectiva + titular + su foto) a la carpeta protegida `artes`, el tema
    pasa a `formato='carrusel'`, las piezas se acotan a las redes de ese formato (IG/FB) y
    cada borrador nace con esos slides en su campo `carrusel` (la PORTADA sigue siendo
    `imagen`/`imagen_fuente` + el `copy_in` paraguas). Degradación honesta: si NINGÚN slide
    se pudo componer (o no hay tema), todo sigue como post normal de foto.

    `sugiere_carrusel` (tema ÚNICO): el modelo eligió `tipo=carrusel` PERO sin slides que hornear
    (no es un panel multi-historia, no hay catálogo de fotos). Es una SUGERENCIA de formato: con
    tema, el `contenido` FLIP-ea a formato carrusel (y se acota a IG/FB) y queda esperando que el
    equipo suba las fotos en diferido; el campo `carrusel` de los borradores queda vacío por ahora.
    """
    creadas: list[dict[str, object]] = []
    # Imagen ORIGINAL de fuente (RSS de marca propia): la DESCARGAMOS una sola vez, la
    # CATALOGAMOS en la Biblioteca (Galería de Artes, carpeta "Originales", por marca) y la
    # pieza nace con ESA imagen auto-inyectada al feed. Tolerante: si algo falla,
    # `imagen_descargada` queda "" y la pieza cae a `imagen_url`=`imagen_fuente`.
    imagen_descargada = ""
    if imagen_fuente:
        imagen_descargada = _descargar_original_a_biblioteca(
            imagen_fuente, marca=marca, titulo=titulo, autor=autor,
        )
    # CARRUSEL: el modelo eligió `tipo=carrusel`. DOS caminos hasta el formato carrusel:
    #   - PANEL multi-historia (`slides_carrusel`): hornea una placa por sub-historia (titular +
    #     su foto) y arma el `carrusel` de la pieza; los borradores llevan los slides tras la portada.
    #   - SUGERENCIA de un tema ÚNICO (`sugiere_carrusel`, sin slides): no hay fotos que hornear, así
    #     que el tema FLIP a formato carrusel COMO SUGERENCIA y queda esperando que el equipo suba
    #     las fotos en diferido (o el motor de arte si su toggle está activo).
    # En AMBOS el formato manda las redes (carrusel -> IG/FB; la pieza de X del copy unificado se omite).
    carrusel_json = ""
    if slides_carrusel and contenido_id:
        objetos = [
            obj
            for s in slides_carrusel
            if (obj := _COMPONER_SLIDE(
                marca, str(s.get("titular") or ""), str(s.get("foto") or "")
            ))
        ]
        if objetos:
            import json

            carrusel_json = json.dumps(
                [{"tipo": "imagen", "objeto": o} for o in objetos], ensure_ascii=False
            )
        else:
            _log.warning(
                "copy: carrusel sin slides componibles; queda como sugerencia de formato — tema %s",
                contenido_id,
            )
    # FLIP a formato carrusel si hay carrusel HORNEADO o el modelo lo SUGIRIÓ (tema único). Requiere
    # tema (`contenido_id`): el formato vive en el `contenido` padre, no en la fila por red.
    quiere_carrusel = bool(contenido_id) and (bool(carrusel_json) or sugiere_carrusel)
    if quiere_carrusel:
        try:
            repos.actualizar_contenido(contenido_id, {"formato": redes.FORMATO_CARRUSEL})
        except Exception:  # noqa: BLE001 -- sin el flip, la pieza sigue valiendo como foto
            _log.warning(
                "copy: no se pudo poner formato carrusel al tema %s", contenido_id, exc_info=True
            )
            carrusel_json = ""
            quiere_carrusel = False
    if quiere_carrusel:
        permitidas_carrusel = set(redes.redes_de_formato(redes.FORMATO_CARRUSEL))
        redes_filtro = (
            permitidas_carrusel if redes_filtro is None else (redes_filtro & permitidas_carrusel)
        )
    # HASHTAGS DE LÍNEA: los hashtags propios de las líneas/estrategias asignadas al tema se
    # inyectan al final del copy de CADA pieza (un único sitio gobierna hashtags + estrategia).
    # Se calcula una vez (todas las piezas cuelgan del mismo tema). Sin tema, no hay línea -> [].
    hashtags_linea = repos.hashtags_de_contenido(contenido_id) if contenido_id else []
    descartes: list[str] = []
    try:
        for pieza in piezas:
            red = pieza.get("red")
            if redes_filtro is not None and isinstance(red, str) and red not in redes_filtro:
                continue  # filtro del llamante (eligió menos redes), no es una pieza inválida
            # Inyecta los hashtags de la línea ANTES de validar (para no pasarnos del límite). Se
            # trabaja sobre una copia de la pieza (no muta la entrada del llamante).
            if hashtags_linea and isinstance(red, str):
                crudo = pieza.get("contenido")
                if isinstance(crudo, str):
                    pieza = {**pieza, "contenido": _inyectar_hashtags(crudo, hashtags_linea, red=red)}
            motivo = _motivo_invalida(pieza)
            if motivo is not None:
                descartes.append(motivo)
                continue
            red = str(red)
            contenido = str(pieza.get("contenido"))
            copy_in = pieza.get("copy_in")
            if not isinstance(copy_in, str):
                copy_in = ""
            # Con imagen ORIGINAL de fuente usamos la descargada a media (asset propio
            # publicable); si la descarga falló, "" y la pieza cae a la URL original. Sin
            # fuente, NO se hornea placa al crear: la placa de marca se RENDERIZA ON-DEMAND
            # desde la receta (marca + copy_in) cuando se muestra/publica (ver `render_pieza`).
            # Así no se duplica un PNG por cada pieza con el mismo logo/pleca y solo cambia el texto.
            imagen = imagen_descargada if imagen_fuente else ""
            creada: dict[str, object] | None = None
            if contenido_id:
                # Nido bajo el tema: adjunta la pieza al `contenido` existente. Devuelve None si
                # el tema no existe (entonces caemos al borrador suelto).
                creada = contrato_publicaciones.crear_borrador_en(
                    contenido_id, marca, red, titulo=titulo, contenido=contenido,
                    copy_in=copy_in, revision=verdicto, imagen=imagen,
                    imagen_fuente=imagen_fuente, carrusel=carrusel_json,
                )
            if creada is None:
                creada = contrato_publicaciones.crear_borrador(
                    marca, red, titulo=titulo, contenido=contenido, copy_in=copy_in,
                    revision=verdicto, origen=origen, autor=autor, imagen=imagen,
                    imagen_fuente=imagen_fuente, tipo_contenido=tipo_contenido,
                )
            creadas.append(creada)
    except Exception:
        if atomico:
            _revertir_borradores([str(p.get("id")) for p in creadas if p.get("id")])
        raise
    if descartes:
        _avisar_piezas_descartadas(descartes, contenido_id=contenido_id, marca=marca)
    return creadas


def _revertir_borradores(ids: list[str]) -> None:
    """Borra borradores ya creados (rollback de un guardado a medias). Tolerante a fallos."""
    for pid in ids:
        try:
            repos.borrar_publicacion(pid)
        except Exception:  # noqa: BLE001 -- el rollback nunca debe enmascarar el error original
            continue


def _persistir_url_fuente(publicaciones: list[dict[str, object]], url_fuente: str) -> None:
    """Persiste `url_fuente` en el `contenido` padre de cada borrador creado (dedup por URL).

    POST-HOC: cada borrador serializado trae el `contenido_id` de su tema padre (sea uno nuevo
    creado por la pieza o uno existente al que se nidó). Escribimos la URL canónica en ese
    `contenido` via `repos.actualizar_contenido` (campo `url_fuente`, editable). Deduplicamos
    los `contenido_id` (varias piezas pueden colgar del mismo tema). Best-effort por tema: un
    fallo NUNCA rompe el post-procesado (el copy ya está hecho).
    """
    vistos: set[str] = set()
    for pub in publicaciones:
        cid = str(pub.get("contenido_id") or "").strip()
        if not cid or cid in vistos:
            continue
        vistos.add(cid)
        try:
            repos.actualizar_contenido(cid, {"url_fuente": url_fuente})
        except Exception:  # noqa: BLE001 -- la trazabilidad es un extra; nunca rompe el post-procesado
            continue


# --------------------------------------------------------------------------- #
# Callbacks de post-procesado (corren al completarse la generacion)            #
# --------------------------------------------------------------------------- #


def construir_procesar_copy(
    prompt_id: str,
    marca: str,
    *,
    redes_ids: list[str],
    titulo_dado: str,
    texto_base: str,
    con_imagenes: bool = False,
    autor: dict[str, str] | None = None,
    contenido_id: str = "",
    imagen_fuente: str = "",
    fotos_notas: list[dict[str, str]] | None = None,
    tipo_contenido: str = "",
    revision_inicial: str = "",
    url_fuente: str = "",
) -> generaciones.Procesar:
    """Callback de post-procesado de una generacion de PIEZAS (copy/RSS).

    Parsea la salida en piezas/verdicto, registra el historial (con metricas), AUTO-GUARDA
    una publicacion (borrador) por pieza y devuelve `{resultado, historial_id, verdicto,
    piezas, publicaciones[, imagenes]}`. `prompt_id` es solo la etiqueta de origen del historial.

    `contenido_id` (lista viva): si apunta a un tema del tablero existente, cada borrador se
    ADJUNTA a ese `contenido` (cuelga de su tarjeta); sin el (default ""), borrador suelto.
    `revision_inicial` (pipeline QPC): revision por DEFECTO de las piezas cuando la salida no
    trae uno propio (p. ej. `no_verificado`, para heredar el aviso de la verificación de la fuente).
    `url_fuente` (RSS, trazabilidad): URL CANONICA de la nota de origen. Si viene, se PERSISTE en
    `contenido.url_fuente` del tema padre de cada borrador creado (dedup por URL). Best-effort:
    un fallo NUNCA rompe el post-procesado (el copy ya esta hecho). "" = no se toca.
    `fotos_notas` (pipeline, DOS tipos de output): catálogo de fotos de fuente propia por
    NOTA (`[{titulo, imagen}, …]`, mismo orden numerado que vio el modelo en el prompt). Si
    la salida declara `tipo=carrusel` con 2+ `slides`, cada slide se resuelve a su foto por
    número y se HORNEA como placa; si no, post de foto como siempre.
    """

    def procesar(salida: str, metricas: stream.MetricasRun | None) -> dict[str, object]:
        # Copy UNIFICADO: UN solo copy + copy_in se replica a TODAS las redes pedidas (incluida
        # X, que así nunca nace sin copy_in). El equipo añade los hashtags aparte por grupos.
        parsed = stream.parsear_salida_unificada(salida, redes_ids)
        titulo = titulo_dado or stream.derivar_titulo(texto_base or str(parsed["resultado"]))
        historial_id = repos.registrar_historial_prompt(
            prompt_id, marca, parsed["resultado"], piezas=parsed["piezas"], titulo=titulo,
            metricas=stream.metricas_a_dict(metricas), autor=autor,
        )
        # El revision de la salida manda; si viene vacío, cae al inicial (p. ej. no_verificado).
        verdicto = (str(parsed["verdicto"]) or "").strip() or (revision_inicial or "")
        # Verificacion de VOZ contra los patrones medidos de la marca: con avisos, un
        # `listo` del modelo baja a `revisar` y la nota viaja al tema (el humano decide).
        verdicto, avisos_voz = verificar_voz(marca, parsed["piezas"], verdicto)
        if avisos_voz:
            _avisar_voz(avisos_voz, contenido_id=contenido_id, marca=marca)
        # CARRUSEL EDITORIAL solo si el MODELO lo eligió (`tipo`) Y emitió 2+ slides (un panel
        # de una tarjeta no es panel). Cada slide resuelve su foto por NÚMERO contra el
        # catálogo que vio en el prompt; la portada sigue viajando como `imagen_fuente`.
        # `tipo=carrusel` es la SUGERENCIA de formato del modelo (cualquier tema). Con 2+ slides
        # (panel multi-historia) se resuelven a sus fotos y se hornean; sin slides (tema único) la
        # sugerencia FLIP-ea el formato igual y las fotos llegan después.
        sugiere_carrusel = parsed.get("tipo") == "carrusel"
        slides_resueltos: list[dict[str, str]] = []
        if sugiere_carrusel:
            urls = [str(f.get("imagen") or "") for f in (fotos_notas or [])]
            crudos = parsed.get("slides") or []
            if isinstance(crudos, list) and len(crudos) >= 2:
                for s in crudos:
                    n = s.get("foto") if isinstance(s, dict) else 0
                    foto = urls[n - 1] if isinstance(n, int) and 1 <= n <= len(urls) else ""
                    slides_resueltos.append(
                        {"titular": str(s.get("titular") or ""), "foto": foto}
                    )
        publicaciones = crear_publicaciones_desde_piezas(
            parsed["piezas"], marca=marca, titulo=titulo,
            verdicto=verdicto, origen=historial_id, autor=autor,
            contenido_id=contenido_id,
            imagen_fuente=imagen_fuente, tipo_contenido=tipo_contenido,
            slides_carrusel=slides_resueltos, sugiere_carrusel=sugiere_carrusel,
        )
        # Trazabilidad de la fuente (RSS): persiste la URL canonica en el `contenido` padre de
        # cada borrador creado. Best-effort: el copy YA esta hecho; un fallo aqui no debe romper
        # el post-procesado. Se deduplican los `contenido_id` (varias piezas pueden compartir
        # tema cuando se nida bajo uno existente).
        if url_fuente:
            _persistir_url_fuente(publicaciones, url_fuente)
        resultado: dict[str, object] = {
            "resultado": parsed["resultado"],
            "historial_id": historial_id,
            "verdicto": verdicto,
            "piezas": parsed["piezas"],
            "publicaciones": publicaciones,
            "avisos_voz": avisos_voz,
        }
        if con_imagenes:
            resultado["imagenes"] = recolectar_imagenes(salida)
        return resultado

    return procesar


def construir_procesar_documento(
    prompt_id: str,
    marca: str,
    *,
    titulo_base: str,
    titulo_dado: str = "",
    con_imagenes: bool = False,
    autor: dict[str, str] | None = None,
) -> generaciones.Procesar:
    """Callback de post-procesado de salida `documento` (sin piezas, sin publicaciones).

    Limpia emojis, deriva verdicto/titulo, registra el historial SIN piezas. Devuelve
    `{documento, verdicto, historial_id, piezas: [], publicaciones: []}` (+ `imagenes`).
    """

    def procesar(salida: str, metricas: stream.MetricasRun | None) -> dict[str, object]:
        doc = stream.quitar_emojis(salida)
        verdicto = stream.derivar_verdicto(salida)
        titulo = titulo_dado or stream.derivar_titulo(titulo_base or doc)
        historial_id = repos.registrar_historial_prompt(
            prompt_id, marca, doc, piezas=[], titulo=titulo,
            metricas=stream.metricas_a_dict(metricas), autor=autor,
        )
        resultado: dict[str, object] = {
            "documento": doc,
            "verdicto": verdicto,
            "historial_id": historial_id,
            "piezas": [],
            "publicaciones": [],
        }
        if con_imagenes:
            resultado["imagenes"] = recolectar_imagenes(salida)
        return resultado

    return procesar
