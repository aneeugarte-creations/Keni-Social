import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AvisoMuestra } from "./AvisoMuestra";

describe("AvisoMuestra", () => {
  it("muestra el badge y el texto por defecto", () => {
    render(<AvisoMuestra />);
    expect(screen.getByText("Datos de muestra (sintéticos)")).toBeInTheDocument();
    expect(
      screen.getByText("Las cifras son de demostración, no datos reales del cliente."),
    ).toBeInTheDocument();
    // Accesible: el aviso se anuncia como status, no es solo decorativo.
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("muestra el texto personalizado cuando se le pasa", () => {
    render(<AvisoMuestra texto="Cifras sintéticas del piloto." />);
    expect(screen.getByText("Datos de muestra (sintéticos)")).toBeInTheDocument();
    expect(screen.getByText("Cifras sintéticas del piloto.")).toBeInTheDocument();
    expect(
      screen.queryByText("Las cifras son de demostración, no datos reales del cliente."),
    ).not.toBeInTheDocument();
  });
});
