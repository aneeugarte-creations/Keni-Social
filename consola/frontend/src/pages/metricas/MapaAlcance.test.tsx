import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { Demografia as DemografiaResp, MarcaDisponible } from "@/types";

import { MapaAlcance } from "./MapaAlcance";

// MapLibre toca WebGL (no existe en jsdom): se sustituye por stubs inertes para que el hijo
// del mapa (MapaGlobo) si monte su DOM real (controles) sin pintar canvas. La CSS de MapLibre
// no se procesa (vitest `css: false`).
vi.mock("maplibre-gl", () => {
  class FakeMap {
    on() {
      return this;
    }
    once() {
      return this;
    }
    off() {
      return this;
    }
    remove() {}
    addSource() {}
    addLayer() {}
    getSource() {
      return undefined;
    }
    getLayer() {
      return undefined;
    }
    setStyle() {}
    setPadding() {}
    isStyleLoaded() {
      return false;
    }
    zoomIn() {}
    zoomOut() {}
    resize() {}
    getCanvas() {
      return { style: {} };
    }
  }
  class FakePopup {
    setLngLat() {
      return this;
    }
    setHTML() {
      return this;
    }
    addTo() {
      return this;
    }
    remove() {}
  }
  return { Map: FakeMap, Popup: FakePopup, default: { Map: FakeMap, Popup: FakePopup } };
});

// Centroides deterministas: el test no depende de los datos geograficos reales de `./geo`.
// "ZZ" no resuelve a proposito (ejercita el conteo de "sin ubicar").
vi.mock("./geo", () => ({
  centroidePais: (codigo: string) =>
    (
      {
        MX: { lat: 23.6, lng: -102.5, nombre: "México" },
        US: { lat: 39.8, lng: -98.6, nombre: "Estados Unidos" },
        AR: { lat: -38.4, lng: -63.6, nombre: "Argentina" },
      } as Record<string, { lat: number; lng: number; nombre: string }>
    )[codigo],
  centroideCiudad: () => undefined,
}));

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const MARCAS: MarcaDisponible[] = [{ id: "claro_sports", nombre: "Claro Sports" }];

const RESP_IG: DemografiaResp = {
  red: "instagram",
  distribuciones: {
    country: [
      { clave: "MX", valor: 35.5 },
      { clave: "US", valor: 20.2 },
      { clave: "AR", valor: 10.1 },
      { clave: "ZZ", valor: 4.0 },
    ],
  },
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("MapaAlcance", () => {
  it("pinta selectores y toggle de ciudades", () => {
    vi.spyOn(api, "metricasDemografia").mockResolvedValue(RESP_IG);
    renderConProviders(<MapaAlcance marcas={MARCAS} marcaActual="claro_sports" />);

    expect(screen.getByText("Alcance mundial")).toBeInTheDocument();
    expect(screen.getByLabelText("Marca")).toBeInTheDocument();
    expect(screen.getByLabelText("Red")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Mostrar ciudades" })).toBeInTheDocument();
  });

  it("ubica los países resueltos en el panel y cuenta los no ubicados", async () => {
    vi.spyOn(api, "metricasDemografia").mockResolvedValue(RESP_IG);
    renderConProviders(<MapaAlcance marcas={MARCAS} marcaActual="claro_sports" />);

    // El país líder y su porcentaje aparecen en el panel flotante.
    expect(await screen.findByText("México")).toBeInTheDocument();
    expect(screen.getAllByText(/35\.5/).length).toBeGreaterThan(0);
    // 3 de 4 claves resuelven a coordenadas; la cuarta ("ZZ") se cuenta como sin ubicar.
    expect(screen.getByText(/3 países en el mapa/)).toBeInTheDocument();
    expect(screen.getByText(/1 sin ubicar/)).toBeInTheDocument();
  });

  it("monta el selector de formato y los botones de zoom sobre el globo", async () => {
    vi.spyOn(api, "metricasDemografia").mockResolvedValue(RESP_IG);
    renderConProviders(<MapaAlcance marcas={MARCAS} marcaActual="claro_sports" />);

    // El hijo del mapa (lazy) aporta los controles estilo Climate TRACE.
    expect(await screen.findByLabelText("Formato del mapa")).toBeInTheDocument();
    expect(screen.getByLabelText("Acercar")).toBeInTheDocument();
    expect(screen.getByLabelText("Alejar")).toBeInTheDocument();
  });

  it("degrada con honestidad cuando la red no expone geografía", async () => {
    vi.spyOn(api, "metricasDemografia").mockResolvedValue({ red: "facebook", distribuciones: {} });
    renderConProviders(<MapaAlcance marcas={MARCAS} marcaActual="claro_sports" />);

    expect(await screen.findByText(/no expone alcance geográfico/i)).toBeInTheDocument();
    expect(screen.queryByText(/en el mapa/)).not.toBeInTheDocument();
  });
});
