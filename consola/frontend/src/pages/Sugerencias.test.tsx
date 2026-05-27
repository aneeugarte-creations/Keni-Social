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
    autor: "Ana",
    creada: "2026-05-20T10:00:00",
  },
];

const RESP_SUGERENCIAS = {
  sugerencias: SUGERENCIAS,
  categorias: ["idea", "producto", "mejora", "bug"],
  estados: ["nueva", "en-estudio", "hecha", "descartada"],
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

describe("Sugerencias · buzón", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lista las sugerencias del buzón", async () => {
    stubFetch();
    renderConProviders(<Sugerencias />);

    expect(await screen.findByText("Exportar métricas a Slack")).toBeInTheDocument();
    expect(screen.getByText("Buzón de sugerencias")).toBeInTheDocument();
  });

  it("no muestra ningún panel ni botón de auto-desarrollo", async () => {
    stubFetch();
    renderConProviders(<Sugerencias />);

    expect(await screen.findByText("Exportar métricas a Slack")).toBeInTheDocument();
    expect(screen.queryByText(/auto-desarrollo/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /implementar con ia/i })).not.toBeInTheDocument();
  });

  it("envía una nueva sugerencia con el formulario", async () => {
    const capturas: { url: string; body: unknown }[] = [];
    stubFetch(capturas);
    renderConProviders(<Sugerencias />);

    fireEvent.change(await screen.findByLabelText("Título"), {
      target: { value: "Nueva idea" },
    });
    fireEvent.click(screen.getByRole("button", { name: /enviar sugerencia/i }));

    await waitFor(() => {
      const alta = capturas.find((c) => c.url.includes("/api/sugerencias"));
      expect(alta?.body).toMatchObject({ titulo: "Nueva idea" });
    });
  });
});
