// Fragmento del cliente API: dominio «algoritmos». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  CuerpoFuenteAlgoritmo,
  FiltrosAlgoritmos,
  RespuestaATextoAlgoritmo,
  RespuestaAlgoritmos,
  RespuestaArchivarAlgoritmo,
  RespuestaFuenteAlgoritmo,
  RespuestaMensaje,
  RespuestaRefrescarAlgoritmos,
  RespuestaSembrarAlgoritmos,
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
  algoritmoATexto: (id: string) =>
    peticion<RespuestaATextoAlgoritmo>(`/algoritmos/${encodeURIComponent(id)}/texto`, {
      metodo: "POST",
    }),
  archivarAlgoritmo: (id: string, archivada = true) =>
    peticion<RespuestaArchivarAlgoritmo>(`/algoritmos/${encodeURIComponent(id)}/archivar`, {
      metodo: "POST",
      json: { archivada },
    }),
};
