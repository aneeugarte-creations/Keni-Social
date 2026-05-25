import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Estado from "@/pages/Estado";
import type { RespuestaEstado } from "@/types";

/**
 * Test minimo de la pagina de referencia Estado con `fetch` mockeado.
 * Cubre el camino feliz (datos) y el de error.
 */

const DATOS: RespuestaEstado = {
  resultados: [
    { estado: "ok", nombre: "Python", detalle: "Versión compatible", icono: "✅" },
    { estado: "aviso", nombre: "Credenciales Meta", detalle: "Faltan algunas", icono: "⚠️" },
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

describe("Estado", () => {
  it("muestra los chequeos, el resumen y el siguiente paso al cargar datos", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(DATOS), { status: 200 })),
    );

    renderConQuery(<Estado />);

    await waitFor(() => {
      expect(screen.getByText("Python")).toBeInTheDocument();
    });
    expect(screen.getByText("Credenciales Meta")).toBeInTheDocument();
    expect(
      screen.getByText("Hay 1 problema que resolver antes de empezar."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Configura tus credenciales en Configuración."),
    ).toBeInTheDocument();
  });

  it("muestra un mensaje de error en español si la API falla", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ mensaje: "El servidor no responde." }), { status: 500 }),
      ),
    );

    renderConQuery(<Estado />);

    await waitFor(() => {
      expect(screen.getByText("El servidor no responde.")).toBeInTheDocument();
    });
    expect(screen.getByText("Reintentar")).toBeInTheDocument();
  });
});
