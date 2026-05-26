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

/** Estado del lazo de auto-desarrollo (flag + auditoría). `activo`/`auditoria` ajustables. */
function estadoAutodes(over: Partial<{ activo: boolean; fijado: boolean; auditoria: object[] }> = {}) {
  return {
    activo: over.activo ?? false,
    fijado_por_entorno: over.fijado ?? false,
    cap_lineas: 400,
    auditoria: over.auditoria ?? [],
    estados: ["bloqueada", "rechazada", "parked", "mergeada", "error"],
  };
}

/** Stub de fetch que enruta /api/sugerencias y /api/autodesarrollo. Captura POSTs. */
function stubFetch(autodes: object, capturas: { url: string; body: unknown }[] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL, init?: RequestInit) => {
      const ruta = String(url);
      const metodo = (init?.method ?? "GET").toUpperCase();
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      if (metodo !== "GET") capturas.push({ url: ruta, body });

      if (ruta.includes("/api/autodesarrollo/flag") && metodo === "POST") {
        return new Response(
          JSON.stringify({ ...estadoAutodes({ activo: !!body?.activo }), mensaje: "ok" }),
          { status: 200 },
        );
      }
      if (ruta.includes("/api/autodesarrollo/implementar") && metodo === "POST") {
        return new Response(JSON.stringify({ mensaje: "Implementación lanzada en segundo plano." }), {
          status: 200,
        });
      }
      if (ruta.includes("/api/autodesarrollo")) {
        return new Response(JSON.stringify(autodes), { status: 200 });
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

describe("Sugerencias · auto-desarrollo (#109)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("muestra el panel de auto-desarrollo desactivado con su advertencia de riesgo", async () => {
    stubFetch(estadoAutodes({ activo: false }));
    renderConProviders(<Sugerencias />);

    expect(await screen.findByText("Auto-desarrollo")).toBeInTheDocument();
    expect(screen.getByText(/Función peligrosa/i)).toBeInTheDocument();
    expect(screen.getByText("Desactivado")).toBeInTheDocument();
    // Con el flag OFF, NO hay botón de «Implementar» en las tarjetas.
    expect(screen.queryByRole("button", { name: /implementar con ia/i })).not.toBeInTheDocument();
  });

  it("activar exige confirmar el riesgo en un diálogo antes de mandar la petición", async () => {
    const capturas: { url: string; body: unknown }[] = [];
    stubFetch(estadoAutodes({ activo: false }), capturas);
    renderConProviders(<Sugerencias />);

    fireEvent.click(await screen.findByRole("button", { name: /^activar$/i }));
    // El botón del diálogo está deshabilitado hasta marcar el checkbox de riesgo.
    const confirmar = await screen.findByRole("button", { name: /activar de todos modos/i });
    expect(confirmar).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox"));
    expect(confirmar).toBeEnabled();
    fireEvent.click(confirmar);

    await waitFor(() => {
      const flag = capturas.find((c) => c.url.includes("/flag"));
      expect(flag).toBeTruthy();
      expect(flag?.body).toMatchObject({ activo: true, confirmo_riesgo: true });
    });
  });

  it("con el lazo activo aparece «Implementar con IA» y dispara la implementación", async () => {
    const capturas: { url: string; body: unknown }[] = [];
    stubFetch(estadoAutodes({ activo: true }), capturas);
    renderConProviders(<Sugerencias />);

    const boton = await screen.findByRole("button", { name: /implementar con ia/i });
    fireEvent.click(boton);

    await waitFor(() => {
      const imp = capturas.find((c) => c.url.includes("/implementar"));
      expect(imp?.body).toMatchObject({ sugerencia_id: "s1" });
    });
  });

  it("pinta la auditoría reciente (mergeada con SHA, parked con motivo)", async () => {
    stubFetch(
      estadoAutodes({
        activo: true,
        auditoria: [
          { id: "a1", fecha: "x", sugerencia_id: "s1", titulo: "Exportar métricas a Slack", estado: "mergeada", sha: "abc12345def" },
          { id: "a2", fecha: "x", sugerencia_id: "s9", titulo: "Otra", estado: "parked", motivo: "ci-roja" },
        ],
      }),
    );
    renderConProviders(<Sugerencias />);

    expect(await screen.findByText("Auditoría reciente")).toBeInTheDocument();
    expect(screen.getByText("abc12345")).toBeInTheDocument(); // SHA recortado
    expect(screen.getByText(/La CI no pasó en verde/i)).toBeInTheDocument();
  });

  it("si el flag está fijado por entorno, no se puede activar desde la UI", async () => {
    stubFetch(estadoAutodes({ activo: false, fijado: true }));
    renderConProviders(<Sugerencias />);

    expect(await screen.findByText(/Fijado por la variable de entorno/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^activar$/i })).toBeDisabled();
  });
});
