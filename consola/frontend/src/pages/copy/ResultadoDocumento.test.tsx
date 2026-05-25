import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { OpcionesPublicaciones } from "@/types";

import { ResultadoDocumento } from "./ResultadoDocumento";

/**
 * Test del visor de documento (skills con `salida === "documento"`): renderiza
 * el Markdown del documento y ofrece guardar como publicación eligiendo una red.
 */

const OPCIONES: OpcionesPublicaciones = {
  redes: [
    { id: "x", nombre: "X", limite: 280 },
    { id: "instagram", nombre: "Instagram", limite: 2200 },
  ],
  estados: [{ id: "borrador", nombre: "Borrador" }],
  marcas: [{ id: "unotv", nombre: "UnoTV" }],
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(OPCIONES), { status: 200 })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ResultadoDocumento", () => {
  it("renderiza el documento Markdown y los controles de guardado", async () => {
    renderConProviders(
      <ResultadoDocumento documento={"# Brief\n\nContenido del brief."} historialId="h1" />,
    );

    // El encabezado del documento se renderiza desde Markdown.
    expect(screen.getByRole("heading", { name: "Brief" })).toBeInTheDocument();
    expect(screen.getByText("Contenido del brief.")).toBeInTheDocument();

    // Botones de acción presentes.
    expect(
      screen.getByRole("button", { name: /Guardar como publicación/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Copiar/ })).toBeInTheDocument();

    // Las opciones de red llegan de la API (selector con placeholder visible).
    await waitFor(() => {
      expect(screen.getByText("Elige una red")).toBeInTheDocument();
    });
  });

  it("deshabilita guardar hasta elegir una red", () => {
    renderConProviders(<ResultadoDocumento documento="texto" historialId="h1" />);
    expect(screen.getByRole("button", { name: /Guardar como publicación/ })).toBeDisabled();
  });
});
