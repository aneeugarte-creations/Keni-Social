// Menú de NIVELES DE ZOOM de ControlesEncuadre: tratamiento visual coherente en todas las filas
// (atajo en <kbd> cuando lo hay + check del nivel actual con hueco SIEMPRE reservado) y el alias
// ⌥⌘0 de «Ajustar a la pantalla» reflejado en tooltip y menú. Más el toggle de ZONAS SEGURAS.

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
