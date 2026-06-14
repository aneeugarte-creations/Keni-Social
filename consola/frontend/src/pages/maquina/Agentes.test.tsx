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

// Sesión mutable: por defecto EDITOR (ve banda global + Workers + economía por motor; los agentes
// IA y los servicios NO-IA son admin —endpoint de daemons— y no se montan). Un test la sube a
// admin para comprobar las tarjetas de agente IA y los servicios no-IA por motor.
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
    por_proceso: {
      investigacion: { procesando: 0, pendientes: 0 },
      produccion: { procesando: enCurso.length, pendientes: esperando.length },
    },
    en_curso: enCurso,
    esperando,
    daemons: [],
    presupuesto: {
      nivel: "normal",
      pausada: false,
      presupuesto_tokens_dia: 0,
      margen_manual_pct: 0,
      gastado: { tokens: 0, tokens_in: 0, tokens_out: 0, coste_usd: 0, generaciones: 0 },
      restante_tokens: null,
      pct_usado: null,
      dia: "2026-06-13",
    },
  };
}

const SERIE = { dias: 14, encolados: [], resultados: [] };

const AGG = {
  total: { items: 0, coste_usd: 0, tokens: 0 },
  por_tipo: [],
  por_dia: [],
  por_proceso: {
    investigacion: { total: { items: 1, coste_usd: 0.1, tokens: 100 }, por_tipo: [], por_dia: [] },
    produccion: { total: { items: 2, coste_usd: 0.2, tokens: 200 }, por_tipo: [], por_dia: [] },
  },
};

// Un daemon por clase/motor: agente IA de cada motor (clase ia), un servicio NO-IA por motor
// (clase maquina) y uno de sistema (clase sistema, que NO debe salir en las columnas).
function daemon(parcial: Record<string, unknown>) {
  return {
    visto: "", activo: true, intervalo_seg: 90, tick_seg: 60, ultimo_barrido: "", ultimo_ok: "",
    ultimo_error: "", error_txt: "", duracion_ms: 0, barridos: 3, errores: 0, edad_seg: 10,
    umbral_atraso_seg: 180, estado: "ok", barrido_solicitado: "", barrible: false,
    grupo: "infra", gasta_tokens: false, clase: "sistema", motor: null, clave_gate: null,
    ...parcial,
  };
}
const DAEMONS = {
  daemons: [
    daemon({ daemon: "investigacion", clase: "ia", motor: "investigacion", barrible: true, clave_gate: "KENI_MAQUINA" }),
    daemon({ daemon: "produccion", clase: "ia", motor: "produccion", clave_gate: "KENI_MAQUINA" }),
    daemon({ daemon: "ingesta", clase: "maquina", motor: "investigacion", barrible: true, clave_gate: "KENI_PIPELINE_SELECCION" }),
    daemon({ daemon: "programador", clase: "maquina", motor: "produccion", clave_gate: null }),
    daemon({ daemon: "reaper", clase: "sistema", motor: null, clave_gate: null }),
  ],
  error: null,
};

function stubFetch(cola: unknown) {
  const fn = vi.fn(async (url: string | URL) => {
    const s = String(url);
    if (s.includes("/api/actividad/cola/series")) {
      return new Response(JSON.stringify(SERIE), { status: 200 });
    }
    if (s.includes("/api/actividad/agregados")) {
      return new Response(JSON.stringify(AGG), { status: 200 });
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

describe("Agentes (dos columnas por motor)", () => {
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
  });

  it("en la vista «Todas» pide la cola sin marca", async () => {
    const fetchFn = stubFetch(snapshot([job({})]));
    renderConProviders(<Agentes />);
    expect(await screen.findByText("Copy de nota")).toBeInTheDocument();
    const urls = fetchFn.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes("/api/actividad/cola") && !u.includes("marca="))).toBe(true);
  });

  it("monta la banda global + las dos columnas por motor (editor no ve agentes IA ni servicios)", async () => {
    stubFetch(snapshot([job({})]));
    renderConProviders(<Agentes />);
    // Banda global: presupuesto/parada de emergencia + KPIs de cómputo + enlace a la cola.
    expect(await screen.findByText("Presupuesto y parada de emergencia")).toBeInTheDocument();
    expect(screen.getByText("Ver cola y cómputo")).toBeInTheDocument();
    // Columnas por motor: Workers + economía de cada motor.
    expect(screen.getAllByText("Workers (reactivos)").length).toBe(2);
    expect(screen.getByText("Economía (tokens) de Investigación")).toBeInTheDocument();
    expect(screen.getByText("Economía (tokens) de Producción")).toBeInTheDocument();
    // Actividad (feed cross-motor) al final.
    expect(screen.getByText("Actividad")).toBeInTheDocument();
    // Los agentes IA y los servicios NO-IA son admin (endpoint de daemons): un editor no los ve.
    expect(screen.queryByText("Agentes IA (proactivos)")).toBeNull();
    expect(screen.queryByText("Servicios (no consumen IA)")).toBeNull();
  });

  it("admin ve las tarjetas de agente IA por motor (toggle in-place) y los servicios NO-IA", async () => {
    sesionStub.usuario = { id: "u1", rol: "admin" };
    stubFetch(snapshot([job({})]));
    renderConProviders(<Agentes />);
    // Tarjeta del agente IA de cada motor (bloque por motor), con su toggle on/off in-place.
    expect(await screen.findAllByText("Agentes IA (proactivos)")).toHaveLength(2);
    expect(
      screen.getByRole("switch", { name: /Encender\/apagar el agente investigacion/i }),
    ).toBeInTheDocument();
    // Servicios NO-IA (clase=maquina) por motor, sección aparte.
    expect(screen.getAllByText("Servicios (no consumen IA)").length).toBe(2);
    // El de clase=sistema (reaper) NO aparece en las columnas de la máquina.
    expect(screen.queryByText("reaper")).toBeNull();
  });

  it("?proceso= enfoca la página a un solo motor", async () => {
    sesionStub.usuario = { id: "u1", rol: "admin" };
    stubFetch(snapshot([job({})]));
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/maquina/agentes?proceso=investigacion"]}>
          <Agentes />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Economía (tokens) de Investigación")).toBeInTheDocument();
    // La columna de Producción no se monta cuando está enfocado a Investigación.
    expect(screen.queryByText("Economía (tokens) de Producción")).toBeNull();
  });

  it("señala los jobs prioritarios de la lista de espera", async () => {
    stubFetch(snapshot([job({ etiqueta: "Manual urgente", prioridad: 10 })]));
    renderConProviders(<Agentes />);
    expect(await screen.findByText("Manual urgente")).toBeInTheDocument();
    expect(screen.getByText("prioritario")).toBeInTheDocument();
  });
});
