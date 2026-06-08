// Fragmento del cliente API: dominio «termometro». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoGenerarTermometro,
  CuerpoGuardarTermometro,
  RespuestaConfigTermometro,
  RespuestaGeneracion,
  RespuestaTermometro,
} from "@/types";

export const apiTermometro = {
  // --- Termómetro mundial ---
  termometro: (signal?: AbortSignal) => peticion<RespuestaTermometro>("/termometro", { signal }),
  guardarTermometro: (cuerpo: CuerpoGuardarTermometro) =>
    peticion<RespuestaConfigTermometro>("/termometro/config", { metodo: "PUT", json: cuerpo }),
  generarTermometro: (cuerpo: CuerpoGenerarTermometro) =>
    peticion<RespuestaGeneracion>("/termometro/generar", { metodo: "POST", json: cuerpo }),

};
