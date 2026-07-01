/**
 * Tests del diálogo de campaña centrados en precio de venta + margen objetivo (alimentan
 * la calculadora de rentabilidad del panel): precarga en edición, default en alta y que
 * viajen en el cuerpo de la mutación.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";
import { MarcaActivaContexto, type ValorMarcaActiva } from "@/hooks/marca-activa-contexto";
import type { Campania } from "@/types";

import { DialogoCampania } from "./DialogoCampania";

const VALOR_MARCA_ACTIVA: ValorMarcaActiva = {
  marcaActiva: "unotv",
  marcaPrimaria: "unotv",
  enMarcaPrimaria: true,
  esMultiMarca: true,
  puedeTodas: false,
  marcasParaSwitch: [
    { id: "unotv", nombre: "UnoTV" },
    { id: "claro-sports", nombre: "Claro Sports" },
  ],
  nombreActiva: "UnoTV",
  cambiarMarca: () => {},
  volverAPrimaria: () => {},
};

function renderDialogo(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MarcaActivaContexto.Provider value={VALOR_MARCA_ACTIVA}>{ui}</MarcaActivaContexto.Provider>
    </QueryClientProvider>,
  );
}

const CAMPANIA: Campania = {
  id: "c1",
  marcas: ["unotv"],
  marcas_nombres: ["UnoTV"],
  nombre: "Chihuahua",
  hashtags: ["Chihuahua"],
  etiqueta_web: "",
  precio_venta: 1200000,
  margen_objetivo_pct: 35,
  activa: true,
  fecha_creacion: "2026-06-01T00:00:00Z",
  fecha_actualizacion: "2026-06-01T00:00:00Z",
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("DialogoCampania · rentabilidad", () => {
  it("alta: margen objetivo nace en 40 y precio de venta vacío", () => {
    renderDialogo(<DialogoCampania abierto campania={null} onCerrar={() => {}} />);

    expect(screen.getByLabelText("Precio de venta (MXN)")).toHaveValue(null);
    expect(screen.getByLabelText("Margen objetivo (%)")).toHaveValue(40);
  });

  it("edición: precarga el precio de venta y margen de la campaña", () => {
    renderDialogo(<DialogoCampania abierto campania={CAMPANIA} onCerrar={() => {}} />);

    expect(screen.getByLabelText("Precio de venta (MXN)")).toHaveValue(1200000);
    expect(screen.getByLabelText("Margen objetivo (%)")).toHaveValue(35);
  });

  it("envía precio_venta y margen_objetivo_pct al crear", async () => {
    const espia = vi
      .spyOn(apiMod.api, "crearCampania")
      .mockResolvedValue({ campania: CAMPANIA });
    renderDialogo(<DialogoCampania abierto campania={null} onCerrar={() => {}} />);

    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Chihuahua" } });
    fireEvent.change(screen.getByLabelText("Hashtags"), { target: { value: "#Chihuahua" } });
    fireEvent.change(screen.getByLabelText("Precio de venta (MXN)"), {
      target: { value: "1200000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear campaña" }));

    await waitFor(() =>
      expect(espia).toHaveBeenCalledWith(
        expect.objectContaining({ precio_venta: 1200000, margen_objetivo_pct: 40 }),
      ),
    );
  });

  it("margen fuera de 0-100 marca error en línea y no envía", () => {
    const espia = vi.spyOn(apiMod.api, "crearCampania");
    renderDialogo(<DialogoCampania abierto campania={null} onCerrar={() => {}} />);

    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Chihuahua" } });
    fireEvent.change(screen.getByLabelText("Hashtags"), { target: { value: "#Chihuahua" } });
    fireEvent.change(screen.getByLabelText("Margen objetivo (%)"), { target: { value: "150" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear campaña" }));

    expect(screen.getByText("Debe estar entre 0 y 100.")).toBeInTheDocument();
    expect(espia).not.toHaveBeenCalled();
  });
});
