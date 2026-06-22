/**
 * Smoke test de la página «Contexto» (`/maquina/contexto`): el pipeline de cada motor como
 * estructura, en cuatro pestañas (Investigación / Producción / Herramientas / Desarrollo). Como
 * editor (no admin) no se piden los ajustes del catálogo, así que basta con mockear la cola:
 * comprobamos que las pestañas y las fases/agentes de cada una se pintan.
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
  api: { cola: vi.fn().mockResolvedValue({ en_curso: [], esperando: [] }) },
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
  it("pinta las cuatro pestañas y el pipeline de Investigación por defecto", () => {
    renderContexto();
    // La subnav unificada (topbar) son botones de sección con `aria-current`, no un tablist Radix.
    expect(screen.getByRole("button", { name: "Investigación" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Producción" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Herramientas" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Desarrollo" })).toBeInTheDocument();
    // Importación dejó de ser una pestaña: sus agentes viven ahora dentro de Herramientas.
    expect(screen.queryByRole("button", { name: "Importación" })).not.toBeInTheDocument();
    // Pestaña por defecto = Investigación: sus fases se leen en orden (incl. el nuevo «Cotejar»).
    expect(screen.getByText("Recolectar")).toBeInTheDocument();
    expect(screen.getByText("Cotejar")).toBeInTheDocument();
    expect(screen.getByText("Macro-evento")).toBeInTheDocument();
    expect(screen.getByText("Verificar")).toBeInTheDocument();
    // «Agrupar» ya NO es una fila: es un sub-paso determinista dentro de Recolectar.
    expect(screen.queryByText("Agrupar")).not.toBeInTheDocument();
  });

  it("en la pestaña Producción muestra sus fases (Redactar/Sugerir hashtags/Ilustrar/Stock/Crítica), sin Aprobar/Publicar ni Idear", () => {
    renderContexto("/maquina/contexto?proceso=produccion");
    expect(screen.getByText("Redactar")).toBeInTheDocument();
    expect(screen.getByText("Sugerir hashtags")).toBeInTheDocument();
    expect(screen.getByText("Ilustrar")).toBeInTheDocument();
    // «Stock»: respaldo inline de imagen (foto de banco gratuito sin licencia) tras Ilustrar.
    expect(screen.getByText("Stock")).toBeInTheDocument();
    // «Crítica» (nivel IA de la cadena de aprobación) vive ahora como fase de Producción, separada
    // de la secuencia automática por un divisor que deja claro CUÁNDO corre.
    expect(screen.getByText("Crítica")).toBeInTheDocument();
    expect(screen.getByText("Cadena de aprobación")).toBeInTheDocument();
    // «Aprobar» y «Publicar» ya NO son fases del flujo: el OK humano y la salida a redes
    // viven en la página de programación/feed, no en este mapa de la máquina.
    expect(screen.queryByText("Aprobar")).not.toBeInTheDocument();
    expect(screen.queryByText("Publicar")).not.toBeInTheDocument();
    expect(screen.queryByText("Idear")).not.toBeInTheDocument();
    // «Revisar» ya NO es una fila: corre dentro de Redactar (sin prompt/logs/toggle propios).
    expect(screen.queryByText("Revisar")).not.toBeInTheDocument();
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
