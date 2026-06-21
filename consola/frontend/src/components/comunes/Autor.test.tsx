import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Autor } from "./Autor";
import { AUTOR_DESCONOCIDO, etiquetaAutor } from "./atribucion";

/**
 * Atribución por usuario: "por <usuario>", con "desconocido" para
 * registros legados/anónimos. Cubre el helper de etiqueta y el render del badge.
 */
describe("etiquetaAutor", () => {
  it("muestra 'por <usuario>' cuando hay nombre", () => {
    expect(etiquetaAutor("ana")).toBe("por ana");
  });

  it("cae a 'por desconocido' cuando el nombre es vacío/nulo (legado/anónimo)", () => {
    expect(etiquetaAutor("")).toBe(`por ${AUTOR_DESCONOCIDO}`);
    expect(etiquetaAutor(null)).toBe(`por ${AUTOR_DESCONOCIDO}`);
    expect(etiquetaAutor(undefined)).toBe(`por ${AUTOR_DESCONOCIDO}`);
  });

  it("recorta espacios; un nombre en blanco cuenta como sin autor", () => {
    expect(etiquetaAutor("  ane  ")).toBe("por ane");
    expect(etiquetaAutor("   ")).toBe(`por ${AUTOR_DESCONOCIDO}`);
  });
});

describe("Autor", () => {
  it("renderiza el autor cuando viene", () => {
    const { container } = render(<Autor nombre="ane" />);
    expect(container.textContent).toContain("por ane");
  });

  it("renderiza 'desconocido' para un registro sin autor", () => {
    const { container } = render(<Autor nombre="" />);
    expect(container.textContent).toContain(`por ${AUTOR_DESCONOCIDO}`);
  });

  it("sin prefijo (conPrefijo=false) muestra solo el nombre, sin 'por' (p. ej. el feed)", () => {
    const { container } = render(<Autor nombre="ane" conPrefijo={false} />);
    expect(container.textContent).toContain("ane");
    expect(container.textContent).not.toContain("por");
  });

  it("sin prefijo y sin autor cae a 'desconocido' (sin 'por')", () => {
    const { container } = render(<Autor nombre="" conPrefijo={false} />);
    expect(container.textContent).toContain(AUTOR_DESCONOCIDO);
    expect(container.textContent).not.toContain("por");
  });
});
