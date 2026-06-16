/**
 * Smoke test de la página «Contexto» (`/maquina/contexto`): el pipeline de cada motor como
 * estructura, en cuatro pestañas (Investigación / Producción / Importación / Herramientas). Como
 * editor (no admin) no se piden los ajustes del catálogo, así que basta con mockear la cola:
 * comprobamos que las pestañas y las fases de cada una se pintan.
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
    iniciarSesion: vi.fn(),
    verificarConPasskey: vi.fn(),
    verificarConCodigo: vi.fn(),
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
    expect(screen.getByRole("tab", { name: "Investigación" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Producción" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Importación" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Herramientas" })).toBeInTheDocument();
    // Pestaña por defecto = Investigación: sus fases se leen en orden (incl. el nuevo «Cotejar»).
    expect(screen.getByText("Recolectar")).toBeInTheDocument();
    expect(screen.getByText("Cotejar")).toBeInTheDocument();
    expect(screen.getByText("Verificar")).toBeInTheDocument();
  });

  it("en la pestaña Producción muestra sus fases (incl. Idear)", () => {
    renderContexto("/maquina/contexto?proceso=produccion");
    expect(screen.getByText("Redactar")).toBeInTheDocument();
    expect(screen.getByText("Publicar")).toBeInTheDocument();
    expect(screen.getByText("Idear")).toBeInTheDocument();
  });

  it("Importación y Herramientas listan sus prompts independientes", () => {
    renderContexto("/maquina/contexto?proceso=importacion");
    expect(screen.getByText("Parrilla")).toBeInTheDocument();
    expect(screen.getByText("Notas")).toBeInTheDocument();
  });

  it("la pestaña Herramientas lista los prompts de apoyo", () => {
    renderContexto("/maquina/contexto?proceso=herramientas");
    expect(screen.getByText("Crítica")).toBeInTheDocument();
    expect(screen.getByText("Hashtags")).toBeInTheDocument();
  });
});
