"""API Sistema: monitorizacion del servidor + estado de S3/Garage. SOLO rol admin.

Superficie de ADMIN de la Consola: da un vistazo operativo a la maquina que sirve la
consola (CPU/RAM/disco) y al object storage (S3/Garage) donde vive la media en hosted.
Es informacion SENSIBLE (capacidad, endpoints, uso) -> exige una SESION admin real, igual
que `/api/usuarios` y `/api/conexiones` (helper unico `permisos.es_admin`). El
token de mantenimiento NO es admin: recibe 403.

Este paquete trocea por AREAS la antigua `api/sistema.py` (PURA reubicacion, mismo
contrato): los handlers viven en `recursos.py`, `s3.py`, `daemons.py`, `backups.py` y
`rendimiento.py`; los helpers compartidos (bloqueo de rol + logger) en `_comun.py`. Este
`__init__` es el FACADE: re-exporta lo que terceros leen (`api.estado` consume `_discos`,
`sonda_daemons`, `sonda_backups`, `sonda_s3_salud`, `UMBRAL_DISCO_*`) y ensambla `RUTAS`
con EXACTAMENTE las mismas rutas/metodos/orden que antes.

Endpoints (bajo `/api/sistema`, CONTRATO con el frontend):

  - GET /api/sistema/recursos -> {cpu:{porcentaje,cores}, ram:{usado,total,porcentaje},
      discos:[{etiqueta, ruta, usado, total, porcentaje}], psutil: bool}. Bytes en crudo;
      el front formatea GB/%. Degradado: si `psutil` no esta, devuelve CPU/RAM nulos pero
      SI el disco (via `shutil.disk_usage`, stdlib) -> nunca 500 por falta de un opcional.
  - GET /api/sistema/s3 -> {configurado, endpoint, bucket, region, salud, objetos, bytes,
      error?}. Con S3 cableado consulta el bucket (head_bucket + conteo/suma de objetos);
      sin cablear devuelve `configurado:false` (degradado, NO 500). `salud` es "ok"/"err".
  - POST /api/sistema/s3/probar -> {salud, error?}. Test de conexion (head_bucket). SOLO
      lectura: NADA destructivo. 409 si S3 no esta configurado (no hay nada que probar).
  - GET /api/sistema/s3/objetos?prefijo=<p> -> {carpetas, objetos, prefijo, migas}.
      Navega el bucket por prefijo usando Delimiter="/": devuelve subcarpetas (CommonPrefixes)
      y objetos del nivel actual ({key, nombre, tamano, modificado}). Tope anti-escaneo de
      1000 objetos por pagina, maximo _MAX_PAGINAS_NAV paginas. Sin S3: degradado, no 500.
      SOLO lectura: NADA destructivo.
  - GET /api/sistema/s3/objeto?key=<k>[&descargar=1] -> STREAMING de los bytes del objeto.
      El endpoint S3 de Garage es INTERNO (`http://files:3900`): el navegador no lo alcanza,
      asi que NO se usan URLs prefirmadas; se proxean los bytes por el back con el Content-Type
      real del objeto. Por defecto `inline` (previsualizacion: sirve para `<img src=...>` con la
      cookie de sesion); `?descargar=1` fuerza `attachment`. Valida la key (sin `..`). Cap de
      tamano (_MAX_BYTES_OBJETO). 404 si no existe, 409 si S3 no configurado. SOLO lectura.
  - POST /api/sistema/s3/borrar {key} -> {borrado, key}. Operacion DESTRUCTIVA: borra UN
      objeto por su key exacta (la que lista el explorador). Valida la key (anti-traversal,
      sin `..`) y rechaza keys de "carpeta" (terminadas en "/"). Confirma existencia con
      head_object para dar un 404 honesto antes de borrar (delete_object de S3 es idempotente
      y no distingue). 400 key invalida, 404 inexistente, 409 sin configurar, 502 fallo.
  - POST /api/sistema/s3/borrar-lote {keys:[...]} -> {borrados:[...], fallidos:[{key,error}]}.
      Operacion DESTRUCTIVA en MASA (seleccion multiple del explorador). Valida y deduplica las
      keys, descarta invalidas/"carpetas", y usa delete_objects (batch nativo, hasta 1000 por
      llamada). NO hace head_object por key (prioriza rapidez): no distingue ausentes. 400 sin
      keys validas, 409 sin configurar, 502 fallo. El RESTO del panel sigue siendo solo lectura.

Implementacion DEFENSIVA: cualquier fallo de psutil/boto3/red se captura y se degrada a un
campo de error legible; la pagina nunca se cae por una sonda.
"""

from __future__ import annotations

from starlette.routing import Route

# Helpers compartidos (bloqueo de rol + logger). Re-exportados por si algun consumidor
# los leyera por su nombre historico de modulo.
# Importamos las AREAS como MODULOS (no sus funciones sueltas) por dos razones:
#  1) los handlers se referencian como `area.handler` al armar `RUTAS`;
#  2) deja cada submodulo accesible como atributo del paquete (p. ej. `sistema.s3`), que
#     es lo que los tests parchean: `monkeypatch.setattr(api_sistema.s3, "_cliente_s3", ...)`.
#     Importar la FUNCION `s3` (homonima del modulo) habria pisado ese atributo.
from . import backups, cuenta, daemons, github, recursos, rendimiento, s3, uso

# Re-exports planos que leen TERCEROS por su nombre historico de modulo:
#   - `api.estado` (doctor) consume `_discos`, `UMBRAL_DISCO_*`, `sonda_daemons`,
#     `sonda_backups`, `sonda_s3_salud` por atributo de `api.sistema` (late binding: los
#     tests del doctor los parchean ahi).
#   - `test_api_sistema` lee `_MAX_BYTES_OBJETO` por atributo de `api.sistema`.
from .backups import sonda_backups
from .daemons import sonda_daemons
from .recursos import UMBRAL_DISCO_AVISO_PCT, UMBRAL_DISCO_ERROR_PCT, _discos
from .s3 import _MAX_BYTES_OBJETO, sonda_s3_salud

__all__ = [
    "RUTAS",
    # Submodulos de area (cada uno con sus handlers y sondas)
    "recursos",
    "daemons",
    "backups",
    "rendimiento",
    "s3",
    "cuenta",
    "uso",
    "github",
    # Sondas compartidas con el doctor (`api.estado`)
    "sonda_daemons",
    "sonda_backups",
    "sonda_s3_salud",
    # Helpers/umbrales que lee el doctor por atributo del paquete
    "_discos",
    "UMBRAL_DISCO_AVISO_PCT",
    "UMBRAL_DISCO_ERROR_PCT",
    # Cap de tamano que comprueba `test_api_sistema`
    "_MAX_BYTES_OBJETO",
]

# El ORDEN y los paths/metodos son CONTRATO (Starlette casa por orden): las rutas mas
# especificas de S3 (/s3/objetos, /s3/objeto, /s3/borrar-lote, /s3/borrar) van ANTES que
# /s3/probar y /s3 para que casen correctamente.
RUTAS = [
    Route("/api/sistema/recursos", recursos.recursos, methods=["GET"]),
    Route("/api/sistema/daemons", daemons.daemons_latidos, methods=["GET"]),
    Route("/api/sistema/daemons/{daemon}/barridos", daemons.daemons_barridos, methods=["GET"]),
    Route("/api/sistema/daemons/{daemon}/barrer", daemons.daemons_barrer, methods=["POST"]),
    Route("/api/sistema/backups", backups.backups, methods=["GET"]),
    Route("/api/sistema/rendimiento", rendimiento.rendimiento_api, methods=["GET"]),
    Route("/api/sistema/s3", s3.s3, methods=["GET"]),
    # IMPORTANTE: las rutas mas especificas (/s3/objetos, /s3/objeto, /s3/borrar) van ANTES
    # que /s3/probar y /s3 para que Starlette las case correctamente.
    Route("/api/sistema/s3/objetos", s3.s3_objetos, methods=["GET"]),
    Route("/api/sistema/s3/objeto", s3.s3_objeto, methods=["GET"]),
    Route("/api/sistema/s3/borrar-lote", s3.s3_borrar_lote, methods=["POST"]),
    Route("/api/sistema/s3/borrar", s3.s3_borrar, methods=["POST"]),
    Route("/api/sistema/s3/probar", s3.probar_s3, methods=["POST"]),
    # Cuenta de Claude del servidor (proxy admin al control del daemons). Las mas
    # especificas (/cuenta/login/...) van ANTES que /cuenta (Starlette casa por orden).
    Route("/api/sistema/cuenta/login/iniciar", cuenta.login_iniciar, methods=["POST"]),
    Route("/api/sistema/cuenta/login/codigo", cuenta.login_codigo, methods=["POST"]),
    Route("/api/sistema/cuenta/login/cancelar", cuenta.login_cancelar, methods=["POST"]),
    Route("/api/sistema/cuenta/logout", cuenta.logout, methods=["POST"]),
    Route("/api/sistema/cuenta", cuenta.cuenta, methods=["GET"]),
    # Uso de la cuenta de Claude: LECTURA del ultimo snapshot persistido (NO ejecuta `claude`),
    # para el indicador siempre-visible de la barra lateral y el gate diario.
    Route("/api/sistema/uso", uso.uso, methods=["GET"]),
    # Cuenta de GitHub del servidor (proxy admin al control del daemons). Las mas
    # especificas (/github/login/...) van ANTES que /github (Starlette casa por orden).
    Route("/api/sistema/github/login/iniciar", github.login_iniciar, methods=["POST"]),
    Route("/api/sistema/github/login/confirmar", github.login_confirmar, methods=["POST"]),
    Route("/api/sistema/github/login/cancelar", github.login_cancelar, methods=["POST"]),
    Route("/api/sistema/github/logout", github.logout, methods=["POST"]),
    Route("/api/sistema/github", github.github, methods=["GET"]),
]
