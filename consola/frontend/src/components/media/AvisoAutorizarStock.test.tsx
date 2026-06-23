/**
 * Tests para AvisoAutorizarStock: cuerpo del diálogo de autorizar una foto de stock, en sus 3
 * ramas según el NIVEL de licencia real:
 *
 * - "libre" (Pexels/Pixabay/CC0/dominio público): licencia de uso libre + los 2 riesgos editoriales.
 * - "atribucion" (CC BY / BY-SA): crédito obligatorio (+ aviso share-alike si BY-SA) + riesgos.
 * - "restringida" (NC/ND/genérico/vacío): el texto de responsabilidad de siempre.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RIESGOS_STOCK_LIBRE } from "@/lib/stock";

import { AvisoAutorizarStock } from "./AvisoAutorizarStock";

describe("AvisoAutorizarStock", () => {
  it("libre: muestra la licencia de uso libre y los 2 riesgos", () => {
    render(<AvisoAutorizarStock proveedor="pexels" licencia="Pexels License" />);
    expect(screen.getByText(/uso libre, incluso comercial/i)).toBeInTheDocument();
    expect(screen.getByText(/Pexels License/i)).toBeInTheDocument();
    for (const riesgo of RIESGOS_STOCK_LIBRE) {
      expect(screen.getByText(riesgo)).toBeInTheDocument();
    }
    expect(screen.queryByText(/Bajo tu responsabilidad/i)).not.toBeInTheDocument();
  });

  it("atribucion (CC BY): exige crédito visible, sin aviso share-alike", () => {
    render(
      <AvisoAutorizarStock proveedor="wikimedia" licencia="CC BY 4.0" autor="Juan Foto" />,
    );
    expect(screen.getByText(/debes mantener el crédito visible/i)).toBeInTheDocument();
    expect(screen.getByText(/Juan Foto/)).toBeInTheDocument();
    expect(screen.queryByText(/misma licencia \(CC BY-SA\)/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Bajo tu responsabilidad/i)).not.toBeInTheDocument();
  });

  it("atribucion (CC BY-SA): añade el aviso de share-alike", () => {
    render(
      <AvisoAutorizarStock proveedor="wikimedia" licencia="CC BY-SA 4.0" autor="Ana" />,
    );
    expect(screen.getByText(/debes mantener el crédito visible/i)).toBeInTheDocument();
    expect(screen.getByText(/misma licencia \(CC BY-SA\)/i)).toBeInTheDocument();
  });

  it("restringida (NC): muestra el texto de responsabilidad", () => {
    render(<AvisoAutorizarStock proveedor="openverse" licencia="by-nc" />);
    expect(screen.getByText(/Bajo tu responsabilidad/i)).toBeInTheDocument();
    expect(screen.queryByText(/uso libre, incluso comercial/i)).not.toBeInTheDocument();
  });

  it("sin proveedor ni licencia: trata como restringida", () => {
    render(<AvisoAutorizarStock />);
    expect(screen.getByText(/Bajo tu responsabilidad/i)).toBeInTheDocument();
  });
});
