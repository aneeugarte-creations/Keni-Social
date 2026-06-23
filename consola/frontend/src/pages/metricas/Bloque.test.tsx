/**
 * Tests del GATE de sección (`Bloque`): visible monta el contenido; oculto NO lo monta
 * (deja una barra fina con el título y un botón "Mostrar" para restaurarlo in situ).
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { Bloque } from "./Bloque";
import { useVistaConfig } from "./vistaConfig";

beforeEach(() => {
  useVistaConfig.getState().reset();
});

describe("Bloque", () => {
  it("visible: monta el contenido", () => {
    render(
      <Bloque id="tendencia">
        <div data-testid="contenido" />
      </Bloque>,
    );
    expect(screen.getByTestId("contenido")).toBeInTheDocument();
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
    // La barra fina conserva el título y ofrece "Mostrar" para restaurarla.
    expect(screen.getByText("Tendencia diaria")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Mostrar Tendencia diaria" }));
    expect(useVistaConfig.getState().seccionVisible("tendencia")).toBe(true);
  });
});
