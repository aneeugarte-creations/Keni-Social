/**
 * PanelAgentes · agentes independientes en CAJAS por tipo (no un pipeline).
 *
 * Herramientas NO es una secuencia: se agrupa por tipo y entre agentes NO hay conector (↓). Este
 * test fija que hay una caja por grupo, con sus agentes (columnas) dentro y solo dentro.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { GrupoAgentes } from "@/pages/maquina/fases";
import { PanelAgentes } from "@/pages/monitor/PanelAgentes";

function renderPanel(grupos: readonly GrupoAgentes[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PanelAgentes grupos={grupos} proceso="herramientas" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const GRUPOS: readonly GrupoAgentes[] = [
  {
    titulo: "Recibir",
    descripcion: "Material que llega del equipo",
    fases: [
      { nombre: "Notas", es_ia: true, claves: [], ayuda: "Notas y links", doc: "prompt/recibir/notas" },
      { nombre: "Portal", es_ia: true, claves: [], ayuda: "Portal/SMS", doc: "prompt/recibir/portal" },
    ],
  },
  {
    titulo: "Importar",
    descripcion: "Calendarios y parrillas",
    fases: [
      { nombre: "Parrilla", es_ia: true, claves: [], ayuda: "Importa una parrilla", doc: "prompt/importar/parrilla" },
    ],
  },
];

describe("PanelAgentes", () => {
  it("pinta una caja por tipo con sus agentes dentro y SIN conector de pipeline", () => {
    renderPanel(GRUPOS);

    // Los títulos de tipo aparecen como cabecera de cada caja.
    expect(screen.getByRole("heading", { name: "Recibir" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Importar" })).toBeInTheDocument();

    // Subtítulo de la caja (qué cubre el tipo).
    expect(screen.getByText("Material que llega del equipo")).toBeInTheDocument();

    // Cada agente cuelga de SU caja (y solo de la suya): «Recibir» trae Notas/Portal, no Parrilla.
    // (`.closest("div")` da la cabecera título+subtítulo; su padre es la caja.)
    const cajaRecibir = screen.getByRole("heading", { name: "Recibir" }).closest("div")!.parentElement!;
    expect(within(cajaRecibir).getByText("Notas")).toBeInTheDocument();
    expect(within(cajaRecibir).getByText("Portal")).toBeInTheDocument();
    expect(within(cajaRecibir).queryByText("Parrilla")).not.toBeInTheDocument();

    // No es una secuencia: ningún conector (los chevron del pipeline llevan aria-hidden); aquí no hay
    // <ol> de fases. La superficie es la caja, no el pipeline.
    expect(screen.queryByTestId("panel-pipeline")).not.toBeInTheDocument();
    expect(screen.getByTestId("panel-agentes")).toBeInTheDocument();
  });

  it("clicar un agente NAVEGA a su subpágina (no abre un pop-up)", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/maquina/contexto?proceso=desarrollo"]}>
          <Routes>
            <Route
              path="/maquina/contexto"
              element={<PanelAgentes grupos={GRUPOS} proceso="desarrollo" />}
            />
            <Route path="/maquina/contexto/:proceso/:fase" element={<p>subpágina</p>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // No hay diálogo/pop-up: la superficie es la caja, y al clicar se cambia de ruta.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Notas").closest("button")!);
    expect(screen.getByText("subpágina")).toBeInTheDocument();
  });
});
