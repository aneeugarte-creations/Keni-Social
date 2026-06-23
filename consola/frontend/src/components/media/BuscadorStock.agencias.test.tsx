/**
 * Tests del BuscadorStock en modo AGENCIAS (foto licenciada de AFP). A diferencia del stock:
 *  - si el proveedor no está disponible (sin credenciales), muestra su `motivo` en vez del grid;
 *  - las candidatas se pintan SIN overlay "Sin licencia"/"Autorizar" (son publicables);
 *  - elegir una llama a `adjuntarAgencia` (no a `adjuntarStock`).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { CandidataStock, PlataformaStock, RespuestaBuscarAgencias } from "@/types";

import { BuscadorStock } from "./BuscadorStock";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function candidata(over: Partial<CandidataStock> = {}): CandidataStock {
  return {
    proveedor: "afp",
    url: "https://afp.example/foto.jpg",
    thumb: "https://afp.example/foto-thumb.jpg",
    autor: "Jane Doe",
    licencia: "AFP",
    credito_url: "https://afp.example/credito",
    titulo: "Final del torneo",
    ...over,
  };
}

const PLATAFORMA: PlataformaStock = {
  id: "pl1",
  imagen_url: "https://media.example/foto.jpg",
  foto: "foto-1",
  falta_imagen: false,
  imagen_origen: "licenciada",
  imagen_proveedor: "afp",
  imagen_autor: "Jane Doe",
  imagen_licencia: "AFP",
  imagen_credito_url: "https://afp.example/credito",
  imagen_autorizada: true,
};

function renderBuscador(respuesta: RespuestaBuscarAgencias) {
  vi.spyOn(api, "buscarAgencias").mockResolvedValue(respuesta);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onAdjuntada = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <BuscadorStock
        open
        onCerrar={vi.fn()}
        piezaId="p1"
        fuente="agencias"
        consultaInicial="final torneo"
        onAdjuntada={onAdjuntada}
      />
    </QueryClientProvider>,
  );
  return { onAdjuntada };
}

describe("BuscadorStock · modo agencias (foto licenciada)", () => {
  it("título de agencia y descripción de foto publicable con crédito", async () => {
    renderBuscador({ proveedores: [], candidatos: [] });
    expect(await screen.findByText("Buscar foto de agencia (AFP)")).toBeInTheDocument();
    expect(screen.getByText(/publicables con crédito obligatorio/i)).toBeInTheDocument();
  });

  it("proveedor no disponible: muestra su motivo en vez del grid", async () => {
    renderBuscador({
      proveedores: [
        { proveedor: "afp", nombre: "AFP", disponible: false, motivo: "AFP sin credenciales." },
      ],
      candidatos: [],
    });
    expect(await screen.findByText("AFP sin credenciales.")).toBeInTheDocument();
  });

  it("pinta las candidatas con su crédito y SIN overlay de 'Sin licencia'", async () => {
    renderBuscador({
      proveedores: [{ proveedor: "afp", nombre: "AFP", disponible: true }],
      candidatos: [candidata()],
    });
    // La candidata se pinta (por su alt) y muestra el crédito (autor · licencia · proveedor).
    expect(await screen.findByAltText("Final del torneo")).toBeInTheDocument();
    expect(screen.getByText(/Jane Doe · AFP · AFP/)).toBeInTheDocument();
    // No hay overlay de stock: ni "Sin licencia" ni "Autorizar".
    expect(screen.queryByText(/sin licencia/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Autorizar")).not.toBeInTheDocument();
  });

  it("elegir una candidata llama a adjuntarAgencia (no a adjuntarStock)", async () => {
    const adjuntarAgencia = vi
      .spyOn(api, "adjuntarAgencia")
      .mockResolvedValue({ plataforma: PLATAFORMA });
    const adjuntarStock = vi.spyOn(api, "adjuntarStock");
    const { onAdjuntada } = renderBuscador({
      proveedores: [{ proveedor: "afp", nombre: "AFP", disponible: true }],
      candidatos: [candidata()],
    });

    const img = await screen.findByAltText("Final del torneo");
    fireEvent.click(img.closest("button")!);

    await vi.waitFor(() => expect(adjuntarAgencia).toHaveBeenCalledTimes(1));
    expect(adjuntarAgencia).toHaveBeenCalledWith({
      pieza_id: "p1",
      url: "https://afp.example/foto.jpg",
      proveedor: "afp",
      autor: "Jane Doe",
      licencia: "AFP",
      credito_url: "https://afp.example/credito",
    });
    expect(adjuntarStock).not.toHaveBeenCalled();
    await vi.waitFor(() => expect(onAdjuntada).toHaveBeenCalledWith(PLATAFORMA));
  });
});
