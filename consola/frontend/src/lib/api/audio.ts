// Fragmento del cliente API: dominio «audio» (gestor de transcripciones audio→texto).
// El objeto compuesto vive en ./index.ts; aquí el fragmento + sus tipos.
import { peticion, query } from "./_core";

/** Una palabra con sus tiempos (word-level; solo la usa el karaoke del motor de vídeo). */
export interface PalabraAudio {
  inicio_ms: number;
  fin_ms: number;
  texto: string;
}

/** Un segmento de la transcripción con sus timestamps (en milisegundos). */
export interface SegmentoAudio {
  inicio_ms: number;
  fin_ms: number;
  texto: string;
  palabras?: PalabraAudio[];
}

export type EstadoTranscripcion =
  | "pendiente"
  | "transcribiendo"
  | "transcrito"
  | "editado"
  | "error";

/** Una transcripción del gestor de audio (audio/vídeo → texto con timestamps). */
export interface TranscripcionAudio {
  id: string;
  marca: string;
  marca_nombre: string;
  nombre: string;
  media_id: string;
  /** URL para reproducir el audio/vídeo original (`/api/media/...`). */
  media_url: string;
  idioma: string;
  estado: EstadoTranscripcion;
  duracion_ms: number;
  segmentos: SegmentoAudio[];
  /** Transcripción plana / texto trabajado por los agentes. */
  texto: string;
  /** Resumen producido por el agente «Resumir» (opcional). */
  resumen: string;
  error: string;
  creado: string;
  actualizado: string;
}

/** Agentes de Claude que trabajan una transcripción. */
export type OperacionAgente = "limpiar" | "resumir" | "aclarar" | "corregir";

export const apiAudio = {
  // --- Gestor de audio (audio→texto): whisper.cpp v3 turbo + agentes de Claude ---
  // El ASR y los agentes se ENCOLAN (no-claude el ASR; claude los agentes) y se SONDEAN con
  // `useGeneracion` por su `gen_id`. El ASR escribe el resultado en la fila; el frontend recarga
  // la transcripción al completar. Los agentes devuelven su texto en `generacion` (salida/documento).
  audio: {
    /** Lista las transcripciones (filtros por `marca`/`estado`, recientes primero). */
    transcripciones: (
      filtros: { marca?: string; estado?: EstadoTranscripcion } = {},
      signal?: AbortSignal,
    ) =>
      peticion<{ transcripciones: TranscripcionAudio[] }>(
        `/audio/transcripciones${query({ marca: filtros.marca, estado: filtros.estado })}`,
        { signal },
      ),
    /** Detalle de una transcripción (`segmentos` ya parseados). */
    transcripcion: (id: string, signal?: AbortSignal) =>
      peticion<{ transcripcion: TranscripcionAudio }>(
        `/audio/transcripciones/${encodeURIComponent(id)}`,
        { signal },
      ),
    /**
     * Sube un audio/vídeo (multipart `archivo` + `marca`, opc. `idioma`/`nombre`), crea la fila y
     * encola el ASR. Devuelve la transcripción (estado 'pendiente') y el `gen_id` a sondear.
     */
    crear: (form: FormData) =>
      peticion<{ transcripcion: TranscripcionAudio; gen_id: string }>("/audio/transcripciones", {
        metodo: "POST",
        form,
      }),
    /** Edita la transcripción (segmentos/texto/estado/resumen/nombre/idioma). */
    guardar: (
      id: string,
      cambios: Partial<
        Pick<TranscripcionAudio, "texto" | "resumen" | "nombre" | "idioma" | "estado">
      > & { segmentos?: SegmentoAudio[] },
    ) =>
      peticion<{ transcripcion: TranscripcionAudio }>(
        `/audio/transcripciones/${encodeURIComponent(id)}`,
        { metodo: "PUT", json: cambios },
      ),
    /** Elimina una transcripción (el media content-addressed se conserva). */
    eliminar: (id: string) =>
      peticion<void>(`/audio/transcripciones/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
    /** Reintenta el ASR de una transcripción. Devuelve `{gen_id}` (sondear con `useGeneracion`). */
    retranscribir: (id: string) =>
      peticion<{ gen_id: string }>(
        `/audio/transcripciones/${encodeURIComponent(id)}/transcribir`,
        { metodo: "POST" },
      ),
    /**
     * Lanza un agente de Claude sobre la transcripción. `respuestas` (opcional) alimenta a
     * «corregir» con las respuestas del equipo a las dudas de «aclarar». Devuelve `{gen_id}`.
     */
    agente: (id: string, operacion: OperacionAgente, respuestas?: string[]) =>
      peticion<{ gen_id: string; operacion: OperacionAgente }>(
        `/audio/transcripciones/${encodeURIComponent(id)}/agente`,
        { metodo: "POST", json: { operacion, respuestas } },
      ),
  },
};
