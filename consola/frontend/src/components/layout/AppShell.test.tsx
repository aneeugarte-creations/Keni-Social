import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/AppShell";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";

/** Catálogo mínimo con una app activa (espejo de un manifest). */
const CATALOGO = {
  apps: [
    {
      id: "produccion",
      etiqueta: "Producción",
      icono: "Sparkles",
      descripcion: "Copy, clips, skills y verificación",
      permisos: ["editor", "admin"],
      rutas_frontend: ["/generacion"],
      nav: [
        { ruta: "/generacion", etiqueta: "Generación", icono: "Sparkles", descripcion: "", grupo: "dia", grupo_orden: 20, orden: 10 },
      ],
    },
  ],
  navegacion: [],
};

function stubFetch() {
  const fn = vi.fn(async (url: string | URL) => {
    const s = String(url);
    if (s.includes("/api/catalogo")) {
      return new Response(JSON.stringify(CATALOGO), { status: 200 });
    }
    if (s.includes("/api/limites")) {
      return new Response(JSON.stringify({ limites: [] }), { status: 200 });
    }
    // estado y demás: respuestas inocuas para no romper el render.
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const sesion: ValorSesion = {
  usuario: { id: "u1", usuario: "x", rol: "editor", debe_cambiar_password: false },
  cargando: false,
  iniciarSesion: async () => {},
  cerrarSesion: async () => {},
  refrescar: async () => {},
};

function renderShell(ruta: string) {
  stubFetch();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesion}>
        <MemoryRouter initialEntries={[ruta]}>
          <Routes>
            <Route path="/" element={<AppShell />}>
              <Route index element={<div>contenido launcher</div>} />
              <Route path="generacion" element={<div>contenido app</div>} />
              <Route path="panel" element={<div>contenido panel</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("AppShell · visibilidad del sidebar", () => {
  it("en el launcher `/` NO renderiza el sidebar", async () => {
    renderShell("/");
    expect(await screen.findByText("contenido launcher")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: /navegación principal/i })).not.toBeInTheDocument();
  });

  it("dentro de una app SÍ renderiza el sidebar (con Panel global y ⊞ Apps)", async () => {
    renderShell("/generacion");
    expect(await screen.findByText("contenido app")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /navegación principal/i })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /^panel$/i })).toBeInTheDocument(),
    );
    expect(screen.getByRole("link", { name: /^apps$/i })).toBeInTheDocument();
  });

  it("en `/panel` SÍ renderiza el sidebar", async () => {
    renderShell("/panel");
    expect(await screen.findByText("contenido panel")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /navegación principal/i })).toBeInTheDocument();
  });
});
