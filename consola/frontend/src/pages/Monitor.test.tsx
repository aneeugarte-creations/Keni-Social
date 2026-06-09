import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Monitor from "./Monitor";
import type { ColaJob } from "@/types";

// El Monitor respeta el switch GLOBAL de marca (igual que Pipelines/Actividad). Stub mutable
// para probar tanto la marca concreta como la vista "Todas".
const marcaActivaStub: { marcaActiva: string | null; nombreActiva: string | null } = {
  marcaActiva: null,
  nombreActiva: null,
};
vi.mock("@/hooks/marca-activa-contexto", () => ({
  useMarcaActiva: () => marcaActivaStub,
}));

// Sesión de EDITOR por defecto: el panel admin (máquina de contenido) no se monta y el test
// se centra en el snapshot de cola. (Los toggles admin se prueban en SeccionFuncionalidad.)
vi.mock("@/hooks/sesion-contexto", () => ({
  useSesion: () => ({ usuario: { id: "u1", rol: "editor" } }),
}));

function job(parcial: Partial<ColaJob>): ColaJob {
  return {
    job_id: "j1",
    gen_id: "g1",
    estado: "pendiente",
    worker: "",
    etiqueta: "Copy de nota",
    tipo: "copy",
    marca: "claro-sports",
    gen_estado: "ejecutando",
    fase: "",
    prioridad: 0,
    encolado_hace_s: 12,
    corriendo_hace_s: null,
    ...parcial,
  };
}

function snapshot(esperando: ColaJob[] = [], enCurso: ColaJob[] = [], marca = "") {
  return {
    marca,
    capacidad: { max_jobs: 2, max_cola: 4, tope: 6 },
    conteo: { pendientes: esperando.length, reclamados: enCurso.length, terminados: 0, activos: esperando.length + enCurso.length },
    cola_llena: false,
    procesando: enCurso.length,
    slots_libres: 2 - enCurso.length,
    workers_activos: [],
    en_curso: enCurso,
    esperando,
    daemons: [],
  };
}

const SERIE = { dias: 14, encolados: [], resultados: [] };

function stubFetch(cola: unknown) {
  const fn = vi.fn(async (url: string | URL) => {
    const s = String(url);
    if (s.includes("/api/actividad/cola/series")) {
      return new Response(JSON.stringify(SERIE), { status: 200 });
    }
    if (s.includes("/api/actividad/cola")) {
      return new Response(JSON.stringify(cola), { status: 200 });
    }
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Monitor (cola de generación)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    marcaActivaStub.marcaActiva = null;
    marcaActivaStub.nombreActiva = null;
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("pide la cola CON la marca activa (el bug: antes no filtraba por marca)", async () => {
    marcaActivaStub.marcaActiva = "claro-sports";
    marcaActivaStub.nombreActiva = "Claro Sports";
    const fetchFn = stubFetch(snapshot([job({ etiqueta: "Copy Claro" })], [], "claro-sports"));
    renderConProviders(<Monitor />);
    expect(await screen.findByText("Copy Claro")).toBeInTheDocument();
    // La petición del snapshot lleva ?marca= (el backend acota las listas a esa marca).
    await waitFor(() => {
      const urls = fetchFn.mock.calls.map((c) => String(c[0]));
      expect(urls.some((u) => u.includes("/api/actividad/cola?marca=claro-sports"))).toBe(true);
    });
    // Y las tarjetas señalan la marca filtrada.
    expect(screen.getAllByText("Claro Sports").length).toBeGreaterThan(0);
  });

  it("en la vista «Todas» pide la cola sin marca", async () => {
    const fetchFn = stubFetch(snapshot([job({})]));
    renderConProviders(<Monitor />);
    expect(await screen.findByText("Copy de nota")).toBeInTheDocument();
    const urls = fetchFn.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes("/api/actividad/cola") && !u.includes("marca="))).toBe(true);
  });

  it("señala los jobs prioritarios de la lista de espera", async () => {
    stubFetch(snapshot([job({ etiqueta: "Manual urgente", prioridad: 10 })]));
    renderConProviders(<Monitor />);
    expect(await screen.findByText("Manual urgente")).toBeInTheDocument();
    expect(screen.getByText("prioritario")).toBeInTheDocument();
  });
});
