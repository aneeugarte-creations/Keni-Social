"""Bloqueo infranqueable: una imagen de STOCK no autorizada NUNCA se publica.

Las fotos de stock (RSS original o APIs gratuitas) entran al sistema SOLO como AYUDA VISUAL:
se muestran atenuadas y con watermark "SIN LICENCIA", `falta_imagen` sigue activo, y NINGÚN
camino a `programado`/`publicado` las deja pasar hasta que un humano REVISE los derechos y las
autorice (`imagen_autorizada=1`). Internamente se pueden descargar/ver como referencia; lo que
queda prohibido es publicarlas sin licencia.

Una pieza es "stock sin autorizar" cuando `imagen_origen == 'stock'` y `imagen_autorizada` es
falso. El disparador es `imagen_origen` (no el default de `imagen_autorizada`), así la seguridad
no depende de un default: las piezas no-stock (todas las históricas) publican como siempre.

Este helper es la FUENTE ÚNICA del criterio; lo invocan los cinco caminos que llevan a publicar
(aprobación manual, auto-programación, PATCH de plataforma / MCP tablero, PUT de pieza, y el
programador que hace el posteo real), para que el bloqueo cubra TODAS las rutas.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Valor de `imagen_origen` que marca una foto externa (RSS/API gratuita) usada como ayuda visual.
ORIGEN_STOCK = "stock"

# Valor de `imagen_origen` de una foto con LICENCIA editorial (p. ej. AFP): SÍ es publicable sin
# autorización manual de derechos (la licencia ya los cubre), con CRÉDITO/BYLINE obligatorio. A
# diferencia del stock gratuito, NO dispara el bloqueo: solo `'stock'` sin autorizar bloquea.
ORIGEN_LICENCIADA = "licenciada"

# Orígenes de imagen PROPIA (sin metadata de licencia de terceros): IA generativa, foto de la
# galería de artes, subida del equipo. Para estos la metadata de licencia NO aplica.
ORIGEN_IA = "ia"
ORIGEN_GALERIA = "galeria"
ORIGEN_SUBIDA = "subida"

# Solo estos orígenes portan metadata de licencia SIGNIFICATIVA (proveedor/autor/licencia/crédito);
# `imagen_origen` es la ÚNICA verdad de si esa metadata aplica.
ORIGENES_CON_METADATA = frozenset({ORIGEN_STOCK, ORIGEN_LICENCIADA})

# Orígenes PROPIOS válidos al REEMPLAZAR la foto por la galería/subida/IA (nunca uno con metadata
# de licencia: el stock/licenciada se adjunta por su propia puerta, no por estos PATCH/PUT).
ORIGENES_PROPIOS = frozenset({"", ORIGEN_IA, ORIGEN_GALERIA, ORIGEN_SUBIDA})

# Campos de metadata de licencia que solo son significativos con un origen de `ORIGENES_CON_METADATA`.
_CAMPOS_METADATA_LICENCIA = (
    "imagen_proveedor",
    "imagen_autor",
    "imagen_licencia",
    "imagen_credito_url",
)

# Estados de publicación cuya entrada exige una imagen publicable (con licencia o autorizada).
ESTADOS_PUBLICABLES = frozenset({"programado", "publicado"})

# Mensaje único de rechazo (lo reusan API y MCP para responder igual en todos los caminos).
MOTIVO_BLOQUEO = (
    "La imagen es de stock SIN LICENCIA (solo ayuda visual): no se puede programar ni publicar "
    "hasta sustituirla por una propia/licenciada o autorizarla expresamente."
)

# BLOQUEO LEGAL por la licencia de la foto. Al componer una placa/título sobre la foto creamos
# una OBRA DERIVADA con uso comercial: una licencia NC (no comercial), ND (sin obra derivada),
# BY-SA (compartir-igual: contaminaría la publicación) o INDETERMINADA no lo permite.
MOTIVO_LICENCIA_NO_PUBLICABLE = (
    "La licencia de la imagen NO permite publicarla con placa de marca (uso no comercial, sin "
    "obra derivada, compartir-igual/BY-SA, o licencia indeterminada): sustitúyela por una propia, "
    "de licencia libre (CC0/Pexels/Pixabay) o licenciada de agencia."
)

# BLOQUEO por crédito ausente: una foto CC BY o de agencia licenciada EXIGE atribución, y el
# crédito DEBE viajar en el caption publicado; sin los datos del crédito no se puede programar.
MOTIVO_CREDITO_AUSENTE = (
    "La imagen exige crédito/atribución (CC BY o foto de agencia) y faltan datos del crédito "
    "(autor y licencia/fuente): complétalos antes de programar o publicar."
)

# Niveles de licencia (espejo de `nivelLicencia` del front), con un nivel propio para BY-SA:
# "compartir_igual" es legalmente distinto de "atribucion" porque BY-SA se BLOQUEA.
NIVEL_LIBRE = "libre"
NIVEL_ATRIBUCION = "atribucion"
NIVEL_COMPARTIR_IGUAL = "compartir_igual"
NIVEL_RESTRINGIDA = "restringida"

# Proveedores con licencia propia libre (uso comercial sin atribución obligatoria).
_PROVEEDORES_LIBRES = frozenset({"pexels", "pixabay"})

# Nombre legible de cada proveedor para la línea de crédito (espejo de `nombreProveedor` del front).
_NOMBRES_PROVEEDOR = {
    "pexels": "Pexels",
    "pixabay": "Pixabay",
    "wikimedia": "Wikimedia Commons",
    "nasa": "NASA",
    "openverse": "Openverse",
    "afp": "AFP",
    "rss": "Fuente original",
    "stock": "Stock",
}


def _norm(valor: Any) -> str:
    """Normaliza un texto a minúsculas sin espacios sobrantes (tolerante a None)."""
    return (valor or "").strip().lower() if isinstance(valor, str) else ""


def _nombre_proveedor(proveedor: str | None) -> str:
    """Nombre legible de un proveedor de stock/agencia para la atribución."""
    p = _norm(proveedor)
    if not p:
        return ""
    return _NOMBRES_PROVEEDOR.get(p, p[:1].upper() + p[1:])


def _clausula_restrictiva(lic: str) -> bool:
    """True si la licencia CC lleva cláusula NC (no comercial) o ND (sin obra derivada)."""
    return (
        "-nc" in lic
        or "nc-" in lic
        or "noncommercial" in lic
        or "non-commercial" in lic
        or "-nd" in lic
        or "nd-" in lic
        or "noderiv" in lic
    )


def es_share_alike(licencia: str | None) -> bool:
    """True si la licencia es share-alike (BY-SA): componer una placa obliga a licenciar igual."""
    lic = _norm(licencia)
    return "by-sa" in lic or "by sa" in lic


def nivel_licencia(licencia: str | None, proveedor: str | None) -> str:
    """Clasifica una foto por su LICENCIA REAL en un nivel (espejo del front, con BY-SA aparte).

    Devuelve `NIVEL_LIBRE`/`NIVEL_ATRIBUCION`/`NIVEL_COMPARTIR_IGUAL`/`NIVEL_RESTRINGIDA`.
    El proveedor solo decide en las agencias con licencia propia (Pexels/Pixabay).
    """
    lic = _norm(licencia)
    prov = _norm(proveedor)
    # 1. NC/ND: uso comercial o edición restringidos -> nunca publicable con garantías.
    if _clausula_restrictiva(lic):
        return NIVEL_RESTRINGIDA
    # 2. Agencias con licencia propia libre (Pexels/Pixabay): por proveedor.
    if prov in _PROVEEDORES_LIBRES:
        return NIVEL_LIBRE
    # 3. Dominio público / CC0 / obra de gobierno: libre, sin atribución obligatoria.
    if (
        "cc0" in lic
        or "publicdomain" in lic
        or "public domain" in lic
        or "dominio público" in lic
        or "dominio publico" in lic
        or "pdm" in lic
        or "us government" in lic
        or lic == "pd"
    ):
        return NIVEL_LIBRE
    # 4. CC BY-SA: comercial con crédito PERO share-alike -> nivel propio (se bloquea).
    if es_share_alike(lic):
        return NIVEL_COMPARTIR_IGUAL
    # 5. CC BY: comercial con crédito.
    if "by" in lic:
        return NIVEL_ATRIBUCION
    # 6. Vacío / genérico / desconocido: por prudencia, restringida (se bloquea).
    return NIVEL_RESTRINGIDA


def _es_foto_de_stock(origen: str | None) -> bool:
    """True si el origen es una foto de STOCK (gratuita); el gate de licencia CC aplica solo aquí."""
    return _norm(origen) == ORIGEN_STOCK


def _es_foto_licenciada(origen: str | None) -> bool:
    """True si el origen es una foto LICENCIADA de agencia (AFP)."""
    return _norm(origen) == ORIGEN_LICENCIADA


def publicable_por_licencia(
    licencia: str | None, proveedor: str | None, origen: str | None
) -> bool:
    """True si la licencia de la foto PERMITE publicarla (con placa de marca = obra derivada).

    - Foto LICENCIADA (AFP): True (su licencia editorial cubre publicar con crédito).
    - Foto NO de stock (propia: ia/galería/subida, o sin origen): True (este gate CC no aplica).
    - Foto de STOCK: True solo si su nivel es LIBRE (CC0/PD/Pexels/Pixabay) o ATRIBUCION (CC BY).
      BLOQUEA NC/ND (restringida), BY-SA (compartir_igual) y la licencia desconocida (restringida).
    """
    if _es_foto_licenciada(origen):
        return True
    if not _es_foto_de_stock(origen):
        return True
    return nivel_licencia(licencia, proveedor) in (NIVEL_LIBRE, NIVEL_ATRIBUCION)


def requiere_atribucion(
    licencia: str | None, proveedor: str | None, origen: str | None
) -> bool:
    """True si la foto EXIGE crédito en el caption: CC BY (stock) o foto de agencia licenciada.

    False para CC0/PD/Pexels/Pixabay/NASA y para fotos propias.
    """
    if _es_foto_licenciada(origen):
        return True
    if not _es_foto_de_stock(origen):
        return False
    return nivel_licencia(licencia, proveedor) == NIVEL_ATRIBUCION


def linea_credito(pieza: Mapping[str, Any] | None) -> str:
    """Texto de crédito para el caption a partir de los metadatos de la foto.

    Formato sobrio `📷 {autor} · {licencia} · vía {Fuente legible}` (+ URL del crédito si la hay).
    Devuelve "" si no hay datos mínimos (al menos autor, licencia o fuente).
    """
    if not pieza:
        return ""
    autor = (pieza.get("imagen_autor") or "").strip()
    licencia = (pieza.get("imagen_licencia") or "").strip()
    fuente = _nombre_proveedor(pieza.get("imagen_proveedor"))
    credito_url = (pieza.get("imagen_credito_url") or "").strip()
    partes: list[str] = []
    if autor:
        partes.append(autor)
    if licencia:
        partes.append(licencia)
    if fuente:
        partes.append(f"vía {fuente}")
    if not partes:
        return ""
    linea = "📷 " + " · ".join(partes)
    if credito_url:
        linea += f" · {credito_url}"
    return linea


def credito_completo(pieza: Mapping[str, Any] | None) -> bool:
    """True si la foto trae crédito SUFICIENTE para publicarla con atribución.

    Mínimo razonable: hay un AUTOR/byline acreditable Y se conoce la licencia o la fuente.
    (Para CC BY el ideal es además `imagen_credito_url`, pero no se exige para no bloquear de más.)
    """
    if not pieza:
        return False
    autor = (pieza.get("imagen_autor") or "").strip()
    licencia = (pieza.get("imagen_licencia") or "").strip()
    fuente = _nombre_proveedor(pieza.get("imagen_proveedor"))
    return bool(autor) and bool(licencia or fuente)


def es_stock_sin_autorizar(pieza: Mapping[str, Any] | None) -> bool:
    """True si la imagen adjunta es de stock y aún no la autorizó un humano.

    Acepta tanto el dict público de pieza (`db_piezas`) como la fila por plataforma
    (`db_publicacion`): ambos exponen `imagen_origen` e `imagen_autorizada`.
    """
    if not pieza:
        return False
    if (pieza.get("imagen_origen") or "") != ORIGEN_STOCK:
        return False
    return not bool(pieza.get("imagen_autorizada"))


def motivo_bloqueo(
    pieza: Mapping[str, Any] | None, estado_destino: str | None
) -> str | None:
    """Motivo (ES) por el que NO se puede mover la pieza a `estado_destino`, o None si pasa.

    Orden de comprobación (de más específico/humano a legal):
      1. Stock SIN LICENCIA no autorizado (gate humano de derechos).
      2. Licencia de la foto no publicable (NC/ND/BY-SA/desconocida) -> BLOQUEO LEGAL.
      3. Atribución requerida (CC BY / agencia) sin crédito suficiente -> BLOQUEO por crédito.
    """
    if (estado_destino or "") not in ESTADOS_PUBLICABLES:
        return None
    if not pieza:
        return None
    if es_stock_sin_autorizar(pieza):
        return MOTIVO_BLOQUEO
    origen = pieza.get("imagen_origen")
    licencia = pieza.get("imagen_licencia")
    proveedor = pieza.get("imagen_proveedor")
    if not publicable_por_licencia(licencia, proveedor, origen):
        return MOTIVO_LICENCIA_NO_PUBLICABLE
    if requiere_atribucion(licencia, proveedor, origen) and not credito_completo(pieza):
        return MOTIVO_CREDITO_AUSENTE
    return None


def bloquea_estado(pieza: Mapping[str, Any] | None, estado_destino: str | None) -> bool:
    """True si mover la pieza a `estado_destino` debe bloquearse (stock sin autorizar o licencia)."""
    return motivo_bloqueo(pieza, estado_destino) is not None


def origen_propio(origen: Any) -> str:
    """Normaliza el origen declarado al REEMPLAZAR la foto a uno PROPIO válido ('' si no es válido).

    Nunca devuelve `stock`/`licenciada`: esos orígenes (con metadata de licencia) solo los fija la
    puerta de adjuntar stock/agencias, jamás un PATCH/PUT de foto propia.
    """
    o = _norm(origen)
    return o if o in ORIGENES_PROPIOS else ""


def normalizar_campos_imagen(
    campos: dict[str, Any], previa: Mapping[str, Any] | None
) -> dict[str, Any]:
    """FUERZA la invariante de metadata de licencia sobre un update de imagen, según el origen RESULTANTE.

    `imagen_origen` es la ÚNICA verdad de si la metadata de licencia aplica. Dado el update
    (`campos`) y la fila previa, calcula el origen resultante (`campos['imagen_origen']` o, si no
    se toca, el de `previa`):
      - Origen resultante ∈ {stock, licenciada}: NO toca la metadata (la pone el adjuntar de
        stock/agencias). Así una COMPOSICIÓN de la misma foto (placa/reframe/render que solo
        cambian `imagen`) CONSERVA crédito/licencia/bloqueo —resetearlos publicaría sin crédito o
        saltaría el gate—.
      - Origen resultante propio/IA/vacío: la metadata NO aplica -> vacía proveedor/autor/
        licencia/crédito, `imagen_autorizada=0` y, si hay imagen propia/IA real, `falta_imagen=0`.

    No hace nada si el update NO toca la imagen (ningún campo de foto/imagen/origen/metadata): es
    seguro llamarla en cualquier mutación. Muta y devuelve `campos`.
    """
    previa = previa or {}
    if not any(
        k in campos
        for k in (
            "foto",
            "imagen",
            "imagen_origen",
            "imagen_autorizada",
            *_CAMPOS_METADATA_LICENCIA,
        )
    ):
        return campos
    origen_resultante = _norm(campos.get("imagen_origen", previa.get("imagen_origen")))
    if origen_resultante in ORIGENES_CON_METADATA:
        return campos
    campos["imagen_origen"] = origen_resultante
    for clave in _CAMPOS_METADATA_LICENCIA:
        campos[clave] = ""
    campos["imagen_autorizada"] = False
    imagen_resultante = campos.get("imagen", previa.get("imagen")) or ""
    foto_resultante = campos.get("foto", previa.get("foto")) or ""
    if imagen_resultante.strip() or foto_resultante.strip():
        campos["falta_imagen"] = False
    return campos
