import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { EstadoMetricas } from "@/types";

import { BotonActualizar } from "./BotonActualizar";

// El toast de error del disparo fallido no necesita el <Toaster /> montado: lo
// mockeamos para poder asertar que se avisa (y evitar efectos colaterales).
vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import { toast } from "sonner";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

beforeEach(() => {
  vi.clearAllMocks();
});

const GENERADO_EN = "2026-06-10T08:00:00";

// Estado "refresco en marcha" cuyo generado_en NO ha avanzado aún: el polling sigue.
const ESTADO_CORRIENDO: EstadoMetricas = {
  corriendo: true,
  iniciado_en: "2026-06-10T08:05:00",
  terminado_en: "",
  ultimo_error: "",
  generado_en: GENERADO_EN,
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("BotonActualizar", () => {
  it("deshabilita el botón mientras no hay rango que refrescar", () => {
    renderConProviders(<BotonActualizar />);
    expect(screen.getByRole("button", { name: /actualizar/i })).toBeDisabled();
  });

  it("dispara el refresco del combo (rango, marca) y muestra «Actualizando…» (aria-live)", async () => {
    const refrescar = vi
      .spyOn(api, "metricasRefrescar")
      .mockResolvedValue(ESTADO_CORRIENDO);
    vi.spyOn(api, "metricasEstado").mockResolvedValue(ESTADO_CORRIENDO);
    renderConProviders(
      <BotonActualizar rango="semana" marca="unotv" generadoEn={GENERADO_EN} />,
    );

    const boton = screen.getByRole("button", { name: /actualizar/i });
    expect(boton).toBeEnabled();
    fireEvent.click(boton);

    expect(refrescar).toHaveBeenCalledWith({ rango: "semana", marca: "unotv" });
    const aviso = await screen.findByText("Actualizando…");
    expect(aviso).toHaveAttribute("aria-live", "polite");
    // Mientras refresca, el botón queda deshabilitado (no se dispara dos veces).
    await waitFor(() => expect(boton).toBeDisabled());
  });

  it("vuelve al estado normal (y avisa) si el POST de refresco falla", async () => {
    vi.spyOn(api, "metricasRefrescar").mockRejectedValue(new Error("sin conexión"));
    renderConProviders(
      <BotonActualizar rango="semana" marca="unotv" generadoEn={GENERADO_EN} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /actualizar/i }));

    // El disparo falló: se avisa con toast y NO se queda en «Actualizando…».
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("sin conexión"));
    await waitFor(() =>
      expect(screen.queryByText("Actualizando…")).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /actualizar/i })).toBeEnabled();
  });
});
