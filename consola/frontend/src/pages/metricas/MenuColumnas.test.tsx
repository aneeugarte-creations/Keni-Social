/**
 * Tests del kebab de COLUMNAS inline (sustituye a la pestaña "Columnas" del antiguo panel
 * macro): mostrar/ocultar y reordenar columnas, persistido en `vistaConfig.columnas[tabla]`.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { metaColumnas, TABLA_REDES } from "./columnasMeta";
import { MenuColumnas } from "./MenuColumnas";
import { useVistaConfig } from "./vistaConfig";

const COLS = metaColumnas(TABLA_REDES);

beforeEach(() => {
  useVistaConfig.getState().reset();
});

describe("MenuColumnas", () => {
  it("oculta una columna y lo persiste en vistaConfig", () => {
    render(<MenuColumnas tablaId={TABLA_REDES} columnas={COLS} />);
    fireEvent.click(screen.getByRole("button", { name: "Campos" }));

    fireEvent.click(screen.getByLabelText("Interacciones"));
    expect(useVistaConfig.getState().columnas[TABLA_REDES].ocultas).toContain("interacciones");
  });

  it("reordena una columna con las flechas", () => {
    render(<MenuColumnas tablaId={TABLA_REDES} columnas={COLS} />);
    fireEvent.click(screen.getByRole("button", { name: "Campos" }));

    // "Red" es la primera columna; bajarla la lleva a la segunda posición.
    fireEvent.click(screen.getByRole("button", { name: "Bajar Red" }));
    const orden = useVistaConfig.getState().columnas[TABLA_REDES].orden;
    expect(orden[0]).not.toBe("red");
    expect(orden[1]).toBe("red");
  });
});
