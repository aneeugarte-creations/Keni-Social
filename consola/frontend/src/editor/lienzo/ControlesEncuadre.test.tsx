// ControlesEncuadre, ahora BARRA INFERIOR estilo Canva: menú de NIVELES DE ZOOM con tratamiento
// visual coherente en todas las filas (atajo en <kbd> cuando lo hay + check del nivel actual con
// hueco SIEMPRE reservado) y el alias ⌥⌘0 de «Ajustar a la pantalla» reflejado en tooltip y menú.
// Más el toggle de ZONAS SEGURAS, el slider compacto de zoom y el menú "⋯" de pantallas estrechas
// (que repite los MISMOS toggles de encuadre).

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ControlesEncuadre } from "./ControlesEncuadre";

function montar(escala = 1, opts: { zonas?: boolean } = {}) {
  const fijarEscala = vi.fn();
  const ajustarPantalla = vi.fn();
  const setZonas = vi.fn();
  render(
    <ControlesEncuadre
      iman={false}
      setIman={vi.fn()}
      grid={false}
      setGrid={vi.fn()}
      tamCelda={8}
      setTamCelda={vi.fn()}
      dentroMarco={false}
      setDentroMarco={vi.fn()}
      zonas={opts.zonas ?? false}
      setZonas={setZonas}
      escala={escala}
      alejar={vi.fn()}
      acercar={vi.fn()}
      zoomReal={vi.fn()}
      ajustarPantalla={ajustarPantalla}
      fijarEscala={fijarEscala}
    />,
  );
  return { fijarEscala, ajustarPantalla, setZonas };
}

const abrirMenu = () => {
  fireEvent.click(screen.getByRole("button", { name: "Nivel de zoom" }));
  return screen.getByRole("menu", { name: "Nivel de zoom" });
};

describe("ControlesEncuadre — menú de zoom", () => {
  it("todas las filas comparten el tratamiento: kbd cuando hay atajo y hueco de check siempre", () => {
    montar(1);
    const menu = abrirMenu();
    const filas = within(menu).getAllByRole("button");
    // Cada fila reserva el hueco del check (visible solo en el nivel actual): sin bailes.
    for (const f of filas) expect(f.querySelector("svg")).not.toBeNull();
    // Atajos en <kbd>: ajustar (con el alias ⌥⌘0 de Canva) y 100 %.
    const ajustar = within(menu).getByRole("button", { name: /ajustar a la pantalla/i });
    expect(ajustar.querySelector("kbd")?.textContent).toBe("⌘0 · ⌥⌘0");
    const real = within(menu).getByRole("button", { name: /100 % \(tamaño real\)/i });
    expect(real.querySelector("kbd")?.textContent).toBe("⇧0");
  });

  it("el check marca el nivel ACTUAL en cualquier fila (también «100 % (tamaño real)»)", () => {
    montar(1); // 100 %
    const menu = abrirMenu();
    const real = within(menu).getByRole("button", { name: /100 % \(tamaño real\)/i });
    expect(real.querySelector("svg")?.classList.contains("invisible")).toBe(false);
    // En una fila inactiva el check existe pero va invisible (solo reserva sitio).
    const paso50 = within(menu).getByRole("button", { name: /^50 %/ });
    expect(paso50.querySelector("svg")?.classList.contains("invisible")).toBe(true);
  });

  it("elegir un nivel fija la escala y cierra el menú", () => {
    const { fijarEscala } = montar(1);
    const menu = abrirMenu();
    fireEvent.click(within(menu).getByRole("button", { name: /^50 %/ }));
    expect(fijarEscala).toHaveBeenCalledWith(0.5);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("el tooltip del botón de ajustar anuncia ambos atajos (⌘0 · ⌥⌘0)", () => {
    montar(1);
    expect(
      screen.getByRole("button", { name: "Ajustar a la pantalla (⌘0 · ⌥⌘0)" }),
    ).toBeInTheDocument();
  });
});

describe("ControlesEncuadre — zonas seguras", () => {
  const nombre = "Zonas seguras: la interfaz de la red puede tapar lo sombreado";

  it("expone el toggle con tooltip explicativo y estado aria-pressed", () => {
    montar(1);
    const boton = screen.getByRole("button", { name: nombre });
    expect(boton).toHaveAttribute("aria-pressed", "false");
  });

  it("refleja el estado activo en aria-pressed", () => {
    montar(1, { zonas: true });
    expect(screen.getByRole("button", { name: nombre })).toHaveAttribute("aria-pressed", "true");
  });

  it("el clic alterna el toggle a través del setter (sin tocar nada más)", () => {
    const { setZonas, fijarEscala } = montar(1);
    fireEvent.click(screen.getByRole("button", { name: nombre }));
    expect(setZonas).toHaveBeenCalledTimes(1);
    expect(fijarEscala).not.toHaveBeenCalled();
  });
});

describe("ControlesEncuadre — slider de zoom (barra inferior)", () => {
  it("expone un slider 10–300 con el porcentaje actual y fija la escala al moverlo", () => {
    const { fijarEscala } = montar(0.5); // 50 %
    const slider = screen.getByRole("slider", { name: "Zoom" }) as HTMLInputElement;
    expect(slider).toHaveAttribute("min", "10");
    expect(slider).toHaveAttribute("max", "300");
    expect(slider.value).toBe("50");
    fireEvent.change(slider, { target: { value: "150" } });
    expect(fijarEscala).toHaveBeenCalledWith(1.5);
  });
});

describe("ControlesEncuadre — menú «⋯» (pantallas estrechas)", () => {
  it("abre un menú con los MISMOS toggles de encuadre (mismos tooltips/aria)", () => {
    montar(1);
    fireEvent.click(screen.getByRole("button", { name: "Opciones de encuadre" }));
    const menu = screen.getByRole("menu", { name: "Opciones de encuadre" });
    expect(
      within(menu).getByRole("button", { name: "Imán: ajustar a objetos, bordes y márgenes" }),
    ).toHaveAttribute("aria-pressed", "false");
    expect(
      within(menu).getByRole("button", { name: "Zonas seguras: la interfaz de la red puede tapar lo sombreado" }),
    ).toBeInTheDocument();
  });
});
