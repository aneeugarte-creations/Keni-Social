// --- Autenticación y usuarios (#auth) --------------------------------------
//
// Auth por usuario/contraseña sobre cookie de sesión (la pone el backend). El
// login devuelve el usuario actual; `GET /api/auth/me` lo recupera al cargar la
// app. La gestión de usuarios (`/api/usuarios`) es solo para el rol admin.

/** Rol de un usuario de la consola. `admin` ve además la gestión de usuarios. */
export type RolUsuario = "admin" | "editor";

/**
 * Cargo (función) de un usuario en el equipo. Ortogonal al rol de permisos: describe
 * QUÉ hace la persona (community manager, director, coordinador de redes...). Allowlist
 * sincronizada con `keni_consola.estados.CARGOS_USUARIO`; cadena vacía = sin
 * clasificar.
 */
export type CargoUsuario =
  // Catalogo original (retrocompat):
  | "director"
  | "gerente"
  | "coordinador"
  | "content_manager"
  | "community_manager"
  | "redactor"
  | "guionista"
  | "editorial"
  | "estrategia"
  | "fotografia"
  // Ampliacion del organigrama del cliente:
  | "coordinador_redes"
  | "coordinador_youtube"
  | "gerente_podcast"
  | "creativo_vertical"
  | "editorial_youtube"
  | "coordinador_invitados"
  | "coordinador_operativo"
  | "fotografia_qa"
  | "editor_video"
  | "disenador"
  | "";

/** Etiqueta legible para cada cargo (para selects/badges/listados). */
export const ETIQUETA_CARGO: Record<Exclude<CargoUsuario, "">, string> = {
  // Catalogo original:
  director: "Director",
  gerente: "Gerente",
  coordinador: "Coordinador",
  content_manager: "Content manager",
  community_manager: "Community manager",
  redactor: "Redactor",
  guionista: "Guionista",
  editorial: "Editorial",
  estrategia: "Estrategia digital",
  fotografia: "Fotografía",
  // Ampliacion organigrama del cliente:
  coordinador_redes: "Coordinador de redes",
  coordinador_youtube: "Coordinador de YouTube",
  gerente_podcast: "Gerente de podcast",
  creativo_vertical: "Creativo de vertical",
  editorial_youtube: "Editorial YouTube",
  coordinador_invitados: "Coordinador de invitados",
  coordinador_operativo: "Coordinador operativo",
  fotografia_qa: "Fotografía + QA",
  editor_video: "Editor de video",
  disenador: "Diseñador",
};

/**
 * Orden estable de los cargos para los selectores (agrupa primero los del organigrama
 * del cliente y deja al final los del catalogo legado por si quedan usuarios sin migrar).
 */
export const CARGOS_ORDENADOS: Exclude<CargoUsuario, "">[] = [
  "director",
  "coordinador_redes",
  "coordinador_youtube",
  "coordinador_operativo",
  "coordinador_invitados",
  "gerente_podcast",
  "content_manager",
  "community_manager",
  "creativo_vertical",
  "editorial_youtube",
  "redactor",
  "fotografia_qa",
  "editor_video",
  "disenador",
  // Catalogo legado (al final):
  "gerente",
  "coordinador",
  "editorial",
  "guionista",
  "estrategia",
  "fotografia",
];

/** Etiqueta legible de un cargo (vacío => "Sin cargo"). */
export function etiquetaCargo(cargo: CargoUsuario): string {
  if (!cargo) return "Sin cargo";
  return ETIQUETA_CARGO[cargo];
}

/** Usuario autenticado (lo que devuelven login y `/api/auth/me`). */
export interface UsuarioSesion {
  id: string;
  usuario: string;
  rol: RolUsuario;
  /** `true` => hay que forzar el cambio de contraseña antes de usar la app. */
  debe_cambiar_password: boolean;
  /**
   * ISO 8601 de creación de la cuenta. Solo llega por `GET /api/auth/me` (la página
   * "Mi cuenta" lo muestra); el login devuelve la forma mínima y no lo incluye.
   */
  creado?: string;
  /** ISO 8601 del último acceso (vacío si nunca entró). Solo llega por `me`. */
  ultimo_acceso?: string;
  /** Cargo (función en el equipo). Cadena vacía si aún sin clasificar. */
  cargo?: CargoUsuario;
  /** `true` => esta persona entra en la rota de turnos (cobertura). */
  cobertura?: boolean;
  /** `true` => candidato a coordinador por celda en el calendario (ola "coord"). */
  puede_coordinar?: boolean;
  /**
   * Verticales/marcas a las que pertenece (relación N:M con `keni_shared.marcas`).
   * Una persona puede estar en varias (editorial de YouTube: claro-sports + unotv + piso-15).
   * Solo llega por `GET /api/auth/me`; el login no lo incluye.
   */
  marcas?: string[];
  /**
   * MFA (segundo factor, passkeys/WebAuthn). Solo llegan por `GET /api/auth/me`:
   *   - `mfa_habilitado`: el flag del servidor (`KENI_CONSOLA_MFA`). Si es `false`/ausente,
   *     la UI NO muestra nada de MFA (la sección de "Mi cuenta" se oculta).
   *   - `mfa_activo`: si ESTA cuenta ya tiene ≥1 llave de acceso registrada.
   */
  mfa_habilitado?: boolean;
  mfa_activo?: boolean;
  /**
   * `true` => este ADMIN está OBLIGADO a tener segundo factor (`KENI_CONSOLA_MFA_ADMIN`, ON por
   * defecto) y aún NO ha registrado ninguna llave. NO bloquea el acceso (sin lockout): la UI lo
   * usa para EMPUJAR la inscripción de una passkey cuanto antes. Solo llega por `GET /api/auth/me`.
   */
  debe_inscribir_mfa?: boolean;
  /**
   * `true` => puede PUBLICAR a producción en la Biblioteca de Prompts (los demás solo
   * solicitan). Lo añade el backend del flujo de publicación; mientras no llegue, la UI
   * cae al rol clásico (`rol === "admin"`). Ver `useEsAdmin`.
   */
  es_admin?: boolean;
}

/** Respuesta de `POST /api/auth/login` cuando el usuario necesita el segundo factor (MFA). */
export interface RespuestaLoginMfa {
  mfa_required: true;
}

/**
 * Opciones de una ceremonia WebAuthn (registro o login). El backend las arma con py_webauthn
 * (`options_to_json`) y son JSON spec-compliant: se pasan TAL CUAL a `@simplewebauthn/browser`
 * (`startRegistration`/`startAuthentication`) como `optionsJSON`. No las tipamos campo a campo:
 * son opacas para nuestro código (la librería conoce su forma).
 */
export type OpcionesCeremoniaWebauthn = Record<string, unknown>;

/**
 * Respuesta de `POST /api/auth/mfa/registro/verificar`. `recovery_codes` solo llega la PRIMERA
 * vez (al registrar la primera passkey); se muestran una sola vez.
 */
export interface RespuestaMfaRegistro {
  ok: true;
  recovery_codes?: string[];
}

/** Una passkey en la lista de `GET /api/auth/mfa/credenciales` (sin secretos). */
export interface CredencialPasskey {
  id: string;
  nombre: string;
  creada: string;
  ultimo_uso: string;
}

/** Respuesta de `GET /api/auth/mfa/credenciales`. */
export interface RespuestaMfaCredenciales {
  credenciales: CredencialPasskey[];
}

/** Respuesta de `POST /api/auth/login` y `GET /api/auth/me`. */
export interface RespuestaSesion {
  usuario: UsuarioSesion;
}

/** Cuerpo de `POST /api/auth/login`. */
export interface CuerpoLogin {
  usuario: string;
  password: string;
}

/** Cuerpo de `POST /api/auth/cambiar-password`. */
export interface CuerpoCambiarPassword {
  password_actual: string;
  password_nueva: string;
}

/** Fila del listado `GET /api/usuarios` (solo admin). */
export interface UsuarioAdmin {
  id: string;
  usuario: string;
  rol: RolUsuario;
  /** ISO 8601 de creación. */
  creado: string;
  /** ISO 8601 del último acceso, o `null` si nunca entró. */
  ultimo_acceso: string | null;
  /** Cargo (función en el equipo). Cadena vacía si aún sin clasificar. */
  cargo?: CargoUsuario;
  /** `true` => esta persona entra en la rota de turnos. */
  cobertura?: boolean;
  /** `true` => candidato a coordinador por celda en el calendario (ola "coord"). */
  puede_coordinar?: boolean;
  /**
   * Nombre HUMANO (organigrama): lo que se pinta en las tarjetas. Cadena vacía en
   * usuarios sin nombre asignado (la UI cae al `usuario`/login).
   */
  nombre?: string;
  /**
   * Id del usuario SUPERIOR al que reporta (organigrama). Cadena vacía = raíz (sin
   * superior, p.ej. el director). Define el árbol del organigrama; es ORTOGONAL a
   * `marcas` (una persona puede trabajar en una vertical y reportar a otra área).
   */
  manager_id?: string;
  /**
   * Verticales/marcas a las que pertenece (relación N:M; ids canónicos del catálogo).
   * Siempre llega (lista vacía si no tiene marcas asignadas). Ola `feat/roles-marcas`.
   */
  marcas?: string[];
}

/** Respuesta de `GET /api/usuarios`: el backend envuelve la lista en `{ usuarios }`. */
export interface RespuestaUsuarios {
  usuarios: UsuarioAdmin[];
}

/** Cuerpo de `POST /api/usuarios` (alta de usuario). */
export interface CuerpoCrearUsuario {
  usuario: string;
  password: string;
  rol: RolUsuario;
  /** Nombre humano opcional (organigrama). Si se omite, queda vacío. */
  nombre?: string;
}

/**
 * Cuerpo de `PATCH /api/usuarios/{id}`: cambiar rol, resetear contraseña, o editar
 * cargo/cobertura/marcas del organigrama del cliente. Todos opcionales (se manda solo lo que
 * cambia). `marcas` reemplaza el conjunto entero (lista vacía = desasignar todas).
 */
export interface CuerpoActualizarUsuario {
  /** Nombre de cuenta (login); no vacío. 409 si otra cuenta ya lo usa. */
  usuario?: string;
  rol?: RolUsuario;
  password?: string;
  /** Cargo del catálogo (`CARGOS_USUARIO`); "" desclasifica. */
  cargo?: CargoUsuario;
  /** Cobertura: entra o no en la rota de turnos. */
  cobertura?: boolean;
  /** Candidato a coordinador por celda en el calendario (ola "coord"). */
  puede_coordinar?: boolean;
  /** Nombre humano (organigrama); "" lo limpia. */
  nombre?: string;
  /**
   * Id del superior al que reporta (organigrama); "" desliga (vuelve a raíz). Debe
   * apuntar a un usuario existente, distinto de uno mismo y sin cerrar ciclos.
   */
  manager_id?: string;
  /** Lista de ids canónicos del catálogo de marcas; reemplaza el conjunto. */
  marcas?: string[];
}
