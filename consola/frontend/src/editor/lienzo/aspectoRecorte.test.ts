// Estado compartido del modo recorte (relación de aspecto + tipo de objeto). Un store de módulo con
// una sola sesión activa: `iniciar` registra el tipo y reinicia a Libre; `fijar` cambia la relación;
// `limpiar` la borra al salir del modo.

import { afterEach, describe, expect, it } from "vitest";

import { OPCIONES_ASPECTO, aspectoRecorteStore } from "./aspectoRecorte";

afterEach(() => aspectoRecorteStore.getState().limpiar());

describe("aspectoRecorte (estado compartido)", () => {
  it("ofrece Libre + presets de plataforma + Original", () => {
    expect(OPCIONES_ASPECTO.map((o) => o.etiqueta)).toEqual(["Libre", "9:16", "4:5", "1:1", "16:9", "Original"]);
    // Libre y Original no fijan una relación numérica.
    expect(OPCIONES_ASPECTO.find((o) => o.clave === "libre")?.ratio).toBeNull();
    expect(OPCIONES_ASPECTO.find((o) => o.clave === "original")?.original).toBe(true);
    // 1:1 = ratio 1; 16:9 > 1; 9:16 < 1.
    expect(OPCIONES_ASPECTO.find((o) => o.clave === "1:1")?.ratio).toBeCloseTo(1);
    expect(OPCIONES_ASPECTO.find((o) => o.clave === "16:9")!.ratio!).toBeGreaterThan(1);
    expect(OPCIONES_ASPECTO.find((o) => o.clave === "9:16")!.ratio!).toBeLessThan(1);
  });

  it("iniciar registra el tipo de objeto y reinicia a Libre", () => {
    aspectoRecorteStore.getState().fijar("1:1", 1);
    aspectoRecorteStore.getState().iniciar(false);
    expect(aspectoRecorteStore.getState().esImagen).toBe(false);
    expect(aspectoRecorteStore.getState().ratio).toBeNull();
    expect(aspectoRecorteStore.getState().clave).toBe("libre");
  });

  it("fijar cambia relación y chip activo; limpiar lo borra", () => {
    aspectoRecorteStore.getState().iniciar(true);
    aspectoRecorteStore.getState().fijar("4:5", 4 / 5);
    expect(aspectoRecorteStore.getState().ratio).toBeCloseTo(4 / 5);
    expect(aspectoRecorteStore.getState().clave).toBe("4:5");
    aspectoRecorteStore.getState().limpiar();
    expect(aspectoRecorteStore.getState().esImagen).toBeNull();
    expect(aspectoRecorteStore.getState().ratio).toBeNull();
  });
});
