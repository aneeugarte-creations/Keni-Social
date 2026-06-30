/**
 * Smoke test del panel Sistema→Cuenta: muestra las cuentas de Claude (A y B), cada una con su
 * propio estado/auth y sus botones de login/logout, RESPETANDO el selector de marca global:
 *   - "Todas" (`marcaActiva === null`) → ambas tarjetas (A y B).
 *   - una marca concreta → solo la tarjeta de la cuenta que sirve esa marca (mapeo marca→cuenta
 *     reutilizado del endpoint de uso, `useUsoCuenta`).
 * Mockeamos `api.sistemaCuenta`, el selector (`useMarcaActiva`) y el uso (`useUsoCuenta`).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { UsoCuenta } from "@/hooks/use-uso-cuenta";
import type { RespuestaCuenta, RespuestaCuentaMarcas } from "@/types";

import { SeccionCuentaClaude } from "./SeccionCuentaClaude";

const CONECTADA: RespuestaCuenta = {
  disponible: true,
  auth: {
    logueado: true,
    metodo: "claude.ai",
    proveedor: "firstParty",
    email: "cuenta-a@kenitech.io",
    plan: "max",
  },
  uso: { disponible: true, mensaje: "", medidores: [] },
};

const SIN_CUENTA: RespuestaCuenta = {
  disponible: true,
  auth: { logueado: false, metodo: null, proveedor: null },
  uso: { disponible: false, mensaje: "", medidores: [] },
};

const sistemaCuenta = vi.fn((cuenta?: "a" | "b") =>
  Promise.resolve(cuenta === "b" ? SIN_CUENTA : CONECTADA),
);

const CUENTA_MARCAS: RespuestaCuentaMarcas = {
  cuentas: [
    { cuenta: "a", etiqueta: "Claro Sports" },
    { cuenta: "b", etiqueta: "UnoTV · Nación Gamer" },
  ],
  defecto: "a",
  marcas: [
    { id: "claro-sports", nombre: "Claro Sports", cuenta: "a", por_defecto: true },
    { id: "unotv", nombre: "UnoTV", cuenta: "b", por_defecto: true },
    { id: "fundacion", nombre: "Fundación", cuenta: "b", por_defecto: false },
  ],
};

const cuentaMarcas = vi.fn(() => Promise.resolve(CUENTA_MARCAS));
const asignarCuentaMarca = vi.fn((datos: { marca: string; cuenta: string }) => {
  void datos;
  return Promise.resolve(CUENTA_MARCAS);
});

vi.mock("@/lib/api", () => ({
  api: {
    sistemaCuenta: (cuenta?: "a" | "b") => sistemaCuenta(cuenta),
    cuentaMarcas: () => cuentaMarcas(),
    asignarCuentaMarca: (datos: { marca: string; cuenta: string }) =>
      asignarCuentaMarca(datos),
  },
  mensajeError: (e: unknown) => String(e),
}));

const marcaActivaMock = vi.fn();
const usoMock = vi.fn();
vi.mock("@/hooks/marca-activa-contexto", () => ({
  useMarcaActiva: () => marcaActivaMock(),
}));
vi.mock("@/hooks/use-uso-cuenta", () => ({
  useUsoCuenta: () => usoMock(),
  CLAVE_USO_CUENTA: ["uso-cuenta"],
}));

/** Cuentas del endpoint de uso con su mapeo marca→cuenta (lo que el componente reutiliza). */
function cuentaUso(parcial: Partial<UsoCuenta>): UsoCuenta {
  return {
    cuenta: "a",
    etiqueta: "Claro Sports",
    marcas: ["claro-sports"],
    conectada: true,
    semana_pct: null,
    sesion_5h_pct: null,
    sonnet_pct: null,
    reset_semana_iso: null,
    reset_semana_txt: null,
    actualizado_ts: null,
    al_100: false,
    alerta_roja: false,
    dia: { consumo_pct: null, umbral_pct: 14.3, limite: "semanal", pausado: false },
    ...parcial,
  };
}

const CUENTAS_USO: UsoCuenta[] = [
  cuentaUso({ cuenta: "a", marcas: ["claro-sports"] }),
  cuentaUso({ cuenta: "b", marcas: ["unotv", "nacion-gamer", "unotv-us", "fundacion"] }),
];

beforeEach(() => {
  marcaActivaMock.mockReturnValue({ marcaActiva: null });
  usoMock.mockReturnValue({ data: { cuentas: CUENTAS_USO } });
});

afterEach(() => {
  vi.clearAllMocks();
});

function renderSeccion() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SeccionCuentaClaude />
    </QueryClientProvider>,
  );
}

describe("SeccionCuentaClaude", () => {
  it("en 'Todas' muestra las dos cuentas (A y B) con su estado y etiqueta la B con sus marcas", async () => {
    marcaActivaMock.mockReturnValue({ marcaActiva: null });
    renderSeccion();

    // Ambas tarjetas presentes, cada una consultada con su selector.
    expect(await screen.findByText("Cuenta de Claude del servidor (A)")).toBeInTheDocument();
    expect(screen.getByText("Cuenta de Claude del servidor (B)")).toBeInTheDocument();

    // La A está conectada: muestra su email; la B no, con el aviso de "sin cuenta".
    expect(await screen.findByText("cuenta-a@kenitech.io")).toBeInTheDocument();
    expect(
      await screen.findByText(/No hay ninguna cuenta de Claude conectada/),
    ).toBeInTheDocument();

    // La B se etiqueta con las marcas que usa (incluida la Fundación).
    expect(screen.getByText(/UnoTV, Nación Gamer, UnoTV US .* y la Fundación/)).toBeInTheDocument();

    // Cada tarjeta pidió su cuenta por separado.
    expect(sistemaCuenta).toHaveBeenCalledWith("a");
    expect(sistemaCuenta).toHaveBeenCalledWith("b");
  });

  it("con una marca de la cuenta A muestra SOLO la tarjeta A", async () => {
    marcaActivaMock.mockReturnValue({ marcaActiva: "claro-sports" });
    renderSeccion();

    expect(await screen.findByText("Cuenta de Claude del servidor (A)")).toBeInTheDocument();
    expect(screen.queryByText("Cuenta de Claude del servidor (B)")).not.toBeInTheDocument();
    expect(sistemaCuenta).toHaveBeenCalledWith("a");
    expect(sistemaCuenta).not.toHaveBeenCalledWith("b");
  });

  it("con una marca de la cuenta B muestra SOLO la tarjeta B", async () => {
    marcaActivaMock.mockReturnValue({ marcaActiva: "unotv" });
    renderSeccion();

    expect(await screen.findByText("Cuenta de Claude del servidor (B)")).toBeInTheDocument();
    expect(screen.queryByText("Cuenta de Claude del servidor (A)")).not.toBeInTheDocument();
    expect(sistemaCuenta).toHaveBeenCalledWith("b");
    expect(sistemaCuenta).not.toHaveBeenCalledWith("a");
  });

  it("lista las marcas por cuenta, marca el defecto vs override y mueve una marca a la otra cuenta", async () => {
    renderSeccion();

    // El bloque "Marcas por cuenta" se pinta con las marcas de cada cuenta.
    expect(await screen.findByText("Marcas por cuenta")).toBeInTheDocument();

    // Una marca por defecto lleva el tag "(defecto)"; la personalizada, el badge.
    const filaUnotv = (await screen.findByText("UnoTV")).closest("li") as HTMLElement;
    expect(within(filaUnotv).getByText("(defecto)")).toBeInTheDocument();
    const filaFundacion = (await screen.findByText("Fundación")).closest("li") as HTMLElement;
    expect(within(filaFundacion).getByText("personalizado")).toBeInTheDocument();

    // "Mover a {otra cuenta}": la Fundación está en B, su botón la manda a la cuenta A.
    fireEvent.click(within(filaFundacion).getByRole("button", { name: /Mover a Claro Sports/ }));
    await waitFor(() =>
      expect(asignarCuentaMarca).toHaveBeenCalledWith({ marca: "fundacion", cuenta: "a" }),
    );

    // La personalizada ofrece además volver al defecto (limpia el override con cuenta vacía).
    fireEvent.click(within(filaFundacion).getByRole("button", { name: /Defecto/ }));
    await waitFor(() =>
      expect(asignarCuentaMarca).toHaveBeenCalledWith({ marca: "fundacion", cuenta: "" }),
    );
  });
});
