import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { MarcaFuentesStock } from "@/types";

import { PanelFuentesStock } from "./PanelFuentesStock";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const MARCA: MarcaFuentesStock = {
  marca: "claro-sports",
  etiqueta: "Claro Sports",
  fuentes: [
    {
      proveedor: "pexels",
      nombre: "Pexels",
      requiere_clave: true,
      disponible: true,
      activa: true,
      motivo: "",
      configurado: true,
      pista: "1234",
    },
    {
      proveedor: "pixabay",
      nombre: "Pixabay",
      requiere_clave: true,
      disponible: false,
      activa: false,
      motivo: "Configúrala en Sistema → Proveedores.",
      configurado: false,
      pista: null,
    },
    { proveedor: "wikimedia", nombre: "Wikimedia", requiere_clave: false, disponible: true, activa: true, motivo: "" },
    { proveedor: "nasa", nombre: "NASA", requiere_clave: false, disponible: true, activa: true, motivo: "" },
    { proveedor: "openverse", nombre: "Openverse", requiere_clave: false, disponible: true, activa: false, motivo: "" },
  ],
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("PanelFuentesStock", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("pide elegir una marca cuando el switch global está en «Todas»", () => {
    renderConProviders(<PanelFuentesStock marca={null} />);
    expect(
      screen.getByText(/Elige una marca concreta/i),
    ).toBeInTheDocument();
  });

  it("pinta un toggle por proveedor y deshabilita el de pago sin clave", async () => {
    vi.spyOn(api, "estadoFuentesStockMarca").mockResolvedValue(MARCA);
    renderConProviders(<PanelFuentesStock marca="claro-sports" />);

    // Los 5 proveedores, cada uno con su switch.
    expect(await screen.findByRole("switch", { name: "Fuente Pexels" })).toBeInTheDocument();
    expect(screen.getAllByRole("switch")).toHaveLength(5);
    // Pixabay (requiere clave, sin configurar) queda deshabilitado con su pista.
    expect(screen.getByRole("switch", { name: "Fuente Pixabay" })).toBeDisabled();
    expect(screen.getByText("Configúrala en Sistema → Proveedores.")).toBeInTheDocument();
  });

  it("al apagar una fuente guarda la lista de activas sin ella", async () => {
    vi.spyOn(api, "estadoFuentesStockMarca").mockResolvedValue(MARCA);
    const guardar = vi.spyOn(api, "guardarFuentesStock").mockResolvedValue(MARCA);
    renderConProviders(<PanelFuentesStock marca="claro-sports" />);

    fireEvent.click(await screen.findByRole("switch", { name: "Fuente Wikimedia" }));
    // Activas actuales = pexels, wikimedia, nasa → al apagar wikimedia quedan pexels y nasa.
    await waitFor(() =>
      expect(guardar).toHaveBeenCalledWith("claro-sports", ["pexels", "nasa"]),
    );
  });
});
