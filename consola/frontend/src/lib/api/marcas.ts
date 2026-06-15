// Fragmento del cliente API: dominio «marcas» (dashboard en vivo).
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type { RespuestaMarcas } from "@/types";

export const apiMarcas = {
  // Foto en vivo de todas las marcas × redes × cuentas (totales + por marca).
  getMarcas: (signal?: AbortSignal) =>
    peticion<RespuestaMarcas>("/marcas", { signal }),
};
