import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IndicadorEstado } from "@/components/layout/IndicadorEstado";
import type { RespuestaEstado } from "@/types";

/**
 * Test del indicador de salud de la topbar (antes página "Estado").
 * Cubre el camino feliz (datos en el popover) y el de error, y verifica que
 * whisper/ffmpeg se agrupan bajo "Herramientas locales".
 */

const DATOS: RespuestaEstado = {
  resultados: [
    { estado: "ok", nombre: "Python", detalle: "Versión compatible", icono: "✅" },
    { estado: "aviso", nombre: "Credenciales Meta", detalle: "Faltan algunas", icono: "⚠️" },
    { estado: "aviso", nombre: "Whisper", detalle: "No instalado", icono: "⚠️" },
    { estado: "error", nombre: "Conexión", detalle: "No se pudo conectar", icono: "❌" },
  ],
  resumen: "Casi listo: revisa un detalle.",
  siguiente_paso: "Configura tus credenciales en Configuración.",
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
  it("muestra los chequeos, el resumen y el siguiente paso al abrir el popover", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(DATOS), { status: 200 })),
    );

    renderConQuery(<IndicadorEstado />);

    // Resumen visible en el botón (aria-label/title) en cuanto cargan los datos.
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Casi listo: revisa un detalle." }),
      ).toBeInTheDocument();
    });

    // Abre el popover.
    fireEvent.click(screen.getByRole("button", { name: "Casi listo: revisa un detalle." }));

    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText("Credenciales Meta")).toBeInTheDocument();
    // Las herramientas locales se agrupan aparte.
    expect(screen.getByText("Herramientas locales")).toBeInTheDocument();
    expect(screen.getByText("Whisper")).toBeInTheDocument();
    expect(
      screen.getByText("Configura tus credenciales en Configuración."),
    ).toBeInTheDocument();
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

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "No se pudo comprobar el estado" }),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "No se pudo comprobar el estado" }));

    expect(screen.getByText("No se pudo ejecutar el autodiagnóstico.")).toBeInTheDocument();
  });
});
