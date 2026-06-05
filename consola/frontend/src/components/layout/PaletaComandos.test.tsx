import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PaletaProvider } from "@/components/layout/PaletaComandos";
import { usePaletaComandos } from "@/hooks/paleta-contexto";

/** Catálogo de prueba: dos apps con su nav (espejo de los manifests). */
const CATALOGO = {
  apps: [
    {
      id: "produccion",
      etiqueta: "Producción",
      icono: "Sparkles",
      descripcion: "",
      permisos: ["editor", "admin"],
      rutas_frontend: ["/generacion"],
      nav: [
        { ruta: "/generacion", etiqueta: "Generación", icono: "Sparkles", descripcion: "", grupo: "dia", grupo_orden: 20, orden: 10 },
        { ruta: "/biblioteca", etiqueta: "Biblioteca", icono: "Wand2", descripcion: "", grupo: "op", grupo_orden: 30, orden: 20 },
      ],
    },
    {
      id: "operacion",
      etiqueta: "Operación",
      icono: "Send",
      descripcion: "",
      permisos: ["editor", "admin"],
      rutas_frontend: ["/publicaciones"],
      nav: [
        { ruta: "/publicaciones", etiqueta: "Publicaciones", icono: "Send", descripcion: "", grupo: "op", grupo_orden: 30, orden: 10 },
      ],
    },
  ],
  navegacion: [],
};

function stubCatalogo() {
  const fn = vi.fn(async (url: string | URL) => {
    if (String(url).includes("/api/catalogo")) {
      return new Response(JSON.stringify(CATALOGO), { status: 200 });
    }
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Sonda del path + botón que abre la paleta vía contexto (como el trigger del sidebar). */
function Sonda() {
  const { abrir } = usePaletaComandos();
  const { pathname } = useLocation();
  return (
    <>
      <button type="button" onClick={abrir}>
        abrir-paleta
      </button>
      <div data-testid="path">{pathname}</div>
    </>
  );
}

function renderPaleta(ruta = "/generacion") {
  stubCatalogo();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[ruta]}>
        <PaletaProvider>
          <Sonda />
        </PaletaProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PaletaComandos", () => {
  it("se abre con ⌘K (mac) y con Ctrl-K, y lista todas las páginas navegables", async () => {
    renderPaleta();
    // Cerrada por defecto.
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    // ⌘K abre.
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(await screen.findByRole("listbox")).toBeInTheDocument();
    // Las hojas de cada app del catálogo.
    expect(await screen.findByRole("option", { name: /producción.*generación/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /operación.*publicaciones/i })).toBeInTheDocument();
    // ⌘K de nuevo togglea cerrado.
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
    // Ctrl-K también abre (Windows/Linux).
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(await screen.findByRole("listbox")).toBeInTheDocument();
  });

  it("abre vía el contexto (trigger externo)", async () => {
    renderPaleta();
    fireEvent.click(screen.getByRole("button", { name: /abrir-paleta/i }));
    expect(await screen.findByRole("listbox")).toBeInTheDocument();
  });

  it("filtra por texto (match en app y en página, sin acentos)", async () => {
    renderPaleta();
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const input = await screen.findByRole("combobox");
    // "publi" (sin acento) matchea Publicaciones; descarta el resto.
    fireEvent.change(input, { target: { value: "publi" } });
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /publicaciones/i })).toBeInTheDocument();
      expect(screen.queryByRole("option", { name: /generación/i })).not.toBeInTheDocument();
    });
    // Sin resultados muestra el aviso.
    fireEvent.change(input, { target: { value: "zzz-no-existe" } });
    expect(await screen.findByText(/sin resultados/i)).toBeInTheDocument();
  });

  it("↑/↓ mueve la selección y ↵ navega y cierra", async () => {
    renderPaleta();
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const input = await screen.findByRole("combobox");
    // Filtra a una sola opción para navegar de forma determinista.
    fireEvent.change(input, { target: { value: "publicaciones" } });
    await screen.findByRole("option", { name: /publicaciones/i });
    // ↓ mantiene la selección en la única opción; ↵ navega.
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(screen.getByTestId("path")).toHaveTextContent("/publicaciones"));
    // Tras navegar, la paleta se cierra.
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("Esc cierra la paleta", async () => {
    renderPaleta();
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const dialogo = await screen.findByRole("dialog");
    fireEvent.keyDown(dialogo, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
  });

  it("hace clic en una opción para navegar", async () => {
    renderPaleta();
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.click(await screen.findByRole("option", { name: /operación.*publicaciones/i }));
    await waitFor(() => expect(screen.getByTestId("path")).toHaveTextContent("/publicaciones"));
  });
});
