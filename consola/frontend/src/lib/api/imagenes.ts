// Fragmento del cliente API: dominio «imagenes». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoImagenesComponer,
  CuerpoImagenesEditar,
  CuerpoImagenesExpandir,
  CuerpoImagenesGenerar,
  CuerpoImagenesRetocar,
  CuerpoImagenesRevisar,
  RespuestaGeneracion,
  RespuestaGeneraciones,
} from "@/types";

export const apiImagenes = {
  // --- Estudio de imagen (generar variantes · editar determinista · expandir generativo) ---
  // Cada endpoint responde de inmediato con registro(s) de generación (tipo "imagen") que se
  // SONDEAN con `useGeneracion` (GET /api/generaciones/{id}); al completar dan `resultado`
  // con `{id, url}`. `imagenesGenerar` devuelve UNA generación por variante.
  imagenesGenerar: (cuerpo: CuerpoImagenesGenerar) =>
    peticion<RespuestaGeneraciones>("/imagenes/generar", { metodo: "POST", json: cuerpo }),
  imagenesEditar: (cuerpo: CuerpoImagenesEditar) =>
    peticion<RespuestaGeneracion>("/imagenes/editar", { metodo: "POST", json: cuerpo }),
  imagenesExpandir: (cuerpo: CuerpoImagenesExpandir) =>
    peticion<RespuestaGeneracion>("/imagenes/expandir", { metodo: "POST", json: cuerpo }),
  // Retoque generativo por instrucción ("oscurece el cielo"): reinterpreta toda la imagen.
  // Distinto de expandir (outpainting fiel). Generativo (con coste); se SONDEA con
  // `useGeneracion` y completa con `resultado` `{id, url}`.
  imagenesRetocar: (cuerpo: CuerpoImagenesRetocar) =>
    peticion<RespuestaGeneracion>("/imagenes/retocar", { metodo: "POST", json: cuerpo }),
  // Revisión legal/editorial de una imagen (gate humano, no bloquea publicar): job
  // "qa-editorial" que se SONDEA con `useGeneracion`; el checklist ✅/⚠️/❌ llega en vivo
  // en `generacion.salida`.
  imagenesRevisar: (cuerpo: CuerpoImagenesRevisar) =>
    peticion<RespuestaGeneracion>("/imagenes/revisar", { metodo: "POST", json: cuerpo }),
  // Componer/estampar la plantilla de marca (logo/pleca/titular) sobre una imagen:
  // composición DETERMINISTA en el backend. Responde con una generación de imagen que
  // se SONDEA con `useGeneracion` y completa con `resultado` `{id, url}` (igual que editar).
  imagenesComponer: (cuerpo: CuerpoImagenesComponer) =>
    peticion<RespuestaGeneracion>("/imagenes/componer", { metodo: "POST", json: cuerpo }),

};
