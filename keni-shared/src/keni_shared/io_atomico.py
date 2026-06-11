"""Escritura atomica de texto a fichero — fuente UNICA del monorepo.

El patron «temporal en el mismo directorio + `os.replace`» estaba copiado en ~10
modulos de dominio de la consola (ficheros, agentes, sugerencias, secretos,
skills_catalogo, preferencias, generaciones) y, ademas, en el
asistente de onboarding de keni-metricas. Esto lo unifica en una sola funcion,
ahora en `keni_shared` para que AMBOS paquetes la importen de la misma fuente
(hallazgo H3/E1; antes H7/N2 dejaba una copia en cada paquete).

Garantias:
  - El fichero destino nunca queda a medias: se escribe a un temporal en el MISMO
    directorio (mismo sistema de ficheros, asi `os.replace` es atomico) y solo al
    final se renombra sobre el destino.
  - Si la escritura falla, el temporal se borra y se propaga el error; el destino
    queda intacto.
  - El directorio padre se crea si no existe.
  - `modo` opcional aplica `os.chmod` al temporal ANTES del replace (p.ej. `0o600`
    para secretos), asi el fichero final nace ya con los permisos correctos.

NO sabe de YAML/JSON/TOML: recibe el TEXTO ya serializado. Las funciones
`_escribir_yaml`/`_escribir` de cada modulo siguen siendo duenas de su formato y
delegan el commit a disco aqui.
"""

from __future__ import annotations

import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# Locks por-ruta (en proceso) para serializar read-modify-write. `escribir_atomico`
# garantiza que el FICHERO nunca queda a medias, pero NO que dos hilos que
# leen-modifican-escriben el mismo fichero no se pisen (last-write-wins -> entradas
# perdidas). La consola es un solo proceso con hilos de fondo, asi que un lock en
# memoria por ruta basta. Se cachean en un dict protegido por `_guard_locks`.
_locks: dict[str, threading.RLock] = {}
_guard_locks = threading.Lock()


def _lock_para(ruta: str | os.PathLike[str]) -> threading.RLock:
    clave = os.fspath(ruta)
    with _guard_locks:
        lk = _locks.get(clave)
        if lk is None:
            lk = threading.RLock()
            _locks[clave] = lk
        return lk


@contextmanager
def bloqueo_archivo(ruta: str | os.PathLike[str]) -> Iterator[None]:
    """Serializa read-modify-write sobre `ruta` DENTRO del proceso.

    Uso: envolver toda la secuencia leer -> modificar -> `escribir_atomico` para que
    dos hilos concurrentes no pierdan la escritura del otro. RLock (re-entrante por
    si la seccion critica re-entra). REGLA anti-deadlock: secciones CORTAS y NUNCA
    anidar locks de rutas distintas. El llamante debe pasar SIEMPRE la misma ruta
    canonica (p.ej. la que devuelve su `ruta_X()`).
    """
    lk = _lock_para(ruta)
    lk.acquire()
    try:
        yield
    finally:
        lk.release()


def escribir_atomico(
    ruta: str | os.PathLike[str],
    texto: str,
    *,
    modo: int | None = None,
    prefijo: str = ".tmp-",
    sufijo: str | None = None,
) -> None:
    """Escribe `texto` en `ruta` de forma ATOMICA (temporal + `os.replace`).

    Args:
        ruta: destino. Su directorio padre se crea si no existe.
        texto: contenido ya serializado (UTF-8).
        modo: si se da, `os.chmod(temporal, modo)` antes del replace (p.ej. 0o600).
        prefijo: prefijo del nombre del temporal (oculto, empieza por punto).
        sufijo: sufijo del temporal; por defecto la extension del destino
            (`ruta.suffix`), para que herramientas que miran la extension no se
            confundan con el temporal.
    """
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if sufijo is None:
        sufijo = destino.suffix

    fd, tmp_nombre = tempfile.mkstemp(dir=str(destino.parent), prefix=prefijo, suffix=sufijo)
    tmp = Path(tmp_nombre)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(texto)
        if modo is not None:
            os.chmod(tmp, modo)
        os.replace(tmp, destino)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
