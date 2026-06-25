// Fragmento del cliente API: dominio «biblioteca» (galería de medios unificada). El índice es
// `catalogo_media` con su dimensión de carpeta (`fuente`: portal | originales | fotografias). El
// objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { descargar, peticion, query } from "./_core";
import type {
  CuerpoAdjuntarBiblioteca,
  CuerpoGuardarRemoto,
  FuenteBiblioteca,
  RespuestaBiblioteca,
  RespuestaCarpetasBiblioteca,
  RespuestaGuardarRemoto,
  RespuestaRafaga,
  RespuestaStock,
} from "@/types";

export const apiBiblioteca = {
  // Buscador GLOBAL: busca en `catalogo_media` por título + descripción + etiquetas (substring,
  // case-insensitive). Sin `fuente`/`grupo` cruza las tres carpetas; filtrable por marca.
  buscarBiblioteca: (
    filtros: { q?: string; fuente?: FuenteBiblioteca; marca?: string; grupo?: string } = {},
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaBiblioteca>(
      `/biblioteca${query({
        q: filtros.q,
        fuente: filtros.fuente,
        marca: filtros.marca,
        grupo: filtros.grupo,
      })}`,
      { signal },
    ),
  // Resumen por carpeta (fuente) y por grupo (conteos) para navegar las secciones.
  carpetasBiblioteca: (marca?: string, signal?: AbortSignal) =>
    peticion<RespuestaCarpetasBiblioteca>(`/biblioteca/carpetas${query({ marca })}`, { signal }),
  // Guarda en Fotografías una foto de un dispositivo conectado: pide el original por el túnel, lo
  // sube a S3 y cataloga la fila conservando las etiquetas del candidato. Devuelve el item.
  guardarRemoto: (cuerpo: CuerpoGuardarRemoto) =>
    peticion<RespuestaGuardarRemoto>("/biblioteca/guardar-remoto", { metodo: "POST", json: cuerpo }),
  // Descarga (attachment) el objeto S3 de un item de la biblioteca.
  descargarBiblioteca: (id: string) =>
    descargar(`/biblioteca/descargar/${encodeURIComponent(id)}`),
  // Adjunta un item de la biblioteca a una pieza (reusa el flujo de stock; deja la pieza publicable).
  adjuntarBiblioteca: (cuerpo: CuerpoAdjuntarBiblioteca) =>
    peticion<RespuestaStock>("/biblioteca/adjuntar", { metodo: "POST", json: cuerpo }),
  // Fotos del MISMO burst del keeper para navegar la ráfaga (por túnel; thumbs).
  rafagaPropio: (
    filtros: { galeria_id: string; archivo: string; marca?: string; dispositivo?: string },
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaRafaga>(
      `/artes/propio/rafaga${query({
        galeria_id: filtros.galeria_id,
        archivo: filtros.archivo,
        marca: filtros.marca,
        dispositivo: filtros.dispositivo,
      })}`,
      { signal },
    ),
};
