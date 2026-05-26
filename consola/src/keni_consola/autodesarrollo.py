"""Lazo de AUTO-DESARROLLO del buzón de sugerencias (F-C-11, #109).

Cierra el lazo que faltaba: que una sugerencia del equipo no solo se RECOJA (eso ya
lo hace `sugerencias.py`), sino que la propia consola la IMPLEMENTE con `claude -p` y,
SOLO si todo pasa, la mergee a `main`. Es una capacidad potente y peligrosa, así que
vive tras un SUELO DE SEGURIDAD innegociable (los 6 gates de #109). Este módulo es el
DOMINIO del lazo; `api/autodesarrollo.py` es su capa HTTP.

================================================================================
LOS 6 GATES DE SEGURIDAD (todos OBLIGATORIOS; sin uno, no se mergea)
================================================================================

1. DEFAULT OFF (`flag_activo`): el lazo vive tras un flag DESACTIVADO por defecto. Se
   activa con `KENI_AUTODESARROLLO=1` (env) o guardándolo en la config local
   (`autodesarrollo.toml`). Con el flag OFF, `implementar()` NO hace nada (devuelve un
   intento `bloqueada` con motivo "flag-off") y el buzón se comporta como hoy.

2. EJECUCIÓN AISLADA (`crear_worktree_efimero`): cada sugerencia se implementa en un
   git WORKTREE EFÍMERO en una carpeta temporal del SO, NUNCA en el árbol vivo del
   operador. El worktree se borra siempre al terminar (éxito o fallo).

3. CI-VERDE-O-NO-MERGE (`correr_ci`): tras generar, se corre el MIRROR LOCAL completo.
   Solo si TODO pasa en verde se considera mergear; si algo falla, la sugerencia queda
   PARKED (estado "necesita revisión humana"), sin merge.

4. CAPS DE ALCANCE (`evaluar_diff`): si el diff toca RUTAS SENSIBLES (secretos,
   persistencia base, credenciales/auth, `.github/`, `keni-shared/`, deps) se RECHAZA
   (parked). Cap de TAMAÑO de diff configurable (`CAP_LINEAS_DEFECTO`, 400) → si lo
   supera, parked.

5. SIN SECRETOS (`entorno_saneado`): el `claude -p` lanzado recibe un entorno SIN
   tokens ni claves (se eliminan `*_API_KEY`, `*_TOKEN`, `KENI_CONSOLA_SECRETOS`, etc.),
   y su cwd es el clon efímero, que NO contiene `secretos.toml` (vive en `~/.config`).

6. KILL SWITCH + AUDITORÍA (`flag_activo` + `registrar_auditoria`/`leer_auditoria`):
   el flag desactiva el lazo en caliente; cada intento se escribe en un LOG DE AUDITORÍA
   persistente (JSONL) con sugerencia → rama/worktree → resultado de CI → estado final
   (mergeado/parked/rechazado) y su SHA o motivo.

INYECTABLES (para tests herméticos): `correr_git`, `correr_ci` y `lanzar_implementacion`
son funciones a nivel de módulo. Los tests las reemplazan por fakes que NO ejecutan git
real, NO corren el mirror y NO llaman a `claude`. Así se verifica la LÓGICA DE GATES sin
efectos reales.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .io_atomico import escribir_atomico

# --------------------------------------------------------------------------- #
# Estados de un intento de auto-desarrollo                                     #
# --------------------------------------------------------------------------- #

# Resultado terminal de un intento. La UI los pinta con etiquetas legibles.
ESTADO_BLOQUEADA = "bloqueada"  # flag OFF u otro pre-requisito; no se intentó nada real
ESTADO_RECHAZADA = "rechazada"  # gate de alcance: tocó rutas sensibles / superó el cap
ESTADO_PARKED = "parked"  # generada pero CI roja o sin diff: necesita revisión humana
ESTADO_MERGEADA = "mergeada"  # generada, CI verde y fast-forward a main: SHA registrado
ESTADO_ERROR = "error"  # fallo inesperado (git/CI/runner); nunca mergea

ESTADOS: tuple[str, ...] = (
    ESTADO_BLOQUEADA,
    ESTADO_RECHAZADA,
    ESTADO_PARKED,
    ESTADO_MERGEADA,
    ESTADO_ERROR,
)

# --------------------------------------------------------------------------- #
# GATE 4: caps de alcance — rutas sensibles + tamaño de diff                   #
# --------------------------------------------------------------------------- #

# Cap por defecto de líneas cambiadas (added+deleted) de un diff. Modesto a propósito:
# un lazo de auto-merge no debe colar cambios grandes sin revisión humana. Override por
# `KENI_AUTODESARROLLO_CAP_LINEAS`.
CAP_LINEAS_DEFECTO = 400

# Rutas SENSIBLES: si el diff toca CUALQUIERA de estas, el intento se RECHAZA (nunca
# mergea). Se comparan contra la ruta de cada fichero del diff (relativa a la raíz del
# repo). Patrones de SUBCADENA (no glob): basta con que aparezcan en la ruta.
#   - secretos*            -> almacén de secretos / claves
#   - persistencia base    -> db / ficheros / repos / estados / indice de la consola
#   - credenciales / auth  -> tokens, conexiones de red, asistente de credenciales
#   - .github/             -> CI / workflows
#   - keni-shared/         -> capa base compartida (catálogo de marca, límites)
#   - pyproject / deps     -> dependencias y empaquetado
_PATRONES_SENSIBLES: tuple[str, ...] = (
    "secretos",
    "credenciales",
    "credencial",
    "/db.py",
    "/ficheros.py",
    "/repos.py",
    "/estados.py",
    "/indice.py",
    "conexiones",
    "asistente.py",  # keni_metricas: escribe tokens/credenciales
    ".github/",
    "keni-shared/",
    "keni_shared/",
    "pyproject.toml",
    "requirements.txt",
    "package-lock.json",
    "uv.lock",
    "poetry.lock",
)

# Prefijos de variables de entorno que se ELIMINAN del entorno del subproceso (gate 5):
# cualquier cosa que huela a credencial/token/secreto no debe llegar al `claude` lanzado.
_PREFIJOS_ENV_PROHIBIDOS: tuple[str, ...] = (
    "KENI_CONSOLA_SECRETOS",
)
_SUFIJOS_ENV_PROHIBIDOS: tuple[str, ...] = (
    "_API_KEY",
    "_TOKEN",
    "_SECRET",
    "_KEY",
    "_PASSWORD",
    "_CREDENTIALS",
)
# Nombres exactos de variables de entorno que también se eliminan (sin sufijo claro).
_NOMBRES_ENV_PROHIBIDOS: frozenset[str] = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "GEMINI_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN",
        "GH_TOKEN",
    }
)


# --------------------------------------------------------------------------- #
# GATE 1 + 6: feature flag (default OFF) + kill switch en caliente             #
# --------------------------------------------------------------------------- #


def ruta_config() -> Path:
    """Ruta del config local del lazo. `KENI_AUTODESARROLLO_CONFIG` la sobreescribe (tests)."""
    if p := os.environ.get("KENI_AUTODESARROLLO_CONFIG"):
        return Path(p).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "keni-social" / "autodesarrollo.toml"


def _leer_config() -> dict[str, Any]:
    """Lee el TOML de config del lazo (o {} si no existe / corrupto). Solo lectura."""
    ruta = ruta_config()
    if not ruta.exists():
        return {}
    try:
        return tomllib.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _verdadero(valor: object) -> bool:
    """Interpreta un valor (env o toml) como booleano de activación."""
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        return valor.strip().lower() in ("1", "true", "si", "sí", "on", "yes")
    return False


def flag_activo() -> bool:
    """GATE 1+6: True solo si el lazo de auto-desarrollo está ACTIVADO. Default OFF.

    Fuentes (cualquiera activa, la env tiene prioridad como KILL SWITCH en caliente):
      - `KENI_AUTODESARROLLO` en el entorno (1/true/on/...).
      - clave `activo = true` en `autodesarrollo.toml`.
    Si ninguna lo activa, devuelve False: `implementar()` no hace nada (gate 1).
    """
    env = os.environ.get("KENI_AUTODESARROLLO")
    if env is not None:
        return _verdadero(env)
    return _verdadero(_leer_config().get("activo"))


def guardar_flag(activo: bool) -> bool:
    """Persiste el flag en `autodesarrollo.toml` (escritura atómica). Devuelve el valor.

    NO toca la variable de entorno (esa es el kill switch en caliente y manda sobre el
    fichero). Activar esto desde la UI exige confirmar el riesgo (la capa HTTP lo pide).
    """
    contenido = (
        "# Config LOCAL del lazo de auto-desarrollo del buzón (#109). Lo gestiona\n"
        "# keni_consola.autodesarrollo (no editar a mano). Peligroso: lee la doc.\n"
        f"activo = {'true' if activo else 'false'}\n"
    )
    escribir_atomico(
        ruta_config(), contenido, prefijo=".autodesarrollo-", sufijo=".toml.tmp"
    )
    return activo


def cap_lineas() -> int:
    """GATE 4: cap de líneas cambiadas de un diff. `KENI_AUTODESARROLLO_CAP_LINEAS` lo fija."""
    crudo = (os.environ.get("KENI_AUTODESARROLLO_CAP_LINEAS") or "").strip()
    if crudo:
        try:
            valor = int(crudo)
        except ValueError:
            return CAP_LINEAS_DEFECTO
        if valor > 0:
            return valor
    return CAP_LINEAS_DEFECTO


# --------------------------------------------------------------------------- #
# GATE 5: entorno saneado (sin secretos ni tokens) para el subproceso          #
# --------------------------------------------------------------------------- #


def _es_var_prohibida(nombre: str) -> bool:
    """True si una variable de entorno debe eliminarse del subproceso (gate 5)."""
    up = nombre.upper()
    if up in _NOMBRES_ENV_PROHIBIDOS:
        return True
    if any(up.startswith(p.upper()) for p in _PREFIJOS_ENV_PROHIBIDOS):
        return True
    return any(up.endswith(s) for s in _SUFIJOS_ENV_PROHIBIDOS)


def entorno_saneado() -> dict[str, str]:
    """GATE 5: copia de `os.environ` SIN credenciales/tokens/secretos.

    Elimina las variables que casan `_es_var_prohibida` (claves `*_API_KEY`, `*_TOKEN`,
    `KENI_CONSOLA_SECRETOS`, tokens de git, etc.). Así el `claude -p` que implementa una
    sugerencia NO recibe ningún secreto por el entorno. (El cwd, además, es el clon
    efímero, que no contiene `secretos.toml`: ese vive en `~/.config`.)
    """
    return {k: v for k, v in os.environ.items() if not _es_var_prohibida(k)}


# --------------------------------------------------------------------------- #
# GATE 4: evaluación del diff (rutas sensibles + tamaño)                        #
# --------------------------------------------------------------------------- #

# Línea de `git diff --numstat`: "<added>\t<deleted>\t<ruta>" (added/deleted "-" si binario).
_RE_NUMSTAT = re.compile(r"^\s*(\d+|-)\t(\d+|-)\t(.+)$")


def _ruta_sensible(ruta: str) -> bool:
    """True si una ruta de fichero del diff casa algún patrón sensible (gate 4)."""
    r = ruta.replace("\\", "/").lower()
    return any(p.lower() in r for p in _PATRONES_SENSIBLES)


def evaluar_diff(numstat: str, *, cap: int | None = None) -> dict[str, Any]:
    """GATE 4: decide si un diff es ACEPTABLE para mergear, a partir de `git diff --numstat`.

    Función PURA (no toca git ni disco). Devuelve un dict:
      - `aceptable`: bool. False si toca rutas sensibles, supera el cap, o no hay cambios.
      - `motivo`: razón legible en español cuando NO es aceptable ("" si lo es).
      - `lineas`: total de líneas cambiadas (added+deleted; binarios cuentan 0).
      - `ficheros`: nº de ficheros tocados.
      - `sensibles`: lista de rutas sensibles detectadas (para la auditoría).

    Reglas:
      - SIN cambios (numstat vacío) -> no aceptable ("sin-cambios"): no hay nada que mergear.
      - CUALQUIER ruta sensible -> no aceptable ("rutas-sensibles"): se rechaza, no parked.
      - líneas > cap -> no aceptable ("supera-cap"): se parkea para revisión humana.
    """
    cap = cap if cap is not None else cap_lineas()
    total_lineas = 0
    ficheros = 0
    sensibles: list[str] = []
    for linea in (numstat or "").splitlines():
        m = _RE_NUMSTAT.match(linea)
        if m is None:
            continue
        ficheros += 1
        added = int(m.group(1)) if m.group(1) != "-" else 0
        deleted = int(m.group(2)) if m.group(2) != "-" else 0
        total_lineas += added + deleted
        ruta = m.group(3).strip()
        if _ruta_sensible(ruta):
            sensibles.append(ruta)

    if ficheros == 0:
        return {
            "aceptable": False,
            "motivo": "sin-cambios",
            "lineas": 0,
            "ficheros": 0,
            "sensibles": [],
        }
    if sensibles:
        return {
            "aceptable": False,
            "motivo": "rutas-sensibles",
            "lineas": total_lineas,
            "ficheros": ficheros,
            "sensibles": sensibles,
        }
    if total_lineas > cap:
        return {
            "aceptable": False,
            "motivo": "supera-cap",
            "lineas": total_lineas,
            "ficheros": ficheros,
            "sensibles": [],
        }
    return {
        "aceptable": True,
        "motivo": "",
        "lineas": total_lineas,
        "ficheros": ficheros,
        "sensibles": [],
    }


# --------------------------------------------------------------------------- #
# GATE 6: log de auditoría persistente (JSONL)                                 #
# --------------------------------------------------------------------------- #


def ruta_auditoria() -> Path:
    """Ruta del log de auditoría (JSONL). `KENI_AUTODESARROLLO_AUDITORIA` la sobreescribe."""
    if p := os.environ.get("KENI_AUTODESARROLLO_AUDITORIA"):
        return Path(p).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "keni-social" / "autodesarrollo-auditoria.jsonl"


def registrar_auditoria(entrada: dict[str, Any]) -> dict[str, Any]:
    """GATE 6: añade una entrada al log de auditoría (JSONL, append atómico).

    Cada entrada documenta un intento completo: sugerencia -> rama/worktree -> CI ->
    estado final (con SHA o motivo). Se le pone `id` y `fecha` si faltan. El append es
    atómico (se relee todo, se reescribe entero con `escribir_atomico`): el log local es
    pequeño (un intento por sugerencia) y así nunca queda una línea a medias.
    """
    completa = {
        "id": entrada.get("id") or uuid.uuid4().hex[:12],
        "fecha": entrada.get("fecha") or datetime.now().isoformat(timespec="seconds"),
        **entrada,
    }
    ruta = ruta_auditoria()
    previas = leer_auditoria()
    lineas = [json.dumps(e, ensure_ascii=False) for e in previas]
    lineas.append(json.dumps(completa, ensure_ascii=False))
    escribir_atomico(
        ruta, "\n".join(lineas) + "\n", prefijo=".auditoria-", sufijo=".jsonl.tmp"
    )
    return completa


def leer_auditoria(limite: int = 100) -> list[dict[str, Any]]:
    """Entradas del log de auditoría, RECIENTES PRIMERO (máx. `limite`). [] si no hay.

    Tolerante: una línea corrupta se ignora (no rompe el listado). Solo lectura.
    """
    ruta = ruta_auditoria()
    if not ruta.exists():
        return []
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return []
    entradas: list[dict[str, Any]] = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            obj = json.loads(linea)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            entradas.append(obj)
    entradas.reverse()  # recientes primero (el append escribe al final)
    return entradas[: max(0, limite)]


# --------------------------------------------------------------------------- #
# GATE 2: worktree efímero + operaciones de git (INYECTABLES)                  #
# --------------------------------------------------------------------------- #


def raiz_repo() -> Path | None:
    """Raíz del repo git de la consola (resolviendo desde este fichero). None si no es repo.

    `KENI_AUTODESARROLLO_REPO` la sobreescribe (tests / despliegues). La detección real
    sube directorios buscando un `.git`; así el lazo opera sobre el repo correcto.
    """
    if p := os.environ.get("KENI_AUTODESARROLLO_REPO"):
        ruta = Path(p).expanduser()
        return ruta if ruta.exists() else None
    actual = Path(__file__).resolve()
    for padre in [actual, *actual.parents]:
        if (padre / ".git").exists():
            return padre
    return None


def correr_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess:
    """Ejecuta `git <args>` en `cwd` (sin shell). INYECTABLE: los tests lo reemplazan.

    Devuelve el `CompletedProcess` (no lanza por código de salida: el llamante decide).
    """
    return subprocess.run(  # noqa: S603 -- argv lista, sin shell
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
    )


def crear_worktree_efimero(sugerencia_id: str) -> tuple[Path, str]:
    """GATE 2: crea un git worktree EFÍMERO en una carpeta temporal del SO.

    Devuelve `(ruta_worktree, rama)`. La rama es `autodesarrollo/<sug>-<rand>` para no
    chocar con ramas del operador. NUNCA opera sobre el árbol vivo. Lanza `RuntimeError`
    (en español) si no hay repo o git falla. El llamante DEBE borrarlo al terminar (lo
    hace `implementar` en un `finally`).
    """
    repo = raiz_repo()
    if repo is None:
        raise RuntimeError("No se encontró el repositorio git para aislar la ejecución.")
    sufijo = uuid.uuid4().hex[:8]
    rama = f"autodesarrollo/{_slug(sugerencia_id)}-{sufijo}"
    destino = Path(tempfile.mkdtemp(prefix=f"ks-autodes-{sufijo}-"))
    # Base = main actualizado de origin si existe; si no, HEAD local. El worktree nace en
    # su propia rama nueva para que el diff/merge posterior sea limpio.
    base = "origin/main"
    res_fetch = correr_git(["fetch", "origin"], cwd=repo)
    if res_fetch.returncode != 0:
        base = "HEAD"
    res = correr_git(["worktree", "add", "-b", rama, str(destino), base], cwd=repo)
    if res.returncode != 0:
        shutil.rmtree(destino, ignore_errors=True)
        detalle = (res.stderr or "").strip() or "error desconocido de git worktree"
        raise RuntimeError(f"No se pudo crear el entorno aislado: {detalle}")
    return destino, rama


def borrar_worktree(worktree: Path, rama: str) -> None:
    """Borra el worktree efímero y su rama (best-effort; nunca propaga)."""
    repo = raiz_repo()
    if repo is not None:
        correr_git(["worktree", "remove", str(worktree), "--force"], cwd=repo)
        correr_git(["branch", "-D", rama], cwd=repo)
    shutil.rmtree(worktree, ignore_errors=True)


def _slug(texto: str) -> str:
    """Slug seguro y corto para nombres de rama (solo `[a-z0-9-]`)."""
    s = re.sub(r"[^a-z0-9]+", "-", (texto or "").lower()).strip("-")
    return (s or "sugerencia")[:24]


# --------------------------------------------------------------------------- #
# GATE 3: mirror de CI (INYECTABLE)                                            #
# --------------------------------------------------------------------------- #


def correr_ci(worktree: Path) -> dict[str, Any]:
    """GATE 3: corre el MIRROR LOCAL de CI sobre el worktree. INYECTABLE en tests.

    La implementación REAL queda intencionadamente como un STUB que reporta "no
    ejecutado": el operador define el comando del mirror por entorno
    (`KENI_AUTODESARROLLO_CI`) y, sin él, el lazo trata el CI como NO verde (parked). Así
    NUNCA se mergea por accidente si no hay un mirror configurado. Si hay comando, se
    ejecuta en el worktree con el entorno SANEADO (sin secretos) y se considera verde
    solo con returncode 0.

    Devuelve `{verde: bool, detalle: str}`.
    """
    comando = (os.environ.get("KENI_AUTODESARROLLO_CI") or "").strip()
    if not comando:
        return {
            "verde": False,
            "detalle": (
                "No hay mirror de CI configurado (KENI_AUTODESARROLLO_CI). Por seguridad "
                "se trata como no verde: la sugerencia queda para revisión humana."
            ),
        }
    res = subprocess.run(  # noqa: S602 -- comando del operador, entorno saneado, cwd aislado
        comando,
        cwd=str(worktree),
        env=entorno_saneado(),
        shell=True,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    return {
        "verde": res.returncode == 0,
        "detalle": (res.stderr or res.stdout or "").strip()[-2000:],
    }


# --------------------------------------------------------------------------- #
# Lanzamiento de `claude -p` en el worktree (INYECTABLE)                        #
# --------------------------------------------------------------------------- #


def _prompt_implementacion(sugerencia: dict[str, Any]) -> str:
    """Prompt para que `claude -p` implemente la sugerencia DENTRO del worktree efímero."""
    titulo = sugerencia.get("titulo", "")
    detalle = sugerencia.get("detalle", "")
    return (
        "Implementa la siguiente sugerencia del equipo en este repositorio. Haz SOLO el "
        "cambio mínimo necesario, con tests, y NO toques: secretos, persistencia base "
        "(db/ficheros/repos/estados/indice), credenciales/auth, .github/, keni-shared/ "
        "ni dependencias (pyproject/locks). Cuando termines, deja los cambios SIN commitear "
        "(el lazo los revisa y commitea aparte).\n\n"
        f"# {titulo}\n\n{detalle}\n"
    )


def lanzar_implementacion(prompt: str, *, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    """Lanza `claude -p` en `cwd` (el worktree efímero) para implementar la sugerencia.

    INYECTABLE: los tests la reemplazan por una fake que NO llama a `claude`. La
    implementación REAL corre `claude -p <prompt> --output-format json` SIN streaming
    (es un trabajo batch), con el `env` SANEADO y cwd restringido al worktree. Devuelve
    `{ok: bool, detalle: str}`. NO commitea: el lazo evalúa el diff del árbol de trabajo.
    """
    if shutil.which("claude") is None:
        return {"ok": False, "detalle": "No se encontró el CLI 'claude' en este equipo."}
    try:
        res = subprocess.run(  # noqa: S603 -- argv lista, sin shell, env saneado, cwd aislado
            ["claude", "-p", prompt, "--output-format", "json"],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "detalle": f"No se pudo lanzar el asistente: {e}"}
    return {
        "ok": res.returncode == 0,
        "detalle": (res.stdout or res.stderr or "").strip()[-2000:],
    }


# --------------------------------------------------------------------------- #
# Orquestación: el lazo completo (con los 6 gates)                             #
# --------------------------------------------------------------------------- #


def implementar(sugerencia: dict[str, Any]) -> dict[str, Any]:
    """Implementa UNA sugerencia con todos los gates. Devuelve la entrada de AUDITORÍA.

    Pasos (cada uno respeta su gate; cualquier corte deja un estado terminal y se AUDITA):
      0. GATE 1: si el flag está OFF -> `bloqueada` (motivo "flag-off"), sin hacer nada.
      1. GATE 2: crear worktree efímero (carpeta temporal, rama propia).
      2. GATE 5: lanzar `claude -p` en el worktree con entorno SANEADO (sin secretos).
      3. GATE 4: `git diff --numstat` -> `evaluar_diff`. Rutas sensibles -> `rechazada`;
         sin cambios o supera el cap -> `parked`.
      4. GATE 3: `correr_ci`. CI roja -> `parked`. CI verde -> commitear + fast-forward a
         main (`git push origin HEAD:main`) -> `mergeada` (SHA registrado).
      5. GATE 6: TODO lo anterior se registra en el log de auditoría.
      6. GATE 2: el worktree se borra SIEMPRE (finally).

    Ningún camino mergea sin: flag ON + diff seguro + cap OK + CI verde. Si algo falla de
    forma inesperada (git/CI), el estado es `error` y NO se mergea.
    """
    sid = sugerencia.get("id", "")
    base_aud: dict[str, Any] = {
        "sugerencia_id": sid,
        "titulo": sugerencia.get("titulo", ""),
        "rama": "",
        "ci_verde": False,
        "sha": "",
    }

    # GATE 1: flag OFF -> no se hace NADA (ni worktree ni claude). Se audita igualmente.
    if not flag_activo():
        return registrar_auditoria(
            {**base_aud, "estado": ESTADO_BLOQUEADA, "motivo": "flag-off",
             "detalle": "El lazo de auto-desarrollo está desactivado (flag OFF)."}
        )

    worktree: Path | None = None
    rama = ""
    try:
        # GATE 2: ejecución aislada en worktree efímero.
        worktree, rama = crear_worktree_efimero(sid)
        base_aud["rama"] = rama

        # GATE 5: entorno saneado (sin secretos) para el subproceso.
        env = entorno_saneado()
        gen = lanzar_implementacion(_prompt_implementacion(sugerencia), cwd=worktree, env=env)
        if not gen.get("ok"):
            return registrar_auditoria(
                {**base_aud, "estado": ESTADO_PARKED, "motivo": "generacion-fallida",
                 "detalle": gen.get("detalle", "")[:1000]}
            )

        # GATE 4: evaluar el diff del árbol de trabajo (rutas sensibles + cap de tamaño).
        ns = correr_git(["diff", "--numstat"], cwd=worktree)
        evaluacion = evaluar_diff(ns.stdout if ns.returncode == 0 else "")
        if not evaluacion["aceptable"]:
            motivo = evaluacion["motivo"]
            # Rutas sensibles -> RECHAZADA (no es revisable: viola el alcance). El resto
            # (sin-cambios / supera-cap) queda PARKED para revisión humana.
            estado = ESTADO_RECHAZADA if motivo == "rutas-sensibles" else ESTADO_PARKED
            return registrar_auditoria(
                {**base_aud, "estado": estado, "motivo": motivo,
                 "lineas": evaluacion["lineas"], "ficheros": evaluacion["ficheros"],
                 "sensibles": evaluacion["sensibles"]}
            )

        # GATE 3: CI verde o no merge.
        ci = correr_ci(worktree)
        base_aud["ci_verde"] = bool(ci.get("verde"))
        if not ci.get("verde"):
            return registrar_auditoria(
                {**base_aud, "estado": ESTADO_PARKED, "motivo": "ci-roja",
                 "lineas": evaluacion["lineas"], "ficheros": evaluacion["ficheros"],
                 "detalle": ci.get("detalle", "")[:1000]}
            )

        # CI verde + diff seguro: commitear y fast-forward a main.
        sha, detalle_merge = _commitear_y_mergear(worktree, sugerencia)
        if not sha:
            return registrar_auditoria(
                {**base_aud, "estado": ESTADO_PARKED, "motivo": "merge-fallido",
                 "lineas": evaluacion["lineas"], "ficheros": evaluacion["ficheros"],
                 "detalle": detalle_merge[:1000]}
            )
        return registrar_auditoria(
            {**base_aud, "estado": ESTADO_MERGEADA, "motivo": "", "sha": sha,
             "lineas": evaluacion["lineas"], "ficheros": evaluacion["ficheros"]}
        )
    except Exception as e:  # noqa: BLE001 -- cualquier fallo inesperado -> error, NUNCA mergea
        return registrar_auditoria(
            {**base_aud, "estado": ESTADO_ERROR, "motivo": "excepcion",
             "detalle": str(e)[:1000]}
        )
    finally:
        # GATE 2: el worktree efímero se borra SIEMPRE.
        if worktree is not None:
            borrar_worktree(worktree, rama)


def _commitear_y_mergear(worktree: Path, sugerencia: dict[str, Any]) -> tuple[str, str]:
    """Commitea el diff del worktree y hace fast-forward a `main`. Devuelve `(sha, detalle)`.

    `sha` vacío si algo falla (el llamante lo trata como `parked`). El push es a
    `origin HEAD:main` (sin force; el rebase previo asegura el fast-forward). Co-autoría
    en el mensaje, como el resto del repo.
    """
    titulo = (sugerencia.get("titulo") or "sugerencia").strip()[:72]
    mensaje = (
        f"feat(auto): {titulo} (auto-desarrollo #109)\n\n"
        "Implementado automáticamente por el lazo de auto-desarrollo del buzón.\n\n"
        "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
    )
    add = correr_git(["add", "-A"], cwd=worktree)
    if add.returncode != 0:
        return "", (add.stderr or "git add falló").strip()
    commit = correr_git(["commit", "-m", mensaje], cwd=worktree)
    if commit.returncode != 0:
        return "", (commit.stderr or "git commit falló").strip()
    rebase = correr_git(["rebase", "origin/main"], cwd=worktree)
    if rebase.returncode != 0:
        correr_git(["rebase", "--abort"], cwd=worktree)
        return "", "El rebase sobre origin/main falló (conflicto fuera de alcance)."
    push = correr_git(["push", "origin", "HEAD:main"], cwd=worktree)
    if push.returncode != 0:
        return "", (push.stderr or "git push falló").strip()
    rev = correr_git(["rev-parse", "HEAD"], cwd=worktree)
    sha = (rev.stdout or "").strip() if rev.returncode == 0 else ""
    return sha, "Fast-forward a main."
