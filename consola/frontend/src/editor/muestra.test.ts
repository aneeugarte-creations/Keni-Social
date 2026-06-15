import { afterEach, describe, expect, it } from "vitest";

import {
  copyMuestra,
  ETIQUETA_MUESTRA_DEFECTO,
  getEtiquetaMuestra,
  getObjetoMuestraExport,
  getTitularMuestra,
  setEtiquetaMuestra,
  setFotoMuestra,
  setObjetoMuestraExport,
  setTitularMuestra,
  TITULAR_MUESTRA_DEFECTO,
} from "./muestra";

// El estado de muestra vive a nivel de módulo (persistido en localStorage): restauramos los
// valores por defecto tras cada test para no filtrar estado entre casos.
afterEach(() => {
  setTitularMuestra(TITULAR_MUESTRA_DEFECTO);
  setEtiquetaMuestra(ETIQUETA_MUESTRA_DEFECTO);
  setFotoMuestra("");
});

describe("copyMuestra", () => {
  it("por defecto devuelve un titular largo para el binding copy_in (saltos de línea y auto-encogido)", () => {
    expect(copyMuestra("copy_in")).toBe(TITULAR_MUESTRA_DEFECTO);
    // "Más bien largo": suficiente para forzar varias líneas en la caja del titular.
    expect(TITULAR_MUESTRA_DEFECTO.length).toBeGreaterThan(40);
  });

  it("por defecto devuelve una pleca para el binding etiqueta_default", () => {
    expect(copyMuestra("etiqueta_default")).toBe(ETIQUETA_MUESTRA_DEFECTO);
  });

  it("devuelve null para texto sin binding (usa su texto normal)", () => {
    expect(copyMuestra(null)).toBeNull();
    expect(copyMuestra(undefined)).toBeNull();
  });
});

describe("copy de muestra editable", () => {
  it("setTitularMuestra cambia lo que ve el binding copy_in", () => {
    setTitularMuestra("Mi titular de prueba");
    expect(getTitularMuestra()).toBe("Mi titular de prueba");
    expect(copyMuestra("copy_in")).toBe("Mi titular de prueba");
  });

  it("setEtiquetaMuestra cambia lo que ve el binding etiqueta_default", () => {
    setEtiquetaMuestra("ÚLTIMA HORA");
    expect(getEtiquetaMuestra()).toBe("ÚLTIMA HORA");
    expect(copyMuestra("etiqueta_default")).toBe("ÚLTIMA HORA");
  });
});

describe("objeto S3 de la foto de muestra para hornear en la descarga", () => {
  it("se cachea y se INVALIDA al cambiar la foto de muestra", () => {
    expect(getObjetoMuestraExport()).toBeNull();
    setObjetoMuestraExport("muestra-obj-1");
    expect(getObjetoMuestraExport()).toBe("muestra-obj-1");
    // Cambiar la foto de muestra invalida el objeto horneado anterior (ya no corresponde).
    setFotoMuestra("data:image/png;base64,abc");
    expect(getObjetoMuestraExport()).toBeNull();
  });
});
