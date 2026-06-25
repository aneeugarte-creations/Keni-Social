/**
 * Tests de VisorFoto: el lightbox de la Galería decide sus ACCIONES por el `origen` de la foto.
 *  - biblioteca (guardada): Descargar + Borrar; nunca Guardar.
 *  - túnel (en vivo): Guardar; nunca Descargar/Borrar. Con coordenadas de túnel, además Ráfaga.
 *  - `indice` null mantiene el visor cerrado (no renderiza nada).
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

function props(extra: Partial<React.ComponentProps<typeof VisorFoto>> = {}) {
  return {
    fotos: [BIB],
    indice: 0,
    onIndice: vi.fn(),
    onCerrar: vi.fn(),
    onGuardar: vi.fn(),
    onDescargar: vi.fn(),
    onBorrar: vi.fn(),
    onRafaga: vi.fn(),
    ...extra,
  };
}

describe("VisorFoto", () => {
  it("cerrado: con indice null no renderiza nada", () => {
    const { container } = render(<VisorFoto {...props({ indice: null })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("biblioteca: Descargar + Borrar, sin Guardar", () => {
    const p = props();
    render(<VisorFoto {...p} />);
    expect(screen.getByRole("button", { name: /Descargar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Borrar/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Guardar/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Borrar/i }));
    expect(p.onBorrar).toHaveBeenCalledWith(BIB);
  });

  it("túnel: Guardar + Ráfaga, sin Descargar/Borrar", () => {
    const p = props({ fotos: [TUN] });
    render(<VisorFoto {...p} />);
    expect(screen.getByRole("button", { name: /Guardar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ráfaga/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Descargar/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Borrar/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Guardar/i }));
    expect(p.onGuardar).toHaveBeenCalledWith(TUN);
  });

  it("varias fotos: muestra el contador y navega", () => {
    const p = props({ fotos: [BIB, TUN], indice: 0 });
    render(<VisorFoto {...p} />);
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Siguiente/i }));
    expect(p.onIndice).toHaveBeenCalledWith(1);
  });
});
