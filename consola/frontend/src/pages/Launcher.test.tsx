import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type * as React from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import Launcher from "./Launcher";

/** Catálogo de prueba con dos apps activas (+ el shell no aparece como app). */
const CATALOGO = {
  apps: [
    {
      id: "produccion",
      etiqueta: "Producción",
      icono: "Sparkles",
      descripcion: "Copy, clips, skills y verificación",
      permisos: ["editor"],
      rutas_frontend: ["/generacion"],
      nav: [
        { ruta: "/generacion", etiqueta: "Generación", icono: "Sparkles", descripcion: "", grupo: "dia", grupo_orden: 20, orden: 10 },
      ],
    },
    {
      id: "operacion",
      etiqueta: "Operación",
      icono: "Send",
      descripcion: "Rota, parrilla y publicación",
      permisos: ["editor"],
      rutas_frontend: ["/publicaciones"],
      nav: [
        { ruta: "/publicaciones", etiqueta: "Publicaciones", icono: "Send", descripcion: "", grupo: "operacion", grupo_orden: 30, orden: 10 },
      ],
    },
  ],
  navegacion: [],
};

function stubCatalogo(catalogo: unknown = CATALOGO) {
  const fn = vi.fn(async (url: string | URL) => {
    if (String(url).includes("/api/catalogo")) {
      return new Response(JSON.stringify(catalogo), { status: 200 });
    }
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Sonda que pinta el path actual, para verificar la navegación al hacer clic. */
function PathActual() {
  return <div data-testid="path">{useLocation().pathname}</div>;
}

function renderLauncher(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={ui} />
          <Route path="/generacion" element={<PathActual />} />
          <Route path="/publicaciones" element={<PathActual />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Launcher · cajón de apps", () => {
  it("pinta SOLO una tarjeta por app del catálogo (data-driven), sin Panel", async () => {
    stubCatalogo();
    renderLauncher(<Launcher />);
    expect(await screen.findByRole("link", { name: /producción/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /operación/i })).toBeInTheDocument();
    // La descripción de la tarjeta sale del catálogo.
    expect(screen.getByText(/copy, clips, skills y verificación/i)).toBeInTheDocument();
    // Panel ya NO es una tarjeta del launcher (es entrada global del sidebar).
    expect(screen.queryByRole("link", { name: /panel/i })).not.toBeInTheDocument();
    // No hay flecha/control "Apps" en el catálogo (eso vive solo en el sidebar).
    expect(screen.queryByRole("link", { name: /^apps$/i })).not.toBeInTheDocument();
    // Hay exactamente tantas tarjetas-enlace como apps del catálogo.
    expect(screen.getAllByRole("link")).toHaveLength(CATALOGO.apps.length);
  });

  it("con las 3 apps activas pinta exactamente 3 tarjetas, sin Panel", async () => {
    const tres = {
      apps: [
        CATALOGO.apps[0],
        CATALOGO.apps[1],
        {
          ...CATALOGO.apps[0],
          id: "metricas",
          etiqueta: "Métricas",
          icono: "BarChart3",
          rutas_frontend: ["/analiticas"],
          nav: [
            { ruta: "/analiticas", etiqueta: "Analíticas", icono: "BarChart3", descripcion: "", grupo: "x", grupo_orden: 10, orden: 10 },
          ],
        },
      ],
      navegacion: [],
    };
    stubCatalogo(tres);
    renderLauncher(<Launcher />);
    expect(await screen.findByRole("link", { name: /producción/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /operación/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /métricas/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /panel/i })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(3);
  });

  it("al hacer clic en una tarjeta navega a la ruta primaria de la app", async () => {
    stubCatalogo();
    renderLauncher(<Launcher />);
    const tarjeta = await screen.findByRole("link", { name: /producción/i });
    tarjeta.click();
    expect(await screen.findByTestId("path")).toHaveTextContent("/generacion");
  });

  it("con UNA sola app activa pinta solo esa tarjeta (sin Panel)", async () => {
    stubCatalogo({ apps: [CATALOGO.apps[0]], navegacion: [] });
    renderLauncher(<Launcher />);
    expect(await screen.findByRole("link", { name: /producción/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /operación/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /panel/i })).not.toBeInTheDocument();
  });
});
