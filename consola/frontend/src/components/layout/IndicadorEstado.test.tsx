import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IndicadorEstado } from "@/components/layout/IndicadorEstado";
import type { RespuestaEstado } from "@/types";

/**
 * Test del indicador de salud de la topbar (issue #88). Cubre: el punto refleja
 * el peor chequeo (aria-label por nivel), el popover abre con el detalle y se
 * mantiene cerrado al inicio, y el camino de error de la API.
 */

const DATOS_AVISO: RespuestaEstado = {
  resultados: [
    { estado: "ok", nombre: "Python", detalle: "Versión compatible", icono: "✅" },
    { estado: "aviso", nombre: "Credenciales", detalle: "Faltan algunas", icono: "⚠️" },
  ],
  resumen: "Casi listo: revisa un detalle.",
  siguiente_paso: "Configura tus credenciales en Configuración.",
};

const DATOS_ERROR: RespuestaEstado = {
  resultados: [
    { estado: "ok", nombre: "Python", detalle: "Versión compatible", icono: "✅" },
    { estado: "error", nombre: "Fuente", detalle: "No se pudo construir", icono: "❌" },
  ],
  resumen: "Hay un problema que impide trabajar.",
  siguiente_paso: "Revisa la fuente de datos.",
};

function renderConQuery(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("IndicadorEstado", () => {
  it("el punto refleja el peor chequeo (aviso) y abre el popover con el detalle", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(DATOS_AVISO), { status: 200 })),
    );

    renderConQuery(<IndicadorEstado />);

    // El punto adopta el nivel "aviso" (hay un chequeo en aviso, ninguno en error).
    const boton = await screen.findByRole("button", { name: "Sistema con avisos" });

    // El popover empieza cerrado.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(boton);

    expect(screen.getByRole("dialog", { name: "Estado del sistema" })).toBeInTheDocument();
    expect(screen.getByText("Casi listo: revisa un detalle.")).toBeInTheDocument();
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText("Credenciales")).toBeInTheDocument();
    expect(
      screen.getByText("Configura tus credenciales en Configuración."),
    ).toBeInTheDocument();
  });

  it("el punto es rojo (error) cuando hay un chequeo en error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(DATOS_ERROR), { status: 200 })),
    );

    renderConQuery(<IndicadorEstado />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Sistema con problemas" }),
      ).toBeInTheDocument();
    });
  });

  it("muestra un estado de error si la API falla", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ mensaje: "El servidor no responde." }), { status: 500 }),
      ),
    );

    renderConQuery(<IndicadorEstado />);

    // En error de la API el indicador se trata como problema (rojo).
    const boton = await screen.findByRole("button", { name: "Sistema con problemas" });
    fireEvent.click(boton);

    expect(screen.getByText("No se pudo ejecutar el autodiagnóstico.")).toBeInTheDocument();
    expect(screen.getByText("Vuelve a intentarlo en un momento.")).toBeInTheDocument();
  });
});
