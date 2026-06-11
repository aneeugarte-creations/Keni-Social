import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AvisoMuestra } from "./AvisoMuestra";

describe("AvisoMuestra", () => {
  it("muestra el badge y el texto por defecto", () => {
    render(<AvisoMuestra />);
    expect(screen.getByText("Datos de muestra")).toBeInTheDocument();
    expect(
      screen.getByText("Cifras de demostración, no reales."),
    ).toBeInTheDocument();
    // Accesible: el aviso se anuncia como status, no es solo decorativo.
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("muestra el texto personalizado cuando se le pasa", () => {
    render(<AvisoMuestra texto="Cifras sintéticas del piloto." />);
    expect(screen.getByText("Datos de muestra")).toBeInTheDocument();
    expect(screen.getByText("Cifras sintéticas del piloto.")).toBeInTheDocument();
    expect(
      screen.queryByText("Cifras de demostración, no reales."),
    ).not.toBeInTheDocument();
  });
});
