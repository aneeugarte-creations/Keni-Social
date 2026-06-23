"""Cuentas de usuario: CRUD, login con anti fuerza bruta y cambio de contrasena.

El esquema de `usuarios`/`sesiones` lo crea `db.py` (on-demand, idempotente); aqui
solo se opera reusando `db.conectar()`. Cada funcion abre/cierra su propia conexion
(la app es local y de poca concurrencia).

FORMA PUBLICA de un usuario (lo que sale a la API): `id, usuario, rol,
debe_cambiar_password, creado, ultimo_acceso`. NUNCA `salt`/`hash`. Las GUARDAS de
negocio (no quedarse sin admins, no auto-borrado) viven en la capa API; aqui solo se
persiste y se exponen los conteos necesarios.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from .. import db, motor_db
from ..estados import ROL_ADMIN, ROL_EDITOR
from . import _comun
from .hashing import hash_en_falso, hashear_password, necesita_rehash, verificar_password

# Anti fuerza bruta: tras N fallos seguidos, el usuario queda bloqueado un rato.
# OJO: el lockout POR CUENTA es, en si mismo, un vector de DoS (un tercero puede bloquear
# la cuenta de otro a base de fallos). La barrera principal contra fuerza bruta es
# el limite POR IP delante (Traefik + `api/auth._login_ip_bloqueada`), asi que este umbral
# es holgado (10): mas tolerante con humanos torpes, igual de inutil
# para un atacante (la IP se corta mucho antes de agotar cuentas).
MAX_INTENTOS_FALLIDOS = 10
BLOQUEO_MINUTOS = 5


# --------------------------------------------------------------------------- #
# Serializacion de filas                                                       #
# --------------------------------------------------------------------------- #


# Columnas PUBLICAS del usuario, en orden estable. `cargo`, `cobertura`,
# `puede_coordinar`, `nombre` y `manager_id` se anadieron a `usuarios` con
# `_migrar_columnas_usuarios`; todo SELECT pasa por aqui para que tipos y columnas no se
# desincronicen.
_COLUMNAS_USUARIO_PUBLICAS = (
    "id", "usuario", "rol", "debe_cambiar_password", "creado", "ultimo_acceso",
    "cargo", "cobertura", "puede_coordinar", "nombre", "manager_id", "mfa_activo",
    "superadmin", "mfa_requerido", "zona_horaria",
)

# Zona IANA por defecto (el equipo del piloto). Respaldo para usuarios legados cuya columna
# pudiera venir vacia/NULL antes de que la migracion la siembre.
ZONA_HORARIA_DEFECTO = "America/Mexico_City"
_SELECT_USUARIO_PUBLICO = ", ".join(_COLUMNAS_USUARIO_PUBLICAS)


def _fila_a_usuario_publico(fila: Any, marcas: list[str] | None = None) -> dict[str, Any]:
    """Forma PUBLICA de un usuario para la API (NUNCA salt/hash).

    `cargo` es la FUNCION del equipo ("director", "community_manager"...). `cobertura` es
    el flag que dice si esa persona entra en la rota de turnos. `puede_coordinar` indica si
    es candidato a coordinador por celda (ola "coord"). Todos vacios/`False` por defecto
    para usuarios legados.

    `marcas` (organigrama del cliente): lista de ids canonicos de las verticales a las que
    pertenece la persona (`["claro-sports", "unotv"]`). Llega de la tabla N:M
    `usuarios_marcas`. Si el caller ya las consulto pasa la lista; en caso contrario se
    consulta aqui (una query por usuario) para mantener la forma publica completa.

    `nombre` es el nombre HUMANO para el organigrama (vacio en usuarios legados; la UI cae
    al `usuario`). `manager_id` es el id del SUPERIOR al que reporta (vacio = raiz/director).
    """
    if marcas is None:
        marcas = _marcas_de_usuario(fila["id"])
    return {
        "id": fila["id"],
        "usuario": fila["usuario"],
        "rol": fila["rol"],
        "debe_cambiar_password": bool(fila["debe_cambiar_password"]),
        "creado": fila["creado"],
        "ultimo_acceso": fila["ultimo_acceso"],
        "cargo": fila["cargo"],
        "cobertura": bool(fila["cobertura"]),
        "puede_coordinar": bool(fila["puede_coordinar"]),
        "nombre": fila["nombre"],
        "manager_id": fila["manager_id"],
        # `mfa_activo` (segundo factor PASSKEYS): bool, = "tiene >=1 passkey". La UI lo usa
        # para mostrar el estado y el login para decidir si eleva. NUNCA salen claves ni recovery.
        "mfa_activo": bool(fila["mfa_activo"]),
        # `superadmin`: gestiona usuarios. `mfa_requerido`: el admin le exige segundo factor.
        "superadmin": bool(fila["superadmin"]),
        "mfa_requerido": bool(fila["mfa_requerido"]),
        # `zona_horaria`: zona IANA de DISPLAY (la consola pinta los instantes en su hora de pared
        # + etiqueta). Vacia/legada -> CDMX.
        "zona_horaria": fila["zona_horaria"] or ZONA_HORARIA_DEFECTO,
        "marcas": marcas,
    }


def _marcas_de_usuario(usuario_id: str, con: Any | None = None) -> list[str]:
    """Lista de marcas (ids canonicos) de un usuario, ordenadas alfabeticamente.

    Si se pasa `con`, REUSA esa conexion (para batches o transacciones); si no, abre la
    suya. Vacio si el usuario no tiene marcas asignadas (caso normal en usuarios legados
    antes del organigrama del cliente).
    """
    cerrar = False
    if con is None:
        con = db.conectar()
        cerrar = True
    try:
        filas = con.execute(
            "SELECT marca_id FROM usuarios_marcas WHERE usuario_id = ? ORDER BY marca_id ASC",
            (usuario_id,),
        ).fetchall()
    finally:
        if cerrar:
            con.close()
    return [f["marca_id"] for f in filas]


def _marcas_de_usuarios(usuario_ids: list[str], con: Any | None = None) -> dict[str, list[str]]:
    """Mapa `id -> [marcas]` para un lote de usuarios (evita N+1 en `listar_usuarios`)."""
    if not usuario_ids:
        return {}
    cerrar = False
    if con is None:
        con = db.conectar()
        cerrar = True
    try:
        # Construimos placeholders parametrizados (los ids vienen de la BD, no del usuario,
        # pero igualmente nunca f-string con datos).
        marcadores = ", ".join(["?"] * len(usuario_ids))
        filas = con.execute(
            "SELECT usuario_id, marca_id FROM usuarios_marcas "
            f"WHERE usuario_id IN ({marcadores}) ORDER BY usuario_id ASC, marca_id ASC",
            tuple(usuario_ids),
        ).fetchall()
    finally:
        if cerrar:
            con.close()
    indice: dict[str, list[str]] = {uid: [] for uid in usuario_ids}
    for fila in filas:
        indice.setdefault(fila["usuario_id"], []).append(fila["marca_id"])
    return indice


def reemplazar_marcas_de_usuario(usuario_id: str, marcas: list[str]) -> bool:
    """Reemplaza el conjunto de marcas de un usuario (DELETE + INSERT en una transaccion).

    Devuelve True si el usuario existia, False si no (no se hace nada). La capa API valida
    cada `marca_id` contra el catalogo canonico ANTES de llegar aqui; este modulo solo
    persiste. Idempotente: si la lista nueva coincide con la actual, el resultado neto es
    el mismo (las filas se reescriben pero el contenido no cambia).

    Acepta strings duplicados (los deduplica) y los ordena para que el orden de insercion
    sea estable (no relevante para correccion, pero ayuda al log/diff).
    """
    con = db.conectar()
    try:
        existe = con.execute(
            "SELECT 1 FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
        if existe is None:
            return False
        con.execute("DELETE FROM usuarios_marcas WHERE usuario_id = ?", (usuario_id,))
        for marca in sorted(set(marcas)):
            con.execute(
                "INSERT INTO usuarios_marcas (usuario_id, marca_id) VALUES (?, ?)",
                (usuario_id, marca),
            )
        con.commit()
        return True
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# CRUD de usuarios                                                             #
# --------------------------------------------------------------------------- #


def crear_usuario(
    usuario: str,
    password: str,
    rol: str = ROL_EDITOR,
    *,
    debe_cambiar_password: bool = False,
    cargo: str = "",
    cobertura: bool = False,
    puede_coordinar: bool = False,
    nombre: str = "",
    manager_id: str = "",
    superadmin: bool = False,
    mfa_requerido: bool = False,
    zona_horaria: str = ZONA_HORARIA_DEFECTO,
    marcas: list[str] | None = None,
) -> dict[str, Any] | None:
    """Inserta un usuario nuevo y lo devuelve (forma publica). None si el nombre ya existe.

    NO valida fuerza/rol/cargo/marcas (lo hace la API contra sus mensajes); aqui solo
    persiste. `cargo` es texto libre validado en la API (allowlist en
    `estados.CARGOS_USUARIO`); `cobertura` indica si la persona entra en la rota de
    turnos (`False` por defecto). `puede_coordinar` indica si es candidato a coordinador
    por celda (ola "coord"; `False` por defecto). `marcas` (organigrama del cliente): lista de
    ids canonicos de verticales (`["claro-sports", "unotv"]`); vacio/`None` deja al
    usuario sin marcas.
    """
    salt_hex, hash_hex = hashear_password(password)
    nuevo = {
        "id": uuid.uuid4().hex[:12],
        "usuario": usuario,
        "rol": rol,
        "salt": salt_hex,
        "hash": hash_hex,
        "debe_cambiar_password": 1 if debe_cambiar_password else 0,
        "intentos_fallidos": 0,
        "bloqueo_hasta": "",
        "creado": _comun.iso(_comun.ahora()),
        "ultimo_acceso": "",
        "cargo": cargo,
        "cobertura": 1 if cobertura else 0,
        "puede_coordinar": bool(puede_coordinar),
        "nombre": nombre,
        "manager_id": manager_id,
        "superadmin": 1 if superadmin else 0,
        "mfa_requerido": 1 if mfa_requerido else 0,
        "zona_horaria": zona_horaria or ZONA_HORARIA_DEFECTO,
    }
    con = db.conectar()
    try:
        con.execute(
            "INSERT INTO usuarios (id, usuario, rol, salt, hash, debe_cambiar_password, "
            "intentos_fallidos, bloqueo_hasta, creado, ultimo_acceso, cargo, cobertura, "
            "puede_coordinar, nombre, manager_id, superadmin, mfa_requerido, zona_horaria) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                nuevo["id"], nuevo["usuario"], nuevo["rol"], nuevo["salt"], nuevo["hash"],
                nuevo["debe_cambiar_password"], nuevo["intentos_fallidos"],
                nuevo["bloqueo_hasta"], nuevo["creado"], nuevo["ultimo_acceso"],
                nuevo["cargo"], nuevo["cobertura"], nuevo["puede_coordinar"],
                nuevo["nombre"], nuevo["manager_id"], nuevo["superadmin"], nuevo["mfa_requerido"],
                nuevo["zona_horaria"],
            ),
        )
        # Marcas del organigrama (N:M): crearlas en la misma conexion para que el
        # alta del usuario quede COMPLETA si la transaccion confirma.
        marcas_norm = sorted(set(marcas or []))
        for marca in marcas_norm:
            con.execute(
                "INSERT INTO usuarios_marcas (usuario_id, marca_id) VALUES (?, ?)",
                (nuevo["id"], marca),
            )
        con.commit()
    except motor_db.IntegrityError:
        return None  # usuario UNIQUE: ya existe (neutro: SQLite o Postgres)
    finally:
        con.close()
    return {
        "id": nuevo["id"],
        "usuario": nuevo["usuario"],
        "rol": nuevo["rol"],
        "debe_cambiar_password": bool(nuevo["debe_cambiar_password"]),
        "creado": nuevo["creado"],
        "ultimo_acceso": nuevo["ultimo_acceso"],
        "cargo": nuevo["cargo"],
        "cobertura": bool(nuevo["cobertura"]),
        "puede_coordinar": bool(nuevo["puede_coordinar"]),
        "nombre": nuevo["nombre"],
        "manager_id": nuevo["manager_id"],
        # Un usuario nuevo nace SIN segundo factor: lo enrola en el login si se le exige.
        "mfa_activo": False,
        "superadmin": bool(nuevo["superadmin"]),
        "mfa_requerido": bool(nuevo["mfa_requerido"]),
        "zona_horaria": nuevo["zona_horaria"],
        "marcas": marcas_norm,
    }


def listar_usuarios() -> list[dict[str, Any]]:
    """Todos los usuarios (forma publica), por nombre ascendente.

    Cada usuario incluye su lista de `marcas` (organigrama del cliente). Para evitar N+1, se hace
    una sola consulta a `usuarios_marcas` y se indexa por `usuario_id`.
    """
    con = db.conectar()
    try:
        filas = con.execute(
            f"SELECT {_SELECT_USUARIO_PUBLICO} FROM usuarios ORDER BY usuario ASC"
        ).fetchall()
        marcas_por_uid = _marcas_de_usuarios([f["id"] for f in filas], con=con)
    finally:
        con.close()
    return [_fila_a_usuario_publico(f, marcas_por_uid.get(f["id"], [])) for f in filas]


def obtener_usuario_por_id(usuario_id: str) -> dict[str, Any] | None:
    """Un usuario por id (forma publica); None si no existe."""
    con = db.conectar()
    try:
        fila = con.execute(
            f"SELECT {_SELECT_USUARIO_PUBLICO} FROM usuarios WHERE id = ?",
            (usuario_id,),
        ).fetchone()
        if fila is None:
            return None
        marcas = _marcas_de_usuario(usuario_id, con=con)
    finally:
        con.close()
    return _fila_a_usuario_publico(fila, marcas)


def actualizar_perfil(
    usuario_id: str,
    *,
    cargo: str | None = None,
    cobertura: bool | None = None,
    puede_coordinar: bool | None = None,
    nombre: str | None = None,
    manager_id: str | None = None,
    superadmin: bool | None = None,
    mfa_requerido: bool | None = None,
    zona_horaria: str | None = None,
    marcas: list[str] | None = None,
) -> bool:
    """Actualiza `cargo`, `cobertura`, `puede_coordinar`, `nombre`, `manager_id`,
    `superadmin`, `mfa_requerido` y/o `marcas`; True si existia.

    NO aplica guardas (lo hace la API contra `CARGOS_USUARIO`, el catalogo de marcas y la
    validacion del organigrama: superior existente, distinto de uno mismo y sin ciclos).
    Pasar `None` deja el campo intacto; `cargo=""`/`nombre=""` lo limpian; `manager_id=""`
    deja al usuario sin superior (raiz del organigrama); `marcas=[]` borra todas las
    asignaciones N:M de ese usuario; `marcas=[...]` las REEMPLAZA al conjunto dado.
    `puede_coordinar` (ola "coord"): bool que marca al usuario como candidato a coordinador
    por celda en el calendario.
    """
    campos: list[str] = []
    valores: list[Any] = []
    if cargo is not None:
        campos.append("cargo = ?")
        valores.append(cargo)
    if cobertura is not None:
        campos.append("cobertura = ?")
        valores.append(1 if cobertura else 0)
    if puede_coordinar is not None:
        campos.append("puede_coordinar = ?")
        valores.append(bool(puede_coordinar))
    if nombre is not None:
        campos.append("nombre = ?")
        valores.append(nombre)
    if manager_id is not None:
        campos.append("manager_id = ?")
        valores.append(manager_id)
    if superadmin is not None:
        campos.append("superadmin = ?")
        valores.append(1 if superadmin else 0)
    if mfa_requerido is not None:
        campos.append("mfa_requerido = ?")
        valores.append(1 if mfa_requerido else 0)
    if zona_horaria is not None:
        campos.append("zona_horaria = ?")
        valores.append(zona_horaria)
    # Sin campos directos ni marcas -> simple existencia.
    if not campos and marcas is None:
        return obtener_usuario_por_id(usuario_id) is not None
    if campos:
        valores.append(usuario_id)
        con = db.conectar()
        try:
            cur = con.execute(
                f"UPDATE usuarios SET {', '.join(campos)} WHERE id = ?", tuple(valores)
            )
            con.commit()
            existia = cur.rowcount > 0
        finally:
            con.close()
        if not existia:
            return False
    if marcas is not None:
        if not reemplazar_marcas_de_usuario(usuario_id, marcas):
            # El usuario no existe (caso ya cubierto si no habia campos directos arriba).
            return False
    return True


def _fila_credenciales(con: Any, usuario: str) -> Any:
    """Fila COMPLETA (incluye salt/hash) por nombre de usuario; None si no existe.

    De uso interno (login): nunca sale de este modulo.
    """
    return con.execute(
        "SELECT id, usuario, rol, salt, hash, debe_cambiar_password, "
        "intentos_fallidos, bloqueo_hasta, creado, ultimo_acceso, cargo, cobertura, "
        "puede_coordinar, nombre, manager_id, mfa_activo, superadmin, mfa_requerido, "
        "zona_horaria "
        "FROM usuarios WHERE usuario = ?",
        (usuario,),
    ).fetchone()


def _ahora_iso() -> str:
    """Marca de tiempo ISO actual (helper local para las filas de passkeys)."""
    return _comun.iso(_comun.ahora())


def contar_admins() -> int:
    """Numero de usuarios con rol admin (para las guardas de 'ultimo admin')."""
    con = db.conectar()
    try:
        fila = con.execute(
            "SELECT COUNT(*) AS n FROM usuarios WHERE rol = ?", (ROL_ADMIN,)
        ).fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def contar_superadmins() -> int:
    """Numero de superadmins (para la guarda 'no te quedes sin quien gestione usuarios')."""
    con = db.conectar()
    try:
        fila = con.execute(
            "SELECT COUNT(*) AS n FROM usuarios WHERE superadmin = 1"
        ).fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def cambiar_rol(usuario_id: str, rol: str) -> bool:
    """Cambia el rol de un usuario; True si existia. NO aplica guardas (lo hace la API)."""
    con = db.conectar()
    try:
        cur = con.execute("UPDATE usuarios SET rol = ? WHERE id = ?", (rol, usuario_id))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def cambiar_usuario(usuario_id: str, nuevo_usuario: str) -> bool | None:
    """Cambia el NOMBRE DE CUENTA (login) de un usuario. NO aplica guardas (lo hace la API).

    Tri-estado: `True` si existia y se renombro; `False` si el id no existe; `None` si el
    nuevo nombre YA esta en uso por otra cuenta (columna `usuario` UNIQUE -> IntegrityError).
    Las sesiones se referencian por `usuario_id` (no por el login), asi que renombrar NO
    invalida la sesion activa de esa persona; solo cambia con que nombre inicia sesion.
    """
    con = db.conectar()
    try:
        cur = con.execute(
            "UPDATE usuarios SET usuario = ? WHERE id = ?", (nuevo_usuario, usuario_id)
        )
        con.commit()
        return cur.rowcount > 0
    except motor_db.IntegrityError:
        return None  # nombre de cuenta ya en uso (UNIQUE; neutro SQLite/Postgres)
    finally:
        con.close()


def establecer_password(
    usuario_id: str, password: str, *, debe_cambiar_password: bool = False
) -> bool:
    """Fija una contrasena nueva (re-salt) y resetea intentos/bloqueo; True si existia.

    Usado tanto por el reset del admin (PATCH) como por el cambio del propio usuario.
    SEGURIDAD: invalida TODAS las sesiones del usuario (revision de seguridad de auth):
    cambiar/resetear la contrasena debe expulsar cualquier sesion activa (token robado,
    equipo prestado, cuenta sospechosa). El cambio voluntario re-emite una sesion nueva
    para el dispositivo actual desde la capa API.
    """
    salt_hex, hash_hex = hashear_password(password)
    con = db.conectar()
    try:
        cur = con.execute(
            "UPDATE usuarios SET salt = ?, hash = ?, debe_cambiar_password = ?, "
            "intentos_fallidos = 0, bloqueo_hasta = '' WHERE id = ?",
            (salt_hex, hash_hex, 1 if debe_cambiar_password else 0, usuario_id),
        )
        con.execute("DELETE FROM sesiones WHERE usuario_id = ?", (usuario_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def borrar_usuario(usuario_id: str) -> bool:
    """Borra un usuario y sus sesiones; True si existia. NO aplica guardas (lo hace la API).

    LIBERA además, en la MISMA transacción, las piezas que esa persona tenía COGIDAS
    (`contenido.responsable_id = su id`): vuelven a «Por coger» (responsable_id=''). Sin esto
    quedaban pegadas a un id FANTASMA —fuera de «Por coger» y de «Mis tareas» de cualquiera, e
    irreclamables (`reclamar_publicacion` exige responsable_id='')—, perdiendo trabajo del
    equipo. Es la misma idea de cascada que el borrado de sesiones.
    """
    con = db.conectar()
    try:
        con.execute(
            "UPDATE publicacion SET responsable_id = '', responsable_nombre = '', actualizado = ? "
            "WHERE responsable_id = ?",
            (_ahora_iso(), usuario_id),
        )
        con.execute("DELETE FROM sesiones WHERE usuario_id = ?", (usuario_id,))
        cur = con.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Login (con anti fuerza bruta) y verificacion de la contrasena actual          #
# --------------------------------------------------------------------------- #


def autenticar(usuario: str, password: str) -> dict[str, Any] | None:
    """Verifica credenciales y devuelve el usuario (forma publica) o None.

    Devuelve None SIN distinguir entre usuario inexistente, contrasena incorrecta o
    cuenta bloqueada: la API responde un mensaje GENERICO (no enumeracion). Cuenta los
    fallos por usuario y bloquea temporalmente tras `MAX_INTENTOS_FALLIDOS`.
    """
    con = db.conectar()
    try:
        fila = _fila_credenciales(con, usuario)
        if fila is None:
            # Usuario inexistente: igualamos el coste con un hash "en falso" para no
            # filtrar por tiempo si el usuario existe o no (best-effort).
            hash_en_falso(password)
            return None

        bloqueo = _comun.parsear_iso(fila["bloqueo_hasta"])
        if bloqueo is not None and _comun.ahora() < bloqueo:
            # Igualamos el coste con un hash "en falso" antes de salir: sin esto la cuenta
            # bloqueada responde mas rapido (sin scrypt) y delata que existe y esta bloqueada.
            hash_en_falso(password)
            return None  # bloqueado: no revelamos el motivo

        if not verificar_password(password, fila["salt"], fila["hash"]):
            fallidos = int(fila["intentos_fallidos"]) + 1
            nuevo_bloqueo = ""
            if fallidos >= MAX_INTENTOS_FALLIDOS:
                nuevo_bloqueo = _comun.iso(_comun.ahora() + timedelta(minutes=BLOQUEO_MINUTOS))
                fallidos = 0  # reiniciamos el contador tras aplicar el bloqueo
            con.execute(
                "UPDATE usuarios SET intentos_fallidos = ?, bloqueo_hasta = ? WHERE id = ?",
                (fallidos, nuevo_bloqueo, fila["id"]),
            )
            con.commit()
            return None

        # Exito: reseteamos contador/bloqueo y marcamos ultimo acceso.
        ahora_iso = _comun.iso(_comun.ahora())
        con.execute(
            "UPDATE usuarios SET intentos_fallidos = 0, bloqueo_hasta = '', ultimo_acceso = ? "
            "WHERE id = ?",
            (ahora_iso, fila["id"]),
        )
        # REHASH-ON-LOGIN: si el hash guardado se derivo por debajo del coste objetivo (legado
        # o `n` menor), lo RE-DERIVAMOS ahora que tenemos la contrasena en claro y verificada.
        # Transparente para el usuario; sube el coste de las cuentas viejas sin pedir reset.
        if necesita_rehash(fila["hash"]):
            nuevo_salt, nuevo_hash = hashear_password(password)
            con.execute(
                "UPDATE usuarios SET salt = ?, hash = ? WHERE id = ?",
                (nuevo_salt, nuevo_hash, fila["id"]),
            )
        con.commit()
        marcas = _marcas_de_usuario(fila["id"], con=con)
        return {
            "id": fila["id"],
            "usuario": fila["usuario"],
            "rol": fila["rol"],
            "debe_cambiar_password": bool(fila["debe_cambiar_password"]),
            "creado": fila["creado"],
            "ultimo_acceso": ahora_iso,
            "cargo": fila["cargo"],
            "cobertura": bool(fila["cobertura"]),
            "puede_coordinar": bool(fila["puede_coordinar"]),
            "nombre": fila["nombre"],
            "manager_id": fila["manager_id"],
            # Para que el login decida si ELEVA al segundo factor (passkey) tras la contrasena,
            # o si lo FUERZA a inscribir una llave (`mfa_requerido`). `superadmin` viaja por
            # consistencia con la forma publica.
            "mfa_activo": bool(fila["mfa_activo"]),
            "superadmin": bool(fila["superadmin"]),
            "mfa_requerido": bool(fila["mfa_requerido"]),
            "zona_horaria": fila["zona_horaria"] or ZONA_HORARIA_DEFECTO,
            "marcas": marcas,
        }
    finally:
        con.close()


def verificar_password_actual(usuario_id: str, password: str) -> bool:
    """True si `password` es la contrasena ACTUAL del usuario (para el cambio de pass)."""
    con = db.conectar()
    try:
        fila = con.execute(
            "SELECT salt, hash FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
    finally:
        con.close()
    if fila is None:
        return False
    return verificar_password(password, fila["salt"], fila["hash"])


# --------------------------------------------------------------------------- #
# MFA PASSKEYS / WebAuthn: credenciales, el flag derivado y los recovery codes   #
# --------------------------------------------------------------------------- #
#
# El TRABAJO criptografico (opciones, verificacion de la respuesta del autenticador, recovery)
# vive en `auth.mfa` (sin tocar la BD). Estas funciones leen/escriben la tabla
# `webauthn_credenciales` (1:N) y las dos columnas de `usuarios` (`mfa_activo`,
# `mfa_recovery_codes`). NUNCA se guarda un secreto del lado servidor: solo la clave PUBLICA y
# el contador de firmas. Los recovery van SIEMPRE hasheados (scrypt).


def estado_mfa(usuario_id: str) -> dict[str, Any] | None:
    """Estado MFA crudo de un usuario: `{activo, num_credenciales}`; None si no existe.

    Uso INTERNO de la capa MFA (la API lo usa para decidir). `activo` deriva de tener >=1
    passkey. Los codigos de recuperacion se retiraron (la recuperacion es por reset de un
    superadmin), asi que ya no se expone `recovery_codes`.
    """
    con = db.conectar()
    try:
        fila = con.execute(
            "SELECT mfa_activo FROM usuarios WHERE id = ?",
            (usuario_id,),
        ).fetchone()
        if fila is None:
            return None
        n = con.execute(
            "SELECT COUNT(*) AS n FROM webauthn_credenciales WHERE usuario_id = ?",
            (usuario_id,),
        ).fetchone()
    finally:
        con.close()
    num = int(n["n"]) if n is not None else 0
    return {
        "activo": bool(fila["mfa_activo"]) and num > 0,
        "num_credenciales": num,
    }


def listar_credenciales_mfa(usuario_id: str) -> list[dict[str, Any]]:
    """Passkeys de un usuario, con su forma INTERNA (incluye `credential_id`/`public_key`).

    La usa la capa MFA para construir `allow_credentials`/`exclude_credentials` y para localizar
    la credencial al verificar un login. La API NO devuelve `public_key`; expone solo
    `{id, nombre, creada, ultimo_uso}` (ver `api/auth`).
    """
    con = db.conectar()
    try:
        filas = con.execute(
            "SELECT id, usuario_id, credential_id, public_key, sign_count, transports, "
            "nombre, creada, ultimo_uso FROM webauthn_credenciales "
            "WHERE usuario_id = ? ORDER BY creada ASC",
            (usuario_id,),
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "id": f["id"],
            "usuario_id": f["usuario_id"],
            "credential_id": f["credential_id"],
            "public_key": f["public_key"],
            "sign_count": int(f["sign_count"] or 0),
            "transports": f["transports"] or "[]",
            "nombre": f["nombre"] or "",
            "creada": f["creada"] or "",
            "ultimo_uso": f["ultimo_uso"] or "",
        }
        for f in filas
    ]


def credencial_mfa_por_credential_id(usuario_id: str, credential_id: str) -> dict[str, Any] | None:
    """Una passkey concreta del usuario por su `credential_id` (base64url); None si no es suya.

    Atar la busqueda al `usuario_id` evita que una assertion verifique contra la credencial de
    OTRO usuario (la cookie pre-auth fija de quien es la ceremonia).
    """
    for c in listar_credenciales_mfa(usuario_id):
        if c["credential_id"] == credential_id:
            return c
    return None


def credencial_mfa_global(credential_id: str) -> dict[str, Any] | None:
    """Una passkey por su `credential_id` (UNIQUE global), SIN atarla a un usuario; None si no existe.

    Para el login PASSWORDLESS (credencial descubrible): la assertion identifica la credencial por
    su id y aqui resolvemos a QUIEN pertenece (`usuario_id`) + su clave publica, para verificar la
    firma y abrir su sesion. La seguridad la da la verificacion criptografica de la assertion
    contra `public_key`, no la confianza en el id que manda el cliente.
    """
    if not credential_id:
        return None
    con = db.conectar()
    try:
        f = con.execute(
            "SELECT id, usuario_id, credential_id, public_key, sign_count, transports, nombre "
            "FROM webauthn_credenciales WHERE credential_id = ?",
            (credential_id,),
        ).fetchone()
    finally:
        con.close()
    if f is None:
        return None
    return {
        "id": f["id"],
        "usuario_id": f["usuario_id"],
        "credential_id": f["credential_id"],
        "public_key": f["public_key"],
        "sign_count": int(f["sign_count"] or 0),
        "transports": f["transports"] or "[]",
        "nombre": f["nombre"] or "",
    }


def guardar_credencial_mfa(
    usuario_id: str,
    *,
    credential_id: str,
    public_key: str,
    sign_count: int,
    transports: str,
    nombre: str,
) -> bool:
    """Inserta una passkey nueva y enciende `mfa_activo`; True si se guardo.

    Es el paso final del ENROLAMIENTO (`/api/auth/mfa/registro/verificar`). Tras insertar marca
    `mfa_activo=1` (el usuario ya tiene >=1 passkey). Devuelve False si el `credential_id` ya
    existia (UNIQUE) o el usuario no existe.
    """
    con = db.conectar()
    try:
        ahora = _ahora_iso()
        con.execute(
            "INSERT INTO webauthn_credenciales (id, usuario_id, credential_id, public_key, "
            "sign_count, transports, nombre, creada, ultimo_uso) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                uuid.uuid4().hex[:12], usuario_id, credential_id, public_key,
                int(sign_count), transports, nombre, ahora, "",
            ),
        )
        cur = con.execute(
            "UPDATE usuarios SET mfa_activo = 1 WHERE id = ?", (usuario_id,)
        )
        con.commit()
        return cur.rowcount > 0
    except motor_db.IntegrityError:
        return False  # credential_id duplicado (mismo autenticador) o usuario inexistente
    finally:
        con.close()


def actualizar_sign_count_mfa(credencial_id: str, sign_count: int) -> bool:
    """Actualiza el `sign_count` y marca `ultimo_uso` de una passkey tras un login OK; True si existia."""
    con = db.conectar()
    try:
        cur = con.execute(
            "UPDATE webauthn_credenciales SET sign_count = ?, ultimo_uso = ? WHERE id = ?",
            (int(sign_count), _ahora_iso(), credencial_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def borrar_credencial_mfa(usuario_id: str, credencial_id: str) -> bool:
    """Borra UNA passkey del usuario; si era la ULTIMA, apaga `mfa_activo`. True si existia.

    Ata el borrado al `usuario_id` (un usuario solo borra las suyas). Recalcula `mfa_activo`
    en la misma transaccion para que el flag siga reflejando "tiene >=1 passkey".
    """
    con = db.conectar()
    try:
        cur = con.execute(
            "DELETE FROM webauthn_credenciales WHERE id = ? AND usuario_id = ?",
            (credencial_id, usuario_id),
        )
        if cur.rowcount == 0:
            return False
        restantes = con.execute(
            "SELECT COUNT(*) AS n FROM webauthn_credenciales WHERE usuario_id = ?",
            (usuario_id,),
        ).fetchone()
        if restantes is not None and int(restantes["n"]) == 0:
            con.execute(
                "UPDATE usuarios SET mfa_activo = 0, mfa_recovery_codes = '[]' WHERE id = ?",
                (usuario_id,),
            )
        con.commit()
        return True
    finally:
        con.close()


def renombrar_credencial_mfa(usuario_id: str, credencial_id: str, nombre: str) -> bool:
    """Renombra UNA passkey del usuario (etiqueta legible); True si existia.

    Ata el cambio al `usuario_id` (un usuario solo renombra las suyas). No toca la clave publica,
    el contador ni ningun flag: solo la etiqueta que el usuario ve en su lista.
    """
    con = db.conectar()
    try:
        cur = con.execute(
            "UPDATE webauthn_credenciales SET nombre = ? WHERE id = ? AND usuario_id = ?",
            (nombre, credencial_id, usuario_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def desactivar_mfa(usuario_id: str) -> bool:
    """Borra TODAS las passkeys + recovery y apaga `mfa_activo`; True si existia.

    Lo usan el `disable` del propio usuario (con su contrasena) y el reset del admin
    (recuperacion de cuenta: dispositivo perdido). Idempotente: dejar a un usuario sin MFA dos
    veces no falla.
    """
    con = db.conectar()
    try:
        con.execute(
            "DELETE FROM webauthn_credenciales WHERE usuario_id = ?", (usuario_id,)
        )
        cur = con.execute(
            "UPDATE usuarios SET mfa_activo = 0, mfa_recovery_codes = '[]' WHERE id = ?",
            (usuario_id,),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
