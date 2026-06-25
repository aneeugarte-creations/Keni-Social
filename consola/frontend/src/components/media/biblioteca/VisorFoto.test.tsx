/**
 * Tests de VisorFoto: el lightbox de la Galería decide sus ACCIONES por el `origen` de la foto y
 * navega el burst DENTRO del propio visor (modo ráfaga, sin segundo modal).
 *  - biblioteca (guardada): Descargar + Borrar; nunca Guardar ni Ráfaga.
 *  - túnel (en vivo): Guardar + Ráfaga; nunca Descargar/Borrar.
 *  - «Ráfaga» entra en el burst (pide los frames) y las flechas los recorren; «Salir» vuelve.
 *  - `indice` null mantiene el visor cerrado.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { FotoVista } from "@/types";

import { VisorFoto } from "./VisorFoto";

const BIB: FotoVista = {
  clave: "bib-1",
  origen: "biblioteca",
  titulo: "Portada",
  thumb: "thumb-bib",
  url: "url-bib",
  etiquetas: ["gol"],
  id: "1",
  fuente: "portal",
};

const TUN: FotoVista = {
  clave: "tun-g-a",
  origen: "tunel",
  titulo: "Atajada",
  thumb: "thumb-tun",
  url: "url-tun",
  etiquetas: [],
  galeria_id: "g",
  archivo: "a.jpg",
  dispositivo: "mac",
};

function renderVisor(extra: Partial<React.ComponentProps<typeof VisorFoto>> = {}) {
  const p = {
    fotos: [BIB],
    indice: 0 as number | null,
    onIndice: vi.fn(),
    onCerrar: vi.fn(),
    marca: "claro-sports",
    onGuardar: vi.fn(),
    onDescargar: vi.fn(),
    onBorrar: vi.fn(),
    ...extra,
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <VisorFoto {...p} />
    </QueryClientProvider>,
  );
  return p;
}

describe("VisorFoto", () => {
  it("cerrado: con indice null no renderiza nada", () => {
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <VisorFoto fotos={[BIB]} indice={null} onIndice={vi.fn()} onCerrar={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("biblioteca: Descargar + Borrar, sin Guardar ni Ráfaga", () => {
    const p = renderVisor();
    expect(screen.getByRole("button", { name: /Descargar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Borrar/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Guardar/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Ráfaga/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Borrar/i }));
    expect(p.onBorrar).toHaveBeenCalledWith(BIB);
  });

  it("túnel: Guardar + Ráfaga, sin Descargar/Borrar", () => {
    const p = renderVisor({ fotos: [TUN] });
    expect(screen.getByRole("button", { name: /Guardar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Ráfaga$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Descargar/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Borrar/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Guardar/i }));
    expect(p.onGuardar).toHaveBeenCalledWith(TUN);
  });

  it("ráfaga: entra en el burst y recorre los frames dentro del visor", async () => {
    vi.spyOn(api, "rafagaPropio").mockResolvedValue({
      fotos: [
        { archivo: "a.jpg", thumb: "ta" },
        { archivo: "b.jpg", thumb: "tb" },
      ],
    });
    renderVisor({ fotos: [TUN] });

    fireEvent.click(screen.getByRole("button", { name: /^Ráfaga$/i }));
    // El botón pasa a «Salir de ráfaga» y, al cargar, arranca en el keeper (a.jpg) con el contador.
    expect(await screen.findByRole("button", { name: /Salir de ráfaga/i })).toBeInTheDocument();
    expect(await screen.findByText("1 / 2")).toBeInTheDocument();
    expect(screen.getByText("keeper")).toBeInTheDocument();
  });

  it("varias fotos: muestra el contador y navega la rejilla", () => {
    const p = renderVisor({ fotos: [BIB, TUN], indice: 0 });
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Siguiente/i }));
    expect(p.onIndice).toHaveBeenCalledWith(1);
  });
});
