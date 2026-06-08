// Fragmento del cliente API: dominio «editor». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";

export const apiEditor = {
  // --- Editor profesional (Documento de capas) ---
  // Re-render server-side de un documento de capas a PNG (fidelidad exacta de fuentes/cover/
  // degradados). El `documento` se valida en el backend (`motores/estudio_imagen/documento.py`).
  // `bindings` (opcional): titular/pleca REAL de la pieza (`copy_in`/`etiqueta_default`) para que
  // las capas con `binding` rendericen el texto real en vez del de muestra. Sin pieza no se pasa.
  editorRender: (documento: unknown, bindings?: Record<string, string>) =>
    peticion<{ id: string; url: string }>("/editor/render", {
      metodo: "POST",
      json: { documento, bindings },
      timeoutMs: 120_000,
    }),
  // Documento de capas editable derivado de la plantilla de una marca (punto de partida del editor).
  editorPlantilla: (marca: string, formato: string, signal?: AbortSignal) =>
    peticion<{ documento: unknown }>(
      `/editor/plantilla/${encodeURIComponent(marca)}/${encodeURIComponent(formato)}`,
      { signal },
    ),
  // Editor anclado a una pieza (historial/versionado): cargar el documento guardado de la pieza
  // y guardar (render + nueva versión + fija la imagen de la publicación).
  editorPieza: (contenidoId: string, plataformaId: string, signal?: AbortSignal) =>
    peticion<{ documento: unknown; versiones: number; bindings: Record<string, string> }>(
      `/editor/pieza/${encodeURIComponent(contenidoId)}/${encodeURIComponent(plataformaId)}`,
      { signal },
    ),
  editorPiezaGuardar: (
    contenidoId: string,
    plataformaId: string,
    documento: unknown,
    bindings?: Record<string, string>,
  ) =>
    peticion<{ id: string; url: string; version: number }>(
      `/editor/pieza/${encodeURIComponent(contenidoId)}/${encodeURIComponent(plataformaId)}`,
      { metodo: "POST", json: { documento, bindings }, timeoutMs: 120_000 },
    ),

};
