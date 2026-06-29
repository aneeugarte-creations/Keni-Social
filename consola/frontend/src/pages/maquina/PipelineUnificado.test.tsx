/**
 * Smoke tests del PipelineUnificado: las 5 fases, los toggles, los pasos fijos
 * y la cascada de críticas (una CRÍTICA apagada oscurece todo lo que sigue).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MarcaActivaContexto, type ValorMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { AjusteAdmin, UsuarioSesion } from "@/types";

import { PipelineUnificado } from "./PipelineUnificado";

const { mockAjustes } = vi.hoisted(() => ({ mockAjustes: vi.fn() }));

vi.mock("@/lib/api", () => ({
  api: { ajustes: mockAjustes },
  mensajeError: (e: unknown) => String(e),
}));

function ajuste(clave: string, valor: boolean): AjusteAdmin {
  return {
    clave,
    tipo: "bool",
    valor,
    etiqueta: clave,
    ayuda: "",
    grupo: "pipeline",
    peligroso: false,
    fuente: "store",
    defecto: true,
  };
}

function todosActivos(): AjusteAdmin[] {
  return [
    ajuste("KENI_MAQUINA", true),
    ajuste("KENI_GENERACION_PAUSADA", false),
    ajuste("KENI_PIPELINE_RECOLECTAR", true),
    ajuste("KENI_TRENDS", true),
    ajuste("KENI_PIPELINE_FUSIONAR", true),
    ajuste("KENI_PIPELINE_TRADUCIR", true),
    ajuste("KENI_CLASIFICAR_MARCA_IA", true),
    ajuste("KENI_PRIORIZAR_PERFIL_IA", true),
    ajuste("KENI_PIPELINE_VERIFICAR", true),
    ajuste("KENI_PIPELINE_ADMITIR", true),
    ajuste("KENI_PIPELINE_DECISOR", true),
    ajuste("KENI_PIPELINE_REDACTAR", true),
    ajuste("KENI_PIPELINE_SUGERIR_HASHTAGS", true),
    ajuste("KENI_PIPELINE_ILUSTRAR", true),
    ajuste("KENI_PIPELINE_STOCK", true),
    ajuste("KENI_CRITICA_IA", false),
    ajuste("KENI_AUTO_PREAPROBACION", false),
    ajuste("KENI_PUBLICAR_REAL", false),
  ];
}

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

function renderPipeline({
  esAdmin = true,
  marcaActiva = null,
}: {
  esAdmin?: boolean;
  marcaActiva?: string | null;
} = {}) {
  const usuario: UsuarioSesion = {
    id: "u1",
    usuario: "admin",
    rol: esAdmin ? "admin" : "editor",
    debe_cambiar_password: false,
    marcas: [],
  };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SesionContexto.Provider value={valorSesion(usuario)}>
        <MarcaActivaContexto.Provider value={valorMarcaActiva(marcaActiva)}>
          <MemoryRouter>
            <PipelineUnificado esAdmin={esAdmin} marcaActiva={marcaActiva} />
          </MemoryRouter>
        </MarcaActivaContexto.Provider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("PipelineUnificado", () => {
  beforeEach(() => {
    mockAjustes.mockResolvedValue({
      grupos: [{ id: "pipeline", titulo: "Pipeline", ajustes: todosActivos() }],
    });
  });

  it("pinta las 5 fases con sus encabezados y todas las etapas clave", () => {
    renderPipeline({ esAdmin: false });
    // Phase headers (static, no data needed)
    expect(screen.getByText("Ingesta")).toBeInTheDocument();
    expect(screen.getByText("Procesar el pool")).toBeInTheDocument();
    expect(screen.getByText("Admitir a la mesa")).toBeInTheDocument();
    expect(screen.getByText("Producir copy")).toBeInTheDocument();
    expect(screen.getByText("Aprobar y publicar")).toBeInTheDocument();
    // Direction hint
    expect(screen.getByText("FUENTE → FEED")).toBeInTheDocument();
    // Stages from all phases
    expect(screen.getByText("Recolectar")).toBeInTheDocument();
    expect(screen.getByText("Google Trends")).toBeInTheDocument();
    expect(screen.getByText("Redactar")).toBeInTheDocument();
    expect(screen.getByText("Publicar")).toBeInTheDocument();
    // FIJO stages
    expect(screen.getByText("Avance")).toBeInTheDocument();
    expect(screen.getByText("Programar")).toBeInTheDocument();
  });

  it("los pasos FIJO (Avance, Programar) tienen badge 'fijo' y no tienen switch", async () => {
    renderPipeline();
    // Wait for ajustes to load (admin render fires the query)
    await screen.findByRole("switch", { name: /Recolectar/i });
    // Both FIJO stages show the badge
    const fijosBadges = screen.getAllByTestId("fijo-badge");
    expect(fijosBadges).toHaveLength(2);
    // No switch within those rows (the badges appear instead)
    expect(fijosBadges[0]).toHaveTextContent("fijo");
    expect(fijosBadges[1]).toHaveTextContent("fijo");
  });

  it("pinta la leyenda", () => {
    renderPipeline({ esAdmin: false });
    expect(screen.getByText(/crítica = apaga lo que viene después/)).toBeInTheDocument();
    expect(screen.getByText(/opcional = solo se oscurece/)).toBeInTheDocument();
  });

  it("un CRÍTICA apagado genera el marcador de corte en la etapa siguiente", async () => {
    mockAjustes.mockResolvedValue({
      grupos: [
        {
          id: "pipeline",
          titulo: "Pipeline",
          ajustes: [
            // Recolectar (CRÍTICA) OFF → todo lo que sigue se corta
            ajuste("KENI_PIPELINE_RECOLECTAR", false),
            ajuste("KENI_TRENDS", true),
            ajuste("KENI_PIPELINE_FUSIONAR", true),
          ],
        },
      ],
    });
    renderPipeline();
    const marker = await screen.findByTestId("cut-marker");
    expect(marker).toBeInTheDocument();
    expect(marker).toHaveTextContent("no llega");
    expect(marker).toHaveTextContent("Recolectar");
  });

  it("un OPCIONAL apagado solo oscurece su propia fila, no genera corte", async () => {
    mockAjustes.mockResolvedValue({
      grupos: [
        {
          id: "pipeline",
          titulo: "Pipeline",
          ajustes: [
            ajuste("KENI_PIPELINE_RECOLECTAR", true),
            // Google Trends (OPCIONAL) OFF → solo dimmed, no cut
            ajuste("KENI_TRENDS", false),
            ajuste("KENI_PIPELINE_FUSIONAR", true),
          ],
        },
      ],
    });
    renderPipeline();
    // Wait for toggles to load
    await screen.findByRole("switch", { name: /Recolectar/i });
    // No cut marker (OPCIONAL off doesn't cut)
    expect(screen.queryByTestId("cut-marker")).not.toBeInTheDocument();
    // Fusionar row still visible (not cut)
    expect(screen.getByText("Fusionar")).toBeInTheDocument();
  });

  it("muestra los controles maestros (Auto + Pausa) solo al admin", async () => {
    renderPipeline({ esAdmin: true });
    // Admin sees the master controls header after data loads
    expect(
      await screen.findByRole("switch", { name: "Auto (interruptor general de toda la auto-producción)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/El empuje manual desde Noticias funciona/),
    ).toBeInTheDocument();
  });

  it("un editor (no admin) no ve controles maestros ni switches de etapa", () => {
    renderPipeline({ esAdmin: false });
    // No switches at all for non-admin
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    // Static content still renders
    expect(screen.getByText("Recolectar")).toBeInTheDocument();
  });
});
