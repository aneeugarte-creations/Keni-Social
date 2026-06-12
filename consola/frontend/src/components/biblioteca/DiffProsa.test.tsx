/**
 * DiffProsa: diff de prosa legible (verde = añadido, rojo tachado = borrado), con las
 * `{{VARIABLES}}` como tokens atómicos (el diff nunca parte una variable) y modo
 * "solo cambios" que colapsa los párrafos sin tocar.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DiffProsa } from "./DiffProsa";

describe("DiffProsa", () => {
  it("marca lo añadido con <ins> y lo borrado con <del>", () => {
    const { container } = render(
      <DiffProsa antes="El copy debe ser corto." despues="El copy debe ser largo." />,
    );
    expect(container.querySelector("del")?.textContent).toBe("corto.");
    expect(container.querySelector("ins")?.textContent).toBe("largo.");
  });

  it("trata {{VAR}} como token atómico (no la parte por la mitad)", () => {
    const { container } = render(
      <DiffProsa antes="Habla de {{MARCA}} hoy" despues="Habla de {{TEMA}} hoy" />,
    );
    // La variable entera cambia: el chip viejo en <del> y el nuevo en <ins>.
    expect(container.querySelector("del")?.textContent).toBe("MARCA");
    expect(container.querySelector("ins")?.textContent).toBe("TEMA");
  });

  it("sin diferencias avisa 'Sin cambios'", () => {
    render(<DiffProsa antes="Igual." despues="Igual." />);
    expect(screen.getByText(/Sin cambios/)).toBeInTheDocument();
  });

  it("'solo cambios' colapsa los párrafos sin tocar y se despliegan al clic", () => {
    const antes = "Uno.\n\nDos.\n\nTres.\n\nViejo.";
    const despues = "Uno.\n\nDos.\n\nTres.\n\nNuevo.";
    render(<DiffProsa antes={antes} despues={despues} soloCambios />);
    const separador = screen.getByText(/3 párrafos sin cambios/);
    expect(screen.queryByText("Dos.")).not.toBeInTheDocument();
    fireEvent.click(separador);
    expect(screen.getByText("Dos.")).toBeInTheDocument();
  });
});
