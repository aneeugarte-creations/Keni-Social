/**
 * Tests de DialogoFotoMuestra (puerta ÚNICA que escribe la muestra de la galería):
 *  - Editar SOLO el texto (titular/pleca) deja la foto SIN tocar => `onAplicar` recibe `foto: null`,
 *    para que el llamante OMITA `foto_muestra` y el backend la conserve. Es la regla del producto:
 *    la foto solo desaparece si la persona la quita aquí.
 *  - «Quitar» pide borrar (`foto: ""`); pegar una URL la cambia (`foto: <url>`).
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PlantillaDiseno } from "@/lib/api";

import { DialogoFotoMuestra } from "./DialogoFotoMuestra";

// Plantilla con una muestra ya asignada (foto + texto): solo se usan los campos de muestra.
const PLANTILLA = {
  id: "p1",
  marca: "unotv",
  foto_muestra: "plantillas/m.jpg",
  foto_muestra_url: "/api/media/plantillas/m.jpg",
  titular_muestra: "HOLA",
  etiqueta_muestra: "EN VIVO",
} as unknown as PlantillaDiseno;

describe("DialogoFotoMuestra", () => {
  it("editar solo el titular NO toca la foto: onAplicar recibe foto=null", () => {
    const onAplicar = vi.fn();
    render(<DialogoFotoMuestra plantilla={PLANTILLA} aplicando={false} onCerrar={vi.fn()} onAplicar={onAplicar} />);
    fireEvent.change(screen.getByPlaceholderText("TITULAR"), { target: { value: "ADIOS" } });
    fireEvent.click(screen.getByRole("button", { name: "Aplicar" }));
    expect(onAplicar).toHaveBeenCalledWith({ foto: null, titular: "ADIOS", etiqueta: "EN VIVO" });
  });

  it("«Quitar» pide borrar la foto: onAplicar recibe foto vacía", () => {
    const onAplicar = vi.fn();
    render(<DialogoFotoMuestra plantilla={PLANTILLA} aplicando={false} onCerrar={vi.fn()} onAplicar={onAplicar} />);
    fireEvent.click(screen.getByRole("button", { name: /Quitar/ }));
    fireEvent.click(screen.getByRole("button", { name: "Aplicar" }));
    expect(onAplicar).toHaveBeenCalledWith({ foto: "", titular: "HOLA", etiqueta: "EN VIVO" });
  });

  it("pegar una URL cambia la foto: onAplicar recibe la URL", () => {
    const onAplicar = vi.fn();
    render(<DialogoFotoMuestra plantilla={PLANTILLA} aplicando={false} onCerrar={vi.fn()} onAplicar={onAplicar} />);
    fireEvent.change(screen.getByPlaceholderText("…o pega una URL"), { target: { value: "https://x/y.jpg" } });
    fireEvent.click(screen.getByRole("button", { name: "Aplicar" }));
    expect(onAplicar).toHaveBeenCalledWith({ foto: "https://x/y.jpg", titular: "HOLA", etiqueta: "EN VIVO" });
  });
});
