/**
 * Tests para AvisoAutorizarStock: cuerpo del diálogo de autorizar una foto de stock.
 *
 * - Proveedor libre (Pexels/Pixabay): muestra la licencia + los 2 riesgos editoriales.
 * - Proveedor no libre (o ausente): muestra el texto de responsabilidad de siempre.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RIESGOS_STOCK_LIBRE } from "@/lib/stock";

import { AvisoAutorizarStock } from "./AvisoAutorizarStock";

describe("AvisoAutorizarStock", () => {
  it("proveedor libre: muestra la licencia y los 2 riesgos", () => {
    render(<AvisoAutorizarStock proveedor="pexels" licencia="Pexels License" />);
    expect(screen.getByText(/uso libre, incluso comercial/i)).toBeInTheDocument();
    expect(screen.getByText(/Pexels License/i)).toBeInTheDocument();
    for (const riesgo of RIESGOS_STOCK_LIBRE) {
      expect(screen.getByText(riesgo)).toBeInTheDocument();
    }
    expect(screen.queryByText(/Bajo tu responsabilidad/i)).not.toBeInTheDocument();
  });

  it("proveedor no libre: muestra el texto de responsabilidad", () => {
    render(<AvisoAutorizarStock proveedor="openverse" />);
    expect(screen.getByText(/Bajo tu responsabilidad/i)).toBeInTheDocument();
    expect(screen.queryByText(/uso libre, incluso comercial/i)).not.toBeInTheDocument();
  });

  it("sin proveedor: trata como no libre", () => {
    render(<AvisoAutorizarStock />);
    expect(screen.getByText(/Bajo tu responsabilidad/i)).toBeInTheDocument();
  });
});
