/**
 * Tests del control de Vistas guardadas (cabecera de Analíticas).
 *
 * Cubre: lista los presets al abrir, aplica uno (vuelca su `config` en el store de
 * presentación y delega marca+periodo al padre), guarda el estado actual bajo un nombre y
 * borra un preset. Las llamadas a la API se mockean; el store `vistaConfig` es el real.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";
import type { VistaGuardada } from "@/types";

import { useVistaConfig } from "./vistaConfig";
import { VistasGuardadas } from "./VistasGuardadas";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

const VISTA: VistaGuardada = {
  id: "v1",
  nombre: "Claro Sports IG dirección",
  marca: "claro-sports",
  marca_nombre: "Claro Sports",
  periodo: "mes",
  config: {
    red: "instagram",
    formato: "reel",
    secciones: { Resumen: false },
    columnas: { piezas: { orden: ["titulo"], ocultas: ["url"] } },
  },
  autor_id: "u1",
  autor_nombre: "Ane",
  fecha_creacion: "2026-06-01T00:00:00Z",
  fecha_actualizacion: "2026-06-01T00:00:00Z",
};

function renderControl(onAplicar = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <VistasGuardadas marcaActual="unotv" periodoActual="semana" onAplicar={onAplicar} />
    </QueryClientProvider>,
  );
  return { onAplicar };
}

beforeEach(() => {
  useVistaConfig.getState().reset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("VistasGuardadas", () => {
  it("lista los presets al abrir el panel", async () => {
    vi.spyOn(apiMod.api, "vistas").mockResolvedValue({ vistas: [VISTA] });
    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /vistas/i }));
    expect(await screen.findByText("Claro Sports IG dirección")).toBeInTheDocument();
    expect(screen.getByText("Claro Sports")).toBeInTheDocument();
  });

  it("aplica un preset: vuelca su config al store y delega marca+periodo", async () => {
    vi.spyOn(apiMod.api, "vistas").mockResolvedValue({ vistas: [VISTA] });
    const { onAplicar } = renderControl();
    fireEvent.click(screen.getByRole("button", { name: /vistas/i }));
    fireEvent.click(await screen.findByText("Claro Sports IG dirección"));
    expect(onAplicar).toHaveBeenCalledWith("claro-sports", "mes");
    expect(useVistaConfig.getState().red).toBe("instagram");
    expect(useVistaConfig.getState().seccionVisible("Resumen")).toBe(false);
  });

  it("guarda el estado actual bajo un nombre", async () => {
    vi.spyOn(apiMod.api, "vistas").mockResolvedValue({ vistas: [] });
    const crear = vi
      .spyOn(apiMod.api, "crearVista")
      .mockResolvedValue({ vista: { ...VISTA, nombre: "Nueva" } });
    useVistaConfig.getState().setRed("youtube");
    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /vistas/i }));
    fireEvent.click(await screen.findByText("Guardar vista actual"));
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Nueva" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(crear).toHaveBeenCalledWith({
        nombre: "Nueva",
        marca: "unotv",
        periodo: "semana",
        config: expect.objectContaining({ red: "youtube" }),
      }),
    );
  });

  it("borra un preset", async () => {
    vi.spyOn(apiMod.api, "vistas").mockResolvedValue({ vistas: [VISTA] });
    const borrar = vi
      .spyOn(apiMod.api, "eliminarVista")
      .mockResolvedValue({ mensaje: "Vista borrada." });
    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /vistas/i }));
    await screen.findByText("Claro Sports IG dirección");
    fireEvent.click(screen.getByRole("button", { name: /borrar vista/i }));
    await waitFor(() => expect(borrar).toHaveBeenCalledWith("v1"));
  });
});
