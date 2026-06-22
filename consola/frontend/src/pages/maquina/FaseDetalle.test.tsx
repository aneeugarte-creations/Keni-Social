/**
 * FaseDetalle · la fase «Google Trends» (respaldada por el daemon `trends`) es navegable y su
 * subpágina muestra los Logs como el LOG por barrido del daemon. Sin prompt ni etapa: sus únicos
 * logs son los barridos.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarcaActivaContexto, type ValorMarcaActiva } from "@/hooks/marca-activa-contexto";
import type { BarridoDaemon } from "@/types";

import FaseDetalle from "./FaseDetalle";

function barrido(parcial: Partial<BarridoDaemon>): BarridoDaemon {
  return {
    id: "b1",
    daemon: "trends",
    ts_inicio: "2026-06-12T10:00:00",
    duracion_ms: 1500,
    ok: true,
    resumen: "Ingirió 12 tendencias",
    error_txt: "",
    ...parcial,
  };
}

function stubFetch(barridos: BarridoDaemon[]) {
  const fn = vi.fn(async (url: string | URL) => {
    const s = String(url);
    if (s.includes("/barridos")) {
      return new Response(JSON.stringify({ daemon: "trends", barridos }), { status: 200 });
    }
    // Cola (y cualquier otra llamada): respuesta vacía válida.
    return new Response(JSON.stringify({ en_curso: [], esperando: [] }), { status: 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
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

function renderEn(ruta: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MarcaActivaContexto.Provider value={valorMarcaActiva(null)}>
        <MemoryRouter initialEntries={[ruta]}>
          <Routes>
            <Route path="/maquina/contexto/:proceso/:fase" element={<FaseDetalle />} />
            <Route path="/maquina/contexto" element={<p>contexto</p>} />
          </Routes>
        </MemoryRouter>
      </MarcaActivaContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("FaseDetalle · Google Trends", () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  it("muestra los logs como el log por barrido del daemon trends", async () => {
    stubFetch([barrido({}), barrido({ id: "b2", ok: false, resumen: "", error_txt: "timeout" })]);
    renderEn("/maquina/contexto/investigacion/google-trends");
    // El título de la fase (en la cabecera) y la tabla de barridos del daemon.
    expect(await screen.findByText("Log por barrido")).toBeInTheDocument();
    expect(await screen.findByText("Ingirió 12 tendencias")).toBeInTheDocument();
    // La fila sin resumen cae a su error.
    expect(screen.getByText("timeout")).toBeInTheDocument();
  });
});
