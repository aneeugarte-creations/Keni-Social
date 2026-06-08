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

describe("SubnavHub", () => {
  it("pinta las pestañas de un hub (Investigación: Noticias / Contenidos / Fuentes)", () => {
    renderSubnav("/datos/investigacion", null);
    expect(screen.getByRole("link", { name: /noticias/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /contenidos/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /fuentes/i })).toBeInTheDocument();
  });

  it("no pinta nada en una página plana (Turnos ya no es un hub con pestañas)", () => {
    const { container } = renderSubnav("/operacion/turnos", null);
    expect(container).toBeEmptyDOMElement();
  });

  it("no pinta nada en Programación (página plana, sin sub-pestañas)", () => {
    const { container } = renderSubnav("/operacion/programacion", "unotv");
    expect(container).toBeEmptyDOMElement();
  });
});
