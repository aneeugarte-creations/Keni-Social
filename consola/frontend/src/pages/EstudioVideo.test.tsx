/**
 * Tests de EstudioVideo (página shell, sin motor de edición):
 *  - Renderiza el header "Editor de video".
 *  - Muestra el placeholder "próximamente" (motor de edición NO está).
 *  - Muestra la zona de subida de video (reusa EditorVideo).
 *  - NO renderiza un canvas de edición ni una línea de tiempo.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import EstudioVideo from "./EstudioVideo";

// EditorVideo llama a `api.subirVideo` a través de useMutation solo cuando el usuario
// interactúa; bastará con un stub genérico de fetch para evitar errores de red.
vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));

function renderEstudioVideo() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <EstudioVideo />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EstudioVideo", () => {
  it("muestra el encabezado 'Editor de video'", () => {
    renderEstudioVideo();
    expect(screen.getByRole("heading", { name: /editor de video/i })).toBeInTheDocument();
  });

  it("muestra el placeholder de motor de edición próximamente", () => {
    renderEstudioVideo();
    expect(screen.getByText(/motor de edición de video/i)).toBeInTheDocument();
    // Puede aparecer en la badge del header y en el texto del placeholder.
    const elementos = screen.getAllByText(/próximamente/i);
    expect(elementos.length).toBeGreaterThanOrEqual(1);
  });

  it("muestra la zona de carga de video (EditorVideo reutilizado)", () => {
    renderEstudioVideo();
    // EditorVideo emite este texto cuando no hay video cargado
    expect(screen.getByText(/subir video/i)).toBeInTheDocument();
  });

  it("NO incluye un canvas o timeline de edición", () => {
    const { container } = renderEstudioVideo();
    // No debe haber <canvas> ni elemento con role=region timeline
    expect(container.querySelector("canvas")).toBeNull();
    expect(screen.queryByRole("region", { name: /timeline/i })).not.toBeInTheDocument();
  });
});
