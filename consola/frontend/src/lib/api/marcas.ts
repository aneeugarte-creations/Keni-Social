// Fragmento del cliente API: dominio «marcas» (vista única + CRUD del catálogo).
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoCrearMarca,
  CuerpoEditarMarca,
  RespuestaCatalogoMarcas,
  RespuestaMarcaCatalogo,
  RespuestaMarcas,
  RespuestaMensaje,
} from "@/types";

export const apiMarcas = {
  // Vista única: por marca, sus redes (estado de conexión + números de Postproxy) y el
  // sumatorio. Solo tienen números las cuentas conectadas en Postproxy.
  getMarcas: (signal?: AbortSignal) =>
    peticion<RespuestaMarcas>("/marcas", { signal }),

  // --- CRUD del catálogo de marcas (fuente única editable) ---
  catalogoMarcas: (signal?: AbortSignal) =>
    peticion<RespuestaCatalogoMarcas>("/marcas/catalogo", { signal }),
  crearMarca: (cuerpo: CuerpoCrearMarca) =>
    peticion<RespuestaMarcaCatalogo>("/marcas/catalogo", { metodo: "POST", json: cuerpo }),
  editarMarca: (id: string, cuerpo: CuerpoEditarMarca) =>
    peticion<RespuestaMarcaCatalogo>(`/marcas/catalogo/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  borrarMarca: (id: string) =>
    peticion<RespuestaMensaje>(`/marcas/catalogo/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
};
