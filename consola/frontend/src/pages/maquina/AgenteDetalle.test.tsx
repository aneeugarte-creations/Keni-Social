import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AgenteDetalle from "./AgenteDetalle";
import type { BarridoDaemon, LatidoDaemon } from "@/types";

// El editor de prompt arrastra DetalleDocumento (cadena de imports pesada e irrelevante para
// esta página): lo stubeamos a un nodo vacío. El overlay solo se monta al abrirlo.
vi.mock("@/components/biblioteca/EditorPromptOverlay", () => ({
  EditorPromptOverlay: () => null,
}));

function latido(parcial: Partial<LatidoDaemon>): LatidoDaemon {
  return {
    daemon: "investigacion",
    visto: "2026-06-12T10:00:00",
    activo: true,
    intervalo_seg: 90,
    tick_seg: 60,
    ultimo_barrido: "2026-06-12T10:00:00",
    ultimo_ok: "2026-06-12T10:00:00",
    ultimo_error: "",
    error_txt: "",
    duracion_ms: 1200,
    barridos: 7,
    errores: 1,
    edad_seg: 10,
    umbral_atraso_seg: 180,
    estado: "ok",
    barrido_solicitado: "",
    barrible: true,
    grupo: "investigacion",
    clase: "ia",
    motor: "investigacion",
    gasta_tokens: true,
    clave_gate: "KENI_MAQUINA",
    ...parcial,
  };
}

function barrido(parcial: Partial<BarridoDaemon>): BarridoDaemon {
  return {
    id: "b1",
    daemon: "investigacion",
    ts_inicio: "2026-06-12T10:00:00",
    duracion_ms: 1500,
    ok: true,
    resumen: "Validó 3 notas, descartó 1",
    error_txt: "",
    ...parcial,
  };
}

function stubFetch(opts: { daemons: LatidoDaemon[]; barridos: BarridoDaemon[]; barridos404?: boolean }) {
  const fn = vi.fn(async (url: string | URL) => {
    const s = String(url);
    if (s.includes("/barridos")) {
      if (opts.barridos404) {
        return new Response(JSON.stringify({ error: "no existe" }), { status: 404 });
      }
      return new Response(
        JSON.stringify({ daemon: "investigacion", barridos: opts.barridos }),
        { status: 200 },
      );
    }
    if (s.includes("/api/sistema/daemons")) {
      return new Response(JSON.stringify({ daemons: opts.daemons, error: null }), { status: 200 });
    }
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderEn(agente: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/maquina/agentes/${agente}`]}>
        <Routes>
          <Route path="/maquina/agentes/:agente" element={<AgenteDetalle />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AgenteDetalle", () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  it("pinta cabecera, controles y log por barrido", async () => {
    stubFetch({ daemons: [latido({})], barridos: [barrido({}), barrido({ id: "b2", ok: false, resumen: "", error_txt: "timeout" })] });
    renderEn("investigacion");
    // Cabecera: nombre legible + estado + clase.
    expect(await screen.findByText("Investigación")).toBeInTheDocument();
    expect(screen.getByText("OK")).toBeInTheDocument();
    expect(screen.getByText("IA")).toBeInTheDocument();
    // Log por barrido: el resumen de la primera fila y, en la segunda (sin resumen), el error.
    expect(await screen.findByText("Validó 3 notas, descartó 1")).toBeInTheDocument();
    expect(screen.getByText("timeout")).toBeInTheDocument();
    // Controles de IA: botón de editar prompt.
    expect(screen.getByText(/Editar prompt/)).toBeInTheDocument();
    // Barrer ahora (barrible).
    expect(screen.getByText("Barrer ahora")).toBeInTheDocument();
  });

  it("muestra el estado vacío cuando no hay barridos", async () => {
    stubFetch({ daemons: [latido({})], barridos: [] });
    renderEn("investigacion");
    expect(await screen.findByText(/Aún no hay barridos registrados/)).toBeInTheDocument();
  });

  it("avisa cuando el agente no existe en la lista", async () => {
    stubFetch({ daemons: [latido({ daemon: "ingesta" })], barridos: [] });
    renderEn("fantasma");
    expect(await screen.findByText("Agente no encontrado")).toBeInTheDocument();
  });

  it("daemon sin gate se pinta como «Siempre activo»", async () => {
    stubFetch({ daemons: [latido({ daemon: "reaper", clase: "sistema", motor: null, clave_gate: null, barrible: false })], barridos: [] });
    renderEn("reaper");
    expect(await screen.findByText("Siempre activo")).toBeInTheDocument();
  });
});
