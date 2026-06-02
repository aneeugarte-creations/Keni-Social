import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { UsuarioSesion } from "@/types";

import FeedIdeacion from "./FeedIdeacion";

const OPCIONES = {
  redes: [{ id: "x", nombre: "X" }],
  estados: [
    { id: "en_revision", nombre: "En revisión" },
    { id: "aprobado", nombre: "Aprobado" },
  ],
  marcas: [{ id: "unotv", nombre: "Uno TV" }],
};

const PUBLICACION = {
  id: "p1",
  contenido_id: "c1",
  titulo: "Gol de último minuto",
  marca: "unotv",
  marca_nombre: "Uno TV",
  red: "x",
  red_nombre: "X",
  contenido: "¡Increíble remontada!",
  copy_in: "",
  estado: "en_revision",
  veredicto: "",
  autor_id: "u9",
  autor_nombre: "Yustine",
  enviado_a_revision_en: "",
  revisor_id: "",
  revisor_nombre: "",
  revisado_en: "",
  preparado_en: "",
  id_post_metricool: "",
  tipo_contenido: "",
  imagen_fuente: "",
  foto: "",
  falta_copy: false,
  falta_imagen: false,
  falta_revision: false,
  falta_publicar: false,
  fecha_creacion: "",
  fecha_actualizacion: "",
  fecha_programada: "",
  origen: "equipo",
  imagen: "",
  imagen_url: "",
  evergreen: false,
  // Etapa real del backend (Flujo C): coherente con estado 'en_revision'.
  etapa_ia: "lista_para_revisar",
};

/** Stub de fetch: enruta opciones, listado, cadena de aprobación y comentarios. */
function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL) => {
      const ruta = String(url);
      if (ruta.includes("/api/publicaciones/opciones")) {
        return new Response(JSON.stringify(OPCIONES), { status: 200 });
      }
      if (ruta.includes("/aprobacion")) {
        return new Response(
          JSON.stringify({
            niveles: [],
            estado: "pendiente",
            nivel_actual: "",
            aprobados: 0,
            minimo_aprobaciones: 0,
            comentarios_sin_resolver: 0,
          }),
          { status: 200 },
        );
      }
      if (ruta.includes("/comentarios")) {
        return new Response(JSON.stringify({ comentarios: [], total: 0 }), { status: 200 });
      }
      if (ruta.includes("/api/publicaciones")) {
        return new Response(
          JSON.stringify({
            publicaciones: [PUBLICACION],
            paginacion: { total: 1, limite: 50, desplazamiento: 0 },
          }),
          { status: 200 },
        );
      }
      return new Response("{}", { status: 200 });
    }),
  );
}

function renderFeed(usuario: Partial<UsuarioSesion> = {}) {
  const valor: ValorSesion = {
    usuario: {
      id: "u1",
      usuario: "revisor",
      rol: "editor",
      debe_cambiar_password: false,
      marcas: ["unotv"],
      ...usuario,
    } as UsuarioSesion,
    cargando: false,
    iniciarSesion: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={valor}>
        <MemoryRouter>
          <FeedIdeacion />
        </MemoryRouter>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("FeedIdeacion · feed de ideación interno", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("muestra la cabecera y las bandejas del feed", async () => {
    stubFetch();
    renderFeed();
    expect(await screen.findByText("Feed de ideación")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Por revisar" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "En proceso" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Aprobadas" })).toBeInTheDocument();
  });

  it("renderiza la pieza como post con etapa IA y acciones de aprobación en línea", async () => {
    stubFetch();
    renderFeed();
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // Etapa IA en vivo: en revisión → lista para revisar.
    expect(screen.getByText("Lista para revisar")).toBeInTheDocument();
    // Aprobación en línea (gate humano).
    expect(screen.getByRole("button", { name: /aprobar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /rechazar/i })).toBeInTheDocument();
  });

  it("abre el hilo de comentarios en línea al pulsar Comentar", async () => {
    stubFetch();
    renderFeed();
    const boton = await screen.findByRole("button", { name: /comentar/i });
    fireEvent.click(boton);
    await waitFor(() =>
      expect(screen.getByPlaceholderText(/comentario para el equipo/i)).toBeInTheDocument(),
    );
  });
});
