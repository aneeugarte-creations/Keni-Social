"""Versionado de la Texto con git (historial · diff · rollback · atribucion).

La Texto es files-as-truth: cada documento es un `.md` bajo `libtexto.raiz()`. Este
modulo envuelve cada escritura con un commit en un repo git DEDICADO a esa raiz, de modo que
el historial, el diff y el rollback salen gratis y `git log` da la ATRIBUCION (quien/cuando
cambio que). Es la opcion acordada en el rediseno: ligera y coherente con files-as-truth.

PRINCIPIO: es BEST-EFFORT y NO CRITICO. El guardado del documento ya ocurrio (atomico) ANTES
de llamar aqui; si git no esta disponible o un comando falla, solo se deja rastro en el log y
la operacion del usuario NUNCA se rompe. Se puede desactivar con `KENI_TEXTO_GIT=0`.

El repo se inicializa de forma perezosa en la raiz de la texto (no en `/data` entero),
asi que solo versiona documentos. La papelera (`.papelera/`) queda fuera (`.gitignore`).
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

_log = logging.getLogger("keni_consola.versionado")

# Tiempo maximo por comando git (un repo de texto plano responde en ms; el tope evita colgar
# la request si el FS o git se atascan).
_TIMEOUT = 15

# Identidad por defecto de los commits cuando no se pasa autor (commits del sistema).
_AUTOR_DEFECTO = ("Consola Keni", "consola@keni.local")


def _habilitado() -> bool:
    """True si el versionado git esta activo (env `KENI_TEXTO_GIT` != '0') y git existe."""
    if os.environ.get("KENI_TEXTO_GIT", "1").strip() == "0":
        return False
    return _git_disponible()


def _git_disponible() -> bool:
    try:
        subprocess.run(
            ["git", "--version"], capture_output=True, text=True, timeout=_TIMEOUT, check=True,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _base() -> Path:
    """Raiz del repo git = raiz de la texto (import perezoso para evitar ciclo)."""
    from . import libtexto

    return libtexto.raiz()


def _git(base: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Corre `git <args>` en `base`. No lanza por codigo de salida (lo decide el llamante)."""
    entorno = dict(os.environ)
    if env:
        entorno.update(env)
    return subprocess.run(
        ["git", "-C", str(base), *args],
        capture_output=True, text=True, timeout=_TIMEOUT, env=entorno, check=False,
    )


def _asegurar_repo(base: Path) -> bool:
    """Garantiza un repo git en `base` (init perezoso + identidad local). True si esta listo."""
    if not base.is_dir():
        return False
    if (base / ".git").exists():
        return True
    if _git(base, "init", "-q").returncode != 0:
        return False
    # Identidad LOCAL del repo: que los commits no dependan de la config global (ausente en el
    # contenedor). El autor real de cada commit se sobreescribe por commit via `--author`/env.
    _git(base, "config", "user.email", _AUTOR_DEFECTO[1])
    _git(base, "config", "user.name", _AUTOR_DEFECTO[0])
    gitignore = base / ".gitignore"
    if not gitignore.exists():
        try:
            gitignore.write_text(".papelera/\n", encoding="utf-8")
        except OSError:
            pass
    return True


def _ident(autor: dict[str, str] | None) -> tuple[str, str]:
    """(nombre, email) del autor del commit. Cae al autor de sistema si no hay usuario."""
    autor = autor or {}
    nombre = (autor.get("usuario") or autor.get("nombre") or "").strip()
    if not nombre:
        return _AUTOR_DEFECTO
    email = (autor.get("email") or "").strip() or f"{_slug_email(nombre)}@keni.local"
    return nombre, email


def _slug_email(nombre: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in nombre.lower()).strip("-") or "autor"


def registrar(
    ruta: Path,
    mensaje: str,
    *,
    ruta_previa: Path | None = None,
    autor: dict[str, str] | None = None,
) -> None:
    """Commitea `ruta` (best-effort). Si `ruta_previa` se dio (un mv), tambien la quita.

    No lanza: cualquier fallo de git se traga (ya quedo escrito el fichero); deja rastro en el
    log para diagnostico. `mensaje` describe la accion ("editar prompt/x", "crear ...").
    """
    if not _habilitado():
        return
    try:
        base = _base()
        if not _asegurar_repo(base):
            return
        if ruta_previa is not None:
            _git(base, "add", "-A", "--", str(ruta_previa))
        _git(base, "add", "-A", "--", str(ruta))
        nombre, email = _ident(autor)
        env = {
            "GIT_AUTHOR_NAME": nombre, "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": _AUTOR_DEFECTO[0], "GIT_COMMITTER_EMAIL": _AUTOR_DEFECTO[1],
        }
        res = _git(base, "commit", "-q", "-m", mensaje, env=env)
        # returncode != 0 con "nothing to commit" es normal (guardado sin cambios reales).
        if res.returncode != 0 and "nothing to commit" not in (res.stdout + res.stderr):
            _log.debug("commit texto fallo: %s", (res.stdout + res.stderr).strip())
    except (OSError, subprocess.SubprocessError) as exc:
        _log.debug("versionado best-effort fallo (%s): %s", mensaje, exc)


def _rel(base: Path, doc_id: str) -> str:
    """Ruta relativa POSIX del `.md` de `doc_id` dentro del repo."""
    return (Path(*doc_id.split("/")).with_suffix(".md")).as_posix()


def historial(doc_id: str, *, limite: int = 50) -> list[dict[str, str]]:
    """Historial de versiones de un documento (recientes primero).

    Cada entrada: `{sha, sha_corto, fecha, autor, mensaje}`. `--follow` sigue el fichero a
    traves de renombrados (titulo/carpeta cambiados). [] si no hay repo/historial.
    """
    if not _habilitado():
        return []
    base = _base()
    if not (base / ".git").exists():
        return []
    rel = _rel(base, doc_id)
    sep = "\x1f"
    fmt = sep.join(["%H", "%h", "%cI", "%an", "%s"])
    res = _git(
        base, "log", f"-n{max(1, min(limite, 500))}", "--follow",
        f"--format={fmt}", "--", rel,
    )
    if res.returncode != 0:
        return []
    entradas: list[dict[str, str]] = []
    for linea in res.stdout.splitlines():
        if not linea.strip():
            continue
        partes = linea.split(sep)
        if len(partes) != 5:
            continue
        sha, corto, fecha, autor, msg = partes
        entradas.append({
            "sha": sha, "sha_corto": corto, "fecha": fecha, "autor": autor, "mensaje": msg,
        })
    return entradas


def version(doc_id: str, sha: str) -> str | None:
    """Contenido `.md` COMPLETO del documento en la version `sha`. None si no existe."""
    if not _habilitado() or not _sha_valido(sha):
        return None
    base = _base()
    if not (base / ".git").exists():
        return None
    rel = _rel(base, doc_id)
    res = _git(base, "show", f"{sha}:{rel}")
    return res.stdout if res.returncode == 0 else None


def sha_documento(doc_id: str) -> str | None:
    """SHA del ULTIMO commit que toco el `.md` de `doc_id` (el "HEAD" del documento).

    Es el sha que el modelo de PUBLICACION compara contra el puntero de produccion
    (`sin_publicar = sha_actual != produccion.sha`). None si el versionado esta apagado,
    no hay repo o el documento aun no tiene commits.
    """
    if not _habilitado():
        return None
    base = _base()
    if not (base / ".git").exists():
        return None
    res = _git(base, "log", "-n1", "--format=%H", "--", _rel(base, doc_id))
    if res.returncode != 0:
        return None
    sha = res.stdout.strip()
    return sha or None


def shas_documentos() -> dict[str, str]:
    """Mapa doc_id -> sha del ultimo commit que toco su `.md`, para TODO el repo.

    Version POR LOTE de `sha_documento`: UNA sola llamada a git (`log --name-only` sobre
    el historial completo del repo de la Texto, que es pequeno) en vez de un subproceso
    por documento. La usan el listado de la Biblioteca y el endpoint de la maquina.
    {} si el versionado esta apagado o no hay repo. Los ficheros borrados/renombrados
    pueden aparecer con su ultima ruta; los consumidores cruzan contra los docs vivos.
    """
    if not _habilitado():
        return {}
    base = _base()
    if not (base / ".git").exists():
        return {}
    # \x01 marca la linea del sha (un separador que no aparece en rutas) y el resto de
    # lineas son las rutas tocadas por ese commit. El PRIMER commit (mas reciente) que
    # menciona una ruta gana: es su "HEAD".
    res = _git(base, "log", "--format=%x01%H", "--name-only")
    if res.returncode != 0:
        return {}
    mapa: dict[str, str] = {}
    sha = ""
    for linea in res.stdout.splitlines():
        if linea.startswith("\x01"):
            sha = linea[1:].strip()
            continue
        ruta = linea.strip()
        if not ruta or not ruta.endswith(".md") or not sha:
            continue
        doc_id = ruta[: -len(".md")]
        if doc_id not in mapa:
            mapa[doc_id] = sha
    return mapa


def _sha_valido(sha: object) -> bool:
    """Acepta solo hex (defensa: el sha viaja en la URL/JSON del cliente)."""
    return isinstance(sha, str) and 4 <= len(sha) <= 40 and all(c in "0123456789abcdef" for c in sha.lower())
