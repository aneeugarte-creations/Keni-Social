import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PanelEstado } from "@/components/layout/PanelEstado";
import type { RespuestaEstado } from "@/types";

/**
 * Test del panel de autodiagnóstico (antes el popover "Estado" de la topbar,
 * ahora una sección de Configuración). Cubre el camino feliz (chequeos, resumen
 * y siguiente paso visibles) y el de error, y verifica que whisper/ffmpeg se
 * agrupan bajo "Herramientas locales".
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

describe("PanelEstado", () => {
  it("muestra los chequeos, el resumen y el siguiente paso", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(DATOS), { status: 200 })),
    );

    renderConQuery(<PanelEstado />);

    await waitFor(() => {
      expect(screen.getByText("Casi listo: revisa un detalle.")).toBeInTheDocument();
    });

    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText("Credenciales Meta")).toBeInTheDocument();
    // Las herramientas locales se agrupan aparte.
    expect(screen.getByText("Herramientas locales")).toBeInTheDocument();
    expect(screen.getByText("Whisper")).toBeInTheDocument();
    expect(
      screen.getByText("Configura tus credenciales en Configuración."),
    ).toBeInTheDocument();
    // Botón para volver a comprobar.
    expect(screen.getByRole("button", { name: "Volver a comprobar" })).toBeInTheDocument();
  });

  it("muestra un estado de error si la API falla", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ mensaje: "El servidor no responde." }), { status: 500 }),
      ),
    );

    renderConQuery(<PanelEstado />);

    await waitFor(() => {
      expect(screen.getByText("No se pudo ejecutar el autodiagnóstico.")).toBeInTheDocument();
    });

    expect(screen.getByText("Vuelve a intentarlo en un momento.")).toBeInTheDocument();
  });
});
