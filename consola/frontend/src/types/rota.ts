// --- Rota de horarios del equipo (F4 · #144) ---

/** Un miembro del equipo (un usuario de la consola) disponible para la rota.
 *
 * `marcas` viene del organigrama del cliente (ola `feat/roles-marcas`): ids canónicos de las
 * verticales a las que pertenece (claro-sports, unotv...). La rota hoy solo cubre
 * ClaroSports; el front filtra por `marcas.includes("claro-sports")`.
 *
 * `cargo` (funcion en el organigrama, p.ej. `community_manager`, `coordinador_redes`) y
 * `cobertura` (¿esta miembro disponible para cubrir turnos?) permiten al frontend
 * restringir la rejilla "Turnos por franja" a los CMs activos sin tener que pedir cada
 * usuario individualmente.
 */
export interface MiembroRota {
  id: string;
  nombre: string;
  marcas?: string[];
  /** Cargo del organigrama (p.ej. `community_manager`). "" si no esta seteado. */
  cargo?: string;
  /** Si el miembro esta disponible para cubrir turnos hoy. */
  cobertura?: boolean;
  /** Candidato a coordinador por celda (ola "coord"). */
  puede_coordinar?: boolean;
}

export interface RespuestaEquipoRota {
  equipo: MiembroRota[];
}

/** Cómo se cubre un evento: con señal (transmisión), solo imágenes, o no se cubre. */
export type TipoCoberturaEvento = "transmision" | "imagenes" | "no_cubrir";

/** Prioridad de un evento del calendario (pista visual para qué cubrir primero). */
export type PrioridadEvento = "alta" | "media" | "baja";

/** Un evento/transmisión a cubrir: cuándo es, QUÉ sacar y CÓMO se cubre. */
export interface EventoRota {
  id: string;
  titulo: string;
  /** ISO (AAAA-MM-DD). */
  fecha: string;
  hora: string;
  /** "Qué sacar" de esta transmisión (el campo clave del Excel del coordinador de la rota). */
  contenido: string;
  nota: string;
  /** Tipo de cobertura: transmisión (con señal) / solo imágenes / no cubrir. */
  tipo_cobertura: TipoCoberturaEvento;
  /** Prioridad del evento (alta/media/baja). */
  prioridad: PrioridadEvento;
  /** `true` si se reprogramó y aún no se ha avisado al equipo ("Cambió"). */
  cambiado: boolean;
  /** ISO de la última edición. */
  actualizado: string;
  es_sabado: boolean;
  /** Id canónico de la marca a la que pertenece el evento ("" = sin marca). */
  marca: string;
  /** Nombre legible de la marca (derivado del catálogo; "" si sin marca). */
  marca_nombre: string;
}

export interface RespuestaEventosRota {
  eventos: EventoRota[];
}

export interface RespuestaEventoRota {
  evento: EventoRota;
}

/**
 * Filtros de la lista de Eventos (pestaña /rota → Eventos). Todo opcional; los
 * arrays vacíos = sin filtro (igual a no enviar el campo). `q` es substring
 * case-insensitive sobre `titulo` y `contenido`. `cambiado=null` = todos.
 */
export interface FiltrosListaEventos {
  desde?: string;
  hasta?: string;
  tipo_cobertura?: TipoCoberturaEvento[];
  prioridad?: PrioridadEvento[];
  /** Tri-estado: `true` solo reprogramados, `false` solo avisados, `null|undefined` todos. */
  cambiado?: boolean | null;
  q?: string;
  /** Id canónico de marca; ausente/vacío = todas las marcas. */
  marca?: string;
}

export interface CuerpoCrearEventoRota {
  titulo: string;
  fecha: string;
  hora?: string;
  contenido?: string;
  nota?: string;
  tipo_cobertura?: TipoCoberturaEvento;
  prioridad?: PrioridadEvento;
  /** Id canónico de marca del evento ("" o ausente = sin marca). */
  marca?: string;
}

/**
 * Edición parcial de un evento (todo opcional; se manda lo que cambia). Editar
 * `fecha`/`hora`/`tipo_cobertura` lo marca como reprogramado (`cambiado=1`);
 * `cambiado:false` es la acción "marcar avisado" (limpia el aviso).
 */
export type CuerpoActualizarEventoRota = Partial<CuerpoCrearEventoRota> & {
  cambiado?: boolean;
};

/** Estado de un turno: `propuesto` (Keni) o `aprobado` (publicado por el coordinador de la rota). */
export type EstadoTurnoRota = "propuesto" | "aprobado";

// Nota: el viejo `TurnoRota` (turno ligado a un evento + cobertura persistida) ya
// no existe. Ahora el turno es persona × día × franja (modelo nuevo, ver más abajo).
// La cobertura es DERIVADA (calculada): para cada evento, los turnos cuya
// `(fecha, franja)` lo cubren. Ver `CoberturaEvento` / `RespuestaCoberturaSemana`.

// --- Gestión de turnos: horario de trabajo + ausencias (F4 · #144, ola A) ---

/** Tipo de una ausencia/vacación. */
export type TipoAusencia = "vacaciones" | "descanso" | "baja" | "otro";

/** Una ausencia: un rango (inclusivo) en que un miembro NO está disponible. */
export interface AusenciaRota {
  id: string;
  miembro_id: string;
  miembro_nombre: string;
  tipo: TipoAusencia;
  /** ISO (AAAA-MM-DD), inclusivo. */
  desde: string;
  hasta: string;
  motivo: string;
}

export interface RespuestaAusenciasRota {
  ausencias: AusenciaRota[];
}

/** Un turno de cobertura YA asignado que cae dentro del rango de una ausencia: el hueco
 *  que esa ausencia deja al registrarse/editarse (aviso, no bloqueo). */
export interface ConflictoCobertura {
  /** ISO (AAAA-MM-DD) del turno que queda descubierto. */
  fecha: string;
  /** Nombre legible de la franja (p. ej. "Mañana"); "" si no resuelve. */
  franja: string;
}

export interface RespuestaAusenciaRota {
  ausencia: AusenciaRota;
  /** Turnos que la ausencia deja sin cubrir; ausente o `[]` = ninguno. */
  conflictos?: ConflictoCobertura[];
}

export interface CuerpoCrearAusenciaRota {
  miembro_id: string;
  desde: string;
  hasta: string;
  tipo?: TipoAusencia;
  motivo?: string;
}

/** Edición de una ausencia (todo opcional; se manda lo que cambia). */
export interface CuerpoActualizarAusenciaRota {
  tipo?: TipoAusencia;
  desde?: string;
  hasta?: string;
  motivo?: string;
}

/** Franja de un turno LEGACY: literal mañana / tarde / descanso. Se mantiene como
 * derivada en la respuesta para retrocompat con UI vieja; codigo nuevo usa
 * `franja_id` + `franja_nombre` (modelo "franjas por semana"). */
export type FranjaTurno = "matutino" | "vespertino" | "descanso" | string;

/**
 * Una franja de la semana (modelo "franjas por semana" / Mundial). Cada lunes tiene
 * sus propias franjas (nombre libre, rangos `HH:MM`, solapes permitidos, soporte a
 * franjas que cruzan medianoche con `fin <= inicio`). Una franja con `es_descanso=true`
 * marca un turno explicito de "no laboral" (la persona no trabaja ese día); no cubre
 * ningún evento en la vista de cobertura.
 */
export interface FranjaSemana {
  id: string;
  /** Lunes ISO (AAAA-MM-DD) de la semana a la que pertenece. */
  lunes: string;
  nombre: string;
  /** "HH:MM" inclusivo. */
  inicio: string;
  /** "HH:MM" exclusivo. Si `fin <= inicio`, cruza medianoche. Para franjas de
   * descanso suele ser "00:00" (decorativo: ni cubren eventos). */
  fin: string;
  /** Orden ascendente en la rejilla (la franja Descanso usa 999 por convencion). */
  orden: number;
  /** Si `true`, esta franja NO es laboral: el turno marca "descanso explicito". */
  es_descanso: boolean;
  /** GRID POR MARCA: id canónico de la marca (rejilla) dueña de esta columna ("" = sin marca). */
  marca: string;
  /** Nombre legible de la marca (derivado del catálogo; "" si sin marca). */
  marca_nombre: string;
}

/**
 * Un turno: una persona × un día × una franja. NO está ligado a un evento — un turno
 * es un horario. La cobertura se calcula DERIVADA: para cada evento, qué turnos lo
 * cubren via las franjas vivas de la semana activas a su hora (UNION si solapan).
 */
export interface TurnoRota {
  id: string;
  /** Lunes ISO de la semana. */
  semana: string;
  /** ISO (AAAA-MM-DD). */
  fecha: string;
  miembro_id: string;
  miembro_nombre: string;
  /** Modelo nuevo: id de `FranjaSemana` viva (UNIQUE por semana). */
  franja_id: string;
  /** Nombre legible de la franja (lo emite el backend para evitar joins en el cliente). */
  franja_nombre: string;
  /** Retrocompat: literal `matutino`/`vespertino`/`descanso` derivado del nombre de la
   * franja para UI vieja. Codigo nuevo lee `franja_id`/`franja_nombre`. */
  franja: FranjaTurno;
  estado: EstadoTurnoRota;
  /** Cobertura forzada que rompe la rotación de sábados (la decide el coordinador de la rota). */
  override: boolean;
  motivo: string;
  /** Reporte de fin de turno: qué queda pendiente para el siguiente. */
  nota_relevo: string;
  es_sabado: boolean;
  /** GRID POR MARCA: rejilla (marca) a la que pertenece el turno; la UI lo etiqueta en "Todas". */
  marca: string;
  marca_nombre: string;
}

/** La rota (horario) de una semana: turnos + rango + si está publicada. */
export interface RotaSemana {
  /** Lunes ISO. */
  lunes: string;
  inicio: string;
  fin: string;
  /** Las 7 fechas ISO (lunes->domingo) de la semana. */
  dias: string[];
  turnos: TurnoRota[];
  /** Franjas vivas de la semana (modelo "franjas por semana"). El backend siembra
   * por defecto Mañana/Tarde/Descanso si la semana esta vacia. */
  franjas: FranjaSemana[];
  /** `true` => todos los turnos aprobados (publicado al equipo). */
  aprobada: boolean;
  total: number;
  /** Mensaje de confirmación (p. ej. tras aprobar). */
  mensaje?: string;
}

/** Respuesta de `GET /api/rota/semana/{lunes}/franjas`. */
export interface RespuestaFranjasSemana {
  franjas: FranjaSemana[];
}

/** Cuerpo de `POST /api/rota/semana/{lunes}/franjas`. */
export interface CuerpoCrearFranjaSemana {
  nombre: string;
  /** "HH:MM". */
  inicio: string;
  /** "HH:MM". */
  fin: string;
  orden?: number;
  es_descanso?: boolean;
}

/** Cuerpo de `PATCH /api/rota/franjas/{id}`. `es_descanso` NO se edita despues de crear. */
export interface CuerpoActualizarFranjaSemana {
  nombre?: string;
  inicio?: string;
  fin?: string;
  orden?: number;
}

export interface CuerpoAprobarRota {
  /** Lunes (o cualquier día) de la semana a aprobar. */
  lunes: string;
  /** GRID POR MARCA: marca concreta cuya rejilla se aprueba/despublica (no "Todas"). */
  marca: string;
}

/**
 * Cuerpo `POST /api/rota/turnos`: crea un turno (persona × día × franja_id).
 * `lunes` opcional: si falta, la semana se deriva del lunes que contiene `fecha`.
 */
export interface CuerpoCrearTurnoRota {
  /** Lunes ISO de la semana; opcional (se deriva de `fecha`). */
  lunes?: string;
  fecha: string;
  miembro_id: string;
  /** Id de la franja viva de la semana (modelo "franjas por semana"). */
  franja_id: string;
  override?: boolean;
  motivo?: string;
  nota_relevo?: string;
  estado?: EstadoTurnoRota;
}

/** Edición parcial de un turno (todo opcional; se manda lo que cambia). */
export interface CuerpoActualizarTurnoRota {
  fecha?: string;
  miembro_id?: string;
  franja_id?: string;
  override?: boolean;
  motivo?: string;
  nota_relevo?: string;
  estado?: EstadoTurnoRota;
}

export interface RespuestaTurnoRota {
  turno: TurnoRota;
}

/** "Mis turnos": la rota + los turnos del usuario actual en esa semana. */
export interface MisTurnosRota extends RotaSemana {
  miembro_id: string;
  miembro_nombre: string;
  mis_turnos: TurnoRota[];
  /** Aviso si no hay sesión (token de mantenimiento). */
  aviso?: string;
}

// --- Cobertura DERIVADA (no persistida): para cada evento, qué turnos lo cubren

/** Un turno que cubre un evento. */
export interface TurnoCobertura {
  turno_id: string;
  miembro_id: string;
  miembro_nombre: string;
  /** Id de la franja viva que aplicaba a la hora del evento. */
  franja_id: string;
  /** Nombre legible de la franja (servido por el backend). */
  franja_nombre: string;
  override: boolean;
}

/** Un evento con su cobertura derivada (lista de turnos que lo cubren). */
export interface CoberturaEvento extends EventoRota {
  cobertura: TurnoCobertura[];
}

export interface RespuestaCoberturaSemana {
  /** Lunes ISO de la semana. */
  lunes: string;
  inicio: string;
  fin: string;
  /** Rangos de franja vigentes (cabecera del cálculo legado). */
  franjas_config: ConfigFranjas;
  /** Franjas vivas de la semana (modelo "franjas por semana"). */
  franjas: FranjaSemana[];
  /** Eventos de la semana (sin `no_cubrir`) con su cobertura derivada. */
  eventos: CoberturaEvento[];
}

export interface RespuestaCoberturaEvento {
  evento: CoberturaEvento;
  franjas_config: ConfigFranjas;
  /** Franjas vivas de la semana del evento. */
  franjas: FranjaSemana[];
}

// --- Coordinador por turno (ola "coord") -----------------------------------
//
// Cada celda del calendario (combinación fecha + franja_id) puede tener UN coordinador
// asignado. Los candidatos son usuarios con `puede_coordinar=true`. La coordinación es
// INDEPENDIENTE de los turnos de CM: cambiar el turno NO toca la coordinación.

/** Coordinador asignado a una celda (fecha, franja_id) del calendario. */
export interface CoordinacionTurno {
  fecha: string;
  franja_id: string;
  coordinador_id: string;
  /** Nombre legible resuelto por el backend (puede quedar vacío si el usuario desapareció). */
  coordinador_nombre: string;
  /** GRID POR MARCA: rejilla (marca) de la celda; la UI la etiqueta en "Todas". */
  marca: string;
  marca_nombre: string;
}

export interface RespuestaCoordinacionSemana {
  lunes: string;
  coordinacion: CoordinacionTurno[];
}

/** Cuerpo `PUT /api/rota/coordinacion`: UPSERT del coordinador en (fecha, franja_id). */
export interface CuerpoSetCoordinador {
  lunes: string;
  fecha: string;
  franja_id: string;
  coordinador_id: string;
}

/** Cuerpo `DELETE /api/rota/coordinacion`: borra el coordinador de la celda. */
export interface CuerpoQuitarCoordinador {
  fecha: string;
  franja_id: string;
}

/** Cuerpo `POST /api/rota/turnos/{id}/duplicar`: overrides opcionales del clon. */
export interface CuerpoDuplicarTurnoRota {
  fecha?: string;
  miembro_id?: string;
  franja_id?: string;
}

/** Cuerpo `POST /api/rota/turnos/lote`: crea N turnos en una sola petición. */
export interface CuerpoCrearTurnosLote {
  turnos: CuerpoCrearTurnoRota[];
}

export interface RespuestaCrearTurnosLote {
  creados: number;
  turnos: TurnoRota[];
}

// --- Solicitudes de cambio de turno entre compañeros (#175) ----------------
//
// Flujo: A (solicitante) crea -> B (destinatario) acepta/rechaza -> admin
// aprueba (ejecuta el swap sobre `rota_turnos_trabajo`) o rechaza. A puede
// cancelar mientras el estado no sea terminal. Estados terminales: `aplicado`,
// `rechazado`, `rechazado_admin`, `cancelado`.

/** Estados del ciclo de vida de una solicitud de cambio de turno. */
export type EstadoSwap =
  | "propuesto"
  | "aceptado"
  | "rechazado"
  | "aprobado"
  | "aplicado"
  | "rechazado_admin"
  | "cancelado";

/** Una solicitud de cambio de turno entre dos compañeros (snapshot de un swap).
 *
 * Tras el modelo "franjas por semana", los campos `franja_a`/`franja_b` ahora son
 * `franja_id` (id de la franja viva de la semana del turno), no literales. Nombre de
 * campo conservado por inercia (cambio de SEMANTICA del dato, no de columna). */
export interface SwapTurno {
  id: string;
  solicitante_id: string;
  solicitante_nombre: string;
  destinatario_id: string;
  destinatario_nombre: string;
  /** ISO (AAAA-MM-DD): día del turno del solicitante. */
  fecha_a: string;
  /** `franja_id` del turno del solicitante. */
  franja_a: string;
  /** Nombre legible de la franja del solicitante (lo emite el backend). Opcional: datos
   *  legacy traían solo el literal en `franja_a`, sin este campo. */
  franja_a_nombre?: string;
  /** ISO (AAAA-MM-DD): día del turno del destinatario. */
  fecha_b: string;
  /** `franja_id` del turno del destinatario. */
  franja_b: string;
  /** Nombre legible de la franja del destinatario (lo emite el backend). Opcional: datos
   *  legacy traían solo el literal en `franja_b`, sin este campo. */
  franja_b_nombre?: string;
  motivo: string;
  estado: EstadoSwap;
  respuesta_destinatario: string;
  respuesta_admin: string;
  /** Timestamp ISO de la creación. */
  creado: string;
  /** Timestamp ISO de la última actualización. */
  actualizado: string;
  /** Timestamp ISO cuando el destinatario aceptó/rechazó. "" si aún no. */
  decidido_destinatario: string;
  /** Timestamp ISO cuando el admin aprobó/rechazó. "" si aún no. */
  decidido_admin: string;
  /** Timestamp ISO cuando el swap se aplicó sobre el horario. "" si no. */
  aplicado: string;
  /** GRID POR MARCA: rejilla (marca) del swap; la UI la etiqueta en "Todas". */
  marca: string;
  marca_nombre: string;
}

/** Cuerpo de `POST /api/rota/swaps`: A pide un cambio con B. `franja_a`/`franja_b` son
 * `franja_id` reales (modelo "franjas por semana"). */
export interface CuerpoCrearSwap {
  destinatario_id: string;
  fecha_a: string;
  franja_a: string;
  fecha_b: string;
  franja_b: string;
  motivo?: string;
}

/** Cuerpo opcional para las transiciones (aceptar/rechazar/aprobar): nota libre. */
export interface CuerpoDecidirSwap {
  respuesta?: string;
}

/** Filtros combinables del listado `/api/rota/swaps`. */
export interface FiltrosSwaps {
  estado?: EstadoSwap;
  solicitante_id?: string;
  destinatario_id?: string;
  /** Si `true` y hay sesión, filtra a swaps donde el usuario es A o B. */
  mio?: boolean;
  /** GRID POR MARCA: acota a la rejilla de esa marca; ausente = todas. */
  marca?: string;
}

export interface RespuestaSwap {
  swap: SwapTurno;
}

export interface RespuestaSwaps {
  swaps: SwapTurno[];
}

/** Cuerpo `POST /api/rota/turnos/lote/borrar`. */
export interface CuerpoBorrarLoteIds {
  ids: string[];
}

/** Respuesta de los borrados en lote: cuántos se fueron y cuáles no existían. */
export interface RespuestaBorrarLote {
  borrados: number;
  no_encontrados: string[];
}

/** Cuerpo opcional `POST /api/rota/eventos/{id}/duplicar`. */
export interface CuerpoDuplicarEventoRota {
  fecha?: string;
  hora?: string;
  titulo?: string;
}

// --- Catálogo de programas (#150, PARRILLA 2026.xlsx) ----------------------
//
// Cada hoja EVERGREEN del Excel es un PROGRAMA ("Álvaro Fidalgo", "Real Oviedo",
// "MUNDIAL"...). Se cataloga con color y fechas; las piezas referencian POR NOMBRE
// (no por id) para que una pieza huérfana siga apareciendo con su texto. Renombrar
// hace cascada sobre `rota_piezas.programa` (transaccional).

/** Un programa/campaña del catálogo editorial. */
export interface ProgramaRota {
  id: string;
  nombre: string;
  descripcion: string;
  /** Color en formato libre (la UI suele usar hex `#RRGGBB`). */
  color: string;
  /** Fecha de inicio (ISO) o "" si es indefinido. */
  inicio: string;
  /** Fecha de fin (ISO) o "" si es indefinido / always-on. */
  fin: string;
  activo: boolean;
  creado: string;
  actualizado: string;
}

export interface RespuestaProgramasRota {
  programas: ProgramaRota[];
}

export interface RespuestaProgramaRota {
  programa: ProgramaRota;
}

/** Cuerpo `POST /api/rota/programas`. */
export interface CuerpoCrearProgramaRota {
  nombre: string;
  descripcion?: string;
  color?: string;
  inicio?: string;
  fin?: string;
  activo?: boolean;
}

/** Cuerpo `PATCH /api/rota/programas/{id}`: cualquier subconjunto editable. */
export interface CuerpoActualizarProgramaRota {
  nombre?: string;
  descripcion?: string;
  color?: string;
  inicio?: string;
  fin?: string;
  activo?: boolean;
}

// --- Configuración editorial de franjas (rangos horarios) ------------------

/** Rangos vigentes de las dos franjas de trabajo (los usa la cobertura derivada). */
export interface ConfigFranjas {
  matutino_inicio: string;
  matutino_fin: string;
  vespertino_inicio: string;
  vespertino_fin: string;
  actualizado?: string;
}

export interface RespuestaConfigFranjas {
  franjas: ConfigFranjas;
}

export interface CuerpoGuardarConfigFranjas {
  matutino_inicio: string;
  matutino_fin: string;
  vespertino_inicio: string;
  vespertino_fin: string;
}

/**
 * Cuerpo de `PATCH /api/rota/turnos/lote`: edita varios turnos a la vez.
 * Todos los campos del cambio son opcionales (al menos uno requerido).
 * `miembro_id=""` desasigna; el backend acepta vacío explícito.
 */
export interface CuerpoActualizarLoteTurnos {
  ids: string[];
  miembro_id?: string;
  franja_id?: string;
  /** Override de rotación de sábados; si falta y hay sábados que la requieren -> 409. */
  override?: boolean;
  motivo?: string;
  nota_relevo?: string;
}

export interface RespuestaActualizarLoteTurnos {
  actualizados: number;
  turnos: TurnoRota[];
}

/**
 * Cuerpo de `POST /api/rota/copiar-semana`: replica turnos de una semana en otra.
 * Simplificado tras ola back3: ya NO hay `alcance` (solo se copian turnos, los
 * eventos son por semana y no se duplican).
 */
export interface CuerpoCopiarSemana {
  de_lunes: string;
  a_lunes: string;
  /** Si `true`, primero borra los turnos existentes de `a_lunes`. */
  reemplazar?: boolean;
  /** GRID POR MARCA: marca concreta cuya rejilla se copia (no "Todas"). */
  marca: string;
}

export interface RespuestaCopiarSemana {
  copiados: number;
}

/** Carga del equipo: cuánto trabajo lleva cada persona esta semana. */
export interface CargaMiembroRota {
  miembro_id: string;
  nombre: string;
  /** Eventos de cobertura asignados al miembro esta semana. */
  eventos: number;
  /** Días distintos en que el miembro entra a trabajar (no descanso). */
  dias_trabajados: number;
  /** True si entra a trabajar el sábado o cubre un evento del sábado. */
  sabado: boolean;
  /** Días distintos con franja "descanso". */
  descansos: number;
}

export interface RespuestaCargaRota {
  lunes: string;
  miembros: CargaMiembroRota[];
}

// --- Importar documento a la parrilla (turnos + eventos) ---
//
// Flujo: el usuario sube un documento (PDF/imagen/docx/xlsx/txt) + la semana destino;
// un `claude -p` lo analiza en 2º plano y produce una PROPUESTA: un diff de operaciones
// que, al aceptarse, se mergea sobre el calendario real. La propuesta se SONDEA hasta que
// `estado != "generando"`; en estado `pendiente` se previsualiza superpuesta al calendario.

/** Estado del ciclo de vida de una propuesta de import. */
export type EstadoPropuestaParrilla =
  | "generando"
  | "pendiente"
  | "aplicada"
  | "descartada"
  | "error";

/** Crear un evento del calendario (verde = nuevo). */
export interface OperacionCrearEvento {
  tipo: "crear_evento";
  /** `true` si el server detectó un conflicto con el calendario actual (rojo). */
  conflicto: boolean;
  /** ISO (AAAA-MM-DD). */
  fecha: string;
  hora: string;
  titulo: string;
  contenido?: string;
  nota?: string;
  tipo_cobertura?: TipoCoberturaEvento;
  prioridad?: PrioridadEvento;
}

/** Crear un turno (persona × día × franja) (verde = nuevo). */
export interface OperacionCrearTurno {
  tipo: "crear_turno";
  conflicto: boolean;
  /** ISO (AAAA-MM-DD). */
  fecha: string;
  /**
   * NOMBRE de la franja (p. ej. "Mañana"/"Tarde"/"Descanso"), no su id: una propuesta
   * abarca muchas semanas y los `franja_id` son por-semana, así que el modelo emite el
   * nombre y la previsualización lo casa contra las filas-plantilla (normalizado).
   */
  franja: string;
  miembro_id: string;
  miembro_nombre: string;
  nota_relevo?: string;
  motivo?: string;
}

/** Forma de los valores `actual` de un `modificar_turno` (el "antes" de la fila).
 *  `franja` es el NOMBRE de la franja (no su id), por la misma razón multi-semana. */
export interface ActualTurnoPropuesta {
  fecha?: string;
  franja?: string;
  miembro_id?: string;
  miembro_nombre?: string;
  [k: string]: unknown;
}

/** Modificar un turno existente (ámbar = cambio). Trae los valores actuales de la fila. */
export interface OperacionModificarTurno {
  tipo: "modificar_turno";
  conflicto: boolean;
  turno_id: string;
  /** Campos a cambiar (parcial). */
  cambios: Partial<CuerpoActualizarTurnoRota> & Record<string, unknown>;
  /** Valores actuales de la fila referenciada (para mostrar el "antes").
   *  `franja` es el NOMBRE de la franja, no `franja_id` (placement multi-semana). */
  actual: ActualTurnoPropuesta;
}

/** Una operación propuesta del diff. El `tipo` discrimina la forma. */
export type OperacionPropuesta =
  | OperacionCrearEvento
  | OperacionCrearTurno
  | OperacionModificarTurno;

/** Una propuesta de import: el diff staged que produjo el `claude -p`. */
export interface PropuestaParrilla {
  id: string;
  estado: EstadoPropuestaParrilla;
  /** Lunes ISO de la semana destino. */
  semana: string;
  /** Resumen legible de lo que propone (lo emite el modelo). */
  resumen: string;
  /** Mensaje de error legible cuando `estado === "error"`. */
  error: string;
  operaciones: OperacionPropuesta[];
  /**
   * Rango que abarca la propuesta (puede cubrir muchas semanas, hasta un año). `semanas`
   * son los lunes ISO con cambios, ordenados ascendente; `desde`/`hasta` son ISO de la
   * primera/última fecha con operaciones; `total` es el nº de operaciones. Opcional:
   * propuestas legadas (de una sola semana) pueden no traerlo. */
  rango?: { desde: string; hasta: string; semanas: string[]; total: number };
  /** Id de la generación `claude -p` que la produjo (opcional). */
  gen_id?: string;
  /** Nombre del objeto en el almacén de media (uuid+ext; NO es el nombre original). Opcional. */
  doc_nombre?: string;
  /** Extensión/tipo del documento subido (p.ej. "pdf"). Opcional. */
  doc_tipo?: string;
  /** ISO de creación (para ordenar la lista de pendientes). Opcional. */
  creado?: string;
}

/** Respuesta de `POST /api/parrilla/importar`. */
export interface RespuestaImportarParrilla {
  propuesta_id: string;
  gen_id: string;
}

/** Respuesta de `GET /api/parrilla/propuestas`. */
export interface RespuestaPropuestasParrilla {
  propuestas: PropuestaParrilla[];
}

/**
 * Payload de un 409 al aplicar: el calendario cambió desde que se generó la propuesta.
 * Best-effort: solo nos importa mostrar el mensaje y que el usuario reabra/refresque.
 */
export interface ConflictoAplicarParrilla {
  /** El backend manda la clave `error`; `mensaje` se mantiene por compatibilidad. */
  mensaje?: string;
  error?: string;
  /** Operaciones que chocan con una celda ocupada / turno desaparecido. */
  conflictos?: OperacionPropuesta[];
  /** Errores de re-validación contra el estado vivo (índice + motivo). */
  errores?: { indice: number; error: string }[];
}
