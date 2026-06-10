/**
 * Tests de ACCESIBILIDAD del overlay de recorte (CropOverlay):
 *  - El contenedor es un `role="group"` con nombre («Recorte de imagen»).
 *  - La superficie de arrastre y los 4 tiradores de esquina son `role="button"` con aria-label
 *    (gestos de puntero sin texto visible: sin label serían invisibles para el lector).
 * La imagen se simula mockeando `useImagen` (en jsdom no hay carga real de imágenes).
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type CapaImagen, documentoVacio, nuevaCapaImagen } from "../documento";
import { crearStoreEditor } from "../store";
import { CropOverlay } from "./CropOverlay";

// Imagen "ya cargada": el hook real espera el onload del navegador, que en jsdom nunca llega.
vi.mock("../useImagen", () => ({
  useImagen: () => ({ src: "blob:foto", width: 800, height: 600 }) as unknown as HTMLImageElement,
}));

function montar() {
  const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 0, safe_bottom: 0 }, "m1");
  const capa = nuevaCapaImagen("obj-1", { id: "img1", x: 100, y: 100, w: 400, h: 300 });
  doc.capas.push(capa);
  const store = crearStoreEditor(doc);
  render(<CropOverlay capa={capa as CapaImagen} escala={0.5} store={store} />);
}

describe("CropOverlay — accesibilidad", () => {
  it("expone el overlay como grupo con nombre", () => {
    montar();
    expect(screen.getByRole("group", { name: "Recorte de imagen" })).toBeInTheDocument();
  });

  it("la superficie de arrastre y los tiradores de esquina tienen nombre accesible", () => {
    montar();
    expect(screen.getByRole("button", { name: "Mover la imagen dentro del marco" })).toBeInTheDocument();
    for (const esquina of [
      "superior izquierda",
      "superior derecha",
      "inferior derecha",
      "inferior izquierda",
    ]) {
      expect(
        screen.getByRole("button", { name: `Escalar la imagen desde la esquina ${esquina}` }),
      ).toBeInTheDocument();
    }
  });
});
