import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/AppShell";
import { AccionesPagina } from "@/components/layout/encabezado";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { FiltrosContenidoProvider } from "@/hooks/use-filtros-contenido";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";

/** Catálogo mínimo con una app activa (espejo de un manifest). */
const CATALOGO = {
  apps: [
    {
      id: "produccion",
      etiqueta: "Producción",
      icono: "Sparkles",
      descripcion: "Copy, clips, imágenes y verificación",
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
  iniciarSesion: async () => ({ mfaRequerido: false }),
  verificarConPasskey: async () => {},
  verificarConCodigo: async () => {},
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
        <FiltrosContenidoProvider>
        <MemoryRouter initialEntries={[ruta]}>
          <Routes>
            <Route path="/" element={<AppShell />}>
              {/* `/` ya no es launcher: redirige al tablero (como en el router real). */}
              <Route index element={<Navigate to="/generacion" replace />} />
              <Route path="generacion" element={<div>contenido app</div>} />
              <Route path="configuracion" element={<div>contenido config</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
        </FiltrosContenidoProvider>
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

  it("ya no hay breadcrumb de ruta en la topbar (la nav es por pestañas)", async () => {
    renderShell("/generacion");
    await screen.findByText("contenido app");
    // El breadcrumb "Hub › Pestaña" se eliminó: no existe la región de navegación "Ruta".
    expect(screen.queryByRole("navigation", { name: /^ruta$/i })).not.toBeInTheDocument();
  });

  it("en MÓVIL las acciones de página van a su fila bajo el header, no a la topbar", async () => {
    // matchMedia simulado: viewport < md (la query "(min-width: 768px)" NO casa).
    const mq = (consulta: string): MediaQueryList =>
      ({
        matches: false,
        media: consulta,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList;
    vi.stubGlobal("matchMedia", mq);

    stubFetch();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SesionContexto.Provider value={sesion}>
          <MarcaActivaProvider>
          <FiltrosContenidoProvider>
          <MemoryRouter initialEntries={["/generacion"]}>
            <Routes>
              <Route path="/" element={<AppShell />}>
                <Route
                  path="generacion"
                  element={
                    <div>
                      contenido app
                      <AccionesPagina>
                        <button type="button">accion-de-pagina</button>
                      </AccionesPagina>
                    </div>
                  }
                />
              </Route>
            </Routes>
          </MemoryRouter>
          </FiltrosContenidoProvider>
          </MarcaActivaProvider>
        </SesionContexto.Provider>
      </QueryClientProvider>,
    );

    await screen.findByText("contenido app");
    const boton = await screen.findByRole("button", { name: "accion-de-pagina" });
    // El portal aterriza en la fila móvil (md:hidden bajo el header), no en el <header>.
    expect(boton.closest("header")).toBeNull();
    expect(boton.parentElement?.className).toContain("md:hidden");
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
