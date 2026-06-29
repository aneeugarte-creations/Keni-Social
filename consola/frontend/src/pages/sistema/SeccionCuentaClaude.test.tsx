/**
 * Smoke test del panel Sistema→Cuenta: ahora muestra DOS cuentas de Claude (A y B), cada una
 * con su propio estado/auth y sus botones de login/logout. Mockeamos `api.sistemaCuenta` para
 * que devuelva una cuenta conectada (A) y una sin conectar (B), y comprobamos que ambas
 * tarjetas se pintan con su estado y que la B se etiqueta con las marcas que usa.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { RespuestaCuenta } from "@/types";

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

vi.mock("@/lib/api", () => ({
  api: { sistemaCuenta: (cuenta?: "a" | "b") => sistemaCuenta(cuenta) },
  mensajeError: (e: unknown) => String(e),
}));

function renderSeccion() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SeccionCuentaClaude />
    </QueryClientProvider>,
  );
}

describe("SeccionCuentaClaude", () => {
  it("muestra las dos cuentas (A y B) con su estado y etiqueta la B con sus marcas", async () => {
    renderSeccion();

    // Ambas tarjetas presentes, cada una consultada con su selector.
    expect(await screen.findByText("Cuenta de Claude del servidor (A)")).toBeInTheDocument();
    expect(screen.getByText("Cuenta de Claude del servidor (B)")).toBeInTheDocument();

    // La A está conectada: muestra su email; la B no, con el aviso de "sin cuenta".
    expect(await screen.findByText("cuenta-a@kenitech.io")).toBeInTheDocument();
    expect(
      await screen.findByText(/No hay ninguna cuenta de Claude conectada/),
    ).toBeInTheDocument();

    // La B se etiqueta con las marcas que usa.
    expect(screen.getByText(/UnoTV, Nación Gamer y UnoTV US/)).toBeInTheDocument();

    // Cada tarjeta pidió su cuenta por separado.
    expect(sistemaCuenta).toHaveBeenCalledWith("a");
    expect(sistemaCuenta).toHaveBeenCalledWith("b");
  });
});
