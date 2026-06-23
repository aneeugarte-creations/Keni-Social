/**
 * Tests del encuadre UNIFORME (`Seccion`): título FUERA del contenido, toggle de ocultar
 * siempre, y editor de campos (kebab) solo cuando la sección declara columnas.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { metaColumnas, TABLA_REDES } from "./columnasMeta";
import { Seccion } from "./Seccion";
import { useVistaConfig } from "./vistaConfig";

beforeEach(() => {
  useVistaConfig.getState().reset();
});

describe("Seccion", () => {
  it("pinta el título fuera del contenido y permite ocultar", () => {
    render(
      <Seccion id="tendencia" titulo="Tendencia diaria">
        <div data-testid="contenido" />
      </Seccion>,
    );
    expect(screen.getByRole("heading", { name: "Tendencia diaria" })).toBeInTheDocument();
    expect(screen.getByTestId("contenido")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Ocultar sección" }));
    expect(useVistaConfig.getState().seccionVisible("tendencia")).toBe(false);
  });

  it("sin columnas no muestra el editor de campos", () => {
    render(
      <Seccion id="tendencia" titulo="Tendencia diaria">
        <div />
      </Seccion>,
    );
    expect(screen.queryByRole("button", { name: "Campos" })).not.toBeInTheDocument();
  });

  it("con columnas muestra el editor de campos", () => {
    render(
      <Seccion id="red-detalle" titulo="Detalle por red" tablaId={TABLA_REDES} columnas={metaColumnas(TABLA_REDES)}>
        <div />
      </Seccion>,
    );
    expect(screen.getByRole("button", { name: "Campos" })).toBeInTheDocument();
  });
});
