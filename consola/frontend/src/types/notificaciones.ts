// --- Webhooks salientes + eventos internos del tablero ---

/** Tipos de evento interno que un webhook puede escuchar (espejo de `dominio/eventos.TIPOS_EVENTO`). */
export type TipoEventoInterno =
  | "pieza.aprobada"
  | "pieza.publicada"
  | "contenido.vencido"
  // Fase 3 auto-operativa: alertas proactivas del barrido `alertas_rendimiento`.
  | "pieza.bajo_rendimiento";

/** Forma del payload del POST saliente: `generico` (evento crudo) | `slack` (`{text}`). */
export type FormatoWebhook = "generico" | "slack";

/** Una suscripción de webhook. El `secreto` NUNCA se expone: solo `tiene_secreto`. */
export interface Webhook {
  id: string;
  nombre: string;
  url: string;
  /** Eventos escuchados; lista vacía = escucha TODOS. */
  eventos: TipoEventoInterno[];
  formato: FormatoWebhook;
  /** True si tiene secreto (firma HMAC); el valor del secreto no se devuelve. */
  tiene_secreto: boolean;
  activo: boolean;
  /** Resultado de la última entrega (p.ej. "ok: HTTP 200" / "error: timeout"). */
  ultimo_estado: string;
  ultimo_en: string;
  autor_id: string;
  autor_nombre: string;
  creado: string;
  actualizado: string;
}

/** Un evento interno ya emitido (bitácora). */
export interface EventoInterno {
  id: string;
  tipo: TipoEventoInterno;
  publicacion_id: string;
  pieza_id: string;
  payload: Record<string, unknown>;
  creado: string;
}

export interface CatalogoWebhooks {
  eventos: TipoEventoInterno[];
  formatos: FormatoWebhook[];
}

export interface RespuestaWebhooks {
  webhooks: Webhook[];
  catalogo: CatalogoWebhooks;
  eventos_recientes: EventoInterno[];
}

export interface RespuestaWebhook {
  webhook: Webhook;
}

export interface CuerpoCrearWebhook {
  nombre?: string;
  url: string;
  eventos?: TipoEventoInterno[];
  formato?: FormatoWebhook;
  secreto?: string;
  activo?: boolean;
}

export interface CuerpoActualizarWebhook {
  nombre?: string;
  url?: string;
  eventos?: TipoEventoInterno[];
  formato?: FormatoWebhook;
  secreto?: string;
  activo?: boolean;
}

export interface RespuestaProbarWebhook {
  ok: boolean;
  estado: string;
}

// --- Notificaciones in-app (el "cajón" de la campana) ---

/** Tipo de notificación; clasifica el evento que la originó. */
export type TipoNotificacion =
  | "mencion"
  | "comentario"
  | "aprobacion"
  | "rechazo"
  | "pieza"
  // El manager te EMPUJÓ una pieza (la señal que retira el «te paso esto» del WhatsApp).
  | "asignacion"
  // Ciclo de vida de un CAMBIO DE TURNO (swap): te lo proponen, falta tu OK, o el desenlace.
  | "cambio_turno"
  // Una AUSENCIA dejó turnos sin cubrir: aviso al admin para resolver el descubierto.
  | "ausencia_descubierto";

/** Una notificación del buzón de un usuario sobre una pieza. */
export interface Notificacion {
  id: string;
  usuario_id: string;
  marca_id: string;
  tipo: TipoNotificacion;
  publicacion_id: string;
  pieza_id: string;
  actor_id: string;
  actor_nombre: string;
  /** Frase ya armada para la UI (p. ej. "la coordinadora de redes te mencionó en «…»"). */
  resumen: string;
  enlace: string;
  leida: boolean;
  creada: string;
}

export interface RespuestaNotificaciones {
  notificaciones: Notificacion[];
  no_leidas: number;
  total: number;
}

export interface RespuestaContadorNotificaciones {
  no_leidas: number;
}

/** Candidato para el autocompletado de menciones (@) en comentarios. */
export interface MencionCandidato {
  id: string;
  nombre: string;
  usuario: string;
}

export interface RespuestaMencionesCandidatos {
  usuarios: MencionCandidato[];
}

/** Tipo de alerta de rendimiento (subconjunto de eventos internos de la bitácora). */
export type TipoAlerta = "pieza.bajo_rendimiento";

/**
 * Una alerta de rendimiento leída de la bitácora (`GET /api/alertas`): aviso proactivo
 * que el daemon `alertas_rendimiento` emite sobre las piezas publicadas.
 */
export interface AlertaRendimiento {
  id: string;
  /** Uno de `TipoAlerta`; se deja `string` por tolerancia ante tipos nuevos del backend. */
  tipo: string;
  publicacion_id: string;
  pieza_id: string;
  /** Payload genérico del evento (`{evento, emitido_en, resumen, datos}`). */
  payload: {
    resumen?: string;
    datos?: Record<string, unknown>;
    [clave: string]: unknown;
  };
  creado: string;
}

/** Respuesta de `GET /api/alertas`. */
export interface RespuestaAlertas {
  alertas: AlertaRendimiento[];
}
