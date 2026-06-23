"""Dominio EXTRACCION DESDE URL: descarga una nota/articulo y saca su texto legible.

Es el "paso de extraccion" (generar copy desde un link). El usuario pega
una URL; ANTES de generar copy, la Consola descarga la pagina y extrae su texto
legible EN EL SERVIDOR (no en la skill de Claude: las skills de copy son dry-run y NO
hacen peticiones de red). El texto extraido se trata SIEMPRE como NO VERIFICADO: lo
sacamos de una pagina ajena, asi que nombres/cifras/fechas pueden venir mal y deben
quedar marcados para que el humano los confirme (honestidad / no alucinacion).

PRIVACIDAD: solo viaja TEXTO. La descarga ocurre aqui (httpx, igual que `api.rss`); a
Anthropic solo llega el texto ya extraido como contexto de la skill `copy-desde-nota`.
No se descarga ni se sube audio/video a terceros: si el link es de video/streaming,
degradamos con honestidad (la transcripcion es whisper LOCAL y vive en `clip-a-copy`
desde un archivo subido, no desde una URL remota).

SEGURIDAD (SSRF): misma defensa que `api.rss`. Solo `http`/`https`; se resuelve el host
y se RECHAZA si CUALQUIER IP cae en loopback / rango privado / link-local / multicast /
reservado (defensa frente a DNS rebinding). Se descarga en trozos con timeout y tope de
tamano. La descarga vive detras de `_DESCARGADOR`, un punto INYECTABLE/mockeable: en
tests se parchea para NUNCA tocar la red.

PARSEO: stdlib `html.parser` (sin deps nuevas, igual que `api.rss` usa `ElementTree`).
Tira `<script>/<style>/...`, prefiere `<article>`/`<main>` si existen, colapsa espacios
y recorta a un tope. Si no hay texto util, se reporta con un mensaje en espanol.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit

# Limites de descarga (defensa frente a paginas gigantes o maliciosas). Alineados con
# los de `api.rss` (mismo orden de magnitud).
_TIMEOUT = 15.0  # segundos
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB de HTML
# Backoff entre reintentos de descarga (misma idea que el motor de feeds de Fuentes): solo
# para fallos TRANSITORIOS (timeout/conexión); un 4xx o "sin texto" no se reintenta.
_ESPERA_REINTENTO_SEG = (3.0, 8.0, 15.0)
# Tope del texto extraido que se pasa a la skill (margen de sobra bajo `_MAX_TEXTO`=60k).
_MAX_TEXTO_EXTRAIDO = 40_000

# Hosts cuyo contenido principal es VIDEO/STREAMING: no se pueden "leer" como articulo.
# La transcripcion es LOCAL (whisper, en `clip-a-copy` desde archivo), no desde URL
# remota: aqui degradamos con honestidad en vez de inventar o mandar el video a terceros.
_HOSTS_VIDEO = (
    "youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com", "fb.watch",
    "twitch.tv", "vimeo.com", "x.com", "twitter.com",
)

# Etiquetas cuyo contenido NO es texto legible (se descarta entero, incluido su texto).
# `head` NO entra aqui: dentro de el solo nos interesa `<title>` (que se capta aparte);
# el resto de `<head>` (meta/link/script/style) no produce texto o ya esta cubierto.
_TAGS_BASURA = frozenset({"script", "style", "noscript", "template", "svg"})
# Etiquetas de bloque: al cerrarlas metemos un salto para no pegar parrafos.
_TAGS_BLOQUE = frozenset({
    "p", "div", "section", "article", "br", "li", "ul", "ol", "h1", "h2", "h3",
    "h4", "h5", "h6", "tr", "table", "blockquote", "header", "footer", "main",
})

_RE_ESPACIOS_LINEA = re.compile(r"[ \t]+")
_RE_LINEAS = re.compile(r"\n{3,}")


class ExtraccionError(Exception):
    """Fallo controlado al descargar o extraer una URL (mensaje ya en espanol)."""


# --------------------------------------------------------------------------- #
# Validacion de URL + guard SSRF (mismo criterio que api.rss)                  #
# --------------------------------------------------------------------------- #


def _ip_es_privada(ip: ipaddress._BaseAddress) -> bool:
    """True si la IP NO debe ser alcanzable desde un fetch de servidor (SSRF)."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _guard_ssrf(host: str) -> str | None:
    """Resuelve `host` y devuelve un error en espanol si apunta a una IP no permitida.

    Si el host ya es una IP literal se comprueba directo. Si es un nombre, se resuelve
    (A/AAAA) y se comprueban TODAS las direcciones: con que UNA sea privada se rechaza
    (defensa frente a DNS rebinding / nombres que resuelven a interno).
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if _ip_es_privada(ip):
            return "La URL apunta a una dirección no permitida."
        return None

    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, OSError):
        return "No se pudo resolver el host de la URL."
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if _ip_es_privada(ip):
            return "La URL apunta a una dirección no permitida."
    return None


def validar_url(url: object) -> tuple[str | None, str | None]:
    """Valida una URL para ingesta: `(url_limpia, None)` o `(None, mensaje_en_espanol)`.

    Reglas (mismas que `api.rss.validar_url`): string no vacio, esquema SOLO
    `http`/`https`, con host, y guard SSRF sobre el host resuelto.
    """
    if not isinstance(url, str) or not url.strip():
        return None, "Pega una URL para generar el borrador."
    url = url.strip()
    try:
        partes = urlsplit(url)
    except ValueError:
        return None, "La URL no es válida."
    if partes.scheme not in ("http", "https"):
        return None, "La URL debe empezar por http:// o https://."
    host = partes.hostname
    if not host:
        return None, "La URL no tiene un host válido."
    error = _guard_ssrf(host)
    if error is not None:
        return None, error
    return url, None


def es_host_de_video(url: str) -> bool:
    """True si la URL es de un host cuyo contenido principal es video/streaming.

    Compara el host (sin `www.`) contra `_HOSTS_VIDEO` (coincidencia de dominio o
    subdominio). Para esos no hay "articulo" que leer: degradamos con honestidad.
    """
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    if host.startswith("www."):
        host = host[4:]
    return any(host == h or host.endswith("." + h) for h in _HOSTS_VIDEO)


# --------------------------------------------------------------------------- #
# Descarga (INYECTABLE) + parseo de HTML a texto legible (stdlib)             #
# --------------------------------------------------------------------------- #


def _un_intento_descarga(url: str, timeout: float | None) -> str:
    """UN intento de descarga con `httpx` (timeout + tope de tamaño). Lo separa del bucle de
    reintentos para poder mockear el intento en tests. Lanza `ExtraccionError` con mensaje en
    español; deja escapar `httpx.TimeoutException`/`httpx.HTTPError` para que el bucle decida si
    reintenta (transitorio) o se rinde."""
    import httpx

    # UA de NAVEGADOR REAL (+ Accept/Accept-Language): muchas notas y páginas de eventos
    # responden 403 a un User-Agent que se delata como bot («KeniSocial/1.0»). Con cabeceras
    # de navegador, una fracción grande de esos 403 desaparece. Los que bloqueen por IP de
    # datacenter siguen fallando aquí, pero entonces cae al fallback web del asistente.
    cabeceras = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    }
    with httpx.Client(
        timeout=timeout or _TIMEOUT, follow_redirects=True, headers=cabeceras
    ) as cliente:
        with cliente.stream("GET", url) as respuesta:
            if respuesta.status_code != 200:
                raise ExtraccionError(
                    f"La página respondió con un error (HTTP {respuesta.status_code})."
                )
            trozos: list[bytes] = []
            total = 0
            for trozo in respuesta.iter_bytes():
                total += len(trozo)
                if total > _MAX_BYTES:
                    raise ExtraccionError("La página es demasiado grande y se canceló la descarga.")
                trozos.append(trozo)
            codificacion = respuesta.encoding or "utf-8"
    try:
        return b"".join(trozos).decode(codificacion, errors="replace")
    except (LookupError, ValueError):
        return b"".join(trozos).decode("utf-8", errors="replace")


def _descargar_real(url: str, timeout: float | None = None, reintentos: int = 1) -> str:
    """Descarga la pagina con `httpx` respetando timeout y tamano maximo.

    Sigue redirects (las notas suelen redirigir a https/canonical), pero el guard SSRF ya se
    aplico al host de partida. `timeout` (opcional) sube el tope por defecto (`_TIMEOUT`) cuando la
    descarga ocurre FUERA de una petición HTTP. `reintentos` (≥1) REINTENTA con backoff los fallos
    TRANSITORIOS (timeout/conexión) —misma resiliencia que el motor de feeds de Fuentes—; un 4xx,
    una página demasiado grande o "sin texto" NO se reintentan. Lanza `ExtraccionError` (español).
    """
    try:
        import httpx
    except ImportError as e:  # pragma: no cover -- httpx es dependencia transitiva
        raise ExtraccionError("Falta la librería para leer páginas en este equipo.") from e

    intentos = max(1, reintentos)
    for i in range(intentos):
        try:
            return _un_intento_descarga(url, timeout)
        except ExtraccionError:
            raise  # HTTP 4xx/5xx o demasiado grande: definitivo, no reintentar.
        except (httpx.TimeoutException, httpx.TransportError) as e:
            # Transitorio (lento/cortó/no contactó): espera con backoff y reintenta.
            if i < intentos - 1:
                time.sleep(_ESPERA_REINTENTO_SEG[min(i, len(_ESPERA_REINTENTO_SEG) - 1)])
                continue
            if isinstance(e, httpx.TimeoutException):
                raise ExtraccionError("La página tardó demasiado y se canceló.") from e
            raise ExtraccionError("No se pudo contactar con la página.") from e
        except httpx.HTTPError as e:
            raise ExtraccionError("No se pudo contactar con la página.") from e
    raise ExtraccionError("No se pudo contactar con la página.")  # pragma: no cover -- inalcanzable


# Punto INYECTABLE: lo unico que toca la red. Los tests lo parchean (sin red real).
_DESCARGADOR = _descargar_real


# --------------------------------------------------------------------------- #
# Descarga de una IMAGEN remota a media (S3/disco)                            #
# --------------------------------------------------------------------------- #
# Reutiliza el MISMO guard SSRF + límites que la extracción de texto. Sirve para
# HOSTEAR la imagen original de un artículo (p.ej. un RSS de marca propia) como un
# asset propio publicable, en vez de depender de una URL externa que puede caducar.


def _descargar_bytes_real(url: str) -> bytes:
    """Descarga los BYTES crudos de una URL (httpx, timeout + tope de tamaño).

    El guard SSRF se aplica ANTES (en `descargar_imagen_a_media`). Import diferido de
    httpx (igual que `_descargar_real`). Punto INYECTABLE (`_DESCARGADOR_BYTES`): los
    tests lo parchean para NUNCA tocar la red. Lanza `ExtraccionError` (en español).
    """
    try:
        import httpx
    except ImportError as e:  # pragma: no cover -- httpx es dependencia transitiva
        raise ExtraccionError("Falta la librería para descargar imágenes.") from e

    cabeceras = {"User-Agent": "Mozilla/5.0 (compatible; KeniSocial/1.0; +operativo)"}
    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True, headers=cabeceras) as cliente:
            with cliente.stream("GET", url) as respuesta:
                if respuesta.status_code != 200:
                    raise ExtraccionError(
                        f"La imagen respondió con un error (HTTP {respuesta.status_code})."
                    )
                trozos: list[bytes] = []
                total = 0
                for trozo in respuesta.iter_bytes():
                    total += len(trozo)
                    if total > _MAX_BYTES:
                        raise ExtraccionError("La imagen es demasiado grande y se canceló la descarga.")
                    trozos.append(trozo)
    except ExtraccionError:
        raise
    except httpx.TimeoutException as e:
        raise ExtraccionError("La imagen tardó demasiado y se canceló.") from e
    except httpx.HTTPError as e:
        raise ExtraccionError("No se pudo descargar la imagen.") from e
    return b"".join(trozos)


# Punto INYECTABLE para tests (sin red): la descarga binaria de imagen.
_DESCARGADOR_BYTES = _descargar_bytes_real


def _ext_imagen(datos: bytes) -> str | None:
    """Extensión de imagen deducida por los magic bytes; None si no es una imagen soportada.

    Validar el contenido REAL (no fiarse del content-type ajeno) evita guardar como imagen
    algo que no lo es, y fija la extensión/`content-type` correctos al servirla.
    """
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if datos.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if datos[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "webp"
    return None


def _dimensiones_imagen(datos: bytes) -> tuple[int, int] | None:
    """`(ancho, alto)` en px leídos de la CABECERA, o None si no se pudo medir. PURA.

    Lee solo los bytes de cabecera de cada formato (png/gif/webp/jpeg) — no decodifica la
    imagen ni depende de Pillow. None cuando el formato no se reconoce o la cabecera está
    truncada: el llamante trata "no medible" como "no bloquear" (solo rechazamos cuando
    MEDIMOS que es demasiado pequeña), así nunca descartamos una imagen válida que no supimos leer.
    """
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(datos) >= 24:
            return (int.from_bytes(datos[16:20], "big"), int.from_bytes(datos[20:24], "big"))
        return None
    if datos[:6] in (b"GIF87a", b"GIF89a"):
        if len(datos) >= 10:
            return (int.from_bytes(datos[6:8], "little"), int.from_bytes(datos[8:10], "little"))
        return None
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        if len(datos) < 30:
            return None
        fourcc = datos[12:16]
        if fourcc == b"VP8X":
            return (
                int.from_bytes(datos[24:27], "little") + 1,
                int.from_bytes(datos[27:30], "little") + 1,
            )
        if fourcc == b"VP8 ":
            return (
                int.from_bytes(datos[26:28], "little") & 0x3FFF,
                int.from_bytes(datos[28:30], "little") & 0x3FFF,
            )
        if fourcc == b"VP8L":
            bits = int.from_bytes(datos[21:26], "little")
            return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        return None
    if datos.startswith(b"\xff\xd8\xff"):
        return _dimensiones_jpeg(datos)
    return None


def _dimensiones_jpeg(datos: bytes) -> tuple[int, int] | None:
    """`(ancho, alto)` de un JPEG recorriendo sus marcadores hasta el SOF. None si no se halla."""
    i, n = 2, len(datos)
    while i + 9 < n:
        if datos[i] != 0xFF:
            i += 1
            continue
        marcador = datos[i + 1]
        # Marcadores sin segmento de longitud (SOI/EOI/RSTn/relleno): se saltan en 2 bytes.
        if marcador in (0xD8, 0xD9, 0x01) or 0xD0 <= marcador <= 0xD7:
            i += 2
            continue
        # SOF (alto/ancho): C0–CF salvo DHT(C4), JPG(C8) y DAC(CC).
        if marcador in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            return (int.from_bytes(datos[i + 7:i + 9], "big"), int.from_bytes(datos[i + 5:i + 7], "big"))
        i += 2 + int.from_bytes(datos[i + 2:i + 4], "big")
    return None


def descargar_imagen_a_media(url: str, *, min_lado: int = 0, categoria: str = "fotos") -> str:
    """Descarga una imagen desde `url` (SSRF guard) y la GUARDA en media (S3/disco).

    Devuelve el nombre del objeto guardado (servible en `/api/media/{nombre}`), ya un
    asset propio publicable. Lanza `ExtraccionError` (mensaje en español) si la URL es
    inválida/insegura, la descarga falla, o el contenido no es una imagen soportada
    (png/jpg/gif/webp).

    `min_lado` (px, 0 = sin filtro): rechaza imágenes cuyo lado MEDIDO sea menor (filtra
    basura tipo el emoji-fallback de WordPress 72×72 que algunas notas traen como og:image).
    Solo bloquea cuando se PUEDE medir y es pequeña; una cabecera que no sabemos leer NO se
    descarta (no rechazamos una imagen válida por no medirla).

    `categoria`: subcarpeta del almacen. Por defecto `fotos` (foto cruda propia: original de
    artículo RSS o subida del equipo). El stock SIN LICENCIA usa `copyright` para aislarlo.
    """
    from .. import media

    url_limpia, error = validar_url(url)
    if error is not None or url_limpia is None:
        raise ExtraccionError(error or "La URL de la imagen no es válida.")
    datos = _DESCARGADOR_BYTES(url_limpia)
    if not datos:
        raise ExtraccionError("La URL no devolvió ninguna imagen.")
    ext = _ext_imagen(datos)
    if ext is None:
        raise ExtraccionError("El contenido descargado no es una imagen (png/jpg/gif/webp).")
    if min_lado > 0:
        dims = _dimensiones_imagen(datos)
        if dims is not None and min(dims) < min_lado:
            raise ExtraccionError(
                f"La imagen es demasiado pequeña ({dims[0]}×{dims[1]} px; mínimo {min_lado} px de lado)."
            )
    try:
        # Foto cruda en su carpeta por tipo: `fotos` para originales propias (RSS/subidas),
        # `copyright` para stock sin licencia. Nunca a `generadas`.
        return media.guardar_bytes(datos, ext=ext, categoria=categoria)
    except media.MediaError as e:
        raise ExtraccionError(str(e)) from e


class _ExtractorTexto(HTMLParser):
    """Extrae texto legible de un HTML: tira basura, separa bloques, capta el titulo.

    Mantiene una profundidad de etiquetas "basura" (`script/style/...`) para ignorar su
    texto. Capta el `<title>` aparte para usarlo de encabezado de la nota. Si aparece un
    `<article>`/`<main>`, marca que hay region principal: el texto fuera de ella se
    descarta (los menus/footers suelen quedar fuera), reduciendo contenido irrelevante.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._basura = 0
        self._en_title = False
        self.titulo: str = ""
        self._trozos: list[str] = []
        # Region principal (<article>/<main>): si existe, solo capturamos dentro de ella.
        self._hay_principal = False
        self._prof_principal = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:  # noqa: ANN001
        if tag in _TAGS_BASURA:
            self._basura += 1
            return
        if tag == "title":
            self._en_title = True
            return
        if tag in ("article", "main"):
            self._hay_principal = True
            self._prof_principal += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _TAGS_BASURA:
            self._basura = max(0, self._basura - 1)
            return
        if tag == "title":
            self._en_title = False
            return
        if tag in ("article", "main") and self._prof_principal > 0:
            self._prof_principal -= 1
        if tag in _TAGS_BLOQUE and self._capturando():
            self._trozos.append("\n")

    def _capturando(self) -> bool:
        """True si el texto actual cuenta (fuera de basura y, si hay region, dentro)."""
        if self._basura > 0:
            return False
        if self._hay_principal:
            return self._prof_principal > 0
        return True

    def handle_data(self, data: str) -> None:
        if self._basura > 0:
            return
        if self._en_title:
            self.titulo += data
            return
        if self._capturando() and data.strip():
            self._trozos.append(data)

    def texto(self) -> str:
        """Texto reunido, con saltos de bloque normalizados (sin pegar palabras)."""
        return " ".join(
            t if t == "\n" else t.strip() for t in self._trozos if t == "\n" or t.strip()
        )


def _normalizar(texto: str) -> str:
    """Colapsa espacios por linea y limita los saltos seguidos (legibilidad)."""
    lineas = [_RE_ESPACIOS_LINEA.sub(" ", ln).strip() for ln in texto.split("\n")]
    unido = "\n".join(ln for ln in lineas if ln)
    return _RE_LINEAS.sub("\n\n", unido).strip()


def _texto_de_html(html: str) -> tuple[str, str]:
    """Extrae `(titulo, cuerpo)` legible de un HTML. Tolerante a HTML mal formado."""
    parser = _ExtractorTexto()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 -- HTML roto: usamos lo reunido hasta el fallo
        pass
    titulo = _RE_ESPACIOS_LINEA.sub(" ", parser.titulo).strip()
    cuerpo = _normalizar(parser.texto())
    if len(cuerpo) > _MAX_TEXTO_EXTRAIDO:
        cuerpo = cuerpo[:_MAX_TEXTO_EXTRAIDO].rstrip() + "…"
    return titulo, cuerpo


def extraer_texto(
    url: str, *, timeout: float | None = None, reintentos: int = 1
) -> tuple[str, str]:
    """Descarga `url` y devuelve `(titulo, cuerpo)` legible. Lanza `ExtraccionError`.

    NO valida la URL (eso es de `validar_url`, que el endpoint llama antes para el guard
    SSRF). Lanza si la pagina es de video/streaming (no se puede leer como articulo) o si
    no se obtiene texto util. La descarga real vive en `_DESCARGADOR` (mockeable).

    `timeout` (opcional) sube el tope de descarga y `reintentos` (≥1) REINTENTA con backoff los
    fallos transitorios (timeout/conexión) —resiliencia del motor de feeds de Fuentes—. Ambos solo
    aplican con el descargador REAL; si `_DESCARGADOR` está mockeado (tests) se respeta el mock. Los
    usa el import en segundo plano, que descarga FUERA de la petición HTTP y puede esperar más.
    """
    if es_host_de_video(url):
        raise ExtraccionError(
            "Ese enlace es de un video o transmisión: no se puede leer como nota. "
            "Para video, descarga el clip y úsalo en «Clip a copy» (se transcribe en tu "
            "equipo); o pega el texto en «Copy desde nota»."
        )
    if (timeout is not None or reintentos != 1) and _DESCARGADOR is _descargar_real:
        html = _descargar_real(url, timeout=timeout, reintentos=reintentos)
    else:
        html = _DESCARGADOR(url)
    titulo, cuerpo = _texto_de_html(html)
    if not cuerpo.strip():
        raise ExtraccionError(
            "No se pudo extraer texto legible de esa página. Copia la nota y pégala en "
            "«Copy desde nota»."
        )
    return titulo, cuerpo


# --------------------------------------------------------------------------- #
# Composicion de la nota NO VERIFICADA para la skill de copy                   #
# --------------------------------------------------------------------------- #

# Encabezado que envuelve el texto extraido: deja CLARO a la skill (y al humano) que el
# contenido es ajeno y NO esta verificado, para que marque nombres/cifras/fechas en su
# auto-verificacion en vez de darlos por buenos. Honestidad / no alucinacion.
_AVISO_NO_VERIFICADO = (
    "AVISO: el siguiente texto se EXTRAJO AUTOMÁTICAMENTE de una página web ajena "
    "({url}). Trátalo como CONTENIDO NO VERIFICADO: la extracción puede traer "
    "nombres, cargos, cifras o fechas equivocados, o mezclar partes de la página que "
    "no son la nota. NO des por buenos esos datos: márcalos como «a verificar» en tu "
    "auto-verificación y, si una cifra o nombre no es fiable, formúlalo con prudencia "
    "u omítelo. No inventes nada que no esté en este texto."
)


def componer_nota_no_verificada(url: str, titulo: str, cuerpo: str) -> str:
    """Arma la nota que se pasa a `copy-desde-nota`, con el aviso de NO VERIFICADO.

    Forma: aviso + (titulo) + cuerpo + linea de fuente. El aviso va PRIMERO para que la
    skill lo lea antes que el contenido.
    """
    partes = [_AVISO_NO_VERIFICADO.format(url=url), ""]
    if titulo:
        partes.append(f"Título de la página (no verificado): {titulo}")
        partes.append("")
    partes.append(cuerpo)
    partes.append("")
    partes.append(f"Fuente (no verificada): {url}")
    return "\n".join(partes)
