/**
 * Smoke tests del PipelineUnificado: las 5 fases, los toggles, el ⚙ por etapa
 * y la cascada de críticas (una CRÍTICA apagada oscurece todo lo que sigue).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MarcaActivaContexto, type ValorMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { AjusteAdmin, UsuarioSesion } from "@/types";

import { PipelineUnificado } from "./PipelineUnificado";

const { mockAjustes, mockCola, mockPreview, mockConfirmar, mockGuardarAjuste } = vi.hoisted(() => ({
  mockAjustes: vi.fn(),
  mockCola: vi.fn(),
  mockPreview: vi.fn(),
  mockConfirmar: vi.fn(),
  mockGuardarAjuste: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    ajustes: mockAjustes,
    cola: mockCola,
    colaPreview: mockPreview,
    guardarAjuste: mockGuardarAjuste,
  },
  mensajeError: (e: unknown) => String(e),
  ApiError: class ApiError extends Error {},
}));

vi.mock("@/components/comunes/confirmar", () => ({ confirmar: mockConfirmar }));

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

function knob(
  clave: string,
  tipo: AjusteAdmin["tipo"],
  valor: number | string,
  etiqueta: string,
): AjusteAdmin {
  return { clave, tipo, valor, etiqueta, ayuda: "", grupo: "pipeline", peligroso: false, fuente: "store", defecto: valor, min: 0 };
}

function todosActivos(): AjusteAdmin[] {
  return [
    ajuste("KENI_MAQUINA", true),
    ajuste("KENI_GENERACION_PAUSADA", false),
    ajuste("KENI_PIPELINE_RECOLECTAR", true),
    ajuste("KENI_TRENDS", true),
    ajuste("KENI_PIPELINE_FUSIONAR", true),
    ajuste("KENI_PIPELINE_TRADUCIR", true),
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
    // Knobs operacionales por etapa (se editan en el ⚙ de su fila).
    ajuste("KENI_RENDIMIENTO_RANKING", false),
    knob("KENI_PROMOVER_MIN_SCORE", "float", 0.45, "Relevancia mínima"),
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
    mockCola.mockResolvedValue({ en_curso: [], esperando: [] });
    mockPreview.mockResolvedValue({ marcas: [] });
    mockConfirmar.mockResolvedValue(true);
    mockGuardarAjuste.mockResolvedValue({ ajuste: ajuste("KENI_PIPELINE_REDACTAR", true) });
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
  });

  it("Avance y Programar NO se pintan como etapas (corren siempre; no son operables)", () => {
    renderPipeline({ esAdmin: false });
    expect(screen.queryByText("Avance")).not.toBeInTheDocument();
    expect(screen.queryByText("Programar")).not.toBeInTheDocument();
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
    // La cascada es POR MARCA: se pinta con una marca concreta (en «Todas las marcas» cada marca
    // diverge y no hay un único corte).
    renderPipeline({ marcaActiva: "unotv" });
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

  it("muestra el control maestro (Auto) solo al admin", async () => {
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

  it("las etapas con knobs muestran su ⚙ y abren su diálogo de ajustes; las demás no", async () => {
    renderPipeline();
    // Admitir tiene knobs operacionales → su ⚙ aparece...
    const gear = await screen.findByRole("button", { name: "Ajustes de Admitir" });
    // ...y Verificar (sin knobs) no lo tiene.
    expect(screen.queryByRole("button", { name: "Ajustes de Verificar" })).not.toBeInTheDocument();
    // El ⚙ abre el diálogo con el knob de ESA etapa (no su toggle on/off).
    fireEvent.click(gear);
    expect(await screen.findByText("Admitir · ajustes")).toBeInTheDocument();
    expect(screen.getByText("Relevancia mínima")).toBeInTheDocument();
  });

  it("el ⚙ no se pinta para un editor (no admin)", () => {
    renderPipeline({ esAdmin: false });
    expect(screen.queryByRole("button", { name: /^Ajustes de / })).not.toBeInTheDocument();
  });

  it("en «Todas las marcas» pinta la MATRIZ: un toggle por marca en cada etapa, con su label", async () => {
    function porMarca(clave: string, marca: string, nombre: string, valor: boolean): AjusteAdmin {
      return {
        clave: `${clave}::${marca}`,
        tipo: "bool",
        valor,
        etiqueta: `${nombre} · Recolectar`,
        ayuda: "",
        grupo: "automatizacion_marca_investigacion",
        peligroso: false,
        fuente: "store",
        defecto: false,
      };
    }
    mockAjustes.mockResolvedValue({
      grupos: [
        { id: "pipeline", titulo: "Pipeline", ajustes: todosActivos() },
        {
          id: "automatizacion_marca_investigacion",
          titulo: "Excepciones por marca",
          ajustes: [
            porMarca("KENI_PIPELINE_RECOLECTAR", "unotv", "UnoTV", true),
            porMarca("KENI_PIPELINE_RECOLECTAR", "claro-sports", "Claro Sports", false),
          ],
        },
      ],
    });
    renderPipeline(); // marcaActiva = null → «Todas las marcas»
    // Cada marca aporta su switch en la etapa Recolectar, etiquetado con su nombre.
    expect(await screen.findByRole("switch", { name: "UnoTV · Recolectar" })).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Claro Sports · Recolectar" })).toBeInTheDocument();
    expect(screen.getByText("UnoTV")).toBeInTheDocument();
    expect(screen.getByText("Claro Sports")).toBeInTheDocument();
  });

  it("Redactar apagado con piezas en espera: muestra la pista y pide confirmación al encenderlo", async () => {
    mockAjustes.mockResolvedValue({
      grupos: [
        {
          id: "pipeline",
          titulo: "Pipeline",
          ajustes: [
            ...todosActivos().filter((a) => a.clave !== "KENI_PIPELINE_REDACTAR"),
            ajuste("KENI_PIPELINE_REDACTAR", false),
          ],
        },
      ],
    });
    mockPreview.mockResolvedValue({ marcas: [{ marca: "unotv", redactar: 7 }] });
    renderPipeline({ marcaActiva: "unotv" });
    // La pista "si activas: ~N piezas" acompaña al toggle de Redactar.
    expect(await screen.findByText(/si activas: ~7 piezas/)).toBeInTheDocument();
    // Encender el toggle pide confirmación antes de persistir.
    const sw = await screen.findByRole("switch", { name: /KENI_PIPELINE_REDACTAR \(Redactar\)/ });
    fireEvent.click(sw);
    await waitFor(() => expect(mockConfirmar).toHaveBeenCalled());
  });
});
