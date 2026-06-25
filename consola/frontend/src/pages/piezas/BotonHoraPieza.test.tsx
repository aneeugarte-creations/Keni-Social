import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BotonHoraPieza } from "./BotonHoraPieza";

/** Abre el popover de hora (el chip de la hora es un botón con `title` estable). */
function abrirPopover() {
  fireEvent.click(screen.getByTitle("Cambiar la hora de este post"));
}

describe("BotonHoraPieza — sugerencia de mejor hora", () => {
  it("muestra la sugerencia cuando hay horaSugerida distinta de la actual", () => {
    render(
      <BotonHoraPieza
        iso="2026-06-15T18:00"
        ocupado={false}
        horaSugerida="19:15"
        onGuardar={vi.fn()}
        onOtroDia={vi.fn()}
      />,
    );
    abrirPopover();
    expect(
      screen.getByRole("button", { name: "Usar la mejor hora para publicar: 19:15" }),
    ).toBeInTheDocument();
    expect(screen.getByText("19:15")).toBeInTheDocument();
  });

  it("al aceptar la sugerencia guarda esa hora", () => {
    const onGuardar = vi.fn();
    render(
      <BotonHoraPieza
        iso="2026-06-15T18:00"
        ocupado={false}
        horaSugerida="19:15"
        onGuardar={onGuardar}
        onOtroDia={vi.fn()}
      />,
    );
    abrirPopover();
    fireEvent.click(
      screen.getByRole("button", { name: "Usar la mejor hora para publicar: 19:15" }),
    );
    expect(onGuardar).toHaveBeenCalledWith("19:15");
  });

  it("no muestra sugerencia cuando horaSugerida es null", () => {
    render(
      <BotonHoraPieza
        iso="2026-06-15T18:00"
        ocupado={false}
        horaSugerida={null}
        onGuardar={vi.fn()}
        onOtroDia={vi.fn()}
      />,
    );
    abrirPopover();
    expect(screen.queryByText(/Mejor hora/)).not.toBeInTheDocument();
  });

  it("no muestra sugerencia cuando coincide con la hora ya programada", () => {
    // 18:00 UTC se proyecta a 12:00 CDMX; sugerir esa misma hora no aporta nada.
    render(
      <BotonHoraPieza
        iso="2026-06-15T18:00"
        ocupado={false}
        horaSugerida="12:00"
        onGuardar={vi.fn()}
        onOtroDia={vi.fn()}
      />,
    );
    abrirPopover();
    expect(screen.queryByText(/Mejor hora/)).not.toBeInTheDocument();
  });
});
