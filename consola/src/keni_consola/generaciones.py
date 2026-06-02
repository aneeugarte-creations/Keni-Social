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

import logging
import os
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
TIPOS = ("copy", "rss", "hashtags", "imagen", "verificacion", "qa-editorial", "prompt")

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
        "etiqueta": _str("etiqueta"),
        "estado": _str("estado"),
        # Fase de PROGRESO (en que etapa va; ausente en registros legados => "").
        "fase": _str("fase"),
        "motivo": _str("motivo"),
        "salida": _str("salida"),
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
    volumen es bajo (trabajos en vuelo + recientes), por eso basta este escaneo.
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
        items.append(_publico(datos, ruta_fichero.stem))
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


def _argv_claude(prompt: str, dirs_permitidos: list[Path] | None = None) -> list[str]:
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
    """
    extra: list[str] = []
    for d in dirs_permitidos or []:
        extra += ["--add-dir", str(d)]
    return [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose", "--include-partial-messages",
        # Headless: sin esto `claude` no carga las skills del proyecto ni usa WebFetch/Bash
        # (no hay forma de aprobar el "trust"/permiso en `-p`). Acotado por cwd + topes.
        *stream.arg_skip_permisos(),
        # Defensa en profundidad anti prompt-injection: veta herramientas peligrosas (por
        # defecto `Bash`). Va DESPUES de skip-permisos para tener efecto. Ver
        # `config.claude_disallowed_tools` y `dominio.generar.componer` (delimitador).
        *stream.arg_tools_restringidas(),
        *preferencias.arg_esfuerzo(),
        *stream.arg_presupuesto(),
        *stream.arg_max_turns(),
        *extra,
    ]


def _entorno_skill() -> dict[str, str]:
    """Entorno del subproceso de la skill.

    Hereda `os.environ` y, si hay una clave de imagen en el ALMACEN (secretos.toml, la
    UNICA fuente de verdad) y la variable correspondiente no esta ya puesta, la inyecta:
    la skill es un plugin independiente que solo lee variables de entorno, asi que este
    es el canal por el que recibe la clave. NO duplica el almacen: solo lo transporta al
    subproceso. Una variable ya presente en el entorno tiene prioridad (no se pisa).
    """
    from . import secretos

    entorno = dict(os.environ)
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


def lanzar_job_claude(
    gen_id: str,
    *,
    prompt: str,
    cwd: Path,
    procesar: Procesar,
    dir_temporal: Path | None = None,
    ya_admitido: bool = False,
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
                        _argv_claude(prompt, [dir_temporal] if dir_temporal else None),
                        cwd=str(cwd),
                        env=_entorno_skill(),
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
