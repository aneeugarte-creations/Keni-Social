// Fragmento del cliente API: dominio «texto». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  CuerpoCrearDocumento,
  CuerpoGuardarDocumento,
  CuerpoLanzarTexto,
  CuerpoPublicarTexto,
  CuerpoResolverSolicitud,
  PreviewPipeline,
  RespuestaAreas,
  RespuestaTexto,
  RespuestaDocumento,
  RespuestaEditoriales,
  RespuestaGeneracion,
  RespuestaHistorialTexto,
  RespuestaMaquinaTexto,
  RespuestaMarcasTexto,
  RespuestaMensaje,
  RespuestaPapelera,
  RespuestaPipelinesTexto,
  RespuestaResolverSolicitud,
  RespuestaSolicitudesTexto,
  RespuestaSolicitudTexto,
  RespuestaVariablesTexto,
  ValidacionEditorial,
} from "@/types";

export const apiTexto = {
  // --- Texto de documentos (prompts + línea editorial) ---
  texto: (
    filtros?: {
      tipo?: string;
      carpeta?: string;
      q?: string;
      estado?: string;
      etiqueta?: string;
      marca?: string;
      clase?: string;
      pipeline?: string;
    },
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaTexto>(
      `/texto${query({
        tipo: filtros?.tipo,
        carpeta: filtros?.carpeta,
        q: filtros?.q,
        estado: filtros?.estado,
        etiqueta: filtros?.etiqueta,
        marca: filtros?.marca,
        clase: filtros?.clase,
        pipeline: filtros?.pipeline,
      })}`,
      { signal },
    ),
  crearDocumento: (cuerpo: CuerpoCrearDocumento) =>
    peticion<RespuestaDocumento>("/texto", { metodo: "POST", json: cuerpo }),
  // El id es una ruta con barras (p. ej. `prompt/x/y`); el backend lo casa con `{doc_id:path}`,
  // así que NO se codifica (los segmentos son slugs seguros [a-z0-9-]).
  documento: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaDocumento>(`/texto/${id}`, { signal }),
  guardarDocumento: (id: string, cuerpo: CuerpoGuardarDocumento) =>
    peticion<RespuestaDocumento>(`/texto/${id}`, { metodo: "PUT", json: cuerpo }),
  eliminarDocumento: (id: string) =>
    peticion<RespuestaMensaje>(`/texto/${id}`, { metodo: "DELETE" }),
  papeleraTexto: (signal?: AbortSignal) =>
    peticion<RespuestaPapelera>("/texto/papelera", { signal }),
  restaurarDocumento: (id: string) =>
    peticion<RespuestaDocumento>(`/texto/papelera/${encodeURIComponent(id)}/restaurar`, {
      metodo: "POST",
    }),
  editorialesTexto: (marca: string, pipeline?: string, signal?: AbortSignal) =>
    peticion<RespuestaEditoriales>(`/texto/editoriales${query({ marca, pipeline })}`, { signal }),
  // --- Pipelines: registro + preview del prompt ensamblado (atribución) ---
  pipelinesTexto: (signal?: AbortSignal) =>
    peticion<RespuestaPipelinesTexto>("/texto/pipelines", { signal }),
  previewPipeline: (pipeline: string, marca: string, contexto?: string, signal?: AbortSignal) =>
    peticion<PreviewPipeline>(
      `/texto/pipelines/${pipeline}/preview${query({ marca, contexto })}`,
      { signal },
    ),
  // --- Las tres máquinas (riel GLOBAL de etapas en orden real de ejecución) ---
  maquinaTexto: (signal?: AbortSignal) =>
    peticion<RespuestaMaquinaTexto>("/texto/maquina", { signal }),
  // --- Variables del catálogo (`{{NOMBRE}}` que la consola sustituye al inyectar) ---
  variablesTexto: (signal?: AbortSignal) =>
    peticion<RespuestaVariablesTexto>("/texto/variables", { signal }),
  // --- Publicación a producción (admin) y solicitudes (no admin) ---
  publicarTexto: (id: string, cuerpo: CuerpoPublicarTexto) =>
    peticion<RespuestaDocumento>(`/texto/${id}/publicar`, { metodo: "POST", json: cuerpo }),
  solicitarPublicacionTexto: (id: string, cuerpo: CuerpoPublicarTexto) =>
    peticion<RespuestaSolicitudTexto>(`/texto/${id}/solicitar`, { metodo: "POST", json: cuerpo }),
  solicitudesTexto: (estado?: string, signal?: AbortSignal) =>
    peticion<RespuestaSolicitudesTexto>(`/texto/solicitudes${query({ estado })}`, { signal }),
  aprobarSolicitudTexto: (id: string, cuerpo: CuerpoResolverSolicitud = {}) =>
    peticion<RespuestaResolverSolicitud>(`/texto/solicitudes/${encodeURIComponent(id)}/aprobar`, {
      metodo: "POST",
      json: cuerpo,
    }),
  rechazarSolicitudTexto: (id: string, cuerpo: CuerpoResolverSolicitud = {}) =>
    peticion<RespuestaResolverSolicitud>(`/texto/solicitudes/${encodeURIComponent(id)}/rechazar`, {
      metodo: "POST",
      json: cuerpo,
    }),
  // --- Versionado git: historial, una versión y rollback no destructivo ---
  historialTexto: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaHistorialTexto>(`/texto/${id}/historial`, { signal }),
  versionTexto: (id: string, sha: string, signal?: AbortSignal) =>
    peticion<RespuestaDocumento>(`/texto/${id}/version/${sha}`, { signal }),
  revertirTexto: (id: string, sha: string) =>
    peticion<RespuestaDocumento>(`/texto/${id}/revertir/${sha}`, { metodo: "POST" }),
  validacionTexto: (marca: string, signal?: AbortSignal) =>
    peticion<ValidacionEditorial>(`/texto/validacion${query({ marca })}`, { signal }),
  areasTexto: (signal?: AbortSignal) =>
    peticion<RespuestaAreas>("/texto/areas", { signal }),
  marcasTexto: (signal?: AbortSignal) =>
    peticion<RespuestaMarcasTexto>("/texto/marcas", { signal }),
  lanzarTexto: (cuerpo: CuerpoLanzarTexto) =>
    peticion<RespuestaGeneracion>("/texto/lanzar", { metodo: "POST", json: cuerpo }),
  lanzarTextoArchivo: (
    archivo: File,
    marca: string,
    opts: {
      prompt_id?: string;
      texto?: string;
      titulo?: string;
      adjuntos?: string[];
      redes?: string[];
    } = {},
  ) => {
    const form = new FormData();
    form.set("archivo", archivo);
    form.set("marca", marca);
    if (opts.prompt_id) form.set("prompt_id", opts.prompt_id);
    if (opts.texto) form.set("texto", opts.texto);
    if (opts.titulo) form.set("titulo", opts.titulo);
    for (const a of opts.adjuntos ?? []) form.append("adjuntos", a);
    for (const r of opts.redes ?? []) form.append("redes", r);
    return peticion<RespuestaGeneracion>("/texto/lanzar-archivo", {
      metodo: "POST",
      form,
      timeoutMs: 120_000,
    });
  },

};
