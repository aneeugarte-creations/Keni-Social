// Fragmento del cliente API: dominio «media». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  CosteMedioArte,
  CuerpoGenerarArte,
  CuerpoGenerarMedia,
  CuerpoGuardarArte,
  RespuestaArte,
  RespuestaArtes,
  RespuestaGenerarArte,
  RespuestaGeneracion,
  RespuestaMedia,
  RespuestaMensaje,
} from "@/types";

export const apiMedia = {
  // --- Media (imágenes) ---
  // `categoria` (opcional) = carpeta de destino en el almacén: `fotos` (def) para una foto de
  // pieza, `plantillas` para un asset del editor de plantillas. Así el bucket queda dividido por
  // tipo y se puede limpiar `fotos/` a mano sin tocar plantillas/logos reusables.
  subirMedia: (archivo: File, categoria?: "fotos" | "plantillas") => {
    const form = new FormData();
    form.set("archivo", archivo);
    if (categoria) form.set("categoria", categoria);
    return peticion<RespuestaMedia>("/media", { metodo: "POST", form, timeoutMs: 120_000 });
  },
  generarMedia: (cuerpo: CuerpoGenerarMedia) =>
    peticion<RespuestaGeneracion>("/media/generar", { metodo: "POST", json: cuerpo }),
  /** Ola F: sube un archivo de video a `POST /api/media/video` y devuelve `{id, url}`. */
  subirVideo: (archivo: File) => {
    const form = new FormData();
    form.set("archivo", archivo);
    return peticion<RespuestaMedia>("/media/video", { metodo: "POST", form, timeoutMs: 300_000 });
  },
  /** Descarga una imagen externa (p.ej. la original de un artículo RSS) al almacén y
   *  devuelve su `{id, url}` ya servible/publicable. */
  mediaDesdeUrl: (url: string) =>
    peticion<RespuestaMedia>("/media/desde-url", { metodo: "POST", json: { url } }),

  // --- Galería de artes (objetos de media catalogados para reutilizar) ---
  // Guardar un arte lo PROTEGE del GC de media huérfana y lo hace seleccionable por marca
  // desde el editor de imagen de una pieza. El `objeto` es UNIQUE: `guardarArte` es idempotente.
  listarArtes: (
    filtros: { marca?: string; tipo?: string; q?: string } = {},
    signal?: AbortSignal,
  ) => peticion<RespuestaArtes>(`/artes${query(filtros)}`, { signal }),
  guardarArte: (cuerpo: CuerpoGuardarArte) =>
    peticion<RespuestaArte>("/artes", { metodo: "POST", json: cuerpo }),
  borrarArte: (id: string, purgar = false) =>
    peticion<RespuestaMensaje>(
      `/artes/${encodeURIComponent(id)}${purgar ? "?purgar=1" : ""}`,
      { metodo: "DELETE" },
    ),

  // --- Lanzamiento manual de ARTE (genera N imágenes a mano para una marca) ---
  // Crea N generaciones de imagen y las ejecuta en 2.º plano; el front sondea cada
  // `GET /api/generaciones/{id}` y, al completarse, lee `resultado={id,url,modelo,coste_usd}`.
  generarArte: (cuerpo: CuerpoGenerarArte) =>
    peticion<RespuestaGenerarArte>("/artes/generar", { metodo: "POST", json: cuerpo }),
  // Coste medio por imagen (USD) para estimar el gasto ANTES de lanzar (`modelo` opcional).
  costeMedioArte: (modelo?: string, signal?: AbortSignal) =>
    peticion<CosteMedioArte>(`/artes/coste-medio${query({ modelo })}`, { signal }),

};
