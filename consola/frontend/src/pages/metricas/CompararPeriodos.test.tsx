import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";
import { api } from "@/lib/api";
import type { CompararMetricas, OpcionesMetricas, UsuarioSesion } from "@/types";

import { CompararPeriodos } from "./CompararPeriodos";
import { diasDePeriodo, seSolapan } from "./rango";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const OPCIONES: OpcionesMetricas = {
  marcas: [
    { id: "unotv", nombre: "UnoTV" },
    { id: "claro_sports", nombre: "Claro Sports" },
  ],
  rangos: [
    { id: "mes", etiqueta: "Este mes" },
    { id: "mes_cerrado", etiqueta: "Mes cerrado" },
  ],
};

const RESP: CompararMetricas = {
  marca: "",
  rango_a: "mes_cerrado",
  rango_b: "mes",
  etiqueta_a: "Mes cerrado",
  etiqueta_b: "Este mes",
  fuente: "muestra",
  generado_en: "2026-06-02T00:00:00",
  total: {
    metricas: [
      { metrica: "visualizaciones", a: 1000, b: 1500, diferencia: 500, variacion_pct: 50 },
    ],
  },
  // `marca` ya viene resuelto del backend; el id `claro_sports` se resuelve por catálogo.
  por_marca: [
    {
      marca_id: "claro_sports",
      marca: "Claro Sports",
      comparativa: [
        { metrica: "visualizaciones", a: 400, b: 600, diferencia: 200, variacion_pct: 50 },
      ],
    },
  ],
};

beforeEach(() => {
  // El provider resuelve el catálogo de marcas vía `publicacionesOpciones`; lo mockeamos
  // para no hacer fetch real. No afecta a la marca activa (deriva de la sesión).
  vi.spyOn(api, "publicacionesOpciones").mockResolvedValue({
    marcas: [
      { id: "unotv", nombre: "UnoTV" },
      { id: "claro-sports", nombre: "Claro Sports" },
    ],
    redes: [],
    estados: [],
    lineas: [],
  } as never);
});

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const sesion: ValorSesion = {
    usuario: {
      id: "u-admin",
      usuario: "admin",
      rol: "admin",
      debe_cambiar_password: false,
      marcas: [],
    } as UsuarioSesion,
    cargando: false,
    iniciarSesion: vi.fn(),
    verificarConPasskey: vi.fn(),
    entrarConPasskey: vi.fn(),
    verificarConCodigo: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesion}>
        <MarcaActivaProvider>{ui}</MarcaActivaProvider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("CompararPeriodos", () => {
  it("usa el selector de tiempo (periodos comunes · mes · fechas exactas) para AMBOS periodos", () => {
    vi.spyOn(api, "metricasComparar").mockResolvedValue(RESP);
    renderConProviders(<CompararPeriodos opciones={OPCIONES} rangoActual="mes" />);

    // Etiquetas claras: A = "Comparar con", B = "Periodo actual".
    expect(screen.getByText("Comparar con")).toBeInTheDocument();
    expect(screen.getByText("Periodo actual")).toBeInTheDocument();

    const modos = screen.getAllByLabelText("Tipo de periodo");
    expect(modos).toHaveLength(2);
  });

  it("hereda el periodo visible como B (actual) y deriva A como su anterior adyacente", async () => {
    const espia = vi.spyOn(api, "metricasComparar").mockResolvedValue(RESP);
    renderConProviders(<CompararPeriodos opciones={OPCIONES} rangoActual="mes" />);

    // B parte del periodo que se ve arriba ("mes"); A es el periodo inmediatamente
    // ANTERIOR adyacente: un token `rango:` de la MISMA longitud (comparable), nunca
    // el propio "mes" ni un preset solapado.
    await screen.findByText("Desglose por marca");
    const { rango_a = "", rango_b = "" } = espia.mock.calls[0][0];
    expect(rango_b).toBe("mes");
    expect(rango_a).not.toBe("mes");
    expect(rango_a).toMatch(/^rango:\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}$/);
    expect(diasDePeriodo(rango_a)).toBe(diasDePeriodo("mes"));
    expect(seSolapan(rango_a, rango_b)).toBe(false);
  });

  it("no revienta con valores null (métrica no comparable) -> muestra '—'", async () => {
    const respNull = {
      ...RESP,
      total: {
        metricas: [
          { metrica: "alcance", a: null, b: null, diferencia: null, variacion_pct: null },
          { metrica: "visualizaciones", a: 1000, b: 1500, diferencia: 500, variacion_pct: 50 },
        ],
      },
    } as unknown as CompararMetricas;
    vi.spyOn(api, "metricasComparar").mockResolvedValue(respNull);
    renderConProviders(<CompararPeriodos opciones={OPCIONES} rangoActual="mes" />);

    // Render asíncrono (la query resuelve): si reventara, esto lanzaría. El valor null
    // de 'alcance' se pinta "—" en vez de tirar la página.
    expect((await screen.findAllByText("—")).length).toBeGreaterThan(0);
  });

  it("marca como 'Nuevo' el crecimiento desde cero (a=0, b>0) en vez de '0.0 %'", async () => {
    // El backend devuelve variacion_pct = 0.0 cuando la base es 0 (división imposible):
    // un BadgeDelta "0.0 %" ocultaría el arranque. Se muestra un badge "Nuevo".
    const respDesdeCero: CompararMetricas = {
      ...RESP,
      total: {
        metricas: [
          { metrica: "visualizaciones", a: 0, b: 500, diferencia: 500, variacion_pct: 0 },
        ],
      },
      por_marca: [],
    };
    vi.spyOn(api, "metricasComparar").mockResolvedValue(respDesdeCero);
    renderConProviders(<CompararPeriodos opciones={OPCIONES} rangoActual="mes" />);

    expect(await screen.findByText("Nuevo")).toBeInTheDocument();
    expect(screen.queryByText("0.0 %")).not.toBeInTheDocument();
  });

  it("muestra el engagement en PUNTOS porcentuales ('+0.4 pts'), nunca variación relativa", async () => {
    // 2.0 % → 2.4 % de engagement es una mejora de 0.4 PUNTOS. La variación relativa
    // del porcentaje ("+20.0 %") es engañosa para un ratio y no se muestra jamás.
    const respEngagement: CompararMetricas = {
      ...RESP,
      total: {
        metricas: [
          { metrica: "engagement_pct", a: 2.0, b: 2.4, diferencia: 0.4, variacion_pct: 20 },
        ],
      },
      por_marca: [],
    };
    vi.spyOn(api, "metricasComparar").mockResolvedValue(respEngagement);
    renderConProviders(<CompararPeriodos opciones={OPCIONES} rangoActual="mes" />);

    expect(await screen.findByText("+0.4 pts")).toBeInTheDocument();
    expect(screen.queryByText(/\+20/)).not.toBeInTheDocument();
  });

  it("no pinta insignia de engagement cuando la diferencia es null (no calculable)", async () => {
    // El backend emite diferencia=null cuando el engagement no es calculable en alguno
    // de los periodos: sin dato no se inventa badge (ni "0.0 pts" ni "—").
    const respSinDiferencia = {
      ...RESP,
      total: {
        metricas: [
          { metrica: "engagement_pct", a: null, b: 2.4, diferencia: null, variacion_pct: null },
        ],
      },
      por_marca: [],
    } as unknown as CompararMetricas;
    vi.spyOn(api, "metricasComparar").mockResolvedValue(respSinDiferencia);
    renderConProviders(<CompararPeriodos opciones={OPCIONES} rangoActual="mes" />);

    // La tarjeta se pinta (valor B), pero sin badge de pts ni de %.
    expect(await screen.findByText("Engagement")).toBeInTheDocument();
    expect(screen.queryByText(/pts/)).not.toBeInTheDocument();
  });

  it("muestra el desglose por marca con el nombre legible (no el id crudo)", async () => {
    vi.spyOn(api, "metricasComparar").mockResolvedValue(RESP);
    renderConProviders(<CompararPeriodos opciones={OPCIONES} rangoActual="mes" />);

    expect(await screen.findByText("Desglose por marca")).toBeInTheDocument();
    expect(screen.getByText("Claro Sports")).toBeInTheDocument();
    expect(screen.queryByText("claro_sports")).not.toBeInTheDocument();
  });
});
