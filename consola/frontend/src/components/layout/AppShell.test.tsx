import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/AppShell";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";

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
  // El sidebar pinta los bloques de flujo de `navegacion` (la nav de las apps
  // activas, ya agrupada por el backend).
  navegacion: [
    {
      etiqueta: "Operación",
      items: [
        { ruta: "/generacion", etiqueta: "Generación", icono: "Sparkles", descripcion: "" },
      ],
    },
    {
      // Un hub (Investigación) como entrada única: su sub-nav son pestañas in-page,
      // y el breadcrumb en una de sus hojas debe leer "Investigación › Pestaña".
      etiqueta: "Datos",
      items: [
        { ruta: "/datos/investigacion", etiqueta: "Investigación", icono: "Search", descripcion: "" },
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
        <MarcaActivaProvider>
        <MemoryRouter initialEntries={[ruta]}>
          <Routes>
            <Route path="/" element={<AppShell />}>
              {/* `/` ya no es launcher: redirige al tablero (como en el router real). */}
              <Route index element={<Navigate to="/generacion" replace />} />
              <Route path="generacion" element={<div>contenido app</div>} />
              <Route path="configuracion" element={<div>contenido config</div>} />
              <Route
                path="datos/investigacion/fuentes"
                element={<div>contenido fuentes</div>}
              />
            </Route>
          </Routes>
        </MemoryRouter>
        </MarcaActivaProvider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("AppShell · sidebar siempre presente", () => {
  it("`/` redirige al tablero (ya no hay launcher)", async () => {
    renderShell("/");
    expect(await screen.findByText("contenido app")).toBeInTheDocument();
  });

  it("dentro de una app renderiza el sidebar", async () => {
    renderShell("/generacion");
    expect(await screen.findByText("contenido app")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /navegación principal/i })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /^generación$/i })).toBeInTheDocument(),
    );
    // Ya no hay control "⊞ Apps" (no hay launcher).
    expect(screen.queryByRole("link", { name: /^apps$/i })).not.toBeInTheDocument();
  });

  it("en una pantalla de shell (Configuración) también renderiza el sidebar", async () => {
    renderShell("/configuracion");
    expect(await screen.findByText("contenido config")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /navegación principal/i })).toBeInTheDocument();
  });

  it("breadcrumb de una página suelta: solo su nombre, sin el nombre de app viejo", async () => {
    renderShell("/generacion");
    await screen.findByText("contenido app");
    const ruta = screen.getByRole("navigation", { name: /^ruta$/i });
    // Espera a que el catálogo (async) hidrate el breadcrumb: la página es el único
    // segmento, marcado actual.
    await waitFor(() =>
      expect(within(ruta).getByText("Generación")).toHaveAttribute("aria-current", "page"),
    );
    // Ya NO se muestra el nombre de app A/B/C ("Producción"), ni hay "›"/enlaces.
    expect(within(ruta).queryByText("Producción")).not.toBeInTheDocument();
    expect(ruta.querySelector("a")).toBeNull();
  });

  it("breadcrumb en una hoja de hub: 'Hub › Pestaña' con el hub enlazable", async () => {
    renderShell("/datos/investigacion/fuentes");
    await screen.findByText("contenido fuentes");
    const ruta = screen.getByRole("navigation", { name: /^ruta$/i });
    // El hub es un enlace a su ruta; la pestaña activa es el segmento actual.
    await waitFor(() =>
      expect(within(ruta).getByRole("link", { name: /^investigación$/i })).toHaveAttribute(
        "href",
        "/datos/investigacion",
      ),
    );
    expect(within(ruta).getByText("Fuentes")).toHaveAttribute("aria-current", "page");
  });

  it("fuera de apps (Configuración) muestra solo su nombre, sin '›' ni enlace", async () => {
    renderShell("/configuracion");
    await screen.findByText("contenido config");
    const ruta = screen.getByRole("navigation", { name: /^ruta$/i });
    expect(ruta).toHaveTextContent("Configuración");
    // En el breadcrumb, el nombre de la pantalla de shell va como TEXTO (no enlace) y sin "›".
    expect(ruta.querySelector("a")).toBeNull();
  });

  it("persiste el estado colapsado del rail en localStorage", async () => {
    localStorage.setItem("keni:sidebar-colapsado", "1");
    renderShell("/configuracion");
    await screen.findByText("contenido config");
    // En rail (colapsado) aparece el botón "Expandir barra"; no el "Colapsar".
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /expandir barra/i })).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: /^colapsar$/i })).not.toBeInTheDocument();
  });
});
