/**
 * Tests del SHELL del editor (EditorDocumento) — rail estilo Canva:
 *  - «Diseño» (plantillas) va PRIMERO en el rail, antes de Elementos/Galería/Capas.
 *  - Con `panelDiseno`, «Diseño» abre ese panel como columna del rail (no un modal).
 *  - Solo con `onPlantillas` (overlay de vídeo), «Diseño» cae al modal clásico (callback).
 *  - Sin ninguno de los dos, «Diseño» no aparece.
 *  - El flyout/inspector de escritorio mide ~350px (md:w-[350px], patrón Canva).
 *
 * El lienzo real (Konva) y los paneles pesados se mockean: aquí se ejercita SOLO el shell.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("./Lienzo", () => ({ Lienzo: () => <div data-testid="lienzo" /> }));
vi.mock("./PanelElementos", () => ({ PanelElementos: () => <div>panel-elementos</div> }));
vi.mock("./PanelGaleria", () => ({ PanelGaleria: () => <div>panel-galeria</div> }));
vi.mock("./Paneles", () => ({
  Inspector: () => <div>inspector</div>,
  PanelCapas: () => <div>panel-capas</div>,
}));
vi.mock("./useFuentesMarca", () => ({ useFuentesMarca: () => [] }));
vi.mock("./ExportarDialogo", () => ({ ExportarDialogo: () => null }));

import { documentoVacio } from "./documento";
import { EditorDocumento } from "./EditorDocumento";
import { crearStoreEditor } from "./store";

const FORMATO = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

function montar(props: Partial<Parameters<typeof EditorDocumento>[0]> = {}) {
  const store = crearStoreEditor(documentoVacio(FORMATO, "m1"));
  return render(<EditorDocumento store={store} marca="m1" {...props} />);
}

function railEscritorio() {
  return screen.getByRole("navigation", { name: "Herramientas del editor" });
}

describe("EditorDocumento — rail estilo Canva", () => {
  it("con panelDiseno, «Diseño» es la PRIMERA herramienta del rail", () => {
    montar({ panelDiseno: <div>panel-de-plantillas</div> });
    const botones = within(railEscritorio()).getAllByRole("button");
    expect(botones[0]).toHaveTextContent("Diseño");
    // Orden completo del rail: Diseño · Elementos · Galería · Capas · Ajustes.
    expect(botones.map((b) => b.textContent)).toEqual([
      "Diseño",
      "Elementos",
      "Galería",
      "Capas",
      "Ajustes",
    ]);
  });

  it("«Diseño» abre el panel de la página como columna del rail (y se cierra al re-pulsar)", () => {
    montar({ panelDiseno: <div>panel-de-plantillas</div> });
    const boton = within(railEscritorio()).getByTitle("Diseño");
    fireEvent.click(boton);
    expect(screen.getByText("panel-de-plantillas")).toBeInTheDocument();
    // Toggle: re-pulsar cierra el flyout.
    fireEvent.click(boton);
    expect(screen.queryByText("panel-de-plantillas")).not.toBeInTheDocument();
  });

  it("solo con onPlantillas (sin panelDiseno) «Diseño» cae al modal clásico", () => {
    const onPlantillas = vi.fn();
    montar({ onPlantillas });
    fireEvent.click(within(railEscritorio()).getByTitle("Diseño"));
    expect(onPlantillas).toHaveBeenCalledTimes(1);
    // No se abre ningún flyout propio.
    expect(document.querySelector("aside")).toBeNull();
  });

  it("sin panelDiseno ni onPlantillas, «Diseño» no aparece en el rail", () => {
    montar();
    expect(within(railEscritorio()).queryByTitle("Diseño")).not.toBeInTheDocument();
    expect(within(railEscritorio()).getAllByRole("button")[0]).toHaveTextContent("Elementos");
  });

  it("el flyout de escritorio mide ~350px (md:w-[350px], patrón Canva)", () => {
    montar({ panelDiseno: <div>panel-de-plantillas</div> });
    fireEvent.click(within(railEscritorio()).getByTitle("Diseño"));
    const aside = document.querySelector("aside");
    expect(aside?.className).toContain("md:w-[350px]");
  });

  it("el inspector («Ajustes») también mide ~350px en escritorio", () => {
    montar();
    fireEvent.click(within(railEscritorio()).getByTitle("Ajustes"));
    const aside = document.querySelector("aside");
    expect(aside?.className).toContain("md:w-[350px]");
  });
});
