import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { AdsMetricas, DesgloseAds } from "@/types";

import { SeccionAds } from "./SeccionAds";
import { useVistaConfig } from "./vistaConfig";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const RESP: AdsMetricas = {
  ads: [
    {
      nombre: "Campaña Mundial 2026",
      red: "facebook",
      impresiones: 250000,
      gasto: 12345,
      clics: 4200,
      moneda: "MXN",
      inicio: "2026-05-26",
      fin: "2026-06-01",
      es_post_impulsado: false,
    },
    {
      nombre: "Post impulsado noticias",
      red: "instagram",
      impresiones: 80000,
      gasto: 2500,
      clics: 900,
      moneda: "MXN",
      inicio: "2026-05-28",
      fin: "2026-06-01",
      es_post_impulsado: true,
    },
  ],
  total: {
    visualizaciones: 330000,
    gasto: 14845,
    clics: 5100,
    campanias: 2,
    moneda: "MXN",
  },
  etiqueta_rango: "Últimos 7 días",
  generado_en: "2026-06-02T00:00:00",
};

// Misma respuesta, pero con campos de rendimiento (CTR/CPC/CPM/Conversiones) y el id de
// proveedor que habilita el drill-down. Una de las dos campañas los trae.
const RESP_AVANZADO: AdsMetricas = {
  ...RESP,
  ads: [
    {
      ...RESP.ads[0],
      ctr: 2.1,
      cpc: 2.94,
      cpm: 49.38,
      conversiones: 320,
      provider_campaign_id: "cmp_123",
    },
    RESP.ads[1],
  ],
};

const DESGLOSE: DesgloseAds = {
  adgroups: [
    { nombre: "Conjunto principal", impresiones: 180000, clics: 3100, gasto: 9000, conversiones: 240, moneda: "MXN" },
  ],
  ads: [
    { nombre: "Creativo video 15s", adgroup: "Conjunto principal", impresiones: 120000, clics: 2200, gasto: 6000, moneda: "MXN" },
  ],
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  vi.restoreAllMocks();
  // La config de vista es un singleton global: restáurala para no contaminar otros tests.
  useVistaConfig.getState().reset();
});

describe("SeccionAds", () => {
  it("pinta las campañas con cifras es-MX e Impresiones (no Vistas) como término", async () => {
    vi.spyOn(api, "metricasAds").mockResolvedValue(RESP);
    renderConProviders(<SeccionAds marcaActual="__todas__" rangoActual="semana" />);

    // Espera al dato cargado (el título "Publicidad" ya se pinta durante la carga).
    expect(await screen.findByText("Campaña Mundial 2026")).toBeInTheDocument();
    expect(screen.getByText("Publicidad")).toBeInTheDocument();
    // En Ads el término correcto es "Impresiones" (KPI + columna), nunca "Vistas".
    expect(screen.getAllByText("Impresiones").length).toBeGreaterThan(0);
    expect(screen.queryByText("Vistas")).not.toBeInTheDocument();
    // KPI de impresiones totales: compacto visible, completo es-MX en el title.
    expect(screen.getByTitle("330,000")).toBeInTheDocument();
    // Gasto con separador de miles es-MX y la moneda de la fuente.
    expect(screen.getByText("14,845 MXN")).toBeInTheDocument();
    expect(screen.getByText("12,345 MXN")).toBeInTheDocument();
    // Las campañas con su red LEGIBLE (facebook -> "Facebook").
    expect(screen.getByText("Facebook")).toBeInTheDocument();
    expect(screen.queryByText("facebook")).not.toBeInTheDocument();
  });

  it("no renderiza la sección sin campañas en el periodo (no ensucia el dashboard)", async () => {
    const espia = vi.spyOn(api, "metricasAds").mockResolvedValue({
      ...RESP,
      ads: [],
      total: { visualizaciones: 0, gasto: 0, clics: 0, campanias: 0, moneda: "MXN" },
    });
    const { container } = renderConProviders(
      <SeccionAds marcaActual="__todas__" rangoActual="semana" />,
    );

    await vi.waitFor(() => expect(espia).toHaveBeenCalled());
    await vi.waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(screen.queryByText("Publicidad")).not.toBeInTheDocument();
  });

  it("muestra un mensaje de error honesto si las campañas no cargan", async () => {
    vi.spyOn(api, "metricasAds").mockRejectedValue(new Error("boom"));
    renderConProviders(<SeccionAds marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText("No se pudieron cargar las campañas de Ads."),
    ).toBeInTheDocument();
  });

  it("NO ofrece las columnas de rendimiento si la fuente no las trae", async () => {
    vi.spyOn(api, "metricasAds").mockResolvedValue(RESP);
    renderConProviders(<SeccionAds marcaActual="__todas__" rangoActual="semana" />);

    await screen.findByText("Campaña Mundial 2026");
    expect(screen.queryByText("CTR")).not.toBeInTheDocument();
    expect(screen.queryByText("CPC")).not.toBeInTheDocument();
    expect(screen.queryByText("Conversiones")).not.toBeInTheDocument();
  });

  it("ofrece las columnas de rendimiento cuando la fuente las trae, con formato es-MX", async () => {
    vi.spyOn(api, "metricasAds").mockResolvedValue(RESP_AVANZADO);
    renderConProviders(<SeccionAds marcaActual="__todas__" rangoActual="semana" />);

    await screen.findByText("Campaña Mundial 2026");
    // Cabeceras avanzadas presentes.
    expect(screen.getByText("CTR")).toBeInTheDocument();
    expect(screen.getByText("CPC")).toBeInTheDocument();
    expect(screen.getByText("CPM")).toBeInTheDocument();
    expect(screen.getByText("Conversiones")).toBeInTheDocument();
    // Valores con formato es-MX (CTR como porcentaje; CPC/CPM con 2 decimales).
    expect(screen.getByText("2.1 %")).toBeInTheDocument();
    expect(screen.getByText("2.94 MXN")).toBeInTheDocument();
    expect(screen.getByText("49.38 MXN")).toBeInTheDocument();
  });

  it("expande el desglose (conjuntos + anuncios) de una campaña con id de proveedor", async () => {
    vi.spyOn(api, "metricasAds").mockResolvedValue(RESP_AVANZADO);
    const espia = vi.spyOn(api, "metricasAdsDesglose").mockResolvedValue(DESGLOSE);
    renderConProviders(<SeccionAds marcaActual="__todas__" rangoActual="semana" />);

    // Solo la campaña con `provider_campaign_id` ofrece el botón de desglose.
    const boton = await screen.findByLabelText("Ver desglose");
    fireEvent.click(boton);

    // "Conjunto principal" aparece como nombre del conjunto y como columna del anuncio.
    expect((await screen.findAllByText("Conjunto principal")).length).toBeGreaterThan(0);
    expect(screen.getByText("Creativo video 15s")).toBeInTheDocument();
    expect(espia).toHaveBeenCalledWith("cmp_123", expect.anything(), expect.anything());
  });

  it("degrada sin romper si el desglose no existe (404/error)", async () => {
    vi.spyOn(api, "metricasAds").mockResolvedValue(RESP_AVANZADO);
    vi.spyOn(api, "metricasAdsDesglose").mockRejectedValue(new Error("404"));
    renderConProviders(<SeccionAds marcaActual="__todas__" rangoActual="semana" />);

    fireEvent.click(await screen.findByLabelText("Ver desglose"));

    expect(
      await screen.findByText("Sin desglose disponible para esta campaña."),
    ).toBeInTheDocument();
  });
});
