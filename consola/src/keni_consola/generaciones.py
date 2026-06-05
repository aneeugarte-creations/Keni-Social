"""Dominio GENERACIONES: trabajos de IA en SEGUNDO PLANO, seguibles en vivo.

TODA generacion de IA de la consola (copy desde nota, copy desde RSS, hashtags,
imagen) corre como un TRABAJO en segundo plano en vez de bloquear la peticion HTTP:

  1. El endpoint valida, crea un registro `{estado: "ejecutando"}` y ENCOLA el trabajo
     (#130 Fase 2): persiste un `spec` serializable en la cola (`cola.py`/tabla `jobs`).
  2. El POST responde de INMEDIATO con el registro (no bloquea, no hay timeout de 180 s
     en la peticion). El trabajo sigue aunque el usuario cambie de pestana o de pagina.
  3. Un WORKER (in-proceso en local, servicio aparte en hosted; ver `worker.py`) CLAVA el
     job, reconstruye prompt+post-procesado desde el `spec` y corre `claude -p` con el
     runner de `lanzar_job_claude` (mismo #137: grupo de procesos, kill del arbol, tope de
     cola, cancelacion). El hilo avanza el registro de forma incremental y ATOMICA: persiste
     el TEXTO en vivo (stream token a token con `--include-partial-messages`) + metricas
     parciales. Al terminar fija el estado terminal (`completado` con el `resultado` ya
     procesado, o `error`).
  4. El frontend SONDEA `GET /api/generaciones/{id}` hasta el estado terminal.

DESACOPLO (#130 Fase 2 / ADR 0002 Fase B): el back ENCOLA (`encolar_job_claude`) y el
WORKER EJECUTA (`lanzar_job_claude`). `lanzar_job_claude` NO desaparece: es la primitiva de
ejecucion del worker (con todo el #137). En el perfil LOCAL el worker corre en un hilo del
propio back (UX de una sola maquina intacta, sin servicio aparte); en HOSTED corre en un
contenedor `worker` que SI tiene `claude` (la imagen del back ya no lleva Node).

El registro YAML es la FUENTE DE VERDAD del sondeo. Los ARTEFACTOS durables (historial
de skills, publicaciones, imagenes) se guardan en su sitio de siempre; el registro de
generacion es estado de ejecucion (efimero, inspeccionable), por eso vive aparte de los
datos editoriales:

    <KENI_CONSOLA_GENERACIONES>/<id>.yaml         (def local ~/.config/keni-social/
    generaciones; bajo KENI_DATA_DIR cuelga de <data_dir>/keni-social/generaciones)

LANZADORES INYECTABLES: `lanzar_job_claude` y `lanzar_job_imagen` son funciones a nivel
de modulo; `crear_app(...)` las reasigna y los tests pasan fakes que NO usan Popen ni
red (NUNCA se llama a `claude` ni a un proveedor de imagen real en tests). El
`procesar` (callback que parsea la salida y crea los artefactos) SI corre en los tests
(con una salida canned), asi se cubre el post-procesado real.

SEGURIDAD: escritura atomica (tmp + os.replace); el id de un registro se sanea contra
traversal al leer; sin shell (argv como lista). Errores en espanol, sin tracebacks.

ENDURECIMIENTO PERMANENTE (#137): la generacion se hace —y se SEGUIRA haciendo— con el
subprocess `claude -p` (ahora en sandbox por usuario; ver ADR 0001), NO con la API de
Claude. Por eso este lanzador NO es transitorio: su robustez es deuda PERMANENTE:
  - GRUPO DE PROCESOS: el subprocess arranca con su propio grupo (`runner.lanzar_proc`)
    y al timeout/cancel se mata el ARBOL entero (`runner.matar_arbol`), no solo el padre.
  - TOPE DE COLA: `runner.slot()` rechaza con `ColaLlenaError` si la cola esta al tope;
    aqui se refleja como `error`/`motivo="cola_llena"` y el llamante lo traduce a 429.
  - CANCELACION: `cancelar(gen_id)` mata el arbol del job y lo marca cancelado; el usuario
    la dispara desde la SPA (`POST /api/generaciones/{id}/cancelar`).
  - SIN TRAGAR EXCEPCIONES: los fallos del hilo se LOGUEAN correlacionados por job-id (y
    por el request-id de la peticion que lo lanzo, #123), ya no se silencian en mudo.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import threading
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from keni_shared.esquema_yaml import migrar, sellar

from . import config, preferencias, rutas
from .dominio import runner, stream
from .dominio.runner import ColaLlenaError  # noqa: F401  (re-export; ver nota abajo)
from .io_atomico import bloqueo_archivo, escribir_atomico
from .observabilidad import request_id_actual

# `ColaLlenaError` se RE-EXPORTA aqui (tope de cola, #137): los endpoints capturan
# `generaciones.ColaLlenaError` sin acoplarse al modulo `dominio.runner`. Lo usan otros
# modulos, no este, de ahi el `noqa: F401` en el import de arriba.

# Logger del lanzador de generaciones: cuelga del logger raiz del paquete (#123), asi
# `configurar_logging()` fija nivel/handler para todo. Aqui logueamos los fallos del hilo
# de generacion CON el job-id en vez de tragarlos (antes `except Exception: pass`).
_log = logging.getLogger("keni_consola.generaciones")

# Estados terminales e intermedio de un trabajo.
ESTADO_EJECUTANDO = "ejecutando"
ESTADO_COMPLETADO = "completado"
ESTADO_ERROR = "error"
# Fases de PROGRESO (en que etapa va el run, no cuanto falta). Re-exportadas del dominio
# (`stream`), unica fuente. La UI las pinta ("Razonando…" → "Escribiendo…" → "Terminando…").
# Migracion suave: registros viejos sin `fase` la traen como "" (la UI cae al comportamiento
# previo); por eso NO sube la version de esquema YAML (anadir un campo opcional vacio es compat).
FASE_RAZONANDO = stream.FASE_RAZONANDO
FASE_GENERANDO = stream.FASE_GENERANDO
FASE_COMPLETADO = stream.FASE_COMPLETADO
# Motivos terminales (campo `motivo`): para que el llamante/UI distingan el porque.
MOTIVO_TIMEOUT = "timeout"
MOTIVO_COLA_LLENA = "cola_llena"
MOTIVO_CANCELADO = "cancelado"
# Una generacion quedo `ejecutando` pero su proceso murio (reinicio/deploy, OOM, worker
# matado, o `generar()` colgado): el finalizador nunca corrio. El reaper la marca asi.
MOTIVO_INTERRUMPIDO = "interrumpido"

# Tipos de trabajo (para que el frontend sepa como renderizar el resultado).
TIPOS = (
    "copy", "rss", "hashtags", "imagen", "verificacion", "qa-editorial", "prompt",
    "parrilla-import",
    # Taller GREEN / brainstorming: `green-ideas` = la PROPUESTA de ideas evergreen (IA);
    # `green` = el copy de una idea APROBADA (pieza `flujo='evergreen'` del tablero).
    "green-ideas", "green",
)

# Wall-timeout (segundos) de un trabajo de claude en background. Override por
# `KENI_CLAUDE_TIMEOUT` (centralizado en `config.claude_timeout`). Sustituye al viejo
# timeout de 180 s de la peticion sincrona.

# Registro EN MEMORIA de trabajos en vuelo (id -> handle). El YAML es la fuente de
# verdad para el sondeo; esto solo permite inspeccionar/cancelar localmente.
_HANDLES: dict[str, dict[str, object]] = {}
_HANDLES_LOCK = threading.Lock()

# Numero de generaciones recientes que devuelve el listado.
_LISTADO_MAX = 50


def _timeout() -> int:
    """Wall-timeout (s) de un trabajo de claude; `KENI_CLAUDE_TIMEOUT` lo sobreescribe."""
    return config.claude_timeout()


# Patron del NOMBRE base de un registro de generacion (`<id>.yaml`): exactamente 12 hex,
# tal como los acuna `nuevo_id`. La poda solo borra ficheros cuyo stem case con esto (nunca
# temporales `.tmp-*` ni nombres ajenos en el dir).
_ES_ID = re.compile(r"[0-9a-f]{12}")


def nuevo_id() -> str:
    """Nuevo id de generacion (12 hex)."""
    return uuid.uuid4().hex[:12]


def ahora_iso() -> str:
    """Fecha-hora ISO a segundos (orden determinista de las generaciones)."""
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Localizacion del almacen + escritura atomica                                #
# --------------------------------------------------------------------------- #


def raiz() -> Path:
    """Dir donde viven los registros de generacion.

    `KENI_CONSOLA_GENERACIONES` lo fija (override de maxima prioridad; tests). Si no,
    cuelga de la raiz de estado unica (`rutas.dir_config()`), igual que el resto de
    recursos de config: local `${XDG_CONFIG_HOME:-~/.config}/keni-social/generaciones`,
    o `<KENI_DATA_DIR>/keni-social/generaciones` en contenedor.

    XDG (#126): antes este recurso IGNORABA `XDG_CONFIG_HOME` (siempre `~/.config`); ahora
    lo respeta como los demas. Con XDG SIN fijar el default es IDENTICO al historico
    (`~/.config/keni-social/generaciones`), asi no se orfanan registros locales existentes.
    """
    if (p := config.override_ruta(config.ENV_GENERACIONES)) is not None:
        return p
    return rutas.dir_config() / "generaciones"


def _ruta(gen_id: str) -> Path:
    """Ruta `<raiz>/<id>.yaml` saneada (solo el nombre base; anti-traversal)."""
    base = raiz()
    seguro = Path(gen_id).name
    if not seguro or seguro != gen_id or seguro in (".", ".."):
        raise ValueError("Identificador de generación no válido.")
    destino = (base / f"{seguro}.yaml").resolve()
    if destino.parent != base.resolve():
        raise ValueError("Ruta de generación fuera del almacén.")
    return destino


# Tipo de esquema de este modulo (un solo tipo de fichero: el registro de generacion).
_TIPO = "generacion"


def _escribir_yaml_atomico(ruta_fichero: Path, datos: dict[str, Any]) -> None:
    """Escribe un dict como YAML de forma ATOMICA (tmp en el mismo dir + os.replace).

    `sellar` estampa la `version` de esquema antes de volcar (#125). Se aplica DESPUES
    de `_cuerpo` (que filtra claves vacias), asi la `version` int siempre sobrevive.
    """
    texto = yaml.safe_dump(
        sellar(_TIPO, datos),
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=4096,
    )
    escribir_atomico(ruta_fichero, texto, sufijo=".yaml")


def _leer_yaml(ruta_fichero: Path) -> dict[str, Any] | None:
    """Lee un YAML como dict, o None si no existe / esta corrupto / no es un mapa.

    `migrar` sube de version el dict legado en memoria (#125).
    """
    try:
        texto = ruta_fichero.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        datos = yaml.safe_load(texto)
    except yaml.YAMLError:
        return None
    if not isinstance(datos, dict):
        return None
    return migrar(_TIPO, datos)


# --------------------------------------------------------------------------- #
# Normalizacion + CRUD del registro                                           #
# --------------------------------------------------------------------------- #


def _publico(datos: dict[str, Any], gen_id: str) -> dict[str, Any]:
    """Reconstruye el dict PUBLICO de una generacion (forma estable para la API/UI)."""
    metricas = datos.get("metricas")
    if not isinstance(metricas, dict) or not metricas:
        metricas = None
    resultado = datos.get("resultado")
    if not isinstance(resultado, dict) or not resultado:
        resultado = None

    def _str(clave: str) -> str:
        valor = datos.get(clave)
        return valor if isinstance(valor, str) else ""

    return {
        "id": gen_id,
        "tipo": _str("tipo"),
        "marca": _str("marca"),
        # Contenido correlacionado (opcional): las generaciones-marcador del pipeline
        # (`tipo='pipeline'`) lo sellan para que la vista Pipelines ate cada etapa a su run.
        # Ausente en registros legados/normales => "" (lo filtra `_cuerpo`, así no engorda).
        "contenido_id": _str("contenido_id"),
        # Generación correlacionada (opcional): un MARCADOR de etapa del pipeline (CD/QA)
        # apunta con `gen_id` a la generación REAL de `claude -p` de esa etapa, para que la
        # vista Pipelines pueda mostrar su STREAM (el proceso de pensamiento del agente).
        # Ausente en registros legados/normales => "" (lo filtra `_cuerpo`, así no engorda).
        "gen_id": _str("gen_id"),
        "etiqueta": _str("etiqueta"),
        "estado": _str("estado"),
        # Fase de PROGRESO (en que etapa va; ausente en registros legados => "").
        "fase": _str("fase"),
        "motivo": _str("motivo"),
        "salida": _str("salida"),
        # Razonamiento (thinking) en vivo, cola acotada: feedback mientras el modelo piensa.
        # Como el prompt, se expone en el detalle y `_todas_ordenadas` lo quita del listado.
        "razonamiento": _str("razonamiento"),
        # Prompt EXACTO enviado a `claude -p` (visibilidad/control). Se persiste pero se
        # expone SOLO en el detalle (`obtener`); `_todas_ordenadas` lo quita del listado
        # para no engordar Actividad. Ausente en registros legados => "".
        "prompt": _str("prompt"),
        "error": _str("error"),
        # Atribucion por usuario (#130 Fase 1). Ausente en registros legados/anonimos => "".
        "autor_id": _str("autor_id"),
        "autor_nombre": _str("autor_nombre"),
        "metricas": metricas,
        "resultado": resultado,
        "fecha_inicio": _str("fecha_inicio"),
        "fecha_fin": _str("fecha_fin"),
    }


def crear(datos: dict[str, Any]) -> dict[str, Any]:
    """Crea un registro de generacion y lo escribe (atomico). Devuelve el dict publico.

    `datos` debe traer al menos `tipo`, `marca`, `etiqueta`. Si no trae `id`/`estado`/
    `fecha_inicio`, se rellenan (`estado="ejecutando"`, fecha = ahora).
    """
    gen_id = datos.get("id") or nuevo_id()
    completo = {
        "estado": ESTADO_EJECUTANDO,
        "fecha_inicio": ahora_iso(),
        **datos,
        "id": gen_id,
    }
    pub = _publico(completo, gen_id)
    _escribir_yaml_atomico(_ruta(gen_id), _cuerpo(pub))
    return pub


# Estados TERMINALES de una generacion (ya no esta en vuelo). Una idempotencia solo retiene a
# DOS lanzamientos del MISMO trabajo mientras hay uno EN VUELO; al terminar, un re-lanzamiento
# legitimo (el usuario quiere regenerar) vuelve a correr.
_ESTADOS_TERMINALES = frozenset({ESTADO_COMPLETADO, ESTADO_ERROR})


def clave_idempotencia(*partes: Any) -> str:
    """Deriva una clave de idempotencia ESTABLE (hex de 32) de las partes del lanzamiento.

    Une las partes (autor, tipo, marca, contenido, prompt...) con un separador que no puede
    aparecer dentro de ellas y la hashea. Dos lanzamientos del MISMO trabajo logico producen la
    MISMA clave; un trabajo distinto (otro tema/tipo/redes -> otro prompt) produce otra. El
    resultado es un nombre de fichero seguro (solo hex), apto para el indice en disco.
    """
    crudo = "\x1f".join("" if p is None else str(p) for p in partes)
    return hashlib.blake2b(crudo.encode("utf-8"), digest_size=16).hexdigest()


def _ruta_idem(clave: str) -> Path:
    """Ruta `<raiz>/idem-<clave>.idx` saneada (solo hex; anti-traversal). El indice clave->gen_id."""
    base = raiz()
    seguro = re.sub(r"[^0-9a-f]", "", (clave or "").lower())
    if not seguro:
        raise ValueError("Clave de idempotencia no válida.")
    destino = (base / f"idem-{seguro}.idx").resolve()
    if destino.parent != base.resolve():
        raise ValueError("Ruta de idempotencia fuera del almacén.")
    return destino


def crear_idempotente(clave: str, datos: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Crea una generacion BAJO una clave de idempotencia. Devuelve `(gen, nueva)`.

    CONVERGENCIA ATOMICA: usa una creacion EXCLUSIVA de fichero (`O_CREAT|O_EXCL`) del indice
    `idem-<clave>.idx` como mutex en disco (el analogo a un indice UNICO): SOLO un llamante puede
    crearlo. El ganador acuña un `gen_id`, escribe el registro, sella el indice con ese id y
    devuelve `(gen, True)` (debe encolar). Un llamante CONCURRENTE que choca con el `O_EXCL` lee
    el `gen_id` del indice; si esa generacion EXISTE y NO es terminal, devuelve `(gen_existente,
    False)` (NO encola: comparte el run en vuelo). Si el indice apunta a una generacion ya
    TERMINAL o desaparecida (claim viejo de un run que ya acabo), el indice se RECLAMA para este
    lanzamiento nuevo (un re-lanzamiento legitimo tras completar debe poder correr).

    Asi dos POST casi-simultaneos del MISMO trabajo convergen a UNA generacion (un solo `claude
    -p`), y dos trabajos DISTINTOS (claves distintas) corren cada uno el suyo.
    """
    base = raiz()
    base.mkdir(parents=True, exist_ok=True)
    ruta_idx = _ruta_idem(clave)
    # Reintento acotado: cubre la carrera "el ganador aun no sello el id" y el reciclaje de un
    # claim terminal. En la practica converge en 1-2 vueltas; el tope evita un bucle infinito.
    for _ in range(50):
        try:
            fd = os.open(ruta_idx, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            gen_id_existente = _leer_idem(ruta_idx)
            if gen_id_existente:
                existente = obtener(gen_id_existente)
                if existente is not None and existente.get("estado") not in _ESTADOS_TERMINALES:
                    return existente, False  # run en vuelo: comparte, NO encoles otro
            # Claim viejo (terminal/ausente) o aun sin sellar: intenta reclamarlo borrandolo y
            # reintentando la creacion exclusiva. Si otro lo recrea entre medias, la siguiente
            # vuelta lo vera y compartira (o reciclara) segun su estado.
            try:
                os.unlink(ruta_idx)
            except FileNotFoundError:
                pass
            continue
        else:
            try:
                gen = crear(datos)
                os.write(fd, gen["id"].encode("ascii"))
            finally:
                os.close(fd)
            return gen, True
    # No deberia ocurrir (la carrera converge): degradamos a un lanzamiento NO idempotente
    # (crear + encolar) antes que bloquear al usuario. Mejor un posible duplicado que un cuelgue.
    _log.warning("idempotencia de generación: no convergió la clave %s; lanzo sin guardia", clave[:16])
    return crear(datos), True


def _leer_idem(ruta_idx: Path) -> str:
    """Lee el `gen_id` sellado en un indice de idempotencia ("" si vacio/ilegible)."""
    try:
        return ruta_idx.read_text(encoding="ascii").strip()
    except OSError:
        return ""


def actualizar(gen_id: str, cambios: dict[str, Any]) -> dict[str, Any]:
    """Mezcla `cambios` sobre el registro existente y lo reescribe (atomico)."""
    ruta_fichero = _ruta(gen_id)
    with bloqueo_archivo(ruta_fichero):
        actual = _leer_yaml(ruta_fichero) or {}
        fusion = {**actual, **cambios}
        pub = _publico(fusion, gen_id)
        _escribir_yaml_atomico(ruta_fichero, _cuerpo(pub))
    return pub


def _cuerpo(pub: dict[str, Any]) -> dict[str, Any]:
    """Cuerpo YAML de una generacion: el dict publico sin `id` y sin claves vacias."""
    return {
        k: v
        for k, v in pub.items()
        if k != "id" and v not in ("", None)
    }


def obtener(gen_id: str) -> dict[str, Any] | None:
    """Una generacion por id (None si no existe / id invalido / YAML corrupto)."""
    if not isinstance(gen_id, str) or not gen_id:
        return None
    try:
        ruta_fichero = _ruta(gen_id)
    except ValueError:
        return None
    if not ruta_fichero.is_file():
        return None
    datos = _leer_yaml(ruta_fichero)
    if datos is None:
        return None
    return _publico(datos, gen_id)


def _todas_ordenadas() -> list[dict[str, Any]]:
    """Todas las generaciones (publicas) ordenadas recientes primero (sin recortar).

    Las generaciones NO viven en el indice SQLite (son estado efimero de ejecucion en
    su propio almacen), asi que el orden/recorte se hace en memoria sobre el glob. El
    volumen lo ACOTA la poda de retencion (`podar_generaciones`, #128): sin ella el
    almacen y este escaneo crecian sin tope. Con la poda activa el conjunto queda en el
    orden de `KENI_GENERACIONES_RETENCION_MAX` (def 2000), un escaneo barato.

    SEGUIMIENTO (no en este cambio, bajo riesgo): este metodo parsea TODOS los .yaml en
    cada peticion solo para devolver una pagina. NO se cambia el orden aqui a mtime porque
    el orden CONTRACTUAL es por `fecha_inicio` (campo DENTRO del YAML), que difiere del
    mtime (el mtime cambia en cada `actualizar`); ordenar por mtime alteraria la semantica
    visible. La via correcta es un indice (un campo/columna `fecha_inicio` indexado) para
    paginar sin parsear todo; queda pendiente. De momento la poda basta para acotar el coste.
    """
    base = raiz()
    if not base.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for ruta_fichero in base.glob("*.yaml"):
        if ruta_fichero.name.startswith(".tmp-"):
            continue
        datos = _leer_yaml(ruta_fichero)
        if datos is None:
            continue
        pub = _publico(datos, ruta_fichero.stem)
        # Prompt y razonamiento pueden pesar (KB); solo se exponen en el detalle (`obtener`),
        # no en el listado de Actividad. Los quitamos aquí para que la lista quede liviana.
        pub.pop("prompt", None)
        pub.pop("razonamiento", None)
        items.append(pub)
    items.sort(key=lambda g: (g["fecha_inicio"], g["id"]), reverse=True)
    return items


def listar(
    limite: int | None = _LISTADO_MAX, desplazamiento: int = 0
) -> list[dict[str, Any]]:
    """Generaciones recientes primero (por `fecha_inicio` desc, luego id), paginadas.

    `limite=None` devuelve TODAS (sin recortar); por defecto recorta a `_LISTADO_MAX`
    (retrocompat con la UI de actividad). `desplazamiento` salta las N primeras.
    """
    items = _todas_ordenadas()
    inicio = max(0, int(desplazamiento or 0))
    if limite is None:
        return items[inicio:]
    return items[inicio : inicio + max(0, int(limite))]


def contar() -> int:
    """Total de generaciones almacenadas (para el `total` del envelope de paginacion)."""
    return len(_todas_ordenadas())


# --------------------------------------------------------------------------- #
# Poda de retencion: acota el almacen de registros (disco + escaneo) #128       #
# --------------------------------------------------------------------------- #

# Defaults de la politica de retencion. Se leen INLINE de `os.environ` (no por
# `config.py`, propiedad de otro agente). Un registro se CONSERVA si es mas nuevo que
# `KENI_GENERACIONES_RETENCION_DIAS` (def 30 d) O si esta entre los `KENI_GENERACIONES_
# RETENCION_MAX` mas recientes (def 2000); solo se borra lo viejo que ademas cae fuera
# del piso de los N mas recientes. Asi el listado de Actividad (`_todas_ordenadas`,
# que parsea TODOS los .yaml en cada peticion) y el disco quedan acotados.
_RETENCION_DIAS_DEF = 30
_RETENCION_MAX_DEF = 2000


def _entero_env(nombre: str, defecto: int, *, minimo: int = 0) -> int:
    """Lee un entero >= `minimo` de `os.environ[nombre]`; cae a `defecto` si falta/inválido.

    Helper INLINE (no toca `config.py`, de otro agente): tolera valores ausentes, no
    numéricos o por debajo del mínimo sin romper la poda.
    """
    crudo = os.environ.get(nombre)
    if crudo is None:
        return defecto
    try:
        valor = int(str(crudo).strip())
    except (TypeError, ValueError):
        return defecto
    return valor if valor >= minimo else defecto


def podar_generaciones(
    *,
    dias: int | None = None,
    maximo: int | None = None,
    ahora: datetime | None = None,
) -> int:
    """Borra registros YAML de generacion fuera de la politica de retencion. Devuelve cuantos.

    POLITICA (conservadora, doble red de seguridad):
      - CONSERVA todo registro mas nuevo que `dias` (def `KENI_GENERACIONES_RETENCION_DIAS`,
        30 d), juzgado por el mtime del fichero (barato; sin parsear el YAML).
      - CONSERVA SIEMPRE los `maximo` registros mas recientes (def `KENI_GENERACIONES_
        RETENCION_MAX`, 2000), AUNQUE sean viejos: el piso de los N mas recientes NUNCA se
        borra. Solo es candidato a borrar lo que es viejo Y ademas cae por debajo del piso.

    SEGURIDAD: solo toca ficheros `<id>.yaml` del dir de generaciones cuyo nombre case con
    el patron de id (12 hex de `nuevo_id`) — nunca temporales `.tmp-*` ni nada ajeno. Tolera
    carreras (fichero ya borrado por otro): un `FileNotFoundError`/`OSError` al hacer stat o
    unlink se ignora por item, sin abortar el barrido. NO parsea los YAML (no depende de que
    sean validos), asi un fichero corrupto no rompe la poda. Loguea el total podado.

    `dias`/`maximo`/`ahora` se inyectan en tests; por defecto salen del entorno / del reloj.
    """
    dias_ret = dias if dias is not None else _entero_env(
        "KENI_GENERACIONES_RETENCION_DIAS", _RETENCION_DIAS_DEF, minimo=0
    )
    max_ret = maximo if maximo is not None else _entero_env(
        "KENI_GENERACIONES_RETENCION_MAX", _RETENCION_MAX_DEF, minimo=0
    )
    base = raiz()
    if not base.is_dir():
        return 0

    referencia = ahora if ahora is not None else datetime.now()
    corte = referencia.timestamp() - dias_ret * 86400.0

    # Recolecta (mtime, ruta) de los registros de generacion REALES (id de 12 hex), saltando
    # temporales y cualquier nombre ajeno. El stat es barato (no parsea el YAML).
    candidatos: list[tuple[float, Path]] = []
    for ruta_fichero in base.glob("*.yaml"):
        nombre = ruta_fichero.stem
        if not _ES_ID.fullmatch(nombre):
            continue  # no es un registro de generacion (`.tmp-*`, ajeno): no se toca
        try:
            mtime = ruta_fichero.stat().st_mtime
        except OSError:
            continue  # carrera (ya borrado) o ilegible: se omite
        candidatos.append((mtime, ruta_fichero))

    if len(candidatos) <= max_ret:
        return 0  # por debajo del piso: nada que podar

    # Mas reciente primero; el piso de los `max_ret` primeros queda SIEMPRE protegido.
    candidatos.sort(key=lambda par: par[0], reverse=True)
    podados = 0
    for mtime, ruta_fichero in candidatos[max_ret:]:
        if mtime >= corte:
            continue  # dentro de la ventana de dias: se conserva pese a estar fuera del piso
        try:
            ruta_fichero.unlink()
            podados += 1
        except FileNotFoundError:
            continue  # carrera: otro lo borro ya; cuenta como hecho sin sumar
        except OSError:
            _log.warning("Poda de generaciones: no se pudo borrar %s", ruta_fichero.name, exc_info=True)
            continue
    if podados:
        _log.info("Poda de generaciones: %d registro(s) viejo(s) borrado(s).", podados)
    return podados


def reclamar_zombis(max_edad_seg: float, *, ahora: datetime | None = None) -> int:
    """Marca como `error` (interrumpida) las generaciones colgadas en `ejecutando`.

    Una generacion nace `ejecutando` y solo pasa a terminal cuando corre su finalizador. Si
    el proceso que la ejecuta MUERE (reinicio/deploy, OOM, worker matado, `generar()` de
    imagen colgado), el finalizador nunca corre y el registro queda ZOMBI en `ejecutando`
    para siempre (el wall-timeout solo protege si el proceso sigue vivo). Este reaper barre
    las `ejecutando` cuyo `fecha_inicio` es mas viejo que `max_edad_seg` y las cierra como
    `error`/`interrumpido`. SEGURO: `max_edad_seg` debe ser MUY superior a cualquier job real
    (que termina en <= wall-timeout), asi nunca mata uno vivo. Devuelve cuantas reclamo.

    `ahora` se inyecta en tests; por defecto es la hora actual. Best-effort por item: un
    fallo al parsear/actualizar uno NO aborta el barrido.
    """
    referencia = ahora if ahora is not None else datetime.now()
    reclamadas = 0
    for gen in _todas_ordenadas():
        if gen.get("estado") != ESTADO_EJECUTANDO:
            continue
        try:
            inicio = datetime.fromisoformat(gen.get("fecha_inicio", ""))
        except ValueError:
            continue  # sin fecha parseable: no podemos juzgar su edad, lo dejamos
        if (referencia - inicio).total_seconds() < max_edad_seg:
            continue  # aun dentro de ventana: podria estar viva de verdad
        try:
            actualizar(
                gen["id"],
                {
                    "estado": ESTADO_ERROR,
                    "motivo": MOTIVO_INTERRUMPIDO,
                    "error": "La generación se interrumpió (el proceso se reinició o se colgó).",
                    "fecha_fin": ahora_iso(),
                },
            )
            reclamadas += 1
        except Exception:  # noqa: BLE001 -- un fallo al reclamar uno no debe abortar el barrido
            continue
    return reclamadas


# --------------------------------------------------------------------------- #
# Lanzador de trabajos de CLAUDE (stream-json + parciales) — INYECTABLE        #
# --------------------------------------------------------------------------- #

# `procesar(salida, metricas) -> dict`: parsea la salida final de claude y crea los
# artefactos (historial, publicaciones, hashtags…), devolviendo el `resultado` que se
# guarda en el registro. Corre en el hilo del trabajo al COMPLETARSE con exito.
Procesar = Callable[[str, Any], dict[str, Any]]


def _argv_claude(
    prompt: str,
    dirs_permitidos: list[Path] | None = None,
    *,
    endurecer: dict[str, Any] | None = None,
) -> list[str]:
    """argv de `claude -p <prompt> --output-format stream-json --verbose
    --include-partial-messages [--effort N] [--max-budget-usd N] [--max-turns N]
    [--add-dir D ...]`.

    `--include-partial-messages` es lo que habilita el STREAMING token a token (eventos
    `stream_event`/`text_delta`). `--verbose` es obligatorio para stream-json. `--effort`
    se añade solo si hay un nivel guardado en preferencias (si no, el predeterminado del
    modelo). `--max-budget-usd`/`--max-turns` se añaden solo si hay un tope valido en el
    entorno (`KENI_CLAUDE_MAX_USD`/`KENI_CLAUDE_MAX_TURNS`): topan el run por coste y por
    turnos de agente (complementan al wall-timeout, que topa por tiempo). Por cada dir en
    `dirs_permitidos` se añade `--add-dir <dir>` para que claude pueda LEER archivos fuera
    de su cwd (p.ej. la foto subida, que vive en un temporal del SO). El default `None`
    mantiene la retrocompat (sin `--add-dir`). Sin shell.

    El presupuesto/max-turns salen del DOMINIO (`dominio.stream`), no de `api.skills`:
    asi `generaciones` ya no necesita el import perezoso que rompia el ciclo dominio↔API.

    ENDURECIMIENTO POR JOB (`endurecer`): un job READ-ONLY (p.ej. la importacion de parrilla)
    pasa overrides que ENDURECEN el argv para ESE run sin tocar la config global:
      - `disallowed_tools`: lista de herramientas EXTRA a vetar (se UNE a la global; sirve
        para prohibir Write/Edit/MCP de escritura en un job que solo debe LEER).
      - `max_turns` / `max_budget_usd`: topes especificos (mas bajos) que SUSTITUYEN a los
        globales para ese run. Se aplican solo si vienen; si no, se usan los globales.
    Los overrides solo pueden ENDURECER (vetar mas, topar mas bajo), nunca relajar.
    """
    endurecer = endurecer or {}
    extra: list[str] = []
    for d in dirs_permitidos or []:
        extra += ["--add-dir", str(d)]

    # Herramientas vetadas: global (config) UNIDA a las extra del job (orden estable, sin dups).
    vetadas_global = stream.arg_tools_restringidas()
    tools_global = vetadas_global[1:] if vetadas_global else []
    extra_tools = [str(t) for t in (endurecer.get("disallowed_tools") or []) if str(t)]
    todas_tools: list[str] = []
    for t in (*tools_global, *extra_tools):
        if t not in todas_tools:
            todas_tools.append(t)
    arg_tools = ["--disallowed-tools", *todas_tools] if todas_tools else []

    # Topes: override del job si viene; si no, el global del dominio.
    if "max_turns" in endurecer and endurecer["max_turns"]:
        arg_turns = ["--max-turns", str(int(endurecer["max_turns"]))]
    else:
        arg_turns = stream.arg_max_turns()
    if "max_budget_usd" in endurecer and endurecer["max_budget_usd"]:
        texto = f"{float(endurecer['max_budget_usd']):.10f}".rstrip("0").rstrip(".")
        arg_budget = ["--max-budget-usd", texto]
    else:
        arg_budget = stream.arg_presupuesto()

    # Esfuerzo (thinking): override del job si viene y es un nivel válido; si no, el global
    # de preferencias. Un job mecánico (p.ej. importar parrilla = transcribir filas a JSON)
    # pasa `esfuerzo="low"` para no "pensar" de más (3× más rápido, misma cobertura) SIN
    # tocar la preferencia global de copy/otros.
    nivel = str(endurecer.get("esfuerzo") or "")
    if nivel in preferencias.ESFUERZOS_VALIDOS:
        arg_effort = ["--effort", nivel]
    else:
        arg_effort = preferencias.arg_esfuerzo()

    return [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose", "--include-partial-messages",
        # Headless: sin esto `claude` se cuelga al usar una tool (WebFetch/Read), no hay forma
        # de aprobar el permiso en `-p`. NO es el flag de skills: no usamos el motor de skills,
        # el contexto se inyecta en el prompt; el cwd es neutro. Acotado por topes.
        *stream.arg_skip_permisos(),
        # Defensa en profundidad anti prompt-injection: veta herramientas peligrosas (por
        # defecto `Bash`/`Write`/`Edit`, mas las extra del job). Va DESPUES de skip-permisos.
        *arg_tools,
        *arg_effort,
        *arg_budget,
        *arg_turns,
        *extra,
    ]


# Prefijos/nombres de variables de entorno que NUNCA deben llegar al subproceso `claude -p`
# (case-insensitive). Defensa contra EXFILTRACION de secretos: la generacion corre con
# skip-permissions y el prompt incluye contenido de usuario/RSS NO confiable; si el modelo
# fuese prompt-injectado y tuviera una herramienta de salida (Web, MCP), no debe poder leer
# del entorno credenciales de la INFRA (Postgres, S3/Garage, Metricool/agencias) y filtrarlas.
# La generacion NO las necesita: solo precisa PATH/HOME/locale/XDG, el token de Claude
# (`CLAUDE_CODE_OAUTH_TOKEN`/`ANTHROPIC_API_KEY`) y, en su caso, la clave del proveedor de
# imagen (que `_entorno_generacion` inyecta explicitamente). Usamos DENYLIST (no allowlist) para no
# romper variables legitimas que `claude` pueda necesitar y que no preveamos. CRITICO: estos
# prefijos NO deben cazar `PATH`/`HOME`/`CLAUDE_*` (`PG` es prefijo, no caza `PATH`: empieza
# por `PA`, no `PG`).
_ENV_DENYLIST_PREFIJOS: tuple[str, ...] = (
    "S3_", "GARAGE_", "POSTGRES_", "APP_DB_", "PG", "METRICOOL", "MC_",
)
_ENV_DENYLIST_EXACTOS: frozenset[str] = frozenset({"DATABASE_URL"})


def _es_secreto_infra(nombre: str) -> bool:
    """True si `nombre` es una var de secreto de INFRA que no debe llegar al subproceso.

    Case-insensitive. Caza por PREFIJO (`S3_`, `POSTGRES_`, `PG`, `METRICOOL`, ...) o por
    nombre EXACTO (`DATABASE_URL`). Nunca caza el token de Claude ni `PATH`/`HOME`.
    """
    arriba = nombre.upper()
    if arriba in _ENV_DENYLIST_EXACTOS:
        return True
    return any(arriba.startswith(p) for p in _ENV_DENYLIST_PREFIJOS)


def _entorno_generacion() -> dict[str, str]:
    """Entorno del subproceso de la generacion.

    Hereda `os.environ` PERO con un SCRUB de los secretos de infra (`_es_secreto_infra`):
    Postgres/S3/Garage/Metricool no deben viajar al subproceso `claude -p` (defensa contra
    exfiltracion si el modelo es prompt-injectado). Se conserva todo lo demas que la
    generacion necesita (PATH/HOME/locale/XDG, `CLAUDE_CODE_OAUTH_TOKEN`/`ANTHROPIC_API_KEY`).
    Si hay una clave de imagen en el ALMACEN (secretos.toml, la UNICA fuente de verdad) y la
    variable correspondiente no esta ya puesta, la inyecta: el motor de imagen es un proceso
    independiente que solo lee variables de entorno, asi que este es el canal por el que recibe la clave. NO
    duplica el almacen: solo lo transporta al subproceso. Una variable ya presente en el
    entorno tiene prioridad (no se pisa).
    """
    from . import secretos

    entorno = {k: v for k, v in os.environ.items() if not _es_secreto_infra(k)}
    clave = secretos.obtener_clave_imagen()
    if not clave:
        return entorno
    var = {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }.get(secretos.obtener_proveedor_imagen())
    if var and not entorno.get(var):
        entorno[var] = clave
    return entorno


def encolar_job_claude(
    gen_id: str,
    *,
    prompt: str,
    cwd: Path,
    procesar: Procesar,
    dir_temporal: Path | None = None,
    spec: dict[str, Any] | None = None,
) -> None:
    """ENCOLA un trabajo de claude (#130 Fase 2): persiste el `spec` y vuelve de INMEDIATO.

    Es el NUEVO seam de lanzamiento que usan los endpoints/dominio en lugar de ejecutar
    `claude -p` en la peticion. El back solo ENCOLA; un WORKER (in-proceso en local,
    servicio aparte en hosted) clava el job y corre `lanzar_job_claude` (el runner real
    con todo el #137). `spec` es la forma serializable (prompt + post-procesado + cwd) que
    el worker usa para reconstruir el trabajo; `procesar`/`cwd`/`dir_temporal` SOLO los
    necesita un lanzador INYECTADO (tests), que recibe la MISMA firma que el viejo
    `lanzar_job_claude` y por eso sigue funcionando sin cambios.

    INYECTABLE: `crear_app(lanzar_generacion=...)` reasigna ESTA funcion; los tests pasan
    fakes que NO tocan `claude` ni la cola (ejecutan `procesar` sincronicamente o dejan el
    registro `ejecutando`). En produccion, el default encola el `spec`.

    TOPE DE COLA (#137, PERMANENTE): la admision se decide AQUI, SINCRONAMENTE: si el
    sistema esta saturado (`runner.admitir()` lanza `ColaLlenaError`) propagamos al llamante,
    que responde 429. Asi el backpressure es inmediato (no se encola un job que no cabe). El
    worker, al clavar el job, llama a `slot(ya_admitido=True)` para heredar y liberar el cupo.
    """
    if spec is None:
        # Defensa: sin spec no se puede reconstruir el job en el worker. El llamante real
        # SIEMPRE pasa spec; un test que inyecte su fake no llega aqui (reasigna la funcion).
        raise ValueError("encolar_job_claude requiere un spec serializable")
    # Admision SINCRONA (mismo tope que el flujo in-process): rechaza con ColaLlenaError
    # ANTES de encolar si el sistema esta al tope (-> 429). El worker hereda esta admision.
    runner.admitir()
    try:
        from . import cola

        cola.encolar(gen_id, spec)
    except Exception:  # noqa: BLE001 -- si el encolado falla, no fugar el cupo de admision
        runner.liberar_admision()
        raise
    # Visibilidad/control: persistimos el prompt EXACTO que recibirá `claude -p`. Se expone
    # SOLO en el detalle (`GET /api/generaciones/{id}`), nunca en el listado (lo quita
    # `_todas_ordenadas`). Best-effort: el job ya está encolado; un fallo al persistir el
    # prompt no debe tumbarlo.
    if prompt:
        try:
            actualizar(gen_id, {"prompt": prompt})
        except Exception:  # noqa: BLE001 -- best-effort
            pass


def lanzar_job_claude(
    gen_id: str,
    *,
    prompt: str,
    cwd: Path,
    procesar: Procesar,
    dir_temporal: Path | None = None,
    ya_admitido: bool = False,
    endurecer: dict[str, Any] | None = None,
) -> None:
    """Lanza un trabajo de claude EN SEGUNDO PLANO (Popen + hilo lector). NO bloquea.

    El hilo lee el NDJSON (stream-json + parciales), persiste `salida` (texto en vivo) y
    metricas parciales en el registro, y al cerrar fija el estado terminal:
      - exito  -> `completado`, `resultado = procesar(texto_final, metricas_finales)`.
      - error/budget/timeout -> `error` (mensaje en espanol).
    Si `dir_temporal` viene (archivo subido), se borra al terminar. INYECTABLE: los tests
    reemplazan esta funcion por una fake que llama a `procesar` con una salida canned.

    LO LLAMA EL WORKER (#130 Fase 2) tras clavar un job, NO la peticion HTTP. `ya_admitido`
    es True cuando el cupo de admision ya lo tomo `encolar_job_claude` (el caso normal del
    worker): asi NO se vuelve a admitir (evita doble cuenta), pero `slot` SIGUE liberandolo.

    TOPE DE COLA (#137, PERMANENTE): la admision se decide SINCRONAMENTE; si el sistema esta
    saturado (`runner.admitir()` lanza `ColaLlenaError`) se propaga al llamante (429). Con
    `ya_admitido` la admision la hizo ya el encolado (el worker no re-admite). El hilo
    hereda la admision (`slot(ya_admitido=True)`) y la libera al terminar.
    """
    acumulador = stream.AcumuladorStream()
    timeout = _timeout()

    # CORRELACION (#123 + #137): capturamos AQUI (sincronicamente, dentro de la peticion)
    # el request-id de quien lanzo el job. El hilo de trabajo corre fuera del contexto de
    # la peticion, asi que el ContextVar ya no estara puesto; por eso lo guardamos ahora y
    # lo incluimos en TODOS los logs del job. Asi un fallo del job se rastrea hasta la
    # peticion que lo origino (y hasta el id que el usuario pudo haber reportado).
    rid = request_id_actual()
    etq = f"generacion {gen_id}" + (f" (req {rid})" if rid else "")

    # Admision SINCRONA: si la cola esta al tope, NO lanzamos el hilo; el llamante recibe
    # ColaLlenaError y responde 429 (#137; PERMANENTE: la generacion sigue siendo `claude
    # -p`, ADR 0001). El hilo, ya admitido, libera el cupo al terminar via `slot`. Si el
    # cupo ya lo tomo `encolar_job_claude` (worker, #130 Fase 2), NO re-admitimos.
    if not ya_admitido:
        runner.admitir()

    def _avance() -> None:
        try:
            actualizar(
                gen_id,
                {
                    "estado": ESTADO_EJECUTANDO,
                    # Etapa de progreso (en que etapa va): razonando → generando.
                    "fase": acumulador.fase(),
                    "salida": acumulador.texto,
                    # Razonamiento en vivo (cola acotada): feedback inmediato mientras piensa.
                    "razonamiento": acumulador.razonamiento,
                    "metricas": stream.metricas_a_dict(acumulador.metricas_parciales()),
                },
            )
        except Exception:  # noqa: BLE001 -- el avance nunca debe romper el hilo
            # Persistir un parcial es best-effort (el cierre fija el estado), pero ya no
            # lo silenciamos en mudo: dejamos rastro con el job-id + request-id (#123, #137).
            _log.warning("%s: fallo al persistir avance parcial", etq, exc_info=True)

    def _finalizar(timed_out: bool, returncode: int | None, cancelado: bool) -> None:
        # OJO: el `dir_temporal` se borra al FINAL (no aqui), porque el post-procesado
        # `procesar` puede necesitar los ARCHIVOS que la skill dejo ahi: las skills de
        # imagen (estudio-imagen) escriben los .png derivados junto a la foto subida y
        # `procesar` los importa al media para previsualizarlos. Borrarlo antes los
        # perderia. La limpieza va en el `finally`, asi corre pase lo que pase.
        fecha_fin = ahora_iso()
        try:
            if cancelado:
                # Cancelacion del usuario (#137): se mato el arbol; estado terminal claro.
                actualizar(gen_id, {
                    "estado": ESTADO_ERROR, "motivo": MOTIVO_CANCELADO,
                    "error": "La generación fue cancelada.",
                    "salida": acumulador.texto,
                    "metricas": stream.metricas_a_dict(acumulador.metricas_parciales()),
                    "fecha_fin": fecha_fin,
                })
                return
            if timed_out:
                actualizar(gen_id, {
                    "estado": ESTADO_ERROR, "motivo": MOTIVO_TIMEOUT,
                    "error": f"El asistente tardó demasiado (más de {timeout} s) y se canceló.",
                    "metricas": stream.metricas_a_dict(acumulador.metricas_parciales()),
                    "fecha_fin": fecha_fin,
                })
                return
            if acumulador.error:
                actualizar(gen_id, {
                    "estado": ESTADO_ERROR, "error": acumulador.mensaje_error,
                    "fecha_fin": fecha_fin,
                })
                return
            if acumulador.terminado:
                try:
                    resultado = procesar(acumulador.texto, acumulador.final)
                except Exception:  # noqa: BLE001 -- fallo del post-procesado -> error claro
                    # El cliente ve un mensaje generico (sin traceback), pero el fallo
                    # queda CORRELACIONADO al job + a la peticion en el log (#123, #137).
                    _log.exception("%s: fallo el post-procesado (procesar)", etq)
                    actualizar(gen_id, {
                        "estado": ESTADO_ERROR,
                        "error": "Se generó el contenido pero no se pudo procesar el resultado.",
                        "salida": acumulador.texto,
                        "metricas": stream.metricas_a_dict(acumulador.final),
                        "fecha_fin": fecha_fin,
                    })
                    return
                actualizar(gen_id, {
                    "estado": ESTADO_COMPLETADO, "fase": FASE_COMPLETADO,
                    "salida": acumulador.texto,
                    "metricas": stream.metricas_a_dict(acumulador.final),
                    "resultado": resultado, "fecha_fin": fecha_fin,
                })
                return
            detalle = "El asistente terminó sin devolver un resultado."
            if returncode not in (0, None):
                detalle = "El asistente terminó con error."
            actualizar(gen_id, {
                "estado": ESTADO_ERROR, "error": detalle,
                # A4: conservar el texto ya acumulado (no descartarlo en stream truncado).
                "salida": acumulador.texto,
                "metricas": stream.metricas_a_dict(acumulador.metricas_parciales()),
                "fecha_fin": fecha_fin,
            })
        except Exception:  # noqa: BLE001 -- el cierre nunca debe propagar
            # Antes era `pass` mudo: un fallo del cierre se volvia un job atascado en
            # "ejecutando" sin rastro. Ahora lo LOGUEAMOS con el job-id + request-id (#123,
            # #137) y, best-effort, intentamos dejarlo en error (no propagamos: es daemon).
            _log.exception("%s: fallo al fijar el estado terminal", etq)
            try:
                actualizar(gen_id, {
                    "estado": ESTADO_ERROR,
                    "error": "Ocurrió un error al finalizar la generación.",
                    "fecha_fin": fecha_fin,
                })
            except Exception:  # noqa: BLE001 -- ya logueamos; no hay mas que hacer
                _log.error("%s: tampoco se pudo marcar el error de cierre", etq)
        finally:
            # Limpieza del temporal de la subida: DESPUES de `procesar` (ver nota arriba).
            if dir_temporal is not None:
                shutil.rmtree(dir_temporal, ignore_errors=True)

    # Evento de cancelacion del job (lo arma `cancelar()`). Se guarda en el handle para
    # que `cancelar()` pueda matar el arbol y para que `_finalizar` sepa el porque.
    cancelado = threading.Event()

    def _ciclo() -> None:
        # Concurrencia (#116) + admision/tope de cola (#137): el job YA fue admitido en
        # `lanzar_job_claude` (sincronicamente), asi que aqui solo esperamos un proceso
        # concurrente libre. `slot(ya_admitido=True)` libera el cupo al salir. El spawn
        # ocurre DENTRO del slot para que el tope limite procesos `claude` reales. Cada
        # job tiene wall-timeout, asi que los slots siempre se liberan.
        try:
            with runner.slot(ya_admitido=True):
                if shutil.which("claude") is None:
                    if dir_temporal is not None:
                        shutil.rmtree(dir_temporal, ignore_errors=True)
                    actualizar(gen_id, {
                        "estado": ESTADO_ERROR,
                        "error": (
                            "No se encontró el asistente en este equipo. Instala Claude "
                            "Code para generar desde la consola."
                        ),
                        "fecha_fin": ahora_iso(),
                    })
                    return
                try:
                    # Subproceso en SU PROPIO grupo (#137): al timeout/cancel matamos el
                    # ARBOL entero (`runner.matar_arbol`), no solo el padre.
                    proc = runner.lanzar_proc(
                        _argv_claude(
                            prompt,
                            [dir_temporal] if dir_temporal else None,
                            endurecer=endurecer,
                        ),
                        cwd=str(cwd),
                        env=_entorno_generacion(),
                    )
                except (OSError, ValueError):
                    if dir_temporal is not None:
                        shutil.rmtree(dir_temporal, ignore_errors=True)
                    actualizar(gen_id, {
                        "estado": ESTADO_ERROR, "error": "No se pudo iniciar la generación.",
                        "fecha_fin": ahora_iso(),
                    })
                    return
                with _HANDLES_LOCK:
                    _HANDLES[gen_id] = {"proc": proc, "cancelado": cancelado}
                # Si ya pidieron cancelar entre el spawn y registrar el handle, matamos ya.
                if cancelado.is_set():
                    runner.matar_arbol(proc)
                runner.leer_stream(proc, acumulador, _avance)
                # `runner.esperar` mata el ARBOL si supera el wall-timeout (#137).
                timed_out = runner.esperar(proc, timeout)
                # Estado terminal ANTES de soltar el handle: un sondeo que ya no ve el
                # handle nunca lee un "ejecutando" obsoleto.
                _finalizar(timed_out, proc.returncode, cancelado.is_set())
        finally:
            with _HANDLES_LOCK:
                _HANDLES.pop(gen_id, None)

    # El hilo (via `slot(ya_admitido=True)`) libera la admision al terminar. Si el
    # arranque del hilo fallara ANTES de entrar al slot, liberamos aqui para no fugar el
    # cupo de `admitir()` (defensa; en la practica `start()` casi nunca falla).
    hilo = threading.Thread(target=_ciclo, name=f"gen-{gen_id}", daemon=True)
    try:
        hilo.start()
    except Exception:  # noqa: BLE001 -- el cupo admitido no debe quedar colgado
        runner.liberar_admision()
        raise


def cancelar(gen_id: str) -> bool:
    """Cancela un job de claude EN VUELO: mata el ARBOL del subproceso (#137, PERMANENTE).

    Devuelve True si se pudo cancelar algo (handle in-memoria del proceso O un job en la
    cola); False si no hay nada que cancelar (ya terminó). Tiene DOS vias, porque el job
    puede correr en ESTE proceso o en otro (worker hosted, #130 Fase 2):
      - IN-MEMORIA: si el job corre aqui (back local con worker in-proceso, o el propio
        worker), hay un handle con el proceso: armamos el evento y matamos el ARBOL ya.
      - CROSS-PROCESO: marcamos el job en la cola como `cancelado` (`cola.cancelar`). El
        worker que lo corre sondea ese flag y mata el arbol; un job aun pendiente se
        finaliza como cancelado al clavarse, sin lanzar `claude`.
    La limpieza del estado terminal la hace el hilo del job en `_finalizar`. La generacion
    es subprocess `claude -p` (ADR 0001): cancelar = matar el arbol del proceso.
    """
    cancelado_algo = False
    with _HANDLES_LOCK:
        handle = _HANDLES.get(gen_id)
        ev = handle.get("cancelado") if handle else None
        proc = handle.get("proc") if handle else None
    if isinstance(ev, threading.Event):
        ev.set()
        cancelado_algo = True
    if isinstance(proc, subprocess.Popen):
        runner.matar_arbol(proc)
        cancelado_algo = True
    # Cross-proceso: marca el job en la cola (lo lee el worker, esté donde esté).
    try:
        from . import cola

        if cola.cancelar(gen_id):
            cancelado_algo = True
    except Exception:  # noqa: BLE001 -- la cancelacion in-memoria ya pudo bastar; no propagar
        _log.warning("generacion %s: fallo al marcar la cancelacion en la cola", gen_id, exc_info=True)
    return cancelado_algo


# --------------------------------------------------------------------------- #
# Lanzador de trabajos de IMAGEN (HTTP a un proveedor) — INYECTABLE            #
# --------------------------------------------------------------------------- #


def lanzar_job_imagen(gen_id: str, *, generar: Callable[[], dict[str, Any]]) -> None:
    """Lanza un trabajo de imagen EN SEGUNDO PLANO (un hilo simple; sin Popen).

    `generar()` hace la llamada al proveedor y guarda la imagen, devolviendo el
    `resultado` (`{id, url}`). No es un stream: el registro pasa de `ejecutando` a
    `completado` (con `resultado`) o `error`. INYECTABLE para tests (sin red).
    """

    def _ciclo() -> None:
        try:
            resultado = generar()
        except Exception as e:  # noqa: BLE001 -- mensaje en espanol; sin traceback al cliente
            mensaje = str(e) if str(e) else "No se pudo generar la imagen."
            actualizar(gen_id, {"estado": ESTADO_ERROR, "error": mensaje, "fecha_fin": ahora_iso()})
        else:
            actualizar(gen_id, {
                "estado": ESTADO_COMPLETADO, "resultado": resultado, "fecha_fin": ahora_iso(),
            })
        # Soltamos el handle DESPUES de fijar el estado terminal (ver `lanzar_job_claude`).
        with _HANDLES_LOCK:
            _HANDLES.pop(gen_id, None)

    hilo = threading.Thread(target=_ciclo, name=f"gen-img-{gen_id}", daemon=True)
    with _HANDLES_LOCK:
        _HANDLES[gen_id] = {"hilo": hilo}
    hilo.start()
