import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BadgeFuente } from "./BadgeFuente";
import { esFuenteMuestra } from "./fuente";

/**
 * Tests del badge de fuente muestra/real (#90). Clave: la lectura DEFENSIVA del
 * campo `fuente` (opcional) — si falta, no se renderiza nada para no afirmar
 * "real" sin saberlo.
 */
describe("esFuenteMuestra", () => {
  it("reconoce la fuente de muestra", () => {
    expect(esFuenteMuestra("muestra")).toBe(true);
  });

  it("considera real cualquier otra fuente", () => {
    expect(esFuenteMuestra("meta")).toBe(false);
    expect(esFuenteMuestra("youtube")).toBe(false);
  });

  it("no afirma muestra cuando falta el dato", () => {
    expect(esFuenteMuestra(undefined)).toBe(false);
    expect(esFuenteMuestra(null)).toBe(false);
    expect(esFuenteMuestra("")).toBe(false);
  });
});

describe("BadgeFuente", () => {
  it("muestra 'Datos de muestra' cuando la fuente es muestra", () => {
    render(<BadgeFuente fuente="muestra" />);
    expect(screen.getByText("Datos de muestra")).toBeInTheDocument();
  });

  it("muestra 'Datos reales' para una fuente real", () => {
    render(<BadgeFuente fuente="meta" />);
    expect(screen.getByText("Datos reales")).toBeInTheDocument();
  });

  it("no renderiza nada cuando la fuente es undefined (defensivo)", () => {
    const { container } = render(<BadgeFuente fuente={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("no renderiza nada cuando la fuente es cadena vacía", () => {
    const { container } = render(<BadgeFuente fuente="" />);
    expect(container).toBeEmptyDOMElement();
  });
});
