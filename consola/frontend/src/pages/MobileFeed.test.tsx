import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { UsuarioSesion } from "@/types";

import MobileFeed from "./MobileFeed";

const OPCIONES = {
  redes: [{ id: "x", nombre: "X" }],
  estados: [
    { id: "en_revision", nombre: "En revisión" },
    { id: "aprobado", nombre: "Aprobado" },
  ],
  marcas: [
    { id: "unotv", nombre: "Uno TV" },
    { id: "claro-sports", nombre: "Claro Sports" },
  ],
};

const PUBLICACION = {
  id: "p1",
  contenido_id: "c1",
  pipeline_id: "",
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
  formato: "foto",
  imagen_fuente: "",
  foto: "",
  falta_copy: false,
  falta_imagen: false,
  falta_revision: false,
  falta_publicar: false,
  falta_video: false,
  video: "",
  fecha_creacion: "",
  fecha_actualizacion: "",
  fecha_programada: "",
  fecha_fuente: "",
  origen: "",
  imagen: "",
  imagen_url: "",
  evergreen: false,
  // Etapa real del backend (Flujo C): coherente con estado 'en_revision'.
  etapa_ia: "lista_para_revisar",
};

/** Stub de fetch: enruta /api/publicaciones y /api/publicaciones/opciones. */
function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL) => {
      const ruta = String(url);
      if (ruta.includes("/api/publicaciones/opciones")) {
        return new Response(JSON.stringify(OPCIONES), { status: 200 });
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
    verificarConPasskey: vi.fn(),
    verificarConCodigo: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={valor}>
        <MemoryRouter>
          <MobileFeed />
        </MemoryRouter>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("MobileFeed · feed móvil de revisión", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("muestra la cabecera, las bandejas y el botón de crear", async () => {
    stubFetch();
    renderFeed();
    expect(await screen.findByText("Feed de revisión")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Por revisar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /crear pieza/i })).toBeInTheDocument();
  });

  it("renderiza una tarjeta con la pieza en revisión y sus acciones", async () => {
    stubFetch();
    renderFeed();
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /aprobar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /rechazar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /comentar/i })).toBeInTheDocument();
  });

  it("activa el scroll magnético por pieza mientras está montado y lo revierte al salir", async () => {
    stubFetch();
    const { unmount } = renderFeed();
    await screen.findByText("Feed de revisión");
    expect(document.documentElement.style.scrollSnapType).toBe("y mandatory");
    unmount();
    expect(document.documentElement.style.scrollSnapType).toBe("");
  });
});
