/**
 * Tests de ACCESIBILIDAD de los banners de modo (reencuadre / recorte):
 *  - Cada banner es una región `role="status"` que ANUNCIA el modo activo al montarse
 *    (texto sr-only con el nombre del modo + las instrucciones visibles).
 *  - Los botones se encuentran por su NOMBRE accesible (el texto visible; los iconos
 *    decorativos van aria-hidden) y disparan sus callbacks.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BannerRecorte, BannerReencuadre } from "./BannersModo";

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
});
