// Fragmento del cliente API: dominio «audio» (gestor de transcripciones audio→texto + artefactos).
// El objeto compuesto vive en ./index.ts; aquí el fragmento + sus tipos.
import { peticion } from "./_core";

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

/** Un audio subido + su transcripción base (los artefactos cuelgan de él). */
export interface TranscripcionAudio {
  id: string;
  marca: string;
  marca_nombre: string;
  nombre: string;
  media_id: string;
  media_url: string;
  idioma: string;
  estado: EstadoTranscripcion;
  duracion_ms: number;
  segmentos: SegmentoAudio[];
  texto: string;
  error: string;
  creado: string;
  actualizado: string;
}

export type TipoArtefacto =
  | "srt"
  | "texto"
  | "limpio"
  | "resumen"
  | "preguntas"
  | "ideas"
  | "corregido";
export type FormatoArtefacto = "srt" | "txt" | "md";
export type EstadoArtefacto = "generando" | "listo" | "error";

/** Un artefacto de un audio: SRT, texto plano o un tratamiento de Claude. */
export interface ArtefactoAudio {
  id: string;
  transcripcion_id: string;
  tipo: TipoArtefacto;
  titulo: string;
  contenido: string;
  formato: FormatoArtefacto;
  estado: EstadoArtefacto;
  gen_id: string;
  error: string;
  creado: string;
  actualizado: string;
}

/** Tratamientos de Claude que se pueden lanzar a mano sobre un audio. */
export type TratamientoClaude = "limpio" | "resumen" | "preguntas" | "ideas";

const enc = encodeURIComponent;

export const apiAudio = {
  // --- Gestor de audio (audio→texto): whisper v3 turbo + artefactos (SRT + tratamientos) ---
  audio: {
    /** Lista los audios (sin filtro de marca por defecto: la herramienta los muestra todos). */
    transcripciones: (
      filtros: { marca?: string; estado?: EstadoTranscripcion } = {},
      signal?: AbortSignal,
    ) => {
      const q = new URLSearchParams();
      if (filtros.marca) q.set("marca", filtros.marca);
      if (filtros.estado) q.set("estado", filtros.estado);
      const qs = q.toString();
      return peticion<{ transcripciones: TranscripcionAudio[] }>(
        `/audio/transcripciones${qs ? `?${qs}` : ""}`,
        { signal },
      );
    },
    /** Detalle de un audio (`segmentos` ya parseados). */
    transcripcion: (id: string, signal?: AbortSignal) =>
      peticion<{ transcripcion: TranscripcionAudio }>(`/audio/transcripciones/${enc(id)}`, { signal }),
    /**
     * Sube un audio/vídeo (multipart `archivo` + `marca`, opc. `idioma`/`nombre`/`tratamientos[]`),
     * crea la fila y encola el ASR. Devuelve la transcripción + el `gen_id` a sondear.
     */
    crear: (form: FormData) =>
      peticion<{ transcripcion: TranscripcionAudio; gen_id: string }>("/audio/transcripciones", {
        metodo: "POST",
        form,
      }),
    /** Edita el audio base (nombre/idioma/estado/segmentos/texto). */
    guardar: (
      id: string,
      cambios: Partial<Pick<TranscripcionAudio, "texto" | "nombre" | "idioma" | "estado">> & {
        segmentos?: SegmentoAudio[];
      },
    ) =>
      peticion<{ transcripcion: TranscripcionAudio }>(`/audio/transcripciones/${enc(id)}`, {
        metodo: "PUT",
        json: cambios,
      }),
    /** Elimina un audio y sus artefactos. */
    eliminar: (id: string) =>
      peticion<void>(`/audio/transcripciones/${enc(id)}`, { metodo: "DELETE" }),
    /** Reintenta el ASR. Devuelve `{gen_id}`. */
    retranscribir: (id: string) =>
      peticion<{ gen_id: string }>(`/audio/transcripciones/${enc(id)}/transcribir`, {
        metodo: "POST",
      }),

    // --- Artefactos ---
    /** Artefactos de un audio (SRT primero). */
    artefactos: (transcripcionId: string, signal?: AbortSignal) =>
      peticion<{ artefactos: ArtefactoAudio[] }>(
        `/audio/transcripciones/${enc(transcripcionId)}/artefactos`,
        { signal },
      ),
    /** Lanza un tratamiento de Claude (limpio/resumen/preguntas/ideas) -> artefacto 'generando'. */
    crearArtefacto: (transcripcionId: string, tipo: TratamientoClaude) =>
      peticion<{ artefacto: ArtefactoAudio }>(
        `/audio/transcripciones/${enc(transcripcionId)}/artefacto`,
        { metodo: "POST", json: { tipo } },
      ),
    /** Un artefacto por id. */
    artefacto: (id: string, signal?: AbortSignal) =>
      peticion<{ artefacto: ArtefactoAudio }>(`/audio/artefactos/${enc(id)}`, { signal }),
    /** Edita el contenido/título de un artefacto (el SRT crudo no es editable). */
    guardarArtefacto: (id: string, cambios: { contenido?: string; titulo?: string }) =>
      peticion<{ artefacto: ArtefactoAudio }>(`/audio/artefactos/${enc(id)}`, {
        metodo: "PUT",
        json: cambios,
      }),
    /** Borra un artefacto. */
    eliminarArtefacto: (id: string) =>
      peticion<void>(`/audio/artefactos/${enc(id)}`, { metodo: "DELETE" }),
    /** Sobre un artefacto de 'preguntas', aplica respuestas -> nuevo artefacto 'corregido'. */
    corregir: (artefactoId: string, respuestas: string[]) =>
      peticion<{ artefacto: ArtefactoAudio }>(`/audio/artefactos/${enc(artefactoId)}/corregir`, {
        metodo: "POST",
        json: { respuestas },
      }),
  },
};
