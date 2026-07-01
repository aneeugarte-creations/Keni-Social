// Fragmento del cliente API: dominio «imagen». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";

// Opciones de EXPORT del editor (descarga con formato/calidad/escala). Sin opciones -> PNG a escala 1.
export interface OpcionesExport {
  formato?: "png" | "jpg";
  calidad?: number; // 1-100, solo aplica a jpg
  escala?: number; // 0.25-4
}

export const apiImagen = {
  // --- Editor profesional (Documento de capas) ---
  // Re-render server-side de un documento de capas a imagen (fidelidad exacta de fuentes/cover/
  // degradados). El `documento` se valida en el backend (`motores/estudio_imagen/documento.py`).
  // `bindings` (opcional): titular/pleca REAL de la pieza (`copy_in`/`etiqueta_default`) para que
  // las capas con `binding` rendericen el texto real en vez del de muestra. Sin pieza no se pasa.
  // `opciones` (opcional): formato/calidad/escala del export (def PNG a escala 1); el back valida.
  imagenRender: (
    documento: unknown,
    bindings?: Record<string, string>,
    opciones?: OpcionesExport,
  ) =>
    peticion<{ id: string; url: string }>("/imagen/render", {
      metodo: "POST",
      json: { documento, bindings, opciones },
      timeoutMs: 120_000,
    }),
  // Documento de capas editable derivado de la plantilla de una marca (punto de partida del editor).
  imagenPlantilla: (marca: string, formato: string, signal?: AbortSignal) =>
    peticion<{ documento: unknown }>(
      `/imagen/plantilla/${encodeURIComponent(marca)}/${encodeURIComponent(formato)}`,
      { signal },
    ),
  // Editor anclado a una pieza (historial/versionado): cargar el documento guardado de la pieza
  // y guardar (render + nueva versión + fija la imagen de la publicación). Cuando no hay versión
  // guardada, `plantilla` trae el documento EFECTIVO (el mismo que compone el feed) y `fotos` las
  // fotos por hueco de la pieza, para arrancar del documento real con su foto.
  imagenPieza: (publicacionId: string, piezaId: string, signal?: AbortSignal) =>
    peticion<{
      documento: unknown;
      versiones: number;
      bindings: Record<string, string>;
      plantilla: unknown | null;
      fotos: { objeto: string; foco: [number, number] | null; zoom: number }[];
    }>(
      `/imagen/pieza/${encodeURIComponent(publicacionId)}/${encodeURIComponent(piezaId)}`,
      { signal },
    ),
  imagenPiezaGuardar: (
    publicacionId: string,
    piezaId: string,
    documento: unknown,
    bindings?: Record<string, string>,
  ) =>
    peticion<{ id: string; url: string; version: number }>(
      `/imagen/pieza/${encodeURIComponent(publicacionId)}/${encodeURIComponent(piezaId)}`,
      { metodo: "POST", json: { documento, bindings }, timeoutMs: 120_000 },
    ),
  // Recorta el sujeto de un objeto de media (rembg server-side) y devuelve un objeto NUEVO: un
  // PNG con el fondo transparente. No muta el original; la capa de imagen cambia su `objeto` al id
  // devuelto. Puede tardar unos segundos (inferencia del modelo); 503 si el servidor no lo soporta.
  imagenQuitarFondo: (objeto: string) =>
    peticion<{ id: string; url: string }>("/imagen/quitar-fondo", {
      metodo: "POST",
      json: { objeto },
      timeoutMs: 120_000,
    }),

};
