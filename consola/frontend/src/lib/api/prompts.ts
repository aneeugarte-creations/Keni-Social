// Fragmento del cliente API: dominio «prompts». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  CuerpoCrearDocumento,
  CuerpoGuardarDocumento,
  CuerpoLanzarTexto,
  CuerpoPublicarTexto,
  CuerpoResolverSolicitud,
  RespuestaContextoInyectado,
  RespuestaTexto,
  RespuestaDocumento,
  RespuestaEditoriales,
  RespuestaGeneracion,
  RespuestaHistorialTexto,
  RespuestaMaquinaTexto,
  RespuestaMarcasTexto,
  RespuestaMensaje,
  RespuestaPapelera,
  RespuestaResolverSolicitud,
  RespuestaSolicitudesTexto,
  RespuestaSolicitudTexto,
  RespuestaVariablesTexto,
  ValidacionEditorial,
} from "@/types";

export const apiPrompts = {
  // --- Listado de documentos (prompts + línea editorial) ---
  prompts: (
    filtros?: {
      tipo?: string;
      carpeta?: string;
      q?: string;
      etiqueta?: string;
      marca?: string;
      clase?: string;
      pipeline?: string;
    },
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaTexto>(
      `/prompts${query({
        tipo: filtros?.tipo,
        carpeta: filtros?.carpeta,
        q: filtros?.q,
        etiqueta: filtros?.etiqueta,
        marca: filtros?.marca,
        clase: filtros?.clase,
        pipeline: filtros?.pipeline,
      })}`,
      { signal },
    ),
  crearDocumento: (cuerpo: CuerpoCrearDocumento) =>
    peticion<RespuestaDocumento>("/prompts", { metodo: "POST", json: cuerpo }),
  // El id es una ruta con barras (p. ej. `prompt/x/y`); el backend lo casa con `{doc_id:path}`,
  // así que NO se codifica (los segmentos son slugs seguros [a-z0-9-]).
  documento: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaDocumento>(`/prompts/${id}`, { signal }),
  guardarDocumento: (id: string, cuerpo: CuerpoGuardarDocumento) =>
    peticion<RespuestaDocumento>(`/prompts/${id}`, { metodo: "PUT", json: cuerpo }),
  eliminarDocumento: (id: string) =>
    peticion<RespuestaMensaje>(`/prompts/${id}`, { metodo: "DELETE" }),
  papeleraPrompts: (signal?: AbortSignal) =>
    peticion<RespuestaPapelera>("/prompts/papelera", { signal }),
  restaurarDocumento: (id: string) =>
    peticion<RespuestaDocumento>(`/prompts/papelera/${encodeURIComponent(id)}/restaurar`, {
      metodo: "POST",
    }),
  editorialesPrompts: (marca: string, pipeline?: string, signal?: AbortSignal) =>
    peticion<RespuestaEditoriales>(`/prompts/editoriales${query({ marca, pipeline })}`, { signal }),
  // --- Las tres máquinas (flujo GLOBAL de etapas en orden real de ejecución) ---
  maquinaPrompts: (signal?: AbortSignal) =>
    peticion<RespuestaMaquinaTexto>("/prompts/maquina", { signal }),
  /** Editoriales que un prompt INYECTA para una marca (pestaña «Contexto» del editor). */
  contextoInyectado: (id: string, marca?: string, signal?: AbortSignal) =>
    peticion<RespuestaContextoInyectado>(`/prompts/${id}/contexto${query({ marca })}`, { signal }),
  // --- Variables del catálogo (`{{NOMBRE}}` que la consola sustituye al inyectar) ---
  variablesPrompts: (signal?: AbortSignal) =>
    peticion<RespuestaVariablesTexto>("/prompts/variables", { signal }),
  // --- Publicación a producción (admin) y solicitudes (no admin) ---
  publicarPrompts: (id: string, cuerpo: CuerpoPublicarTexto) =>
    peticion<RespuestaDocumento>(`/prompts/${id}/publicar`, { metodo: "POST", json: cuerpo }),
  solicitarPublicacionPrompts: (id: string, cuerpo: CuerpoPublicarTexto) =>
    peticion<RespuestaSolicitudTexto>(`/prompts/${id}/solicitar`, { metodo: "POST", json: cuerpo }),
  solicitudesPrompts: (estado?: string, signal?: AbortSignal) =>
    peticion<RespuestaSolicitudesTexto>(`/prompts/solicitudes${query({ estado })}`, { signal }),
  aprobarSolicitudPrompts: (id: string, cuerpo: CuerpoResolverSolicitud = {}) =>
    peticion<RespuestaResolverSolicitud>(`/prompts/solicitudes/${encodeURIComponent(id)}/aprobar`, {
      metodo: "POST",
      json: cuerpo,
    }),
  rechazarSolicitudPrompts: (id: string, cuerpo: CuerpoResolverSolicitud = {}) =>
    peticion<RespuestaResolverSolicitud>(`/prompts/solicitudes/${encodeURIComponent(id)}/rechazar`, {
      metodo: "POST",
      json: cuerpo,
    }),
  // --- Versionado git: historial, una versión y rollback no destructivo ---
  historialPrompts: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaHistorialTexto>(`/prompts/${id}/historial`, { signal }),
  versionPrompts: (id: string, sha: string, signal?: AbortSignal) =>
    peticion<RespuestaDocumento>(`/prompts/${id}/version/${sha}`, { signal }),
  revertirPrompts: (id: string, sha: string) =>
    peticion<RespuestaDocumento>(`/prompts/${id}/revertir/${sha}`, { metodo: "POST" }),
  // Resetea el borrador al contenido publicado (descarta los cambios sin publicar).
  descartarPrompts: (id: string) =>
    peticion<RespuestaDocumento>(`/prompts/${id}/descartar`, { metodo: "POST" }),
  validacionPrompts: (marca: string, signal?: AbortSignal) =>
    peticion<ValidacionEditorial>(`/prompts/validacion${query({ marca })}`, { signal }),
  marcasPrompts: (signal?: AbortSignal) =>
    peticion<RespuestaMarcasTexto>("/prompts/marcas", { signal }),
  lanzarPrompts: (cuerpo: CuerpoLanzarTexto) =>
    peticion<RespuestaGeneracion>("/prompts/lanzar", { metodo: "POST", json: cuerpo }),
  lanzarPromptsArchivo: (
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
    return peticion<RespuestaGeneracion>("/prompts/lanzar-archivo", {
      metodo: "POST",
      form,
      timeoutMs: 120_000,
    });
  },

};
