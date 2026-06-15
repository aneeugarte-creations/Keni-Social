/**
 * Tests del diálogo de EXPORTACIÓN del editor, centrados en el HORNEADO de la foto de muestra:
 * el export es server-side (`api.imagenRender`) y la foto de muestra vive como dataURL en cliente,
 * así que el hueco de foto vacío saldría GRIS. Con la "Vista con muestra (foto)" activa, al descargar
 * se sube la foto de muestra y se hornea su objeto en el hueco para que el archivo sea WYSIWYG.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";

import { documentoVacio } from "./documento";
import { ExportarDialogo } from "./ExportarDialogo";
import { setFotoMuestra } from "./muestra";
import { crearStoreEditor } from "./store";

const FORMATO = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };
// 1×1 PNG válido (para que `dataUrlABlob`/atob no falle).
const FOTO_MUESTRA =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

function montar(muestraFoto: boolean) {
  const store = crearStoreEditor(documentoVacio(FORMATO, "claro-sports"));
  render(<ExportarDialogo store={store} muestraFoto={muestraFoto} />);
  return store;
}

function huecoFoto(doc: { capas: { tipo: string; es_foto?: boolean; objeto?: string }[] }) {
  return doc.capas.find((c) => c.tipo === "imagen" && c.es_foto);
}

describe("ExportarDialogo — horneado de la foto de muestra al descargar", () => {
  beforeEach(() => {
    // fetch + createObjectURL: la descarga (fetch del render → blob → <a download>) no debe tocar red.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, blob: async () => new Blob(["x"]) }) as unknown as Response),
    );
    URL.createObjectURL = vi.fn(() => "blob:fake");
    URL.revokeObjectURL = vi.fn();
    // El <a download> programático: en jsdom seguir su href lanza "Not implemented: navigation".
    // No nos interesa la navegación real (solo que se dispare), así que la silenciamos.
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    vi.spyOn(apiMod.api, "imagenRender").mockResolvedValue({ id: "out", url: "/api/media/out.png" });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    setFotoMuestra(""); // limpia la muestra (e invalida la caché del objeto subido) entre casos
  });

  it("con muestra activa y foto real, sube la foto y hornea su objeto en el hueco vacío", async () => {
    const subir = vi
      .spyOn(apiMod.api, "subirMedia")
      .mockResolvedValue({ id: "muestra-obj-1", url: "/api/media/muestra-obj-1.png" });
    setFotoMuestra(FOTO_MUESTRA);
    montar(true);

    fireEvent.click(screen.getByRole("button", { name: "Exportar" }));
    fireEvent.click(await screen.findByRole("button", { name: /Descargar/ }));

    await waitFor(() => expect(apiMod.api.imagenRender).toHaveBeenCalled());
    expect(subir).toHaveBeenCalledTimes(1);
    const docEnviado = vi.mocked(apiMod.api.imagenRender).mock.calls[0][0] as Parameters<
      typeof huecoFoto
    >[0];
    expect(huecoFoto(docEnviado)?.objeto).toBe("muestra-obj-1");
  });

  it("con la muestra DESACTIVADA no sube nada y exporta el documento tal cual (hueco vacío)", async () => {
    const subir = vi.spyOn(apiMod.api, "subirMedia");
    setFotoMuestra(FOTO_MUESTRA); // hay foto de muestra, pero el toggle está apagado
    montar(false);

    fireEvent.click(screen.getByRole("button", { name: "Exportar" }));
    fireEvent.click(await screen.findByRole("button", { name: /Descargar/ }));

    await waitFor(() => expect(apiMod.api.imagenRender).toHaveBeenCalled());
    expect(subir).not.toHaveBeenCalled();
    const docEnviado = vi.mocked(apiMod.api.imagenRender).mock.calls[0][0] as Parameters<
      typeof huecoFoto
    >[0];
    expect(huecoFoto(docEnviado)?.objeto).toBe("");
  });
});
