import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { GateDiarioIA, PresupuestoIA } from "@/types";

import { PanelPresupuesto } from "./cola-comun";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function gate(parcial: Partial<GateDiarioIA> = {}): GateDiarioIA {
  return {
    consumo_hoy_pct: null,
    umbral_pct: 14.3,
    aceptados_hoy: 0,
    pausado_por_pct: false,
    base_umbral_pct: 14.3,
    paso_pct: 10,
    dia: "2026-06-28",
    ...parcial,
  };
}

function presupuesto(parcial: Partial<PresupuestoIA> = {}): PresupuestoIA {
  return {
    marca: "",
    nivel: "normal",
    pausada: false,
    presupuesto_tokens_dia: 0,
    presupuesto_usd_dia: 0,
    margen_manual_pct: 20,
    gastado: { tokens: 0, tokens_in: 0, tokens_out: 0, coste_usd: 0, generaciones: 0 },
    restante_tokens: null,
    pct_usado: null,
    pct_usado_usd: null,
    proyeccion_usd_dia: null,
    pct_proyectado_usd: null,
    dia: "2026-06-28",
    ...parcial,
  };
}

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("PanelPresupuesto · gate diario por %", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("sin pausa ni datos del % no pinta el gate diario", () => {
    renderConProviders(
      <PanelPresupuesto presupuesto={presupuesto({ gate_diario: gate() })} esAdmin />,
    );
    expect(screen.queryByText(/consumo del día/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Aceptar continuar/i)).not.toBeInTheDocument();
  });

  it("pausado por % muestra la pantalla y el botón Aceptar +10% (admin) y al pulsarlo llama al endpoint", async () => {
    const aceptar = vi
      .spyOn(api, "gateDiarioAceptar")
      .mockResolvedValue(gate({ consumo_hoy_pct: 16, umbral_pct: 24.3, aceptados_hoy: 1, pausado_por_pct: false }));
    renderConProviders(
      <PanelPresupuesto
        presupuesto={presupuesto({
          nivel: "pausado",
          gate_diario: gate({ consumo_hoy_pct: 16, umbral_pct: 14.3, pausado_por_pct: true }),
        })}
        esAdmin
      />,
    );
    expect(screen.getByText(/Generación pausada por el consumo del día/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Aceptar continuar \(\+10%\)/i }));
    await waitFor(() => expect(aceptar).toHaveBeenCalledTimes(1));
  });

  it("pausado por % a un NO-admin: ve la pausa pero ningún botón de aceptar", () => {
    renderConProviders(
      <PanelPresupuesto
        presupuesto={presupuesto({
          nivel: "pausado",
          gate_diario: gate({ consumo_hoy_pct: 16, umbral_pct: 14.3, pausado_por_pct: true }),
        })}
        esAdmin={false}
      />,
    );
    expect(screen.getByText(/Generación pausada por el consumo del día/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Aceptar continuar/i })).not.toBeInTheDocument();
    expect(screen.getByText(/administrador puede aceptar \+10%/i)).toBeInTheDocument();
  });

  it("con datos del % sin pausa muestra una línea discreta de consumo del día", () => {
    renderConProviders(
      <PanelPresupuesto
        presupuesto={presupuesto({ gate_diario: gate({ consumo_hoy_pct: 9.5, umbral_pct: 14.3 }) })}
        esAdmin
      />,
    );
    expect(screen.getByText(/Consumo de hoy: 9.5% del límite semanal/i)).toBeInTheDocument();
  });
});
