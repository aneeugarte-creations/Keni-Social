/**
 * Tests de ACCESIBILIDAD del overlay de recorte (CropOverlay):
 *  - El contenedor es un `role="group"` con nombre («Recorte de imagen»).
 *  - La superficie de arrastre (pan) y los 8 tiradores del marco son `role="button"` con aria-label
 *    (gestos de puntero sin texto visible: sin label serían invisibles para el lector).
 * La imagen se simula mockeando `useImagen` (en jsdom no hay carga real de imágenes).
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { type CapaImagen, documentoVacio, nuevaCapaImagen } from "../documento";
import { crearStoreEditor, type StoreEditor } from "../store";
import { aspectoRecorteStore } from "./aspectoRecorte";
import { CropOverlay } from "./CropOverlay";

// Imagen "ya cargada": el hook real espera el onload del navegador, que en jsdom nunca llega.
vi.mock("../useImagen", () => ({
  useImagen: () => ({ src: "blob:foto", width: 800, height: 600 }) as unknown as HTMLImageElement,
}));

function montar(): { store: StoreEditor } {
  const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 0, safe_bottom: 0 }, "m1");
  const capa = nuevaCapaImagen("obj-1", { id: "img1", x: 100, y: 100, w: 400, h: 300 });
  doc.capas.push(capa);
  const store = crearStoreEditor(doc);
  render(<CropOverlay capa={capa as CapaImagen} escala={0.5} store={store} />);
  return { store };
}

// jsdom no trae `PointerEvent` (así fireEvent no propaga clientX) ni `setPointerCapture`; el gesto
// de recorte los necesita. MouseEvent lleva clientX/clientY, suficiente para el arrastre del marco.
beforeAll(() => {
  if (typeof window.PointerEvent === "undefined") {
    window.PointerEvent = class extends MouseEvent {} as unknown as typeof PointerEvent;
  }
  if (!Element.prototype.setPointerCapture) Element.prototype.setPointerCapture = () => {};
});

afterEach(() => aspectoRecorteStore.getState().limpiar());

describe("CropOverlay — accesibilidad", () => {
  it("expone el overlay como grupo con nombre", () => {
    montar();
    expect(screen.getByRole("group", { name: "Recorte de imagen" })).toBeInTheDocument();
  });

  it("registra en el estado compartido que el recorte es de una FOTO", () => {
    montar();
    expect(aspectoRecorteStore.getState().esImagen).toBe(true);
  });

  it("la superficie de arrastre (pan) y los 8 tiradores del marco tienen nombre accesible", () => {
    montar();
    expect(screen.getByRole("button", { name: "Mover la imagen dentro del marco" })).toBeInTheDocument();
    for (const etiqueta of [
      "Recortar desde la esquina superior izquierda",
      "Recortar desde el borde superior",
      "Recortar desde la esquina superior derecha",
      "Recortar desde el borde derecho",
      "Recortar desde la esquina inferior derecha",
      "Recortar desde el borde inferior",
      "Recortar desde la esquina inferior izquierda",
      "Recortar desde el borde izquierdo",
    ]) {
      expect(screen.getByRole("button", { name: etiqueta })).toBeInTheDocument();
    }
  });
});

describe("CropOverlay — el tirador ENCOGE el marco (corta sin ampliar)", () => {
  it("arrastrar el borde derecho hacia dentro reduce la caja y compensa el crop", () => {
    const { store } = montar();
    const asa = screen.getByRole("button", { name: "Recortar desde el borde derecho" });
    const grupo = screen.getByRole("group", { name: "Recorte de imagen" });
    // escala 0.5: -50px de pantalla = -100px del documento (borde derecho: 400 -> 300).
    fireEvent.pointerDown(asa, { clientX: 200, clientY: 200, pointerId: 1 });
    fireEvent.pointerMove(grupo, { clientX: 150, clientY: 200, pointerId: 1 });
    fireEvent.pointerUp(grupo, { pointerId: 1 });
    const capa = store.getState().documento.capas.find((c) => c.id === "img1") as CapaImagen;
    expect(capa.w).toBeCloseTo(300, 3); // la CAJA encoge (no la foto)
    expect(capa.h).toBeCloseTo(300, 3); // el alto no cambia
    expect(capa.x).toBeCloseTo(100, 3); // el borde derecho no mueve el origen
    expect(capa.crop).toEqual({ cx: 0, cy: 0, cw: 0.75, ch: 1 });
  });
});
