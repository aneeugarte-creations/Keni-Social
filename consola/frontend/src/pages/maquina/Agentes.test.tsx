import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Agentes from "./Agentes";

// Sesión mutable: la página de Agentes es ADMIN (el endpoint de daemons lo es). Un editor solo
// ve el aviso de «solo administradores»; un admin ve las tarjetas de agente IA.
const sesionStub: { usuario: { id: string; rol: string } } = {
  usuario: { id: "u1", rol: "admin" },
};
vi.mock("@/hooks/sesion-contexto", () => ({
  useSesion: () => sesionStub,
}));

// Un daemon por clase/motor: agente IA de cada motor (clase ia) + servicios NO-IA (clase maquina)
// y uno de sistema (clase sistema) — estos ÚLTIMOS no deben salir como agentes en esta página.
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
    daemon({ daemon: "investigacion", clase: "ia", motor: "investigacion", barrible: true, gasta_tokens: true, clave_gate: "KENI_MAQUINA" }),
    daemon({ daemon: "produccion", clase: "ia", motor: "produccion", clave_gate: "KENI_MAQUINA" }),
    daemon({ daemon: "recolectar", clase: "maquina", motor: "investigacion", barrible: true, clave_gate: "KENI_PIPELINE_RECOLECTAR" }),
    daemon({ daemon: "programador", clase: "maquina", motor: "produccion", clave_gate: null }),
    daemon({ daemon: "limpiador", clase: "sistema", motor: null, clave_gate: null }),
  ],
  error: null,
};

function stubFetch() {
  const fn = vi.fn(async (url: string | URL) => {
    const s = String(url);
    if (s.includes("/api/sistema/daemons")) {
      return new Response(JSON.stringify(DAEMONS), { status: 200 });
    }
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderConProviders(ui: React.ReactElement, ruta = "/maquina/agentes") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[ruta]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Agentes (agents-first)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sesionStub.usuario = { id: "u1", rol: "admin" };
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("un editor solo ve el aviso de administradores (sin tarjetas de agente)", async () => {
    sesionStub.usuario = { id: "u1", rol: "editor" };
    stubFetch();
    renderConProviders(<Agentes />);
    expect(
      await screen.findByText(/solo están disponibles para administradores/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("switch")).toBeNull();
  });

  it("admin ve una tarjeta por agente IA, con su toggle in-place y sus acciones", async () => {
    stubFetch();
    renderConProviders(<Agentes />);
    // Toggle on/off in-place de cada agente IA (clase=ia).
    expect(
      await screen.findByRole("switch", { name: /Encender\/apagar el agente investigacion/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("switch", { name: /Encender\/apagar el agente produccion/i }),
    ).toBeInTheDocument();
    // Acciones in-place subidas a la tarjeta: barrer (solo barrible) y editar prompts.
    expect(screen.getByRole("button", { name: /Barrer ahora/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Editar: Verificar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Editar: Redactar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Editar: Ilustrar/i })).toBeInTheDocument();
    // «Ver log» enlaza al detalle de cada agente.
    const logs = screen.getAllByRole("link", { name: /Ver log/i });
    const hrefs = logs.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/maquina/agentes/investigacion");
    expect(hrefs).toContain("/maquina/agentes/produccion");
  });

  it("NO muestra los daemons que no son agentes IA (clase maquina/sistema)", async () => {
    stubFetch();
    renderConProviders(<Agentes />);
    await screen.findByRole("switch", { name: /agente investigacion/i });
    // Servicios NO-IA (clase maquina) y de sistema NO aparecen como agentes.
    expect(screen.queryByText(/Recolección de noticias/)).toBeNull();
    expect(screen.queryByText(/Programador de parrilla/)).toBeNull();
    expect(screen.queryByText(/Limpiador/)).toBeNull();
  });

  it("?proceso= enfoca la página a un solo motor", async () => {
    stubFetch();
    renderConProviders(<Agentes />, "/maquina/agentes?proceso=investigacion");
    expect(
      await screen.findByRole("switch", { name: /agente investigacion/i }),
    ).toBeInTheDocument();
    // El agente del otro motor (producción) no se monta cuando está enfocado a investigación.
    expect(screen.queryByRole("switch", { name: /agente produccion/i })).toBeNull();
  });
});
