/**
 * Tests de ACCESIBILIDAD de los banners de modo (reencuadre / recorte):
 *  - Cada banner es una región `role="status"` que ANUNCIA el modo activo al montarse
 *    (texto sr-only con el nombre del modo + las instrucciones visibles).
 *  - Los botones se encuentran por su NOMBRE accesible (el texto visible; los iconos
 *    decorativos van aria-hidden) y disparan sus callbacks.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { aspectoRecorteStore } from "./aspectoRecorte";
import { BannerRecorte, BannerReencuadre } from "./BannersModo";

afterEach(() => aspectoRecorteStore.getState().limpiar());

describe("BannerReencuadre — accesibilidad", () => {
  it("anuncia el modo en una región de estado y «Listo» confirma", () => {
    const onListo = vi.fn();
    render(<BannerReencuadre onListo={onListo} />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(/modo reencuadre activo/i);
    expect(status).toHaveTextContent(/arrastra la foto/i);
    fireEvent.click(screen.getByRole("button", { name: "Listo" }));
    expect(onListo).toHaveBeenCalledTimes(1);
  });
});

describe("BannerRecorte — accesibilidad", () => {
  it("anuncia el modo en una región de estado", () => {
    render(<BannerRecorte />);
    expect(screen.getByRole("status")).toHaveTextContent(/modo recorte activo/i);
  });

  it("«Hecho» confirma y «Cancelar» restaura (nombres accesibles de los botones)", () => {
    const onListo = vi.fn();
    const onCancelar = vi.fn();
    render(<BannerRecorte onListo={onListo} onCancelar={onCancelar} />);
    fireEvent.click(screen.getByRole("button", { name: "Hecho" }));
    expect(onListo).toHaveBeenCalledTimes(1);
    expect(onCancelar).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(onCancelar).toHaveBeenCalledTimes(1);
  });

  it("ofrece los chips de relación de aspecto y «Libre» está activo por defecto", () => {
    aspectoRecorteStore.getState().iniciar(true);
    render(<BannerRecorte />);
    const grupo = screen.getByRole("radiogroup", { name: "Relación de aspecto" });
    expect(grupo).toBeInTheDocument();
    for (const etiqueta of ["Libre", "1:1", "4:5", "9:16", "16:9", "Original"]) {
      expect(screen.getByRole("radio", { name: etiqueta })).toBeInTheDocument();
    }
    expect(screen.getByRole("radio", { name: "Libre" })).toHaveAttribute("aria-checked", "true");
  });

  it("elegir un chip fija su relación en el estado compartido y lo marca activo", () => {
    aspectoRecorteStore.getState().iniciar(true);
    render(<BannerRecorte />);
    fireEvent.click(screen.getByRole("radio", { name: "1:1" }));
    expect(aspectoRecorteStore.getState().ratio).toBeCloseTo(1);
    expect(screen.getByRole("radio", { name: "1:1" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Libre" })).toHaveAttribute("aria-checked", "false");
  });

  it("diferencia la ayuda de FORMA (encoge el recuadro) de la de FOTO", () => {
    aspectoRecorteStore.getState().iniciar(false);
    render(<BannerRecorte />);
    expect(screen.getByRole("status")).toHaveTextContent(/recortar el recuadro/i);
  });

  it("con FOTO la ayuda habla de reencuadrar dentro del marco", () => {
    aspectoRecorteStore.getState().iniciar(true);
    render(<BannerRecorte />);
    expect(screen.getByRole("status")).toHaveTextContent(/encuadrar/i);
  });
});
