import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SelectorRedMultiple } from "./SelectorRedMultiple";

/**
 * Tests del selector de redes múltiple (chips). El sufijo diferencia entre
 * `SelectorRedMultiple` (chips) y `SelectorRed` (dropdown único).
 */
const OPCIONES = [
  { id: "instagram", nombre: "Instagram" },
  { id: "x", nombre: "X" },
  { id: "tiktok", nombre: "TikTok" },
];

describe("SelectorRedMultiple", () => {
  it("renderiza un chip por opción con role checkbox", () => {
    render(
      <SelectorRedMultiple
        opciones={OPCIONES}
        seleccionadas={new Set()}
        onCambio={() => {}}
      />,
    );
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
  });

  it("marca aria-checked en las redes seleccionadas", () => {
    render(
      <SelectorRedMultiple
        opciones={OPCIONES}
        seleccionadas={new Set(["x"])}
        onCambio={() => {}}
      />,
    );
    expect(screen.getByRole("checkbox", { name: "X" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Instagram" })).not.toBeChecked();
  });

  it("avisa con el estado contrario al pulsar un chip", () => {
    const onCambio = vi.fn();
    render(
      <SelectorRedMultiple
        opciones={OPCIONES}
        seleccionadas={new Set(["instagram"])}
        onCambio={onCambio}
      />,
    );
    // Pulsar una marcada la desmarca; una sin marcar la marca.
    fireEvent.click(screen.getByRole("checkbox", { name: "Instagram" }));
    expect(onCambio).toHaveBeenCalledWith("instagram", false);
    fireEvent.click(screen.getByRole("checkbox", { name: "TikTok" }));
    expect(onCambio).toHaveBeenCalledWith("tiktok", true);
  });

  it("deshabilita los chips cuando disabled", () => {
    render(
      <SelectorRedMultiple
        opciones={OPCIONES}
        seleccionadas={new Set()}
        onCambio={() => {}}
        disabled
      />,
    );
    screen.getAllByRole("checkbox").forEach((chip) => expect(chip).toBeDisabled());
  });
});
