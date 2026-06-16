// El overlay de recorte de CAJA: pinta los 8 tiradores y calza con la rotación del objeto (una línea
// "vertical" es una línea rotada 90°). El cálculo del arrastre vive en `recortarCaja`/`recortarCajaRotada`
// (probado aparte); aquí se verifica el render y que el overlay adopta la rotación de la capa.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AsaRecorte } from "../recorte";
import { documentoVacio, nuevaCapaMarco } from "../documento";
import { crearStoreEditor } from "../store";
import { RecorteCajaOverlay } from "./RecorteCajaOverlay";
import { etiquetaAsa } from "./tiradoresRecorte";

function montar(rotacion = 0) {
  const store = crearStoreEditor(documentoVacio({ w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 }, "t"));
  const marco = nuevaCapaMarco({ id: "m1", x: 100, y: 100, w: 200, h: 100, rotacion });
  store.getState().agregar(marco);
  render(<RecorteCajaOverlay capa={marco} escala={1} store={store} />);
}

describe("RecorteCajaOverlay", () => {
  it("pinta los 8 tiradores (4 esquinas + 4 lados)", () => {
    montar();
    expect(screen.getAllByRole("button")).toHaveLength(8);
    for (const a of ["nw", "n", "ne", "e", "se", "s", "sw", "w"] as AsaRecorte[]) {
      expect(screen.getByRole("button", { name: etiquetaAsa(a) })).toBeInTheDocument();
    }
  });

  it("adopta la rotación del objeto (una línea 'vertical' = línea rotada 90°)", () => {
    montar(90);
    expect(screen.getByRole("group", { name: "Recortar objeto" })).toHaveStyle({
      transform: "rotate(90deg)",
    });
  });

  it("sin rotación no aplica transform", () => {
    montar(0);
    expect(screen.getByRole("group", { name: "Recortar objeto" }).style.transform).toBe("");
  });
});
