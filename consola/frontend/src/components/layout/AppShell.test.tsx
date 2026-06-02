import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
  // El sidebar pinta los bloques de flujo de `navegacion` (Panel + la nav de las
  // apps activas, ya agrupada por el backend).
  navegacion: [
    {
      etiqueta: "Operación",
      items: [
        { ruta: "/panel", etiqueta: "Panel", icono: "LayoutDashboard", descripcion: "" },
        { ruta: "/generacion", etiqueta: "Generación", icono: "Sparkles", descripcion: "" },
      ],
    },
  ],
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

/**
 * localStorage de juguete (jsdom no siempre expone `clear`). Persiste el estado
 * colapsado del rail; lo reseteamos entre tests.
 */
function instalarLocalStorage() {
  let store: Record<string, string> = {};
  const mock: Storage = {
    get length() {
      return Object.keys(store).length;
    },
    clear: () => {
      store = {};
    },
    getItem: (k: string) => (k in store ? store[k] : null),
    key: (i: number) => Object.keys(store)[i] ?? null,
    removeItem: (k: string) => {
      delete store[k];
    },
    setItem: (k: string, v: string) => {
      store[k] = String(v);
    },
  };
  vi.stubGlobal("localStorage", mock);
}

beforeEach(() => {
  instalarLocalStorage();
});

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
              {/* `/` ya no es launcher: redirige a /panel (como en el router real). */}
              <Route index element={<Navigate to="/panel" replace />} />
              <Route path="generacion" element={<div>contenido app</div>} />
              <Route path="panel" element={<div>contenido panel</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("AppShell · sidebar siempre presente", () => {
  it("`/` redirige a `/panel` (ya no hay launcher)", async () => {
    renderShell("/");
    expect(await screen.findByText("contenido panel")).toBeInTheDocument();
  });

  it("dentro de una app renderiza el sidebar (con Panel global)", async () => {
    renderShell("/generacion");
    expect(await screen.findByText("contenido app")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /navegación principal/i })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /^panel$/i })).toBeInTheDocument(),
    );
    // Ya no hay control "⊞ Apps" (no hay launcher).
    expect(screen.queryByRole("link", { name: /^apps$/i })).not.toBeInTheDocument();
  });

  it("en `/panel` también renderiza el sidebar", async () => {
    renderShell("/panel");
    expect(await screen.findByText("contenido panel")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /navegación principal/i })).toBeInTheDocument();
  });

  it("dentro de una app muestra breadcrumb 'App › Página' con la App clicable", async () => {
    renderShell("/generacion");
    await screen.findByText("contenido app");
    // "Producción" es un ENLACE a su 1ª página (rutaPrimaria → /generacion).
    const enlaceApp = await screen.findByRole("link", { name: /^producción$/i });
    expect(enlaceApp).toHaveAttribute("href", "/generacion");
    // "Generación" es la página actual (texto, marcada aria-current). Acotamos al
    // breadcrumb (la misma etiqueta también aparece como hoja en el sidebar).
    const ruta = screen.getByRole("navigation", { name: /^ruta$/i });
    const pagina = within(ruta).getByText("Generación");
    expect(pagina).toHaveAttribute("aria-current", "page");
  });

  it("fuera de apps (Panel) muestra solo 'Panel', sin '›' ni enlace de app", async () => {
    renderShell("/panel");
    await screen.findByText("contenido panel");
    const ruta = screen.getByRole("navigation", { name: /^ruta$/i });
    expect(ruta).toHaveTextContent("Panel");
    // En el breadcrumb, "Panel" va como TEXTO (no como enlace de app) y no hay "›".
    expect(ruta.querySelector("a")).toBeNull();
  });

  it("persiste el estado colapsado del rail en localStorage", async () => {
    localStorage.setItem("keni:sidebar-colapsado", "1");
    renderShell("/panel");
    await screen.findByText("contenido panel");
    // En rail (colapsado) aparece el botón "Expandir barra"; no el "Colapsar".
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /expandir barra/i })).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: /^colapsar$/i })).not.toBeInTheDocument();
  });
});
