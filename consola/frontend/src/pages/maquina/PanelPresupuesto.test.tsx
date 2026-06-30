import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { GateDiarioIA, PresupuestoIA } from "@/types";

import { PanelPresupuesto } from "./cola-comun";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function gate(parcial: Partial<GateDiarioIA> = {}): GateDiarioIA {
  return {
    cuenta: "a",
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
    ritmo: 100,
    ritmo_global: 100,
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
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

// Modo "una marca": el back manda `gate_diario` (el bloque de la cuenta de esa marca).
describe("PanelPresupuesto · gate diario por % · modo una marca", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("sin pausa ni datos del % no pinta el gate diario", () => {
    renderConProviders(
      <PanelPresupuesto presupuesto={presupuesto({ marca: "unotv", gate_diario: gate() })} esAdmin />,
    );
    expect(screen.queryByText(/consumo del día/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Aceptar continuar/i)).not.toBeInTheDocument();
  });

  it("pausado por % muestra la pantalla y el botón Aceptar +10% (admin) y al pulsarlo llama al endpoint con la cuenta", async () => {
    const aceptar = vi
      .spyOn(api, "gateDiarioAceptar")
      .mockResolvedValue(
        gate({ cuenta: "b", consumo_hoy_pct: 16, umbral_pct: 24.3, aceptados_hoy: 1, pausado_por_pct: false }),
      );
    renderConProviders(
      <PanelPresupuesto
        presupuesto={presupuesto({
          marca: "unotv",
          nivel: "pausado",
          gate_diario: gate({ cuenta: "b", consumo_hoy_pct: 16, umbral_pct: 14.3, pausado_por_pct: true }),
        })}
        esAdmin
      />,
    );
    expect(screen.getByText(/Generación pausada por el consumo del día \(cuenta B\)/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Aceptar continuar \(\+10%\)/i }));
    await waitFor(() => expect(aceptar).toHaveBeenCalledWith("b"));
  });

  it("pausado por % a un NO-admin: ve la pausa pero ningún botón de aceptar", () => {
    renderConProviders(
      <PanelPresupuesto
        presupuesto={presupuesto({
          marca: "unotv",
          nivel: "pausado",
          gate_diario: gate({ cuenta: "b", consumo_hoy_pct: 16, umbral_pct: 14.3, pausado_por_pct: true }),
        })}
        esAdmin={false}
      />,
    );
    expect(screen.getByText(/Generación pausada por el consumo del día/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Aceptar continuar/i })).not.toBeInTheDocument();
    expect(screen.getByText(/administrador puede aceptar \+10%/i)).toBeInTheDocument();
  });

  it("con datos del % sin pausa muestra una línea discreta de consumo del día (con la cuenta)", () => {
    renderConProviders(
      <PanelPresupuesto
        presupuesto={presupuesto({
          marca: "unotv",
          gate_diario: gate({ cuenta: "b", consumo_hoy_pct: 9.5, umbral_pct: 14.3 }),
        })}
        esAdmin
      />,
    );
    expect(screen.getByText(/Consumo de hoy \(cuenta B\): 9.5% del límite semanal/i)).toBeInTheDocument();
  });
});

// Modo "Todas" (sin marca): el back manda `gate_diario` null y `gate_diario_cuentas` con ambas.
// Solo se pintan los avisos de las cuentas GATEADAS; cada «Aceptar» actúa sobre SU cuenta.
describe("PanelPresupuesto · gate diario por % · modo Todas", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("pausa solo la cuenta B: muestra el aviso de B, no el de A, y aceptar usa la cuenta B", async () => {
    const aceptar = vi.spyOn(api, "gateDiarioAceptar").mockResolvedValue(gate({ cuenta: "b" }));
    renderConProviders(
      <PanelPresupuesto
        presupuesto={presupuesto({
          marca: "",
          gate_diario: null,
          gate_diario_cuentas: {
            a: gate({ cuenta: "a", consumo_hoy_pct: 5, pausado_por_pct: false }),
            b: gate({ cuenta: "b", consumo_hoy_pct: 16, umbral_pct: 14.3, pausado_por_pct: true }),
          },
        })}
        esAdmin
      />,
    );
    expect(screen.getByText(/Generación pausada por el consumo del día \(cuenta B\)/i)).toBeInTheDocument();
    expect(screen.queryByText(/\(cuenta A\)/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Aceptar continuar \(\+10%\)/i }));
    await waitFor(() => expect(aceptar).toHaveBeenCalledWith("b"));
  });

  it("ambas cuentas gateadas: dos avisos, uno por cuenta", () => {
    renderConProviders(
      <PanelPresupuesto
        presupuesto={presupuesto({
          marca: "",
          gate_diario: null,
          gate_diario_cuentas: {
            a: gate({ cuenta: "a", consumo_hoy_pct: 20, umbral_pct: 14.3, pausado_por_pct: true }),
            b: gate({ cuenta: "b", consumo_hoy_pct: 30, umbral_pct: 14.3, pausado_por_pct: true }),
          },
        })}
        esAdmin
      />,
    );
    expect(screen.getByText(/Generación pausada por el consumo del día \(cuenta A\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Generación pausada por el consumo del día \(cuenta B\)/i)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Aceptar continuar \(\+10%\)/i })).toHaveLength(2);
  });

  it("ninguna cuenta gateada: no pinta avisos del gate diario", () => {
    renderConProviders(
      <PanelPresupuesto
        presupuesto={presupuesto({
          marca: "",
          gate_diario: null,
          gate_diario_cuentas: {
            a: gate({ cuenta: "a", consumo_hoy_pct: 5, pausado_por_pct: false }),
            b: gate({ cuenta: "b", consumo_hoy_pct: 8, pausado_por_pct: false }),
          },
        })}
        esAdmin
      />,
    );
    expect(screen.queryByText(/consumo del día/i)).not.toBeInTheDocument();
  });
});

// Trabajo pendiente: el coste estimado de vaciar el backlog (lo que costará generar lo que espera).
describe("PanelPresupuesto · trabajo pendiente", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("muestra los tokens y el coste pendientes cuando se pasa `estimadoPendiente`", () => {
    renderConProviders(
      <PanelPresupuesto
        presupuesto={presupuesto({ marca: "" })}
        esAdmin
        estimadoPendiente={{ tokens: 1_200_000, coste_usd: 4.2 }}
      />,
    );
    expect(
      screen.getByText(/Trabajo pendiente: ~1\.2\s*M tokens · USD\s*4\.20\s*estimado/i),
    ).toBeInTheDocument();
  });

  it("sin trabajo pendiente (todo a 0) no pinta la línea", () => {
    renderConProviders(
      <PanelPresupuesto
        presupuesto={presupuesto({ marca: "" })}
        esAdmin
        estimadoPendiente={{ tokens: 0, coste_usd: 0 }}
      />,
    );
    expect(screen.queryByText(/Trabajo pendiente/i)).not.toBeInTheDocument();
  });
});

// Dial de ritmo: la palanca protagonista del panel. El global siempre; el de la marca cuando hay
// marca activa. Al pulsar un nivel escribe la clave de ajuste correcta con `guardarAjuste`.
describe("PanelPresupuesto · dial de ritmo", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("en vista global, pulsar 50% escribe KENI_RITMO con valor 50", async () => {
    const guardar = vi
      .spyOn(api, "guardarAjuste")
      .mockResolvedValue({ ajuste: { clave: "KENI_RITMO", etiqueta: "Ritmo", valor: 50 } } as never);
    renderConProviders(
      <PanelPresupuesto presupuesto={presupuesto({ marca: "", ritmo_global: 100 })} esAdmin />,
    );
    const dial = screen.getByRole("group", { name: /Ritmo de producción \(global\)/i });
    fireEvent.click(within(dial).getByRole("button", { name: "50%" }));
    await waitFor(() => expect(guardar).toHaveBeenCalledWith({ clave: "KENI_RITMO", valor: 50 }));
  });

  it("con marca activa, su dial escribe KENI_RITMO::<marca>", async () => {
    const guardar = vi
      .spyOn(api, "guardarAjuste")
      .mockResolvedValue({ ajuste: { clave: "KENI_RITMO::unotv", etiqueta: "Ritmo", valor: 25 } } as never);
    renderConProviders(
      <PanelPresupuesto
        presupuesto={presupuesto({ marca: "unotv", ritmo: 100, ritmo_global: 100 })}
        esAdmin
        nombreMarca="UnoTV"
      />,
    );
    const dial = screen.getByRole("group", { name: /Ritmo de UnoTV/i });
    fireEvent.click(within(dial).getByRole("button", { name: "25%" }));
    await waitFor(() =>
      expect(guardar).toHaveBeenCalledWith({ clave: "KENI_RITMO::unotv", valor: 25 }),
    );
  });
});
