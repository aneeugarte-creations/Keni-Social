import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SugerenciaReciclaje } from "@/types";

import { PanelReciclaje } from "./PanelReciclaje";

const SUGERENCIAS: SugerenciaReciclaje[] = [
  {
    id: "s1",
    titulo: "Especial Día de las Madres",
    marca: "unotv",
    marca_nombre: "UnoTV",
    red: "x",
    red_nombre: "X",
    fecha_creacion: "2025-05-01T10:00:00",
    fecha_actualizacion: "2025-05-01T10:00:00",
    motivo: "efemeride",
    motivo_detalle: "Día de las Madres es en 5 días: este contenido vuelve a ser relevante.",
    puntuacion: 1016,
    rendimiento: null,
  },
];

const PARAMETROS = {
  ventana_efemeride_dias: 21,
  edad_minima_evergreen_dias: 30,
  edad_minima_antiguedad_dias: 60,
  umbral_engagement_rendimiento: 3.5,
};

/** Stub de fetch: GET sugerencias devuelve `sugerencias`; POST /reciclar responde ok. */
function stubFetch(sugerencias = SUGERENCIAS) {
  const fn = vi.fn(async (url: string | URL, init?: RequestInit) => {
    const ruta = String(url);
    const metodo = (init?.method ?? "GET").toUpperCase();
    if (ruta.includes("/api/reciclaje/sugerencias") && metodo === "GET") {
      return new Response(JSON.stringify({ sugerencias, parametros: PARAMETROS }), {
        status: 200,
      });
    }
    if (ruta.includes("/reciclar") && metodo === "POST") {
      return new Response(
        JSON.stringify({ publicacion: { id: "copia" }, encolado: true }),
        { status: 200 },
      );
    }
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("PanelReciclaje (sugerencias proactivas)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("muestra el panel con el recuento y revela las sugerencias al expandir", async () => {
    stubFetch();
    renderConProviders(
      <PanelReciclaje filtros={{}} onConfigurarCadencia={() => {}} />,
    );

    // Cabecera del panel con su recuento.
    const cabecera = await screen.findByRole("button", { name: /sugerencias para reciclar/i });
    expect(cabecera).toHaveAttribute("aria-expanded", "false");

    // Plegado: el contenido no se ve todavía.
    expect(screen.queryByText("Especial Día de las Madres")).not.toBeInTheDocument();

    fireEvent.click(cabecera);
    expect(await screen.findByText("Especial Día de las Madres")).toBeInTheDocument();
    // El detalle concreto de la pieza (distinto de la descripción general del panel).
    expect(screen.getByText(/Día de las Madres es en 5 días/i)).toBeInTheDocument();
    expect(screen.getByText("Efeméride")).toBeInTheDocument();
  });

  it("no se renderiza cuando no hay candidatas", async () => {
    stubFetch([]);
    const { container } = renderConProviders(
      <PanelReciclaje filtros={{}} onConfigurarCadencia={() => {}} />,
    );
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("lanza el reciclado existente al pulsar «Reciclar»", async () => {
    const fn = stubFetch();
    renderConProviders(
      <PanelReciclaje filtros={{}} onConfigurarCadencia={() => {}} />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /sugerencias para reciclar/i }));
    const boton = await screen.findByRole("button", { name: /reciclar especial día de las madres/i });
    fireEvent.click(boton);

    await waitFor(() => {
      const post = fn.mock.calls.find(
        ([url, init]) =>
          String(url).includes("/api/publicaciones/s1/reciclar") &&
          (init?.method ?? "").toUpperCase() === "POST",
      );
      expect(post).toBeTruthy();
    });
  });
});
