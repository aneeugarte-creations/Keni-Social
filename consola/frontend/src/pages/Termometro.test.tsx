import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Termometro from "./Termometro";

const PAYLOAD_BASE = {
  config: { numero: 8, regiones: "", hora: "07:00", marca: "" },
  skill_disponible: true,
  marcas: [
    { id: "unotv", nombre: "UnoTV" },
    { id: "claro-sports", nombre: "Claro Sports" },
  ],
  regiones_sugeridas: ["EEUU", "Europa", "Asia"],
  ultimo: null,
};

function stubFetch(payload: object) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL) => {
      const ruta = String(url);
      if (ruta.includes("/api/termometro")) {
        return new Response(JSON.stringify(payload), { status: 200 });
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

describe("Termometro", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("carga la config y muestra el encabezado y el formulario", async () => {
    stubFetch(PAYLOAD_BASE);
    renderConProviders(<Termometro />);

    expect(await screen.findByRole("heading", { name: "Termómetro mundial" })).toBeInTheDocument();
    // El formulario de generación aparece tras cargar la config.
    expect(await screen.findByLabelText(/noticias internacionales del día/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generar termómetro/i })).toBeInTheDocument();
  });

  it("deshabilita Generar sin noticias y lo habilita al escribirlas", async () => {
    stubFetch(PAYLOAD_BASE);
    renderConProviders(<Termometro />);

    const boton = await screen.findByRole("button", { name: /generar termómetro/i });
    expect(boton).toBeDisabled();

    const noticias = screen.getByLabelText(/noticias internacionales del día/i);
    fireEvent.change(noticias, { target: { value: "China: algo grande.\nEuropa: otra cosa." } });
    expect(boton).toBeEnabled();
  });

  it("repinta el último termómetro guardado (resultado persistente)", async () => {
    stubFetch({
      ...PAYLOAD_BASE,
      ultimo: {
        historial_id: "h-123",
        documento: "Galeria internacional del dia de ayer",
        titulo: "Termómetro mundial · 2026-05-31",
        fecha: "2026-05-31",
        marca: "unotv",
      },
    });
    renderConProviders(<Termometro />);

    // El documento del último termómetro aparece sin haber generado nada en esta sesión.
    expect(await screen.findByText(/galeria internacional del dia de ayer/i)).toBeInTheDocument();
  });

  it("avisa cuando la skill no está instalada", async () => {
    stubFetch({ ...PAYLOAD_BASE, skill_disponible: false });
    renderConProviders(<Termometro />);

    expect(await screen.findByText(/no está instalada en este equipo/i)).toBeInTheDocument();
    // Sin la skill, no se puede generar aunque haya noticias.
    const noticias = await screen.findByLabelText(/noticias internacionales del día/i);
    fireEvent.change(noticias, { target: { value: "algo" } });
    expect(screen.getByRole("button", { name: /generar termómetro/i })).toBeDisabled();
  });
});
