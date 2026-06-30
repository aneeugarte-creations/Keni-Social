import { fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { SelectorHoras } from "./SelectorHoras";

/** Envoltorio con estado: refleja el value para poder comprobar las chips tras cada cambio. */
function Controlado({ inicial }: { inicial: string }) {
  const [v, setV] = React.useState(inicial);
  return <SelectorHoras value={v} onChange={setV} ariaLabel="Horas" />;
}

const ETIQUETA_CAMPO = "Hora (CDMX): teclea o elige";

describe("SelectorHoras", () => {
  it("pinta las horas del value como chips", () => {
    render(<SelectorHoras value="08:45, 12:00" onChange={() => {}} ariaLabel="Horas" />);
    expect(screen.getByText("08:45")).toBeInTheDocument();
    expect(screen.getByText("12:00")).toBeInTheDocument();
  });

  it("teclear una hora y pulsar Enter la añade (redondeada a 5 min)", () => {
    render(<Controlado inicial="08:45" />);
    fireEvent.click(screen.getByRole("button", { name: "Añadir hora" }));
    const campo = screen.getByLabelText(ETIQUETA_CAMPO);
    fireEvent.change(campo, { target: { value: "1043" } });
    fireEvent.keyDown(campo, { key: "Enter" });
    // Aseveramos por la × de la chip (su nombre es único; en la lista «10:45» también aparece).
    expect(screen.getByRole("button", { name: "Quitar 10:45" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Quitar 08:45" })).toBeInTheDocument();
  });

  it("elegir una hora de la lista desplegable la añade", () => {
    const onChange = vi.fn();
    render(<SelectorHoras value="" onChange={onChange} ariaLabel="Horas" />);
    fireEvent.click(screen.getByRole("button", { name: "Añadir hora" }));
    const opcion = document.querySelector('[data-hora="12:00"]') as HTMLElement;
    expect(opcion).not.toBeNull();
    fireEvent.mouseDown(opcion);
    expect(onChange).toHaveBeenCalledWith("12:00");
  });

  it("la × de una chip quita esa hora", () => {
    render(<Controlado inicial="08:45, 12:00" />);
    fireEvent.click(screen.getByRole("button", { name: "Quitar 08:45" }));
    expect(screen.queryByText("08:45")).not.toBeInTheDocument();
    expect(screen.getByText("12:00")).toBeInTheDocument();
  });

  it("una hora fuera de rango no se añade", () => {
    const onChange = vi.fn();
    render(<SelectorHoras value="" onChange={onChange} ariaLabel="Horas" />);
    fireEvent.click(screen.getByRole("button", { name: "Añadir hora" }));
    const campo = screen.getByLabelText(ETIQUETA_CAMPO);
    fireEvent.change(campo, { target: { value: "99" } });
    fireEvent.keyDown(campo, { key: "Enter" });
    expect(onChange).not.toHaveBeenCalled();
  });
});
