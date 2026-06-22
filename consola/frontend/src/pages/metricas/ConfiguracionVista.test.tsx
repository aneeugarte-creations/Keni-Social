/**
 * Tests del panel "Configurar vista": refleja y muta `vistaConfig` (visibilidad de
 * secciones) y "Restablecer" vuelve al estado por defecto.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { ConfiguracionVista } from "./ConfiguracionVista";
import { useVistaConfig } from "./vistaConfig";

beforeEach(() => {
  useVistaConfig.getState().reset();
});

function abrir() {
  render(<ConfiguracionVista />);
  fireEvent.click(screen.getByRole("button", { name: "Configurar vista" }));
}

describe("ConfiguracionVista — secciones", () => {
  it("arranca con todas las secciones marcadas (visibles por defecto)", () => {
    abrir();
    expect(screen.getByRole("checkbox", { name: "Comparativa y detalle por marca" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("desmarcar una sección la oculta en el store", () => {
    abrir();
    fireEvent.click(screen.getByRole("checkbox", { name: "Publicidad pagada" }));
    expect(useVistaConfig.getState().seccionVisible("ads")).toBe(false);
  });

  it("'Restablecer' vuelve todo a visible", () => {
    useVistaConfig.getState().setSeccionVisible("ads", false);
    abrir();
    fireEvent.click(screen.getByRole("button", { name: /Restablecer/ }));
    expect(useVistaConfig.getState().seccionVisible("ads")).toBe(true);
  });
});

describe("ConfiguracionVista — columnas", () => {
  /** Abre el diálogo, va a la pestaña Columnas y devuelve el fieldset de una tabla. */
  function abrirColumnas(tituloTabla: string) {
    abrir();
    // Radix Tabs (modo automático) activa la pestaña al enfocarla.
    const tab = screen.getByRole("tab", { name: "Columnas" });
    tab.focus();
    fireEvent.focus(tab);
    return within(screen.getByText(tituloTabla).closest("fieldset")!);
  }

  it("desmarcar una columna la añade a las ocultas de esa tabla", () => {
    const tabla = abrirColumnas("Detalle por marca");
    fireEvent.click(tabla.getByRole("checkbox", { name: "Interacciones" }));
    expect(useVistaConfig.getState().columnas.cuentas.ocultas).toContain("interacciones");
  });

  it("'Bajar' reordena la columna en la config de esa tabla", () => {
    const tabla = abrirColumnas("Detalle por marca");
    fireEvent.click(tabla.getByRole("button", { name: "Bajar Marca" }));
    const orden = useVistaConfig.getState().columnas.cuentas.orden;
    // Marca pasa de la posición 0 a la 1 (intercambio con Vistas).
    expect(orden.indexOf("marca")).toBe(1);
    expect(orden[0]).toBe("visualizaciones");
  });
});
