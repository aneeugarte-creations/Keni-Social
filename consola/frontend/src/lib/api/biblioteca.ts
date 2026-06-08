// Fragmento del cliente API: dominio «biblioteca». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  CuerpoCrearDocumento,
  CuerpoGuardarDocumento,
  CuerpoLanzarBiblioteca,
  PreviewPipeline,
  RespuestaAreas,
  RespuestaBiblioteca,
  RespuestaDocumento,
  RespuestaEditoriales,
  RespuestaGeneracion,
  RespuestaHistorialBiblioteca,
  RespuestaMarcasBiblioteca,
  RespuestaMensaje,
  RespuestaPapelera,
  RespuestaPipelinesBiblioteca,
  ValidacionEditorial,
} from "@/types";

export const apiBiblioteca = {
  // --- Biblioteca de documentos (prompts + línea editorial) ---
  biblioteca: (
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
    peticion<RespuestaBiblioteca>(
      `/biblioteca${query({
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
    peticion<RespuestaDocumento>("/biblioteca", { metodo: "POST", json: cuerpo }),
  // El id es una ruta con barras (p. ej. `prompt/x/y`); el backend lo casa con `{doc_id:path}`,
  // así que NO se codifica (los segmentos son slugs seguros [a-z0-9-]).
  documento: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaDocumento>(`/biblioteca/${id}`, { signal }),
  guardarDocumento: (id: string, cuerpo: CuerpoGuardarDocumento) =>
    peticion<RespuestaDocumento>(`/biblioteca/${id}`, { metodo: "PUT", json: cuerpo }),
  eliminarDocumento: (id: string) =>
    peticion<RespuestaMensaje>(`/biblioteca/${id}`, { metodo: "DELETE" }),
  papeleraBiblioteca: (signal?: AbortSignal) =>
    peticion<RespuestaPapelera>("/biblioteca/papelera", { signal }),
  restaurarDocumento: (id: string) =>
    peticion<RespuestaDocumento>(`/biblioteca/papelera/${encodeURIComponent(id)}/restaurar`, {
      metodo: "POST",
    }),
  editorialesBiblioteca: (marca: string, pipeline?: string, signal?: AbortSignal) =>
    peticion<RespuestaEditoriales>(`/biblioteca/editoriales${query({ marca, pipeline })}`, { signal }),
  // --- Pipelines: registro + preview del prompt ensamblado (atribución) ---
  pipelinesBiblioteca: (signal?: AbortSignal) =>
    peticion<RespuestaPipelinesBiblioteca>("/biblioteca/pipelines", { signal }),
  previewPipeline: (pipeline: string, marca: string, contexto?: string, signal?: AbortSignal) =>
    peticion<PreviewPipeline>(
      `/biblioteca/pipelines/${pipeline}/preview${query({ marca, contexto })}`,
      { signal },
    ),
  // --- Versionado git: historial, una versión y rollback no destructivo ---
  historialBiblioteca: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaHistorialBiblioteca>(`/biblioteca/${id}/historial`, { signal }),
  versionBiblioteca: (id: string, sha: string, signal?: AbortSignal) =>
    peticion<RespuestaDocumento>(`/biblioteca/${id}/version/${sha}`, { signal }),
  revertirBiblioteca: (id: string, sha: string) =>
    peticion<RespuestaDocumento>(`/biblioteca/${id}/revertir/${sha}`, { metodo: "POST" }),
  validacionBiblioteca: (marca: string, signal?: AbortSignal) =>
    peticion<ValidacionEditorial>(`/biblioteca/validacion${query({ marca })}`, { signal }),
  areasBiblioteca: (signal?: AbortSignal) =>
    peticion<RespuestaAreas>("/biblioteca/areas", { signal }),
  marcasBiblioteca: (signal?: AbortSignal) =>
    peticion<RespuestaMarcasBiblioteca>("/biblioteca/marcas", { signal }),
  lanzarBiblioteca: (cuerpo: CuerpoLanzarBiblioteca) =>
    peticion<RespuestaGeneracion>("/biblioteca/lanzar", { metodo: "POST", json: cuerpo }),
  lanzarBibliotecaArchivo: (
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
    return peticion<RespuestaGeneracion>("/biblioteca/lanzar-archivo", {
      metodo: "POST",
      form,
      timeoutMs: 120_000,
    });
  },

};
