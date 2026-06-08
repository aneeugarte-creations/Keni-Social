// Fragmento del cliente API: dominio «algoritmos». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  CuerpoFuenteAlgoritmo,
  EstadoSugerenciaEditorial,
  FiltrosAlgoritmos,
  RespuestaABibliotecaAlgoritmo,
  RespuestaAlgoritmos,
  RespuestaAplicarSugerencia,
  RespuestaArchivarAlgoritmo,
  RespuestaDescartarSugerencia,
  RespuestaFuenteAlgoritmo,
  RespuestaMensaje,
  RespuestaRefrescarAlgoritmos,
  RespuestaSembrarAlgoritmos,
  RespuestaSugerenciasAlgoritmo,
} from "@/types";

export const apiAlgoritmos = {
  // --- Algoritmos (inteligencia de plataforma: cambios de algoritmo + tendencias) ---
  // Solo lectura + curación ligera. Las noticias ya vienen clasificadas/ordenadas por
  // importancia; refrescar ingiere los feeds; las fuentes se gestionan como el RSS.
  algoritmos: (filtros: FiltrosAlgoritmos = {}, signal?: AbortSignal) =>
    peticion<RespuestaAlgoritmos>(
      `/algoritmos${query({
        plataforma: filtros.plataforma,
        nivel: filtros.nivel,
        solo_cambios: filtros.solo_cambios ? "1" : undefined,
        incluir_archivadas: filtros.incluir_archivadas ? "1" : undefined,
        limite: filtros.limite?.toString(),
      })}`,
      { signal },
    ),
  refrescarAlgoritmos: (fuente?: string) =>
    peticion<RespuestaRefrescarAlgoritmos>("/algoritmos/refrescar", {
      metodo: "POST",
      json: fuente ? { fuente } : {},
    }),
  sembrarAlgoritmos: () =>
    peticion<RespuestaSembrarAlgoritmos>("/algoritmos/sembrar", { metodo: "POST" }),
  crearFuenteAlgoritmo: (cuerpo: CuerpoFuenteAlgoritmo) =>
    peticion<RespuestaFuenteAlgoritmo>("/algoritmos/fuentes", { metodo: "POST", json: cuerpo }),
  actualizarFuenteAlgoritmo: (id: string, cuerpo: CuerpoFuenteAlgoritmo) =>
    peticion<RespuestaFuenteAlgoritmo>(`/algoritmos/fuentes/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  borrarFuenteAlgoritmo: (id: string) =>
    peticion<RespuestaMensaje>(`/algoritmos/fuentes/${encodeURIComponent(id)}`, {
      metodo: "DELETE",
    }),
  algoritmoABiblioteca: (id: string) =>
    peticion<RespuestaABibliotecaAlgoritmo>(`/algoritmos/${encodeURIComponent(id)}/biblioteca`, {
      metodo: "POST",
    }),
  archivarAlgoritmo: (id: string, archivada = true) =>
    peticion<RespuestaArchivarAlgoritmo>(`/algoritmos/${encodeURIComponent(id)}/archivar`, {
      metodo: "POST",
      json: { archivada },
    }),

  // --- Sugerencias editoriales (digest diario: cambios a fichas/límites de plataforma) ---
  sugerenciasAlgoritmo: (estado?: EstadoSugerenciaEditorial, signal?: AbortSignal) =>
    peticion<RespuestaSugerenciasAlgoritmo>(
      `/algoritmos/sugerencias${query({ estado })}`,
      { signal },
    ),
  generarSugerenciasAlgoritmo: () =>
    peticion<RespuestaMensaje>("/algoritmos/sugerencias/generar", { metodo: "POST" }),
  aplicarSugerenciaAlgoritmo: (id: string) =>
    peticion<RespuestaAplicarSugerencia>(
      `/algoritmos/sugerencias/${encodeURIComponent(id)}/aplicar`,
      { metodo: "POST" },
    ),
  descartarSugerenciaAlgoritmo: (id: string) =>
    peticion<RespuestaDescartarSugerencia>(
      `/algoritmos/sugerencias/${encodeURIComponent(id)}/descartar`,
      { metodo: "POST" },
    ),

};
