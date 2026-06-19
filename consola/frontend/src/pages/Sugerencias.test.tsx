import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Sugerencias from "./Sugerencias";

const SUGERENCIAS = [
  {
    id: "s1",
    titulo: "Exportar métricas a Slack",
    detalle: "Un resumen semanal",
    categoria: "mejora",
    estado: "nueva",
    complejidad: "",
    fase: "",
    spec: "",
    plan: "",
    gen_id: "",
    rama: "",
    diff_resumen: "",
    coste_usd: 0,
    autor: "Ana",
    creada: "2026-05-20T10:00:00",
    actualizada: "2026-05-20T10:00:00",
  },
];

const RESP_SUGERENCIAS = {
  sugerencias: SUGERENCIAS,
  // El kanban (Tablero) con sus columnas solo lo ve el superadmin; el equipo ve solo SUS ideas.
  superadmin: true,
  categorias: ["idea", "producto", "mejora", "bug"],
  estados: ["nueva", "discovery", "en_cola", "building", "revision", "hecha"],
  // superadmin: la página pinta el tablero kanban completo (el resto del equipo ve solo MIS ideas).
  superadmin: true,
};

/** Stub de fetch que enruta /api/sugerencias. Captura POSTs/PATCH/DELETE. */
function stubFetch(capturas: { url: string; body: unknown }[] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL, init?: RequestInit) => {
      const ruta = String(url);
      const metodo = (init?.method ?? "GET").toUpperCase();
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      if (metodo !== "GET") capturas.push({ url: ruta, body });

      if (ruta.includes("/api/sugerencias") && metodo === "POST") {
        return new Response(JSON.stringify({ sugerencia: SUGERENCIAS[0] }), { status: 200 });
      }
      if (ruta.includes("/api/sugerencias")) {
        return new Response(JSON.stringify(RESP_SUGERENCIAS), { status: 200 });
      }
      return new Response("{}", { status: 200 });
    }),
  );
}

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Sugerencias · kanban", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("pinta las sugerencias en el tablero kanban", async () => {
    stubFetch();
    renderConProviders(<Sugerencias />);

    expect(await screen.findByText("Exportar métricas a Slack")).toBeInTheDocument();
    expect(screen.getByText("Sugerencias")).toBeInTheDocument();
    // Columnas del flujo de desarrollo (Nolan v2).
    expect(screen.getByText("Discovery")).toBeInTheDocument();
    expect(screen.getByText("Building")).toBeInTheDocument();
  });

  it("crea una idea desde el diálogo de alta", async () => {
    const capturas: { url: string; body: unknown }[] = [];
    stubFetch(capturas);
    renderConProviders(<Sugerencias />);

    await screen.findByText("Exportar métricas a Slack");
    fireEvent.click(screen.getByRole("button", { name: /nueva idea/i }));

    fireEvent.change(await screen.findByLabelText("Título"), {
      target: { value: "Nueva idea" },
    });
    fireEvent.click(screen.getByRole("button", { name: /crear idea/i }));

    await waitFor(() => {
      const alta = capturas.find(
        (c) => c.url.includes("/api/sugerencias") && (c.body as { titulo?: string })?.titulo,
      );
      expect(alta?.body).toMatchObject({ titulo: "Nueva idea" });
    });
  });
});
