import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";
import { api } from "@/lib/api";
import type { CompararMetricas, OpcionesMetricas, UsuarioSesion } from "@/types";

import { CompararPeriodos } from "./CompararPeriodos";

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

// La marca ahora la manda el switch global (`useMarcaActiva`), así que el componente
// debe renderizarse bajo `MarcaActivaProvider` (y su sesión). Usamos un usuario admin
// sin marcas asignadas → marca activa = null ("Todas"), que es el valor agregado por
// defecto que la comparativa usaba antes (`MARCA_TODAS`).
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
  it("usa el selector de tiempo (atajos · mes · personalizado) para AMBOS periodos", () => {
    vi.spyOn(api, "metricasComparar").mockResolvedValue(RESP);
    renderConProviders(<CompararPeriodos opciones={OPCIONES} rangoActual="mes" />);

    // Etiquetas claras Periodo A (origen) / Periodo B (comparado).
    expect(screen.getByText("Periodo A")).toBeInTheDocument();
    expect(screen.getByText("Periodo B")).toBeInTheDocument();

    // SelectorTiempo expone un combobox "Modo de tiempo" por cada periodo (A y B),
    // que el antiguo SelectorRango (solo presets) NO tenía. Dos periodos => dos
    // selectores de modo: es lo que habilita comparar periodos arbitrarios
    // (mes:AAAA-MM / rango:AAAA-MM-DD_AAAA-MM-DD), no solo preset vs preset.
    const modos = screen.getAllByLabelText("Modo de tiempo");
    expect(modos).toHaveLength(2);
  });

  it("hereda el rango visible como Periodo B (comparado) y consulta la comparativa", async () => {
    const espia = vi.spyOn(api, "metricasComparar").mockResolvedValue(RESP);
    renderConProviders(<CompararPeriodos opciones={OPCIONES} rangoActual="mes" />);

    // Periodo B parte del rango que se ve arriba ("mes"); A parte de otro distinto.
    await screen.findByText("Desglose por marca");
    const { rango_a, rango_b } = espia.mock.calls[0][0];
    expect(rango_b).toBe("mes");
    expect(rango_a).not.toBe("mes");
  });

  it("no revienta con valores null (métrica no comparable) -> muestra '—'", async () => {
    // Regresión: una métrica con valor null (p.ej. 'alcance', que ya no se mide, o
    // engagement no comparable entre redes) reventaba TODA la página vía
    // `valor.toLocaleString` sin guardia. Ahora se muestra "—".
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

  it("muestra el desglose por marca con el nombre legible (no el id crudo)", async () => {
    vi.spyOn(api, "metricasComparar").mockResolvedValue(RESP);
    renderConProviders(<CompararPeriodos opciones={OPCIONES} rangoActual="mes" />);

    expect(await screen.findByText("Desglose por marca")).toBeInTheDocument();
    expect(screen.getByText("Claro Sports")).toBeInTheDocument();
    expect(screen.queryByText("claro_sports")).not.toBeInTheDocument();
  });
});
