// Fragmento del cliente API: dominio «marcas» (vista única por marca × red).
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type { RespuestaMarcas } from "@/types";

export const apiMarcas = {
  // Vista única: por marca, sus redes (estado de conexión + números de Postproxy) y el
  // sumatorio. Solo tienen números las cuentas conectadas en Postproxy.
  getMarcas: (signal?: AbortSignal) =>
    peticion<RespuestaMarcas>("/marcas", { signal }),
};
