// Fragmento del cliente API: dominio «video». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  ComposicionResumen,
  ComposicionVideo,
  EstadoComposicion,
  EstadoSubtitulos,
  PresetFormatoVideo,
  SegmentoSub,
  Subtitulo,
} from "../video";

export const apiVideo = {
  // --- Estudio de video (composición + render FFmpeg + subtítulos ASR) ---
  // CONTRATO: docs/maquina-contenido/G-video-engine.md. El documento de composición se valida
  // en el backend (`keni_shared.video.validar_composicion`). El render y la transcripción se
  // ENCOLAN como jobs de proceso (no-claude) y se SONDEAN con `useGeneracion` (tipos
  // "render-video" / "transcribir"); al completar dan `resultado` `{media_id, url}`.
  video: {
    /** Presets de formato + zonas seguras por preset (`GET /api/video/formatos`). */
    formatos: (signal?: AbortSignal) =>
      peticion<{ formatos: PresetFormatoVideo[] }>("/video/formatos", { signal }),
    /**
     * Lista composiciones (filtro por `marca` y/o `contenido_id`). El `documento` viene YA
     * parseado a objeto. Sirve al GESTOR de composiciones y al puente find-or-create por pieza.
     */
    listarComposiciones: (
      filtros: { marca?: string; contenido_id?: string } = {},
      signal?: AbortSignal,
    ) =>
      peticion<{ composiciones: ComposicionResumen[] }>(
        `/video/composiciones${query({ marca: filtros.marca, contenido_id: filtros.contenido_id })}`,
        { signal },
      ),
    /**
     * Crea la composición. `marca` es obligatoria (del catálogo). `titulo`/`estado` opcionales
     * (default backend "" / "borrador"). Devuelve `{id}`.
     */
    crearComposicion: (cuerpo: {
      marca: string;
      documento: ComposicionVideo;
      contenido_id?: string;
      titulo?: string;
      estado?: EstadoComposicion;
    }) => peticion<{ id: string }>("/video/composiciones", { metodo: "POST", json: cuerpo }),
    composicion: (id: string, signal?: AbortSignal) =>
      peticion<{
        composicion: {
          id: string;
          documento: ComposicionVideo;
          titulo: string;
          estado: EstadoComposicion;
        };
      }>(`/video/composiciones/${encodeURIComponent(id)}`, { signal }),
    /** Guarda el `documento` (autosave). Reusa el PUT (que admite documento/titulo/estado). */
    guardarComposicion: (id: string, documento: ComposicionVideo) =>
      peticion<{ composicion: { id: string; documento: ComposicionVideo } }>(
        `/video/composiciones/${encodeURIComponent(id)}`,
        { metodo: "PUT", json: { documento } },
      ),
    /**
     * Actualiza SÓLO metadatos del borrador (titulo/estado) sin reenviar el documento. Permite
     * renombrar o cambiar de estado (borrador↔listo). Todos los campos son opcionales.
     */
    actualizarComposicion: (
      id: string,
      cambios: { titulo?: string; estado?: EstadoComposicion },
    ) =>
      peticion<{ composicion: { id: string; titulo: string; estado: EstadoComposicion } }>(
        `/video/composiciones/${encodeURIComponent(id)}`,
        { metodo: "PUT", json: cambios },
      ),
    /** Renombra un borrador (azúcar sobre `actualizarComposicion`). */
    renombrarComposicion: (id: string, titulo: string) =>
      peticion<{ composicion: { id: string; titulo: string; estado: EstadoComposicion } }>(
        `/video/composiciones/${encodeURIComponent(id)}`,
        { metodo: "PUT", json: { titulo } },
      ),
    /** Elimina una composición/borrador. `{ok:true}` / 404. */
    eliminarComposicion: (id: string) =>
      peticion<{ ok: boolean }>(`/video/composiciones/${encodeURIComponent(id)}`, {
        metodo: "DELETE",
      }),
    /** Encola el render FFmpeg. Devuelve `{gen_id}` (sondear con `api.generacion`). */
    render: (id: string) =>
      peticion<{ gen_id: string }>(`/video/composiciones/${encodeURIComponent(id)}/render`, {
        metodo: "POST",
      }),
    /**
     * Encola el ASR (word-level) del `media_id` dado. Crea la fila de subtítulos si no existe.
     * Devuelve `{gen_id, subtitulo_id}` (sondear con `api.generacion`).
     */
    transcribir: (id: string, mediaId: string, idioma = "es-MX") =>
      peticion<{ gen_id: string; subtitulo_id: string }>(
        `/video/composiciones/${encodeURIComponent(id)}/transcribir`,
        { metodo: "POST", json: { media_id: mediaId, idioma } },
      ),
    /** Fila de subtítulos de una composición (`null` si aún no hay). */
    subtitulosDe: (composicionId: string, signal?: AbortSignal) =>
      peticion<{ subtitulo: Subtitulo | null }>(
        `/video/subtitulos${query({ composicion_id: composicionId })}`,
        { signal },
      ),
    /** Guarda la corrección humana de los segmentos. `estado` opcional ("editado"/"listo"). */
    guardarSubtitulo: (
      id: string,
      cuerpo: { segmentos: SegmentoSub[]; estado?: EstadoSubtitulos },
    ) =>
      peticion<{ subtitulo: Subtitulo }>(`/video/subtitulos/${encodeURIComponent(id)}`, {
        metodo: "PUT",
        json: cuerpo,
      }),
  },

};
