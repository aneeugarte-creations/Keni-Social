/**
 * Tests del encuadre de sección con visibilidad INLINE (`Bloque`): ocultar/mostrar con su
 * propio toggle y, oculto, NO montar el contenido (deja una barra para restaurarlo in situ).
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { Bloque } from "./Bloque";
import { useVistaConfig } from "./vistaConfig";

beforeEach(() => {
  useVistaConfig.getState().reset();
});

describe("Bloque", () => {
  it("visible (con cabecera): muestra el contenido y permite ocultar", () => {
    render(
      <Bloque id="tendencia" conCabecera>
        <div data-testid="contenido" />
      </Bloque>,
    );
    expect(screen.getByTestId("contenido")).toBeInTheDocument();
    // El título sale fuera del contenido, en la cabecera.
    expect(screen.getByText("Tendencia diaria")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Ocultar sección" }));
    expect(useVistaConfig.getState().seccionVisible("tendencia")).toBe(false);
  });

  it("oculto: barra con título + Mostrar, sin montar el contenido", () => {
    useVistaConfig.getState().setSeccionVisible("tendencia", false);
    render(
      <Bloque id="tendencia">
        <div data-testid="contenido" />
      </Bloque>,
    );
    // El contenido NO se monta (así no se dispara su consulta).
    expect(screen.queryByTestId("contenido")).not.toBeInTheDocument();
    // El título permanece y hay un botón para volver a mostrarla.
    expect(screen.getByText("Tendencia diaria")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Mostrar Tendencia diaria" }));
    expect(useVistaConfig.getState().seccionVisible("tendencia")).toBe(true);
  });
});
