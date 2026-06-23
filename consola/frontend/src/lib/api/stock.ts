// Fragmento del cliente API: dominio «stock» (fuentes de fotos de stock por marca).
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
//
// Dos áreas, una misma regla de oro de `conexiones`: los SECRETOS no salen nunca al
// navegador; solo se reporta presencia/estado y, como mucho, una PISTA (`····last4`).
//   · Claves por marca (Pexels/Pixabay): se gestionan en Sistema → Proveedores.
//   · Toggles de fuentes por marca: en la subpágina de la etapa Stock (Contexto).
import { peticion, query } from "./_core";
import type {
  CuerpoGuardarClaveStock,
  CuerpoGuardarFuentesStock,
  MarcaFuentesStock,
  RespuestaClaveStock,
  RespuestaFuentesStock,
  RespuestaProbarStock,
} from "@/types";

export const apiStock = {
  // Estado de fuentes de TODAS las marcas (cada marca con sus 5 proveedores).
  estadoFuentesStock: (signal?: AbortSignal) =>
    peticion<RespuestaFuentesStock>("/stock/fuentes", { signal }),
  // Estado de fuentes de UNA marca.
  estadoFuentesStockMarca: (marca: string, signal?: AbortSignal) =>
    peticion<MarcaFuentesStock>(`/stock/fuentes${query({ marca })}`, { signal }),
  // Fija qué proveedores se usan en la marca (lista vacía o todos = sin filtro).
  guardarFuentesStock: (marca: string, activas: string[]) =>
    peticion<MarcaFuentesStock>(`/stock/fuentes/${encodeURIComponent(marca)}`, {
      metodo: "PUT",
      json: { activas } satisfies CuerpoGuardarFuentesStock,
    }),
  // Guarda la API key (write-only) de un proveedor de pago en una marca.
  guardarClaveStock: (marca: string, proveedor: string, apiKey: string) =>
    peticion<RespuestaClaveStock>(`/stock/clave/${encodeURIComponent(marca)}`, {
      metodo: "PUT",
      json: { proveedor, api_key: apiKey } satisfies CuerpoGuardarClaveStock,
    }),
  // Borra la clave de un proveedor en una marca.
  eliminarClaveStock: (marca: string, proveedor: string) =>
    peticion<RespuestaClaveStock>(
      `/stock/clave/${encodeURIComponent(marca)}/${encodeURIComponent(proveedor)}`,
      { metodo: "DELETE" },
    ),
  // Valida la clave GUARDADA con una búsqueda barata. No expone la clave.
  probarClaveStock: (marca: string, proveedor: string) =>
    peticion<RespuestaProbarStock>(`/stock/probar/${encodeURIComponent(marca)}`, {
      metodo: "POST",
      json: { proveedor },
    }),
};
