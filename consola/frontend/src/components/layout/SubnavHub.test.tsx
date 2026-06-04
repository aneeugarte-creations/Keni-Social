import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { MarcaActivaContexto, type ValorMarcaActiva } from "@/hooks/marca-activa-contexto";

import { SubnavHub } from "./SubnavHub";

/** Valor mínimo del contexto de marca activa (SubnavHub solo lee `marcaActiva`). */
function valorMarca(marcaActiva: string | null): ValorMarcaActiva {
  return {
    marcaActiva,
    marcaPrimaria: marcaActiva,
    enMarcaPrimaria: true,
    esMultiMarca: true,
    puedeTodas: true,
    marcasParaSwitch: [],
    nombreActiva: null,
    cambiarMarca: () => {},
    volverAPrimaria: () => {},
  };
}

function renderSubnav(ruta: string, marcaActiva: string | null) {
  return render(
    <MarcaActivaContexto.Provider value={valorMarca(marcaActiva)}>
      <MemoryRouter initialEntries={[ruta]}>
        <SubnavHub />
      </MemoryRouter>
    </MarcaActivaContexto.Provider>,
  );
}

describe("SubnavHub · gating de Turnos por marca", () => {
  it("Claro Sports ve Programación y Turnos", () => {
    renderSubnav("/operacion/calendario/calendario", "claro-sports");
    expect(screen.getByRole("link", { name: /programación/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /turnos/i })).toBeInTheDocument();
  });

  it("otra marca (UnoTV) NO ve Turnos; al quedar una sola pestaña, no se pinta la barra", () => {
    renderSubnav("/operacion/calendario/calendario", "unotv");
    expect(screen.queryByRole("link", { name: /turnos/i })).not.toBeInTheDocument();
    // Programación es la única pestaña que queda → SubnavHub no renderiza la barra.
    expect(screen.queryByRole("link", { name: /programación/i })).not.toBeInTheDocument();
  });

  it("'Todas' (admin, marcaActiva null) ve Turnos", () => {
    renderSubnav("/operacion/calendario/calendario", null);
    expect(screen.getByRole("link", { name: /turnos/i })).toBeInTheDocument();
  });
});
