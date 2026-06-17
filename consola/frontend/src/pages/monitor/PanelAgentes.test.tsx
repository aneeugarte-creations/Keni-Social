/**
 * PanelAgentes · agentes independientes en CAJAS por tipo (no un pipeline).
 *
 * Herramientas NO es una secuencia: se agrupa por tipo y entre agentes NO hay conector (↓). Este
 * test fija que hay una caja por grupo, con sus agentes (columnas) dentro y solo dentro.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { GrupoAgentes } from "@/pages/maquina/fases";
import { PanelAgentes } from "@/pages/monitor/PanelAgentes";

function renderPanel(grupos: readonly GrupoAgentes[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PanelAgentes grupos={grupos} />
    </QueryClientProvider>,
  );
}

const GRUPOS: readonly GrupoAgentes[] = [
  {
    titulo: "Recibir",
    fases: [
      { nombre: "Notas", es_ia: true, claves: [], ayuda: "Notas y links", doc: "prompt/recibir/notas" },
      { nombre: "Portal", es_ia: true, claves: [], ayuda: "Portal/SMS", doc: "prompt/recibir/portal" },
    ],
  },
  {
    titulo: "Importar",
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

    // Cada agente cuelga de SU caja (y solo de la suya): «Recibir» trae Notas/Portal, no Parrilla.
    const cajaRecibir = screen.getByRole("heading", { name: "Recibir" }).closest("div")!;
    expect(within(cajaRecibir).getByText("Notas")).toBeInTheDocument();
    expect(within(cajaRecibir).getByText("Portal")).toBeInTheDocument();
    expect(within(cajaRecibir).queryByText("Parrilla")).not.toBeInTheDocument();

    // No es una secuencia: ningún conector (los chevron del pipeline llevan aria-hidden); aquí no hay
    // <ol> de fases. La superficie es la caja, no el pipeline.
    expect(screen.queryByTestId("panel-pipeline")).not.toBeInTheDocument();
    expect(screen.getByTestId("panel-agentes")).toBeInTheDocument();
  });
});
