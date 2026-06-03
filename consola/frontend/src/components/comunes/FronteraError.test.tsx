/**
 * Tests para FronteraError — frontera de error (error boundary) de la app.
 *
 * Verifica que:
 *  - Si los hijos renderizan bien, los muestra tal cual.
 *  - Si un hijo lanza un TypeError, muestra el fallback de "página con problema"
 *    (aislando el fallo en vez de dejar la app en blanco) y permite reintentar.
 *  - Si el error es un fallo de carga de chunk (deploy nuevo), recarga SOLA.
 *  - Si ya recargó hace nada (sospecha de bucle), cae al botón manual.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FronteraError } from "./FronteraError";

/** Componente que lanza al renderizar, para disparar la frontera. */
function Explota({ mensaje }: { mensaje: string }): JSX.Element {
  throw new Error(mensaje);
}

const ERROR_CHUNK = "Failed to fetch dynamically imported module: /assets/Panel-abc.js";

describe("FronteraError", () => {
  let reload: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    try {
      sessionStorage.clear();
    } catch {
      /* sin sessionStorage en el entorno: el guard simplemente no persiste */
    }
    // jsdom no implementa navegación: sustituimos `reload` por un espía.
    reload = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, reload },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

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
    expect(reload).not.toHaveBeenCalled();
    espia.mockRestore();
  });

  it("ante un fallo de chunk (deploy nuevo) recarga automáticamente", () => {
    const espia = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <FronteraError>
        <Explota mensaje={ERROR_CHUNK} />
      </FronteraError>,
    );
    expect(reload).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/actualizando/i)).toBeInTheDocument();
    espia.mockRestore();
  });

  it("si ya recargó hace nada (bucle), ofrece recargar a mano en vez de insistir", () => {
    const espia = vi.spyOn(console, "error").mockImplementation(() => {});
    // Marca una recarga reciente: el guard anti-bucle debe suprimir la automática.
    sessionStorage.setItem("keni:ultima-recarga-auto", String(Date.now()));
    render(
      <FronteraError>
        <Explota mensaje={ERROR_CHUNK} />
      </FronteraError>,
    );
    expect(reload).not.toHaveBeenCalled();
    expect(screen.getByText("Hay una versión nueva de la consola")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /recargar la app/i })).toBeInTheDocument();
    espia.mockRestore();
  });
});
