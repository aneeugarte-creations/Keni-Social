import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { Demografia as DemografiaResp } from "@/types";

import { Demografia } from "./Demografia";
import { useVistaConfig } from "./vistaConfig";

beforeEach(() => {
  useVistaConfig.getState().reset();
});

const RESP: DemografiaResp = {
  red: "instagram",
  distribuciones: {
    gender: [
      { clave: "M", valor: 62.5 },
      { clave: "F", valor: 37.5 },
    ],
    age: [{ clave: "25-34", valor: 41.2 }],
    postsTypes: [
      { clave: "reel", valor: 18 },
      { clave: "carrusel", valor: 7 },
    ],
  },
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("Demografia", () => {
  it("con una red en foco, muestra esa red sin conmutador y con sus distribuciones", async () => {
    useVistaConfig.getState().setRed("instagram");
    vi.spyOn(api, "metricasDemografia").mockResolvedValue(RESP);
    renderConProviders(<Demografia marcaActual="claro_sports" />);

    expect(screen.getByText("Demografía de la audiencia")).toBeInTheDocument();
    // La ficha encabeza con Instagram; con una sola red en foco no hay conmutador a Facebook.
    expect(await screen.findByText("Instagram")).toBeInTheDocument();
    expect(screen.queryByText("Facebook")).not.toBeInTheDocument();
    // Las dimensiones del nuevo diseño (etiquetas de la ficha única).
    expect(await screen.findByText("Género")).toBeInTheDocument();
    expect(screen.getByText("Edad")).toBeInTheDocument();
    expect(screen.getByText("Formatos publicados")).toBeInTheDocument();
  });

  it("sin foco de red, arranca en Instagram y ofrece conmutar a Facebook (no apila redes)", async () => {
    const spy = vi.spyOn(api, "metricasDemografia").mockResolvedValue(RESP);
    renderConProviders(<Demografia marcaActual="claro_sports" />);

    // Una sola red a la vez: "Género" aparece UNA vez, no duplicado por red.
    expect(await screen.findByText("Género")).toBeInTheDocument();
    expect(screen.getAllByText("Género")).toHaveLength(1);

    // El conmutador ofrece Facebook; al pulsarlo, consulta esa red.
    const botonFb = screen.getByRole("button", { name: /facebook/i });
    expect(botonFb).toBeInTheDocument();
    fireEvent.click(botonFb);
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith(
        expect.objectContaining({ red: "facebook" }),
        expect.anything(),
      ),
    );
  });

  it("lista las principales ciudades como línea fina bajo el ranking de lugar", async () => {
    useVistaConfig.getState().setRed("instagram");
    vi.spyOn(api, "metricasDemografia").mockResolvedValue({
      red: "instagram",
      distribuciones: {
        country: [{ clave: "México", valor: 71.2 }],
        city: [
          { clave: "Ciudad de México", valor: 22.4 },
          { clave: "Guadalajara", valor: 8.1 },
        ],
      },
    });
    renderConProviders(<Demografia marcaActual="claro_sports" />);

    expect(await screen.findByText("Ciudades")).toBeInTheDocument();
    expect(screen.getByText("Ciudad de México")).toBeInTheDocument();
    expect(screen.getByText("Guadalajara")).toBeInTheDocument();
  });

  it("muestra países por nombre (ISO→legible) y la edad en orden, sin el bucket «U»", async () => {
    useVistaConfig.getState().setRed("instagram");
    vi.spyOn(api, "metricasDemografia").mockResolvedValue({
      red: "instagram",
      distribuciones: {
        country: [
          { clave: "MX", valor: 71.2 },
          { clave: "US", valor: 8.1 },
        ],
        age: [
          { clave: "25-34", valor: 30 },
          { clave: "U", valor: 5 },
          { clave: "18-24", valor: 20 },
        ],
      },
    });
    renderConProviders(<Demografia marcaActual="claro_sports" />);

    // Códigos ISO mapeados a nombre; nunca se ve el código crudo.
    expect(await screen.findByText("Estados Unidos")).toBeInTheDocument();
    expect(screen.getAllByText("México").length).toBeGreaterThan(0);
    expect(screen.queryByText("MX")).not.toBeInTheDocument();
    // El bucket de edad desconocida ("U") no se pinta.
    expect(screen.queryByText("U")).not.toBeInTheDocument();
  });

  it("degrada con honestidad cuando la red en foco no expone demografía", async () => {
    useVistaConfig.getState().setRed("instagram");
    vi.spyOn(api, "metricasDemografia").mockResolvedValue({ red: "instagram", distribuciones: {} });
    renderConProviders(<Demografia marcaActual="claro_sports" />);

    expect(await screen.findByText(/no expone demografía de audiencia/i)).toBeInTheDocument();
    expect(screen.queryByText("Género")).not.toBeInTheDocument();
  });

  it("si el foco de red no incluye redes demográficas, lo dice sin consultar", async () => {
    useVistaConfig.getState().setRed("tiktok");
    const spy = vi.spyOn(api, "metricasDemografia").mockResolvedValue(RESP);
    renderConProviders(<Demografia marcaActual="claro_sports" />);

    expect(
      await screen.findByText(/las redes en foco no exponen demografía/i),
    ).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });
});
