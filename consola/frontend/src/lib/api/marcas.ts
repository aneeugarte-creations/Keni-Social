// Fragmento del cliente API: dominio «marcas» (dashboard en vivo).
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type { RespuestaMarcas, RespuestaNumeros } from "@/types";

export const apiMarcas = {
  // Estado en vivo de todas las marcas × redes × cuentas (control de conexiones).
  // Rápido: solo estado, sin métricas (las métricas viven en Analíticas).
  getMarcas: (signal?: AbortSignal) =>
    peticion<RespuestaMarcas>("/marcas", { signal }),
  // Monitor de conteos por marca × red (seguidores/posts/posts-día) desde Postproxy.
  // Solo aparecen las cuentas conectadas en Postproxy.
  getMarcasNumeros: (signal?: AbortSignal) =>
    peticion<RespuestaNumeros>("/marcas/numeros", { signal }),
};
