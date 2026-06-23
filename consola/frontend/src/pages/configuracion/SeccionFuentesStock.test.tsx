import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { RespuestaProveedoresStock } from "@/types";

import { SeccionFuentesStock } from "./SeccionFuentesStock";

// Admin: la sección solo se pinta para administradores.
vi.mock("@/hooks/sesion-contexto", () => ({
  useSesion: () => ({ usuario: { rol: "admin" } }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// Claves GLOBALES: una sola lista de proveedores, sin marca. Solo los de pago llevan clave.
const RESP: RespuestaProveedoresStock = {
  proveedores: [
    {
      proveedor: "pexels",
      nombre: "Pexels",
      requiere_clave: true,
      disponible: true,
      configurado: true,
      pista: "····1234",
    },
    {
      proveedor: "pixabay",
      nombre: "Pixabay",
      requiere_clave: true,
      disponible: false,
      configurado: false,
      pista: null,
    },
    {
      proveedor: "wikimedia",
      nombre: "Wikimedia",
      requiere_clave: false,
      disponible: true,
    },
  ],
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

/** La sección arranca colapsada (SeccionColapsable): se abre pulsando su cabecera. */
function abrir() {
  fireEvent.click(screen.getByText("Fotos de stock · Claves globales"));
}

describe("SeccionFuentesStock", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("muestra SOLO los proveedores de pago con su estado de clave global", async () => {
    vi.spyOn(api, "estadoProveedoresStock").mockResolvedValue(RESP);
    const { container } = renderConProviders(<SeccionFuentesStock />);
    abrir();

    // Pexels (clave guardada): badge con la pista; Pixabay sin configurar.
    expect(await screen.findByText("Configurada ····1234")).toBeInTheDocument();
    expect(screen.getByText("Sin configurar")).toBeInTheDocument();
    // Solo los dos proveedores con clave tienen input; los gratuitos (Wikimedia) no aparecen aquí.
    expect(container.querySelectorAll('input[type="password"]')).toHaveLength(2);
  });

  it("guarda la clave global de un proveedor al escribirla y pulsar Reemplazar", async () => {
    vi.spyOn(api, "estadoProveedoresStock").mockResolvedValue(RESP);
    const guardar = vi
      .spyOn(api, "guardarClaveStock")
      .mockResolvedValue({ configurado: true, mensaje: "ok" });
    const { container } = renderConProviders(<SeccionFuentesStock />);
    abrir();

    await screen.findByText("Configurada ····1234");
    // Primer input de clave = Pexels (configurado): el botón dice «Reemplazar».
    const inputs = container.querySelectorAll<HTMLInputElement>('input[type="password"]');
    fireEvent.change(inputs[0], { target: { value: "nueva-key" } });
    fireEvent.click(screen.getByRole("button", { name: "Reemplazar" }));

    await waitFor(() => expect(guardar).toHaveBeenCalledWith("pexels", "nueva-key"));
  });
});
