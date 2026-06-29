/**
 * Smoke test de la página «Contexto» (`/maquina/contexto`): tres pestañas (Pipeline /
 * Herramientas / Desarrollo). Pipeline es la vista única FUENTE→FEED con toggles por etapa.
 * Como editor (no admin) los toggles no se piden, así que la cola está mockeada pero inactiva;
 * solo comprobamos que las pestañas y el contenido estático de cada una se pintan.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { MarcaActivaContexto, type ValorMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { UsuarioSesion } from "@/types";

import Contexto from "./Contexto";

vi.mock("@/lib/api", () => ({
  api: { ajustes: vi.fn().mockResolvedValue({ grupos: [] }) },
  mensajeError: (e: unknown) => String(e),
}));

function valorSesion(usuario: UsuarioSesion | null): ValorSesion {
  return {
    usuario,
    cargando: false,
    errorConexion: false,
    iniciarSesion: vi.fn(),
    verificarConPasskey: vi.fn(),
    entrarConPasskey: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
}

function valorMarcaActiva(marcaActiva: string | null): ValorMarcaActiva {
  return {
    marcaActiva,
    marcaPrimaria: marcaActiva,
    enMarcaPrimaria: true,
    esMultiMarca: true,
    puedeTodas: true,
    marcasParaSwitch: [],
    nombreActiva: null,
    cambiarMarca: () => {},
    volverAPrimaria: () => {},
  };
}

function renderContexto(ruta = "/maquina/contexto") {
  const usuario: UsuarioSesion = {
    id: "u1",
    usuario: "u",
    rol: "editor",
    debe_cambiar_password: false,
    marcas: ["unotv"],
  };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SesionContexto.Provider value={valorSesion(usuario)}>
        <MarcaActivaContexto.Provider value={valorMarcaActiva("unotv")}>
          <MemoryRouter initialEntries={[ruta]}>
            <Contexto />
          </MemoryRouter>
        </MarcaActivaContexto.Provider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("Contexto · la máquina en una página", () => {
  it("pinta las tres pestañas y el Pipeline unificado por defecto", () => {
    renderContexto();
    // Pipeline es la pestaña por defecto
    expect(screen.getByRole("button", { name: "Pipeline" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Herramientas" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Desarrollo" })).toBeInTheDocument();
    // Investigación y Producción ya no son pestañas independientes: forman el Pipeline unificado.
    expect(screen.queryByRole("button", { name: "Investigación" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Producción" })).not.toBeInTheDocument();
    // Pipeline muestra sus fases (contenido estático, sin ajustes de admin)
    expect(screen.getByText("Ingesta")).toBeInTheDocument();
    expect(screen.getByText("Recolectar")).toBeInTheDocument();
    expect(screen.getByText("FUENTE → FEED")).toBeInTheDocument();
  });

  it("la pestaña Herramientas reúne los agentes independientes (material recibido + ideación)", () => {
    renderContexto("/maquina/contexto?proceso=herramientas");
    // Material recibido (antes en «Importación»): ahora en cajas dentro de Herramientas.
    expect(screen.getByText("Parrilla")).toBeInTheDocument();
    expect(screen.getByText("Notas")).toBeInTheDocument();
    // Ideación evergreen.
    expect(screen.getByText("Idear")).toBeInTheDocument();
    // Crítica y envoltorios YA NO viven aquí: pertenecen a una fase (Crítica = nivel IA de la
    // cadena de aprobación; envoltorios = sub-prompts de Redactar).
    expect(screen.queryByText("Carrusel")).not.toBeInTheDocument();
    expect(screen.queryByText("Envoltorios")).not.toBeInTheDocument();
    // Hashtags (suggest) y el asistente de copy se retiraron (solo MCP/sin UI).
    expect(screen.queryByText("Hashtags")).not.toBeInTheDocument();
  });

  it("la pestaña Desarrollo presenta los agentes en cajas por tipo, con nombres cortos", () => {
    renderContexto("/maquina/contexto?proceso=desarrollo");
    // Cajas por tipo (igual que Herramientas): el carril del kanban y los Ralph.
    expect(screen.getByRole("heading", { name: "Carril" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ralph" })).toBeInTheDocument();
    // Nombres de 1-2 palabras (no el título largo del documento).
    expect(screen.getByText("Analyze")).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
    expect(screen.getByText("Operativo")).toBeInTheDocument();
    expect(screen.queryByText("Analyze · explorar el repo")).not.toBeInTheDocument();
  });
});
