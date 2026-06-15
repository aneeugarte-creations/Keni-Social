/**
 * Tests del diálogo de EXPORTACIÓN del editor, centrados en el HORNEADO de lo que se ve (WYSIWYG):
 * el export es server-side (`api.imagenRender`) y tanto la foto de muestra (dataURL en cliente) como
 * el texto de los titulares/plecas con `binding` (que sin pieza llega vacío) saldrían MAL —gris la
 * foto, vacío el texto—. Al descargar:
 *   · la foto de muestra se sube y se hornea en el hueco de foto vacío (si "Vista con muestra (foto)").
 *   · el texto visible (escrito por el equipo, o el copy de muestra si ese modo está activo) se
 *     congela en la capa y se le quita el binding, para que el render lo pinte literal.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";

import type { Capa } from "./documento";
import { documentoVacio, nuevaCapaTexto } from "./documento";
import { ExportarDialogo } from "./ExportarDialogo";
import { setFotoMuestra, setTitularMuestra, TITULAR_MUESTRA_DEFECTO } from "./muestra";
import { crearStoreEditor } from "./store";

const FORMATO = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };
// 1×1 PNG válido (para que `dataUrlABlob`/atob no falle).
const FOTO_MUESTRA =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

type CapaLite = { tipo: string; es_foto?: boolean; objeto?: string; binding?: string | null; texto?: string };
type DocLite = { capas: CapaLite[] };

function montar(opts: {
  muestraFoto?: boolean;
  muestraCopy?: boolean;
  bindings?: Record<string, string>;
  capas?: Capa[];
} = {}) {
  const base = documentoVacio(FORMATO, "claro-sports");
  const doc = opts.capas ? { ...base, capas: opts.capas } : base;
  const store = crearStoreEditor(doc);
  render(
    <ExportarDialogo
      store={store}
      muestraFoto={opts.muestraFoto}
      muestraCopy={opts.muestraCopy}
      bindings={opts.bindings}
    />,
  );
  return store;
}

async function descargar() {
  fireEvent.click(screen.getByRole("button", { name: "Exportar" }));
  fireEvent.click(await screen.findByRole("button", { name: /Descargar/ }));
  await waitFor(() => expect(apiMod.api.imagenRender).toHaveBeenCalled());
}

function docEnviado(): DocLite {
  return vi.mocked(apiMod.api.imagenRender).mock.calls[0][0] as DocLite;
}
function huecoFoto(doc: DocLite) {
  return doc.capas.find((c) => c.tipo === "imagen" && c.es_foto);
}

beforeEach(() => {
  // fetch + createObjectURL: la descarga (fetch del render → blob → <a download>) no debe tocar red.
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, blob: async () => new Blob(["x"]) }) as unknown as Response),
  );
  URL.createObjectURL = vi.fn(() => "blob:fake");
  URL.revokeObjectURL = vi.fn();
  // El <a download> programático: en jsdom seguir su href lanza "Not implemented: navigation".
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  vi.spyOn(apiMod.api, "imagenRender").mockResolvedValue({ id: "out", url: "/api/media/out.png" });
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  setFotoMuestra(""); // limpia la muestra (e invalida la caché del objeto subido) entre casos
  setTitularMuestra(TITULAR_MUESTRA_DEFECTO);
});

describe("ExportarDialogo — horneado de la foto de muestra", () => {
  it("con muestra activa y foto real, sube la foto y hornea su objeto en el hueco vacío", async () => {
    const subir = vi
      .spyOn(apiMod.api, "subirMedia")
      .mockResolvedValue({ id: "muestra-obj-1", url: "/api/media/muestra-obj-1.png" });
    setFotoMuestra(FOTO_MUESTRA);
    montar({ muestraFoto: true });

    await descargar();
    expect(subir).toHaveBeenCalledTimes(1);
    expect(huecoFoto(docEnviado())?.objeto).toBe("muestra-obj-1");
  });

  it("con la muestra DESACTIVADA no sube nada y exporta el hueco vacío", async () => {
    const subir = vi.spyOn(apiMod.api, "subirMedia");
    setFotoMuestra(FOTO_MUESTRA); // hay foto de muestra, pero el toggle está apagado
    montar({ muestraFoto: false });

    await descargar();
    expect(subir).not.toHaveBeenCalled();
    expect(huecoFoto(docEnviado())?.objeto).toBe("");
  });
});

describe("ExportarDialogo — horneado del texto al descargar", () => {
  it("congela el titular ESCRITO y le quita el binding (sin pieza el binding iría vacío)", async () => {
    montar({ capas: [nuevaCapaTexto({ binding: "copy_in", texto: "MARADONA ETERNO" })] });

    await descargar();
    const t = docEnviado().capas[0];
    expect(t.texto).toBe("MARADONA ETERNO");
    expect(t.binding).toBeNull();
  });

  it("con 'Copy de muestra' activo, hornea el copy de ejemplo en el titular vacío", async () => {
    setTitularMuestra("TITULAR DE MUESTRA");
    montar({ muestraCopy: true, capas: [nuevaCapaTexto({ binding: "copy_in", texto: "" })] });

    await descargar();
    const t = docEnviado().capas[0];
    expect(t.texto).toBe("TITULAR DE MUESTRA");
    expect(t.binding).toBeNull();
  });

  it("NO hornea el placeholder de un titular vacío (no contamina con 'Titular de ejemplo')", async () => {
    montar({ capas: [nuevaCapaTexto({ binding: "copy_in", texto: "" })] });

    await descargar();
    const t = docEnviado().capas[0];
    expect(t.texto).toBe(""); // queda vacío; el server lo pinta sin texto, no el placeholder
    expect(t.binding).toBe("copy_in"); // binding intacto: nada que congelar
  });

  it("respeta el copy REAL de la pieza (binding intacto: lo pinta el server vía bindings)", async () => {
    montar({
      bindings: { copy_in: "Titular real de la pieza" },
      capas: [nuevaCapaTexto({ binding: "copy_in", texto: "borrador viejo" })],
    });

    await descargar();
    const t = docEnviado().capas[0];
    expect(t.binding).toBe("copy_in"); // no se congela: el render usará el binding real
    expect(t.texto).toBe("borrador viejo");
  });
});
