/**
 * Tests del SHELL del editor (EditorDocumento) — rail estilo Canva:
 *  - «Diseño» (plantillas) va PRIMERO en el rail, antes de Elementos/Galería/Capas.
 *  - Con `panelDiseno`, «Diseño» abre ese panel como columna del rail (no un modal).
 *  - Solo con `onPlantillas` (overlay de vídeo), «Diseño» cae al modal clásico (callback).
 *  - Sin ninguno de los dos, «Diseño» no aparece.
 *  - El flyout/inspector de escritorio mide ~350px (md:w-[350px], patrón Canva).
 *  - HOVER del rail: reposar ~200 ms abre el panel SIN FIJAR; el clic lo fija; salir del
 *    rail+panel sin fijar lo cierra a los ~300 ms. Solo con puntero real (hover:hover).
 *
 * El lienzo real (Konva) y los paneles pesados se mockean: aquí se ejercita SOLO el shell.
 */
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./Lienzo", () => ({ Lienzo: () => <div data-testid="lienzo" /> }));
vi.mock("./PanelElementos", () => ({ PanelElementos: () => <div>panel-elementos</div> }));
vi.mock("./PanelGaleria", () => ({ PanelGaleria: () => <div>panel-galeria</div> }));
vi.mock("./PanelMarca", () => ({ PanelMarca: () => <div>panel-marca</div> }));
vi.mock("./PanelSubidas", () => ({ PanelSubidas: () => <div>panel-subidas</div> }));
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
  it("con panelDiseno, «Plantillas» es la PRIMERA herramienta del rail", () => {
    montar({ panelDiseno: <div>panel-de-plantillas</div> });
    const botones = within(railEscritorio()).getAllByRole("button");
    expect(botones[0]).toHaveTextContent("Plantillas");
    // Orden completo del rail (estilo Canva): Plantillas · Elementos · Recursos · Marca · Subidas ·
    // Capas · [Atajos · Ajustes]. «Subidas» (tus propias fotos) va tras Marca y antes de Capas;
    // «Atajos» (chuleta de teclado) y «Ajustes» van al fondo del rail.
    expect(botones.map((b) => b.textContent)).toEqual([
      "Plantillas",
      "Elementos",
      "Recursos",
      "Marca",
      "Subidas",
      "Capas",
      "Atajos",
      "Ajustes",
    ]);
  });

  it("«Subidas» abre el panel de subidas como flyout (y se cierra al re-pulsar)", () => {
    montar();
    const boton = within(railEscritorio()).getByTitle("Subidas");
    fireEvent.click(boton);
    expect(screen.getByText("panel-subidas")).toBeInTheDocument();
    fireEvent.click(boton);
    expect(screen.queryByText("panel-subidas")).not.toBeInTheDocument();
  });

  it("«Marca» abre el panel del kit de marca como flyout (y se cierra al re-pulsar)", () => {
    montar();
    const boton = within(railEscritorio()).getByTitle("Marca");
    fireEvent.click(boton);
    expect(screen.getByText("panel-marca")).toBeInTheDocument();
    fireEvent.click(boton);
    expect(screen.queryByText("panel-marca")).not.toBeInTheDocument();
  });

  it("«Diseño» abre el panel de la página como columna del rail (y se cierra al re-pulsar)", () => {
    montar({ panelDiseno: <div>panel-de-plantillas</div> });
    const boton = within(railEscritorio()).getByTitle("Plantillas");
    fireEvent.click(boton);
    expect(screen.getByText("panel-de-plantillas")).toBeInTheDocument();
    // Toggle: re-pulsar cierra el flyout.
    fireEvent.click(boton);
    expect(screen.queryByText("panel-de-plantillas")).not.toBeInTheDocument();
  });

  it("solo con onPlantillas (sin panelDiseno) «Diseño» cae al modal clásico", () => {
    const onPlantillas = vi.fn();
    montar({ onPlantillas });
    fireEvent.click(within(railEscritorio()).getByTitle("Plantillas"));
    expect(onPlantillas).toHaveBeenCalledTimes(1);
    // No se abre ningún flyout propio.
    expect(document.querySelector("aside")).toBeNull();
  });

  it("sin panelDiseno ni onPlantillas, «Diseño» no aparece en el rail", () => {
    montar();
    expect(within(railEscritorio()).queryByTitle("Plantillas")).not.toBeInTheDocument();
    expect(within(railEscritorio()).getAllByRole("button")[0]).toHaveTextContent("Elementos");
  });

  it("el flyout de escritorio mide ~350px (md:w-[350px], patrón Canva)", () => {
    montar({ panelDiseno: <div>panel-de-plantillas</div> });
    fireEvent.click(within(railEscritorio()).getByTitle("Plantillas"));
    const aside = document.querySelector("aside");
    expect(aside?.className).toContain("md:w-[350px]");
  });

  it("el inspector («Ajustes») también mide ~350px en escritorio", () => {
    montar();
    fireEvent.click(within(railEscritorio()).getByTitle("Ajustes"));
    const aside = document.querySelector("aside");
    expect(aside?.className).toContain("md:w-[350px]");
  });

  it("«Galería» abre el panel de galería (id interno renombrado a «galeria»)", () => {
    montar();
    fireEvent.click(within(railEscritorio()).getByTitle("Recursos"));
    expect(screen.getByText("panel-galeria")).toBeInTheDocument();
    fireEvent.click(within(railEscritorio()).getByTitle("Recursos"));
    expect(screen.queryByText("panel-galeria")).not.toBeInTheDocument();
  });

  it("el «?» del rail abre la chuleta de atajos de teclado", () => {
    montar();
    expect(screen.queryByRole("dialog", { name: "Atajos de teclado" })).not.toBeInTheDocument();
    fireEvent.click(within(railEscritorio()).getByTitle("Atajos"));
    expect(screen.getByRole("dialog", { name: "Atajos de teclado" })).toBeInTheDocument();
  });

  it("«Atajos de teclado» del menú «Más» abre la misma chuleta", () => {
    montar();
    fireEvent.click(screen.getByTitle("Más acciones"));
    fireEvent.click(screen.getByText("Atajos de teclado"));
    expect(screen.getByRole("dialog", { name: "Atajos de teclado" })).toBeInTheDocument();
  });
});

describe("EditorDocumento — estado vacío guía del lienzo", () => {
  it("con el lienzo en blanco pinta el estado vacío con las CTAs de subir foto y texto", () => {
    montar();
    expect(screen.getByText("Empieza tu diseño")).toBeInTheDocument();
    expect(screen.getByText("Sube una foto")).toBeInTheDocument();
    expect(screen.getByText("Añade texto")).toBeInTheDocument();
  });

  it("la CTA «Elige una plantilla» solo aparece si la página aporta plantillas", () => {
    const { unmount } = montar();
    expect(screen.queryByText("Elige una plantilla")).not.toBeInTheDocument();
    unmount();
    montar({ panelDiseno: <div>panel-de-plantillas</div> });
    expect(screen.getByText("Elige una plantilla")).toBeInTheDocument();
  });

  it("«Sube una foto» del estado vacío abre el flyout de subidas", () => {
    montar();
    fireEvent.click(screen.getByText("Sube una foto"));
    expect(screen.getByText("panel-subidas")).toBeInTheDocument();
  });

  it("«Añade texto» del estado vacío abre el flyout de elementos", () => {
    montar();
    fireEvent.click(screen.getByText("Añade texto"));
    expect(screen.getByText("panel-elementos")).toBeInTheDocument();
  });
});

describe("EditorDocumento — rail agrupado por función", () => {
  it("el rail separa los grupos con divisores (empezar · añadir · medios · estructura)", () => {
    montar({ panelDiseno: <div>panel-de-plantillas</div> });
    // 6 herramientas en 4 grupos → 3 divisores internos + 1 antes de Atajos/Ajustes = 4.
    const divisores = railEscritorio().querySelectorAll("div.h-px");
    expect(divisores.length).toBe(4);
  });
});

/** Stub de matchMedia POR CONSULTA: el hover del rail solo aplica con puntero real
 *  (`hover: hover`) y sin `prefers-reduced-motion: reduce`. */
function stubHover(hover: boolean, reduceMovimiento = false) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((consulta: string) => ({
      matches: consulta.includes("prefers-reduced-motion") ? reduceMovimiento : hover,
      addEventListener: () => {},
      removeEventListener: () => {},
    })),
  );
}

describe("EditorDocumento — hover del rail (abre sin fijar; el clic fija)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("reposar ~200 ms sobre un botón abre su panel y salir del rail sin fijar lo cierra a los ~300 ms", () => {
    vi.useFakeTimers();
    stubHover(true);
    montar();
    fireEvent.mouseEnter(within(railEscritorio()).getByTitle("Elementos"));
    // Aún no: hay un reposo de ~200 ms antes de abrir (un roce no abre nada).
    expect(screen.queryByText("panel-elementos")).not.toBeInTheDocument();
    act(() => void vi.advanceTimersByTime(200));
    expect(screen.getByText("panel-elementos")).toBeInTheDocument();
    // Sale del rail sin haber fijado: gracia de ~300 ms y cierre.
    fireEvent.mouseLeave(railEscritorio());
    expect(screen.getByText("panel-elementos")).toBeInTheDocument(); // todavía (gracia)
    act(() => void vi.advanceTimersByTime(300));
    expect(screen.queryByText("panel-elementos")).not.toBeInTheDocument();
  });

  it("entrar al panel cancela el cierre; el clic FIJA (mouse-leave ya no cierra; re-pulsar sí)", () => {
    vi.useFakeTimers();
    stubHover(true);
    montar();
    const boton = within(railEscritorio()).getByTitle("Elementos");
    fireEvent.mouseEnter(boton);
    act(() => void vi.advanceTimersByTime(200));
    // rail → panel: el mouseleave del rail arma el cierre y entrar al panel lo cancela.
    fireEvent.mouseLeave(railEscritorio());
    fireEvent.mouseEnter(document.querySelector("aside")!);
    act(() => void vi.advanceTimersByTime(500));
    expect(screen.getByText("panel-elementos")).toBeInTheDocument();
    // El clic en el botón del rail FIJA el panel hover-abierto (no lo cierra)…
    fireEvent.click(boton);
    expect(screen.getByText("panel-elementos")).toBeInTheDocument();
    // …y salir ya no lo cierra.
    fireEvent.mouseLeave(railEscritorio());
    act(() => void vi.advanceTimersByTime(1000));
    expect(screen.getByText("panel-elementos")).toBeInTheDocument();
    // Toggle clásico intacto: re-pulsar cierra el panel fijado.
    fireEvent.click(boton);
    expect(screen.queryByText("panel-elementos")).not.toBeInTheDocument();
  });

  it("interactuar DENTRO del panel hover-abierto lo fija (no se esfuma mientras se usa)", () => {
    vi.useFakeTimers();
    stubHover(true);
    montar();
    fireEvent.mouseEnter(within(railEscritorio()).getByTitle("Capas"));
    act(() => void vi.advanceTimersByTime(200));
    const aside = document.querySelector("aside")!;
    fireEvent.mouseDown(aside); // p. ej. clicar una capa del panel
    fireEvent.mouseLeave(aside);
    act(() => void vi.advanceTimersByTime(1000));
    expect(screen.getByText("panel-capas")).toBeInTheDocument();
  });

  it("sin puntero con hover real (táctil), el hover NO abre nada", () => {
    vi.useFakeTimers();
    stubHover(false);
    montar();
    fireEvent.mouseEnter(within(railEscritorio()).getByTitle("Elementos"));
    act(() => void vi.advanceTimersByTime(1000));
    expect(screen.queryByText("panel-elementos")).not.toBeInTheDocument();
  });

  it("con prefers-reduced-motion, el hover NO abre paneles (solo el clic)", () => {
    vi.useFakeTimers();
    stubHover(true, true); // hay puntero real, pero el usuario pide movimiento reducido
    montar();
    const boton = within(railEscritorio()).getByTitle("Elementos");
    fireEvent.mouseEnter(boton);
    act(() => void vi.advanceTimersByTime(1000));
    expect(screen.queryByText("panel-elementos")).not.toBeInTheDocument();
    // El clic sigue funcionando con normalidad (y fija el panel).
    fireEvent.click(boton);
    expect(screen.getByText("panel-elementos")).toBeInTheDocument();
  });

  it("con solo onPlantillas, «Diseño» NO dispara el modal por hover (solo por clic)", () => {
    vi.useFakeTimers();
    stubHover(true);
    const onPlantillas = vi.fn();
    montar({ onPlantillas });
    fireEvent.mouseEnter(within(railEscritorio()).getByTitle("Plantillas"));
    act(() => void vi.advanceTimersByTime(1000));
    expect(onPlantillas).not.toHaveBeenCalled();
    expect(document.querySelector("aside")).toBeNull();
  });
});
