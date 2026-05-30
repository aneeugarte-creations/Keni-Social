/**
 * Tests para FronteraError — frontera de error (error boundary) de la app.
 *
 * Verifica que:
 *  - Si los hijos renderizan bien, los muestra tal cual.
 *  - Si un hijo lanza un TypeError, muestra el fallback de "página con problema"
 *    (aislando el fallo en vez de dejar la app en blanco) y permite reintentar.
 *  - Si el error es un fallo de carga de chunk (deploy nuevo), muestra el mensaje
 *    de "versión nueva" con el botón de recargar.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FronteraError } from "./FronteraError";

/** Componente que lanza al renderizar, para disparar la frontera. */
function Explota({ mensaje }: { mensaje: string }): JSX.Element {
  throw new Error(mensaje);
}

describe("FronteraError", () => {
  it("renderiza los hijos cuando no hay error", () => {
    render(
      <FronteraError>
        <p>contenido ok</p>
      </FronteraError>,
    );
    expect(screen.getByText("contenido ok")).toBeInTheDocument();
  });

  it("muestra el fallback de página ante un TypeError de render", () => {
    // Silencia el console.error que React emite al atrapar el error.
    const espia = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <FronteraError>
        <Explota mensaje="Cannot read properties of undefined (reading 'x')" />
      </FronteraError>,
    );
    expect(screen.getByText("Esta página tuvo un problema")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reintentar/i })).toBeInTheDocument();
    espia.mockRestore();
  });

  it("detecta el fallo de chunk de un deploy y ofrece recargar", () => {
    const espia = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <FronteraError>
        <Explota mensaje="Failed to fetch dynamically imported module: /assets/Panel-abc.js" />
      </FronteraError>,
    );
    expect(screen.getByText("Hay una versión nueva de la consola")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /recargar la app/i })).toBeInTheDocument();
    espia.mockRestore();
  });
});
