// Fragmento del cliente API: dominio «stock» (fuentes de fotos de stock).
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
//
// Dos áreas, una misma regla de oro de `conexiones`: los SECRETOS no salen nunca al
// navegador; solo se reporta presencia/estado y, como mucho, una PISTA (`····last4`).
//   · Claves GLOBALES (Pexels/Pixabay): una por agencia, vale para todas las marcas;
//     se gestionan en Sistema → Proveedores.
//   · Toggles de fuentes por marca: en la subpágina de la etapa Stock (Contexto).
import { peticion, query } from "./_core";
import type {
  Agencia,
  CuerpoGuardarAgencia,
  CuerpoGuardarClaveStock,
  CuerpoGuardarFuentesStock,
  MarcaFuentesStock,
  RespuestaAgencias,
  RespuestaClaveStock,
  RespuestaProbarStock,
  RespuestaProveedoresStock,
} from "@/types";

export const apiStock = {
  // Estado GLOBAL de las claves de los proveedores de pago (Pexels/Pixabay).
  estadoProveedoresStock: (signal?: AbortSignal) =>
    peticion<RespuestaProveedoresStock>("/stock/proveedores", { signal }),
  // Estado de fuentes de UNA marca.
  estadoFuentesStockMarca: (marca: string, signal?: AbortSignal) =>
    peticion<MarcaFuentesStock>(`/stock/fuentes${query({ marca })}`, { signal }),
  // Fija qué proveedores se usan en la marca (lista vacía o todos = sin filtro).
  guardarFuentesStock: (marca: string, activas: string[]) =>
    peticion<MarcaFuentesStock>(`/stock/fuentes/${encodeURIComponent(marca)}`, {
      metodo: "PUT",
      json: { activas } satisfies CuerpoGuardarFuentesStock,
    }),
  // Guarda la API key GLOBAL (write-only) de un proveedor de pago.
  guardarClaveStock: (proveedor: string, apiKey: string) =>
    peticion<RespuestaClaveStock>("/stock/clave", {
      metodo: "PUT",
      json: { proveedor, api_key: apiKey } satisfies CuerpoGuardarClaveStock,
    }),
  // Borra la clave GLOBAL de un proveedor.
  eliminarClaveStock: (proveedor: string) =>
    peticion<RespuestaClaveStock>(`/stock/clave/${encodeURIComponent(proveedor)}`, {
      metodo: "DELETE",
    }),
  // Valida la clave GLOBAL guardada con una búsqueda barata. No expone la clave.
  probarClaveStock: (proveedor: string) =>
    peticion<RespuestaProbarStock>("/stock/probar", {
      metodo: "POST",
      json: { proveedor },
    }),

  // Estado (dirigido por metadatos) de las agencias AFP/Reuters: campos + presencia de secretos.
  estadoAgencias: (signal?: AbortSignal) =>
    peticion<RespuestaAgencias>("/stock/agencias", { signal }),
  // Guarda credenciales de una agencia (solo los campos enviados; un secreto vacío no se borra).
  guardarAgencia: (agencia: string, valores: Record<string, string>) =>
    peticion<Agencia>(`/stock/agencias/${encodeURIComponent(agencia)}`, {
      metodo: "PUT",
      json: { valores } satisfies CuerpoGuardarAgencia,
    }),
  // Valida en vivo las credenciales guardadas de una agencia. No expone secretos.
  probarAgencia: (agencia: string) =>
    peticion<RespuestaProbarStock>(`/stock/agencias/${encodeURIComponent(agencia)}/probar`, {
      metodo: "POST",
    }),
  // Limpia las credenciales de una agencia.
  eliminarAgencia: (agencia: string) =>
    peticion<Agencia>(`/stock/agencias/${encodeURIComponent(agencia)}`, {
      metodo: "DELETE",
    }),
};
