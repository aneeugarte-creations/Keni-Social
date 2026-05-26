#!/usr/bin/env python3
"""analiza-video.py - reune SENALES para saber si un video es nuevo o ya circulaba antes.

Resuelve el "pega el link y dime si es reciente o si ya salio hace anos" del equipo de
AMX Contenido. NO da el veredicto final: junta evidencia objetiva y se la pasa a la skill
(Claude) y al humano para que decidan. Pensado para el camino GRATIS (sin APIs de pago):

  1. Metadatos de la plataforma con yt-dlp  -> fecha de SUBIDA, autor, titulo, miniatura.
  2. Fotogramas con ffmpeg                  -> muestras del video para OCR e inspeccion.
  3. OCR con tesseract sobre los fotogramas -> caza fechas/anos en pantalla (timestamp de
                                               camara de seguridad, "2013", marcas de agua).
  4. Enlaces de BUSQUEDA INVERSA por URL    -> Google Lens / Yandex / TinEye(mas antiguo) /
                                               Bing, sobre la MINIATURA PUBLICA del video.
                                               El humano hace clic; no scrapeamos nada.
  5. Google Fact Check API (OPCIONAL)       -> solo si GOOGLE_FACTCHECK_API_KEY esta definida.
  6. Senales de IA generativa (PASIVO)      -> metadatos EXIF/C2PA (exiftool, opcional),
                                               campos Software/encoder del contenedor,
                                               watermarks de generadores en el texto OCR,
                                               y ausencia de metadatos de camara fisica.
                                               Sin red, sin clave, sin subir nada.
                                               LIMITE: cobertura baja; la ausencia de
                                               senales NO confirma autenticidad.

Privacidad: solo se usa lo que YA es publico (la miniatura que la plataforma sirve). Los
fotogramas se guardan en LOCAL para que el humano los arrastre a la busqueda inversa; este
script no sube fotogramas a ningun sitio.

Sin dependencias de terceros: solo stdlib + los binarios yt-dlp, ffmpeg, ffprobe, tesseract.
exiftool es OPCIONAL: si esta instalado amplifica la lectura de metadatos C2PA/EXIF.

Uso:
  python3 analiza-video.py ENTRADA [--salida DIR] [--frames N] [--contexto "texto"]
    ENTRADA      URL del video (X/TikTok/Facebook/YouTube/Instagram...) o ruta a un archivo local.
    --salida     carpeta de trabajo (por defecto un tmp con marca de tiempo).
    --frames     cuantos fotogramas muestrear para OCR (por defecto 8).
    --contexto   que se afirma del video ("supuestamente de las protestas de mayo 2026"),
                 para que el reporte pueda comparar contra esa fecha.

La ultima linea de stdout es 'REPORTE=<ruta del reporte.json>' (parseable por la skill).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ANIO_ACTUAL = datetime.now().year


# --------------------------------------------------------------------------- #
# Utilidades                                                                  #
# --------------------------------------------------------------------------- #

def _log(msg: str) -> None:
    """Mensaje de progreso a stderr (stdout se reserva para el reporte parseable)."""
    print(msg, file=sys.stderr, flush=True)


def _tiene(binario: str) -> bool:
    return shutil.which(binario) is not None


def _run(cmd: list[str], timeout: int) -> tuple[int, str, str]:
    """Ejecuta un comando; devuelve (returncode, stdout, stderr). Nunca lanza por fallo."""
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout tras {timeout}s"
    except FileNotFoundError:
        return 127, "", f"no encontrado: {cmd[0]}"
    except Exception as e:  # noqa: BLE001  (defensivo: nunca tumbar el pipeline)
        return 1, "", str(e)


def _es_url(entrada: str) -> bool:
    return entrada.lower().startswith(("http://", "https://"))


# --------------------------------------------------------------------------- #
# 1. Metadatos (yt-dlp para URL, ffprobe para archivo local)                  #
# --------------------------------------------------------------------------- #

def metadatos_url(url: str) -> dict:
    """Saca metadatos publicos del video con yt-dlp (sin descargar todavia)."""
    meta = {"disponible": False}
    if not _tiene("yt-dlp"):
        meta["error"] = (
            "yt-dlp no esta instalado. Instalalo con 'brew install yt-dlp' "
            "(o 'pipx install yt-dlp'). Sin el no se pueden leer los metadatos ni "
            "descargar el video desde un enlace."
        )
        return meta
    rc, out, err = _run(
        ["yt-dlp", "-J", "--no-warnings", "--no-playlist", url], timeout=90
    )
    if rc != 0 or not out.strip():
        meta["error"] = f"yt-dlp no pudo leer el enlace: {err.strip()[:300] or 'sin detalle'}"
        return meta
    try:
        j = json.loads(out)
    except json.JSONDecodeError:
        meta["error"] = "yt-dlp devolvio una salida que no se pudo interpretar."
        return meta

    subido_iso = None
    anio_subida = None
    ud = j.get("upload_date")  # 'YYYYMMDD'
    if isinstance(ud, str) and len(ud) == 8 and ud.isdigit():
        subido_iso = f"{ud[0:4]}-{ud[4:6]}-{ud[6:8]}"
        anio_subida = int(ud[0:4])
    ts = j.get("timestamp")
    if subido_iso is None and isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        subido_iso = dt.date().isoformat()
        anio_subida = dt.year

    meta.update(
        disponible=True,
        plataforma=j.get("extractor_key") or j.get("extractor") or "desconocida",
        titulo=j.get("title"),
        descripcion=(j.get("description") or "")[:1000],
        autor=j.get("uploader") or j.get("channel") or j.get("uploader_id"),
        canal=j.get("channel"),
        url_pagina=j.get("webpage_url") or url,
        miniatura=j.get("thumbnail"),
        duracion_s=j.get("duration"),
        vistas=j.get("view_count"),
        likes=j.get("like_count"),
        subido_iso=subido_iso,
        anio_subida=anio_subida,
    )
    return meta


def metadatos_archivo(ruta: str) -> dict:
    """Metadatos basicos de un archivo local con ffprobe (creation_time si el contenedor lo trae)."""
    meta = {"disponible": True, "plataforma": "archivo local", "url_pagina": None, "miniatura": None}
    if not _tiene("ffprobe"):
        return meta
    rc, out, _ = _run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_entries", "format=duration:format_tags=creation_time", ruta,
        ],
        timeout=30,
    )
    if rc == 0 and out.strip():
        try:
            j = json.loads(out)
            fmt = j.get("format", {})
            if fmt.get("duration"):
                meta["duracion_s"] = float(fmt["duration"])
            ct = (fmt.get("tags") or {}).get("creation_time")
            if ct:
                meta["creation_time"] = ct
                m = re.match(r"(\d{4})", ct)
                if m:
                    meta["anio_subida"] = int(m.group(1))
                    meta["subido_iso"] = ct[:10]
        except (json.JSONDecodeError, ValueError):
            pass
    return meta


# --------------------------------------------------------------------------- #
# 2. Descarga (solo URL) + 3. Fotogramas con ffmpeg                           #
# --------------------------------------------------------------------------- #

def descargar(url: str, destino: Path) -> tuple[Path | None, str | None]:
    """Descarga el video (<=720p) para poder sacar fotogramas. Devuelve (ruta, error)."""
    if not _tiene("yt-dlp"):
        return None, "yt-dlp no instalado: no se puede descargar el video."
    plantilla = str(destino / "video.%(ext)s")
    rc, _, err = _run(
        [
            "yt-dlp", "--no-warnings", "--no-playlist",
            "-f", "best[height<=720]/best",
            "-o", plantilla, url,
        ],
        timeout=300,
    )
    if rc != 0:
        return None, f"no se pudo descargar el video: {err.strip()[:300] or 'sin detalle'}"
    videos = sorted(destino.glob("video.*"))
    if not videos:
        return None, "yt-dlp termino pero no quedo ningun archivo de video."
    return videos[0], None


def _duracion(ruta: Path) -> float | None:
    rc, out, _ = _run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(ruta)],
        timeout=30,
    )
    if rc == 0 and out.strip():
        try:
            return float(out.strip())
        except ValueError:
            return None
    return None


def extraer_fotogramas(video: Path, carpeta: Path, n: int) -> list[Path]:
    """Saca n fotogramas repartidos uniformemente (cubre overlays/timestamps persistentes)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    dur = _duracion(video) or 0.0
    frames: list[Path] = []
    if dur <= 0:
        # Sin duracion fiable: saca el primer fotograma y ya.
        salida = carpeta / "frame-01.jpg"
        _run(["ffmpeg", "-y", "-i", str(video), "-frames:v", "1",
              "-vf", "scale=1280:-1", str(salida)], timeout=60)
        if salida.exists():
            frames.append(salida)
        return frames
    for i in range(n):
        t = dur * (i + 0.5) / n
        salida = carpeta / f"frame-{i + 1:02d}.jpg"
        rc, _, _ = _run(
            ["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video),
             "-frames:v", "1", "-vf", "scale=1280:-1", str(salida)],
            timeout=60,
        )
        if rc == 0 and salida.exists():
            frames.append(salida)
    return frames


# --------------------------------------------------------------------------- #
# 4. OCR con tesseract                                                        #
# --------------------------------------------------------------------------- #

def _langs_tesseract() -> str:
    """Devuelve la mejor combinacion de idiomas disponible (spa+eng > eng > spa > default)."""
    rc, out, _ = _run(["tesseract", "--list-langs"], timeout=20)
    disponibles = set(out.split()) if rc == 0 else set()
    tiene_spa, tiene_eng = "spa" in disponibles, "eng" in disponibles
    if tiene_spa and tiene_eng:
        return "spa+eng"
    if tiene_eng:
        return "eng"
    if tiene_spa:
        return "spa"
    return ""  # usa el idioma por defecto del binario


def ocr_fotogramas(frames: list[Path]) -> dict:
    """Pasa OCR a cada fotograma y junta el texto + las fechas/anos detectados."""
    resultado = {"frames_analizados": 0, "texto": "", "anios": [], "fechas": [], "horas": []}
    if not frames:
        return resultado
    if not _tiene("tesseract"):
        resultado["error"] = "tesseract no instalado: no se pudo leer texto en pantalla."
        return resultado
    lang = _langs_tesseract()
    textos: list[str] = []
    for f in frames:
        cmd = ["tesseract", str(f), "stdout"]
        if lang:
            cmd += ["-l", lang]
        rc, out, _ = _run(cmd, timeout=60)
        if rc == 0 and out.strip():
            textos.append(out)
            resultado["frames_analizados"] += 1
    texto = "\n".join(textos)
    resultado["texto"] = texto[:4000]

    anios: set[int] = set()
    for m in re.findall(r"\b(19[5-9]\d|20[0-3]\d)\b", texto):
        a = int(m)
        if 1950 <= a <= ANIO_ACTUAL:
            anios.add(a)
    fechas = re.findall(r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b", texto)
    fechas += re.findall(r"\b\d{4}-\d{2}-\d{2}\b", texto)
    horas = re.findall(r"\b\d{1,2}:\d{2}:\d{2}\b", texto)
    resultado["anios"] = sorted(anios)
    resultado["fechas"] = sorted(set(fechas))[:20]
    resultado["horas"] = sorted(set(horas))[:20]
    return resultado


# --------------------------------------------------------------------------- #
# 5. Busqueda inversa por URL (sobre la miniatura publica)                    #
# --------------------------------------------------------------------------- #

def enlaces_busqueda_inversa(imagen_url: str | None) -> dict:
    """Construye enlaces de busqueda inversa listos para que el humano haga clic."""
    if not imagen_url:
        return {"base": "ninguna", "enlaces": {}}
    q = urllib.parse.quote(imagen_url, safe="")
    return {
        "base": "miniatura publica del video",
        "imagen_url": imagen_url,
        "enlaces": {
            # TinEye ordenado por mas ANTIGUO: lo mejor para datar "ya existia desde...".
            "tineye_mas_antiguo": f"https://www.tineye.com/search?url={q}&sort=crawl_date&order=asc",
            "google_lens": f"https://lens.google.com/uploadbyurl?url={q}",
            "yandex": f"https://yandex.com/images/search?rpt=imageview&url={q}",
            "bing": f"https://www.bing.com/images/search?view=detailv2&iss=sbi&form=SBIVSP&q=imgurl:{q}",
        },
    }


# --------------------------------------------------------------------------- #
# 6. Google Fact Check Tools API (opcional)                                   #
# --------------------------------------------------------------------------- #

def fact_check(query: str | None) -> dict:
    """Consulta la Fact Check Tools API SOLO si hay GOOGLE_FACTCHECK_API_KEY. Gratis."""
    key = os.environ.get("GOOGLE_FACTCHECK_API_KEY")
    if not key:
        return {"consultado": False, "motivo": "sin GOOGLE_FACTCHECK_API_KEY (opcional, gratuita)."}
    if not query or not query.strip():
        return {"consultado": False, "motivo": "sin titulo/consulta para buscar."}
    params = urllib.parse.urlencode(
        {"query": query[:200], "languageCode": "es", "pageSize": 5, "key": key}
    )
    url = f"https://factchecktools.googleapis.com/v1alpha1/claims:search?{params}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:  # noqa: S310 (url fijo de google)
            datos = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"consultado": False, "motivo": f"error consultando la API: {e}"}
    resultados = []
    for c in datos.get("claims", []):
        rev = (c.get("claimReview") or [{}])[0]
        resultados.append({
            "afirmacion": c.get("text"),
            "quien_lo_dijo": c.get("claimant"),
            "verificador": (rev.get("publisher") or {}).get("name"),
            "veredicto": rev.get("textualRating"),
            "url": rev.get("url"),
            "fecha": rev.get("reviewDate") or c.get("claimDate"),
        })
    return {"consultado": True, "resultados": resultados}


# --------------------------------------------------------------------------- #
# 6. Senales de IA generativa (pasivo, sin red, sin claves)                   #
# --------------------------------------------------------------------------- #

# Nombres de generadores de video con IA que pueden aparecer en metadatos
# o en watermarks visibles. Lista de mantenimiento periodico: los generadores
# cambian sus marcas de agua y sus campos de metadata con cada version.
_GENERADORES_IA = (
    "sora", "veo", "runway", "runwayml", "pika", "pikaart",
    "kling", "kling ai", "made with kling",
    "midjourney", "stable diffusion", "animatediff", "stable video",
    "heygan", "heygen", "luma", "luma dream", "dream machine",
    "invideo", "haiper", "genmo", "hotshot",
    "created with ai", "generated by ai", "generated with ai",
    "ai generated", "ai-generated",
)

# Campos de metadatos del contenedor donde los generadores suelen dejar huella.
_CAMPOS_SOFTWARE = ("software", "comment", "description", "encoder",
                    "createdby", "created_by", "handler_name",
                    "xmp:creatortool", "xmp:creator", "xmp:source")

# Campos que indican que el video vino de una camara fisica real.
# Su ausencia COMPLETA es una pista debil (no concluyente) de origen digital.
_CAMPOS_CAMARA = ("make", "model", "cameramake", "cameramodel",
                  "focallength", "fnumber", "iso", "exposuretime",
                  "lensmodel", "exif:make", "exif:model")


def _normaliza_campo(texto: str) -> str:
    """Minusculas sin espacios extra, para comparacion robusta."""
    return re.sub(r"\s+", " ", texto.lower().strip())


def metadatos_ia(video_path: Path | None, meta_base: dict) -> dict:
    """Lee metadatos extendidos buscando huellas de generadores de IA.

    Usa tres fuentes en orden de preferencia:
      1. ffprobe (ya disponible si el usuario tiene ffmpeg): campos format_tags.
      2. exiftool (OPCIONAL): lectura rica de XMP, EXIF y C2PA JUMBF.
      3. La estructura de meta_base ya leida por ffprobe/yt-dlp.

    Devuelve un dict con:
      - software_encontrado: lista de valores de campos Software/encoder hallados.
      - generadores_detectados: lista de nombres de generadores reconocidos.
      - c2pa_presente: True si se detecto manifiesto C2PA (exiftool).
      - c2pa_es_ia: True si el manifiesto declara generacion por IA.
      - c2pa_resumen: texto del manifiesto C2PA si lo hay.
      - tiene_metadatos_camara: True si hay campos Make/Model/ISO/etc.
      - metodo: que herramienta se uso.
    """
    resultado: dict = {
        "software_encontrado": [],
        "generadores_detectados": [],
        "c2pa_presente": False,
        "c2pa_es_ia": False,
        "c2pa_resumen": None,
        "tiene_metadatos_camara": False,
        "metodo": "ninguno",
    }
    if video_path is None or not video_path.is_file():
        return resultado

    # --- ffprobe: format_tags extendidos ---
    if _tiene("ffprobe"):
        rc, out, _ = _run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_entries",
                "format_tags:stream_tags",
                str(video_path),
            ],
            timeout=30,
        )
        if rc == 0 and out.strip():
            try:
                j = json.loads(out)
                tags: dict = {}
                tags.update(j.get("format", {}).get("tags") or {})
                for stream in j.get("streams") or []:
                    tags.update(stream.get("tags") or {})
                # Normaliza claves y valores para busqueda
                for k, v in tags.items():
                    kn = _normaliza_campo(k)
                    vn = _normaliza_campo(str(v))
                    if kn in _CAMPOS_SOFTWARE and vn:
                        resultado["software_encontrado"].append(f"{k}={v}")
                        for gen in _GENERADORES_IA:
                            if gen in vn and gen not in resultado["generadores_detectados"]:
                                resultado["generadores_detectados"].append(gen)
                    if kn.replace(":", "").replace("_", "").replace("-", "") in {
                        c.replace(":", "").replace("_", "").replace("-", "")
                        for c in _CAMPOS_CAMARA
                    } and vn:
                        resultado["tiene_metadatos_camara"] = True
                resultado["metodo"] = "ffprobe"
            except (json.JSONDecodeError, AttributeError):
                pass

    # --- exiftool (OPCIONAL): XMP, EXIF completo y C2PA JUMBF ---
    if _tiene("exiftool"):
        rc, out, _ = _run(
            ["exiftool", "-j", "-XMP:all", "-EXIF:Make", "-EXIF:Model",
             "-EXIF:ISO", "-EXIF:FocalLength", "-Comment", "-Software",
             str(video_path)],
            timeout=30,
        )
        if rc == 0 and out.strip():
            try:
                jlist = json.loads(out)
                j_ex = jlist[0] if isinstance(jlist, list) and jlist else {}
                for k, v in j_ex.items():
                    kn = _normaliza_campo(k)
                    vn = _normaliza_campo(str(v))
                    if kn in _CAMPOS_SOFTWARE and vn:
                        entrada = f"{k}={v}"
                        if entrada not in resultado["software_encontrado"]:
                            resultado["software_encontrado"].append(entrada)
                        for gen in _GENERADORES_IA:
                            if gen in vn and gen not in resultado["generadores_detectados"]:
                                resultado["generadores_detectados"].append(gen)
                    if kn in {c.lower() for c in _CAMPOS_CAMARA} and vn:
                        resultado["tiene_metadatos_camara"] = True
                    # C2PA: exiftool >= 12.70 expone algunos campos JUMBF
                    if "c2pa" in kn or "jumbf" in kn or "contentcredential" in kn:
                        resultado["c2pa_presente"] = True
                        resumen = str(v)[:500]
                        resultado["c2pa_resumen"] = resumen
                        # Si el manifiesto menciona un generador de IA -> c2pa_es_ia
                        for gen in _GENERADORES_IA:
                            if gen in _normaliza_campo(resumen):
                                resultado["c2pa_es_ia"] = True
                                break
                resultado["metodo"] = "exiftool"
            except (json.JSONDecodeError, IndexError, AttributeError):
                pass

    return resultado


def senales_ia_generativa(meta_ia: dict, ocr: dict) -> list[dict]:
    """Genera senales sobre posible origen de IA generativa.

    IMPORTANTE: estas senales son INDICIOS, no pruebas. La ausencia de senales
    NO confirma que el video sea autentico. La deteccion de IA es inherentemente
    limitada; los generadores modernos (Veo 3, Kling 2.5, Runway Gen-4) no
    dejan huellas detectables con herramientas locales cuando se distribuyen
    sin watermark ni C2PA.
    """
    senales: list[dict] = []

    # 1. C2PA con declaracion explicita de IA -> alto
    if meta_ia.get("c2pa_es_ia"):
        senales.append({
            "nivel": "alto",
            "categoria": "ia_generativa",
            "texto": (
                "El manifiesto C2PA del video declara explicitamente generacion por IA. "
                f"Resumen del manifiesto: {meta_ia.get('c2pa_resumen', '')[:200]}. "
                "C2PA es una firma criptografica: si el archivo no fue manipulado, "
                "este dato es altamente fiable."
            ),
        })
    elif meta_ia.get("c2pa_presente"):
        senales.append({
            "nivel": "info",
            "categoria": "ia_generativa",
            "texto": (
                "El video tiene un manifiesto C2PA (cadena de procedencia verificable). "
                "No declara IA generativa, pero puedes inspeccionarlo con c2patool para "
                "ver la cadena completa de edicion y firma."
            ),
        })

    # 2. Nombre de generador en campos de metadatos -> alto
    if meta_ia.get("generadores_detectados"):
        generadores = meta_ia["generadores_detectados"]
        campos = meta_ia.get("software_encontrado", [])
        senales.append({
            "nivel": "alto",
            "categoria": "ia_generativa",
            "texto": (
                f"Se encontro el nombre de un generador de IA en los metadatos del video: "
                f"{generadores}. "
                f"Campos donde aparecio: {campos[:5]}. "
                "OJO: cualquiera puede escribir cualquier cosa en estos campos; "
                "es un indicio, no una prueba. Confirma con el video en pantalla."
            ),
        })
    elif meta_ia.get("software_encontrado"):
        # Hay software registrado pero no es un generador conocido -> info
        senales.append({
            "nivel": "bajo",
            "categoria": "ia_generativa",
            "texto": (
                f"Campos de software en los metadatos: {meta_ia['software_encontrado'][:3]}. "
                "No coincide con generadores conocidos, pero puede indicar que el video "
                "fue procesado o re-encodificado."
            ),
        })

    # 3. Watermark visible de generador en el texto OCR -> alto
    if ocr.get("texto"):
        texto_ocr = ocr["texto"].lower()
        watermarks_encontrados = [
            gen for gen in _GENERADORES_IA
            if gen in texto_ocr
        ]
        if watermarks_encontrados:
            senales.append({
                "nivel": "alto",
                "categoria": "ia_generativa",
                "texto": (
                    f"El OCR encontro en pantalla posibles watermarks de generadores de IA: "
                    f"{watermarks_encontrados}. "
                    "Confirma mirando los fotogramas: puede ser un watermark visible en "
                    "la esquina del video (tipico de las versiones gratuitas de Runway, "
                    "Pika, Kling...). Si el watermark fue recortado, no aparecera."
                ),
            })

    # 4. Sin metadatos de camara fisica -> info/bajo (senal debil)
    if not meta_ia.get("tiene_metadatos_camara") and meta_ia.get("metodo") != "ninguno":
        senales.append({
            "nivel": "bajo",
            "categoria": "ia_generativa",
            "texto": (
                "El video no tiene metadatos de camara fisica (Make/Model/ISO/FocalLength). "
                "Esto es comun en videos generados con IA, grabados en pantalla, "
                "o descargados de redes sociales que los eliminan. "
                "Es una senal DEBIL: la mayoria de videos en redes sociales no los tienen."
            ),
        })

    return senales


# --------------------------------------------------------------------------- #
# Senales (pistas objetivas; el veredicto lo da la skill + el humano)         #
# --------------------------------------------------------------------------- #

def construir_senales(meta: dict, ocr: dict, fc: dict) -> list[dict]:
    senales: list[dict] = []
    anio_subida = meta.get("anio_subida")

    # Ano en pantalla anterior a la subida -> pista fuerte de material reciclado.
    if anio_subida and ocr.get("anios"):
        previos = [a for a in ocr["anios"] if a < anio_subida]
        if previos:
            senales.append({
                "nivel": "alto",
                "texto": (
                    f"El OCR leyo en pantalla el/los ano(s) {previos}, anterior(es) al ano de "
                    f"subida ({anio_subida}). Posible material viejo re-subido. "
                    "OJO: el OCR se equivoca (un marcador, un dorsal o una placa pueden parecer un ano); "
                    "confirma mirando el fotograma."
                ),
            })

    if ocr.get("fechas"):
        senales.append({
            "nivel": "medio",
            "texto": (
                f"Hay fechas en pantalla: {ocr['fechas'][:5]}. Compara con la fecha de subida "
                f"({meta.get('subido_iso') or 'desconocida'}) y con lo que se afirma del video."
            ),
        })
    if ocr.get("horas"):
        senales.append({
            "nivel": "bajo",
            "texto": (
                f"Hay marcas de hora tipo camara de seguridad ({ocr['horas'][:3]}): "
                "suelen venir con una fecha al lado; revisa el fotograma a tamano grande."
            ),
        })

    fc_res = fc.get("resultados") or []
    if fc_res:
        senales.append({
            "nivel": "alto",
            "texto": (
                f"Hay {len(fc_res)} verificacion(es) previa(s) relacionadas en la Fact Check API. "
                "Revisa si alguna ya desmintio o data este video."
            ),
        })

    if not senales:
        senales.append({
            "nivel": "info",
            "texto": (
                "El analisis automatico no encontro pistas claras de que el video sea viejo. "
                "Eso NO confirma que sea nuevo: la prueba de fuego es la busqueda inversa "
                "(abre los enlaces) para ver si los fotogramas ya aparecian online antes."
            ),
        })
    return senales


# --------------------------------------------------------------------------- #
# Orquestacion                                                                #
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(description="Reune senales para datar un video (nuevo vs reciclado).")
    ap.add_argument("entrada", help="URL del video o ruta a un archivo local.")
    ap.add_argument("--salida", default=None, help="Carpeta de trabajo (por defecto un tmp).")
    ap.add_argument("--frames", type=int, default=8, help="Fotogramas a muestrear para OCR (def. 8).")
    ap.add_argument("--contexto", default="", help="Que se afirma del video (fecha/evento), para comparar.")
    args = ap.parse_args()

    entrada = args.entrada.strip()
    es_url = _es_url(entrada)
    if not es_url and not Path(entrada).is_file():
        _log(f"ERROR: la entrada no es una URL ni un archivo existente: {entrada}")
        return 2

    if args.salida:
        salida = Path(args.salida).expanduser()
    else:
        sello = datetime.now().strftime("%Y%m%d-%H%M%S")
        salida = Path(tempfile.gettempdir()) / "keni-verifica-video" / sello
    salida.mkdir(parents=True, exist_ok=True)
    frames_dir = salida / "frames"

    reporte = {
        "entrada": entrada,
        "tipo_entrada": "url" if es_url else "archivo",
        "contexto_afirmado": args.contexto or None,
        "generado": datetime.now().isoformat(timespec="seconds"),
        "carpeta_trabajo": str(salida),
    }

    # 1. Metadatos
    _log("[1/6] Leyendo metadatos...")
    meta = metadatos_url(entrada) if es_url else metadatos_archivo(entrada)
    reporte["metadatos"] = meta

    # 2. Conseguir el video (descargar si es URL; usar el archivo si es local)
    video_path: Path | None = None
    if es_url:
        if meta.get("disponible"):
            _log("[2/6] Descargando el video (<=720p) para sacar fotogramas...")
            video_path, err = descargar(entrada, salida)
            if err:
                reporte.setdefault("avisos", []).append(err)
                _log(f"   aviso: {err}")
        else:
            reporte.setdefault("avisos", []).append(
                "No se leyeron metadatos; no se intento descargar."
            )
    else:
        video_path = Path(entrada)

    # 3. Fotogramas + 4. OCR
    ocr = {"frames_analizados": 0, "anios": [], "fechas": [], "horas": []}
    frames: list[Path] = []
    if video_path and video_path.is_file():
        if not _tiene("ffmpeg"):
            reporte.setdefault("avisos", []).append("ffmpeg no instalado: sin fotogramas ni OCR.")
        else:
            _log(f"[3/6] Extrayendo {args.frames} fotogramas...")
            frames = extraer_fotogramas(video_path, frames_dir, args.frames)
            _log(f"[4/6] OCR sobre {len(frames)} fotogramas...")
            ocr = ocr_fotogramas(frames)
    else:
        reporte.setdefault("avisos", []).append(
            "No se obtuvo el video; no hay fotogramas ni OCR. Aun asi tienes metadatos y "
            "los enlaces de busqueda inversa sobre la miniatura."
        )
    reporte["ocr"] = ocr
    reporte["fotogramas"] = [str(f) for f in frames]

    # 5. Busqueda inversa (sobre la miniatura publica) + Fact Check opcional
    _log("[5/6] Construyendo enlaces de busqueda inversa y consultando Fact Check (si hay key)...")
    reporte["busqueda_inversa"] = enlaces_busqueda_inversa(meta.get("miniatura"))
    reporte["busqueda_inversa"]["fotogramas_guardados_en"] = str(frames_dir) if frames else None
    reporte["fact_check"] = fact_check(meta.get("titulo") or args.contexto)

    # 6. Senales de IA generativa (pasivo: metadatos extendidos + OCR watermarks)
    _log("[6/6] Buscando senales de IA generativa (metadatos, C2PA, watermarks)...")
    meta_ia = metadatos_ia(video_path, meta)
    reporte["ia_generativa"] = meta_ia
    senales_ia = senales_ia_generativa(meta_ia, ocr)

    # Senales combinadas: recirculacion + IA
    reporte["senales"] = construir_senales(meta, ocr, reporte["fact_check"])
    reporte["senales_ia"] = senales_ia if senales_ia else [{
        "nivel": "info",
        "categoria": "ia_generativa",
        "texto": (
            "No se encontraron senales automaticas de IA generativa (metadatos, C2PA ni "
            "watermarks en OCR). IMPORTANTE: esto NO confirma que el video sea autentico. "
            "Los generadores modernos de alta calidad no dejan huellas detectables con "
            "herramientas locales. Aplica criterio editorial y revisa el contexto."
        ),
    }]

    # Escribir reporte
    ruta_reporte = salida / "reporte.json"
    ruta_reporte.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")

    # Resumen humano a stderr (stdout solo lleva la linea parseable)
    _log("")
    _log("===== RESUMEN =====")
    _log(f"Plataforma : {meta.get('plataforma')}")
    _log(f"Titulo     : {meta.get('titulo')}")
    _log(f"Subido     : {meta.get('subido_iso') or 'desconocido'}  (autor: {meta.get('autor')})")
    _log(f"OCR anos   : {ocr.get('anios')}   fechas: {ocr.get('fechas')}")
    for s in reporte["senales"]:
        _log(f"  [{s['nivel'].upper()}] {s['texto']}")
    _log(f"--- Senales IA generativa ---")
    for s in reporte["senales_ia"]:
        _log(f"  [{s['nivel'].upper()}] {s['texto']}")
    _log(f"Fotogramas : {frames_dir if frames else '(ninguno)'}")
    _log("===================")

    print(f"REPORTE={ruta_reporte}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
