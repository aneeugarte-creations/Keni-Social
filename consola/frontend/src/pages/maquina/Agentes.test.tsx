import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Agentes from "./Agentes";
import type { ColaJob } from "@/types";

// Agentes respeta el switch GLOBAL de marca (igual que Pipelines/Actividad). Stub mutable
// para probar tanto la marca concreta como la vista "Todas".
const marcaActivaStub: { marcaActiva: string | null; nombreActiva: string | null } = {
  marcaActiva: null,
  nombreActiva: null,
};
vi.mock("@/hooks/marca-activa-contexto", () => ({
  useMarcaActiva: () => marcaActivaStub,
}));

// Sesión mutable: por defecto EDITOR (Workers/economía/actividad; Daemons es admin y no se
// monta). Un test la sube a admin para comprobar el gemelo Daemons.
const sesionStub: { usuario: { id: string; rol: string } } = {
  usuario: { id: "u1", rol: "editor" },
};
vi.mock("@/hooks/sesion-contexto", () => ({
  useSesion: () => sesionStub,
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
    proceso: "produccion",
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

// Un daemon de cada tipo de toggle: uno con gate (Switch) y uno siempre-activo (sin gate).
const DAEMONS = {
  daemons: [
    {
      daemon: "ingesta", visto: "", activo: true, intervalo_seg: 90, tick_seg: 60,
      ultimo_barrido: "", ultimo_ok: "", ultimo_error: "", error_txt: "", duracion_ms: 0,
      barridos: 3, errores: 0, edad_seg: 10, umbral_atraso_seg: 180, estado: "ok",
      barrido_solicitado: "", barrible: true, grupo: "investigacion", gasta_tokens: true,
      clave_gate: "KENI_DAEMON_INGESTA",
    },
    {
      daemon: "reaper", visto: "", activo: true, intervalo_seg: 300, tick_seg: 60,
      ultimo_barrido: "", ultimo_ok: "", ultimo_error: "", error_txt: "", duracion_ms: 0,
      barridos: 5, errores: 0, edad_seg: 10, umbral_atraso_seg: 600, estado: "ok",
      barrido_solicitado: "", barrible: false, grupo: "infra", gasta_tokens: false,
      clave_gate: null,
    },
  ],
  error: null,
};

function stubFetch(cola: unknown) {
  const fn = vi.fn(async (url: string | URL) => {
    const s = String(url);
    if (s.includes("/api/actividad/cola/series")) {
      return new Response(JSON.stringify(SERIE), { status: 200 });
    }
    if (s.includes("/api/actividad/cola")) {
      return new Response(JSON.stringify(cola), { status: 200 });
    }
    if (s.includes("/api/sistema/daemons")) {
      return new Response(JSON.stringify(DAEMONS), { status: 200 });
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

describe("Agentes (Workers + Daemons)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    marcaActivaStub.marcaActiva = null;
    marcaActivaStub.nombreActiva = null;
    sesionStub.usuario = { id: "u1", rol: "editor" };
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("pide la cola CON la marca activa (el bug: antes no filtraba por marca)", async () => {
    marcaActivaStub.marcaActiva = "claro-sports";
    marcaActivaStub.nombreActiva = "Claro Sports";
    const fetchFn = stubFetch(snapshot([job({ etiqueta: "Copy Claro" })], [], "claro-sports"));
    renderConProviders(<Agentes />);
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
    renderConProviders(<Agentes />);
    expect(await screen.findByText("Copy de nota")).toBeInTheDocument();
    const urls = fetchFn.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes("/api/actividad/cola") && !u.includes("marca="))).toBe(true);
  });

  it("monta los gemelos Workers + economía + actividad (editor no ve Daemons)", async () => {
    stubFetch(snapshot([job({})]));
    renderConProviders(<Agentes />);
    expect(await screen.findByText("Workers")).toBeInTheDocument();
    expect(screen.getByText("Economía de tokens")).toBeInTheDocument();
    expect(screen.getByText("Actividad")).toBeInTheDocument();
    // Daemons es admin (endpoint 403 si no): un editor no ve el gemelo.
    expect(screen.queryByText("Daemons")).toBeNull();
  });

  it("admin ve el gemelo Daemons con encendido in-place (Switch con gate, «Siempre activo» sin gate)", async () => {
    sesionStub.usuario = { id: "u1", rol: "admin" };
    stubFetch(snapshot([job({})]));
    renderConProviders(<Agentes />);
    expect(await screen.findByText("Daemons")).toBeInTheDocument();
    // El daemon con `clave_gate` pinta un Switch; el de gate null, el texto «Siempre activo».
    expect(await screen.findByText("ingesta")).toBeInTheDocument();
    expect(
      screen.getByRole("switch", { name: /Encender\/apagar el daemon ingesta/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Siempre activo")).toBeInTheDocument();
  });

  it("señala los jobs prioritarios de la lista de espera", async () => {
    stubFetch(snapshot([job({ etiqueta: "Manual urgente", prioridad: 10 })]));
    renderConProviders(<Agentes />);
    expect(await screen.findByText("Manual urgente")).toBeInTheDocument();
    expect(screen.getByText("prioritario")).toBeInTheDocument();
  });
});
