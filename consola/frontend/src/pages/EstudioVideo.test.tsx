/**
 * Tests de EstudioVideo (editor REAL del "toque RRSS"):
 *  - Renderiza el header "Editor de video" y la sub-navegación de secciones.
 *  - La sección Base muestra el selector de formato (9:16/1:1/16:9) y la zona de subida.
 *  - Las secciones Overlay/PiP/Subtítulos/Render están deshabilitadas hasta subir un clip base.
 *  - El selector de formato es accesible (radiogroup) con 9:16 marcado por defecto.
 *
 * No se ejercita el editor de capas (Konva) ni el render real: eso es preview/server-side.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import EstudioVideo from "./EstudioVideo";

// Marca activa: la página solo lee `marcaActiva`/`marcaPrimaria`.
vi.mock("@/hooks/marca-activa-contexto", () => ({
  useMarcaActiva: () => ({ marcaActiva: "unotv", marcaPrimaria: "unotv" }),
}));

// Stub de red genérico (la query de formatos cae al fallback local con retry:false).
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

  it("muestra el selector de formato con 9:16 seleccionado por defecto", () => {
    renderEstudioVideo();
    const grupo = screen.getByRole("radiogroup", { name: /formato de video/i });
    expect(grupo).toBeInTheDocument();
    const vertical = screen.getByRole("radio", { name: /9:16/i });
    expect(vertical).toHaveAttribute("aria-checked", "true");
  });

  it("muestra la zona de carga del clip base (EditorVideo reutilizado)", () => {
    renderEstudioVideo();
    expect(screen.getByText(/subir video/i)).toBeInTheDocument();
  });

  it("deshabilita las secciones que requieren clip base (Render, Subtítulos)", () => {
    renderEstudioVideo();
    // Las pestañas son botones; sin clip base, Render/Subtítulos están deshabilitadas.
    const render = screen.getByRole("button", { name: /^render$/i });
    const subs = screen.getByRole("button", { name: /subtítulos/i });
    expect(render).toBeDisabled();
    expect(subs).toBeDisabled();
    // La sección Base sí está activa.
    expect(screen.getByRole("button", { name: /^base$/i })).not.toBeDisabled();
  });

  it("avisa que el preview es aproximado (render fiel = servidor)", () => {
    renderEstudioVideo();
    expect(screen.getByText(/preview aproximado/i)).toBeInTheDocument();
  });
});
