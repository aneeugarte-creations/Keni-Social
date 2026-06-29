/**
 * Tests de la página Controles (`/maquina/controles`): el mando único de la máquina.
 *
 * Cubre: el interruptor maestro y la pausa se renderizan; hay al menos un switch de
 * investigación y uno de producción; la sección avanzada está colapsada por defecto;
 * la nota sobre el empuje manual siempre está presente.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import {
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "@/hooks/marca-activa-contexto";
import type { AjusteAdmin } from "@/types";

import Controles from "./Controles";

// vi.mock se eleva (hoisted) al tope del archivo: NO puede referenciar variables definidas
// después. Todo el valor de respuesta debe estar inline en la factory.
vi.mock("@/lib/api", () => {
  function aj(
    clave: string,
    etiqueta: string,
    valor = true,
    grupoId = "test",
  ): AjusteAdmin {
    return {
      clave,
      tipo: "bool",
      etiqueta,
      ayuda: `Ayuda de ${etiqueta}`,
      grupo: grupoId,
      peligroso: false,
      valor,
      fuente: "store",
      defecto: false,
    };
  }

  const AJUSTES = {
    grupos: [
      {
        id: "maquina_global",
        titulo: "Máquina",
        ajustes: [
          aj("KENI_MAQUINA", "Máquina (auto)"),
          aj("KENI_GENERACION_PAUSADA", "Pausa de emergencia", false),
        ],
      },
      {
        id: "pipeline_investigacion",
        titulo: "Investigación",
        ajustes: [
          aj("KENI_PIPELINE_RECOLECTAR", "Recolectar"),
          aj("KENI_PIPELINE_VERIFICAR", "Verificar"),
          aj("KENI_TRENDS", "Google Trends"),
        ],
      },
      {
        id: "pipeline_produccion",
        titulo: "Producción",
        ajustes: [
          aj("KENI_PIPELINE_REDACTAR", "Redactar"),
          aj("KENI_PIPELINE_ILUSTRAR", "Ilustrar"),
          aj("KENI_PIPELINE_STOCK", "Stock"),
          aj("KENI_PIPELINE_SUGERIR_HASHTAGS", "Keywords"),
          aj("KENI_CRITICA_IA", "Crítica"),
        ],
      },
      {
        id: "avanzado",
        titulo: "Avanzado",
        ajustes: [
          aj("KENI_PIPELINE_FUSIONAR", "Fusionar"),
          aj("KENI_CLASIFICAR_MARCA_IA", "Clasificar"),
          aj("KENI_PRIORIZAR_PERFIL_IA", "Priorizar"),
          aj("KENI_PIPELINE_DECISOR", "Decisor"),
          // KENI_PIPELINE_REVISAR está ausente → fila "vía env".
        ],
      },
    ],
  };

  class ApiError extends Error {
    status: number;
    constructor(msg: string, status: number) {
      super(msg);
      this.name = "ApiError";
      this.status = status;
    }
  }

  return {
    api: {
      ajustes: vi.fn().mockResolvedValue(AJUSTES),
      guardarAjuste: vi.fn().mockResolvedValue({
        ajuste: aj("KENI_MAQUINA", "Máquina (auto)", false),
      }),
      sistemaCuenta: vi.fn().mockResolvedValue({
        disponible: true,
        auth: { logueado: false, metodo: null, proveedor: null },
        uso: { disponible: false, mensaje: "", medidores: [] },
      }),
      cuentaMarcas: vi.fn().mockResolvedValue({
        cuentas: [],
        defecto: "a",
        marcas: [],
      }),
    },
    mensajeError: (e: unknown) => String(e),
    ApiError,
  };
});

vi.mock("@/hooks/use-uso-cuenta", () => ({
  useUsoCuenta: () => ({ data: undefined, isPending: false }),
  CLAVE_USO_CUENTA: ["uso-cuenta"],
}));

function valorMarca(marcaActiva: string | null): ValorMarcaActiva {
  return {
    marcaActiva,
    marcaPrimaria: marcaActiva,
    enMarcaPrimaria: true,
    esMultiMarca: false,
    puedeTodas: false,
    marcasParaSwitch: [],
    nombreActiva: marcaActiva,
    cambiarMarca: vi.fn(),
    volverAPrimaria: vi.fn(),
  };
}

function renderControles(marcaActiva: string | null = null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MarcaActivaContexto.Provider value={valorMarca(marcaActiva)}>
        <MemoryRouter>
          <Controles />
        </MemoryRouter>
      </MarcaActivaContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("Controles · Estado global", () => {
  it("renderiza el switch maestro (Máquina) y la pausa", async () => {
    renderControles();
    expect(
      await screen.findByRole("switch", {
        name: /Máquina \(auto\): interruptor general/,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("switch", {
        name: /Pausa de emergencia: corta toda la generación/,
      }),
    ).toBeInTheDocument();
  });

  it("muestra la nota: el empuje manual ignora el maestro pero la pausa lo detiene", async () => {
    renderControles();
    await screen.findByRole("switch", { name: /Máquina/ });
    const nota = screen.getByTestId("nota-manual");
    expect(nota).toBeInTheDocument();
    expect(nota.textContent).toMatch(/empuje manual desde Noticias ignora/);
    expect(nota.textContent).toMatch(/pausa de emergencia/);
  });
});

describe("Controles · Pipeline Investigación", () => {
  it("renderiza el switch de Recolectar y Verificar", async () => {
    renderControles();
    expect(
      await screen.findByRole("switch", { name: /Recolectar/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /Verificar/ })).toBeInTheDocument();
  });

  it("renderiza el switch de Google Trends", async () => {
    renderControles();
    await screen.findByRole("switch", { name: /Recolectar/ });
    expect(screen.getByRole("switch", { name: /Google Trends/ })).toBeInTheDocument();
  });
});

describe("Controles · Pipeline Producción", () => {
  it("renderiza el switch de Redactar e Ilustrar", async () => {
    renderControles();
    expect(
      await screen.findByRole("switch", { name: /Redactar/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /Ilustrar/ })).toBeInTheDocument();
  });

  it("renderiza el switch de Crítica", async () => {
    renderControles();
    await screen.findByRole("switch", { name: /Redactar/ });
    expect(screen.getByRole("switch", { name: /Crítica/ })).toBeInTheDocument();
  });
});

describe("Controles · Sección Avanzado", () => {
  it("está colapsada por defecto: aria-expanded=false y no muestra toggles avanzados", async () => {
    renderControles();
    await screen.findByRole("switch", { name: /Máquina/ });
    const btnAvanzado = screen.getByRole("button", { name: /Avanzado/ });
    expect(btnAvanzado).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("switch", { name: /Fusionar/ })).not.toBeInTheDocument();
  });

  it("al expandir muestra los toggles presentes en el catálogo", async () => {
    renderControles();
    const btnAvanzado = await screen.findByRole("button", { name: /Avanzado/ });
    fireEvent.click(btnAvanzado);
    await waitFor(() => {
      expect(screen.getByRole("switch", { name: /Fusionar/ })).toBeInTheDocument();
    });
    expect(screen.getByRole("switch", { name: /Clasificar/ })).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /Decisor/ })).toBeInTheDocument();
  });

  it("las claves ausentes del catálogo muestran 'vía env' en lugar de switch", async () => {
    renderControles();
    const btnAvanzado = await screen.findByRole("button", { name: /Avanzado/ });
    fireEvent.click(btnAvanzado);
    await waitFor(() => {
      expect(screen.getByText("Revisar")).toBeInTheDocument();
    });
    // Claves ausentes (REVISAR, AUTO_PREAPROBACION) → info-env, no switch.
    expect(screen.getAllByTestId("info-env").length).toBeGreaterThan(0);
    expect(
      screen.queryByRole("switch", { name: /Revisar \(KENI_PIPELINE_REVISAR\)/ }),
    ).not.toBeInTheDocument();
  });
});
