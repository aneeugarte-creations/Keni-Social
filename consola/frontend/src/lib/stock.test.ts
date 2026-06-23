/**
 * Tests del clasificador de LICENCIA de fotos de stock: `nivelLicencia` (3 niveles, por licencia
 * real, no por proveedor) y `esShareAlike`. La decisión legal gobierna el tratamiento de la UI
 * (overlay, bloqueo, crédito obligatorio), así que se cubre por valores típicos de cada API.
 */
import { describe, expect, it } from "vitest";

import {
  esLicenciada,
  esShareAlike,
  esStock,
  etiquetaOverlayStock,
  mensajeBloqueoStock,
  MENSAJE_BLOQUEO_STOCK,
  nivelLicencia,
  stockNoAutorizado,
  tituloAutorizarStock,
} from "./stock";

describe("nivelLicencia", () => {
  it("CC0 → libre", () => {
    expect(nivelLicencia({ licencia: "CC0" })).toBe("libre");
  });

  it("dominio público (NASA) → libre", () => {
    expect(nivelLicencia({ licencia: "NASA (dominio público)" })).toBe("libre");
    expect(nivelLicencia({ licencia: "Public domain" })).toBe("libre");
    expect(nivelLicencia({ licencia: "US Government work" })).toBe("libre");
  });

  it("CC BY 4.0 → atribucion", () => {
    expect(nivelLicencia({ licencia: "CC BY 4.0" })).toBe("atribucion");
    expect(nivelLicencia({ licencia: "by" })).toBe("atribucion");
  });

  it("CC BY-SA 4.0 → atribucion (y share-alike)", () => {
    expect(nivelLicencia({ licencia: "CC BY-SA 4.0" })).toBe("atribucion");
    expect(esShareAlike("CC BY-SA 4.0")).toBe(true);
    expect(nivelLicencia({ licencia: "by-sa" })).toBe("atribucion");
  });

  it("by-nc → restringida", () => {
    expect(nivelLicencia({ licencia: "by-nc" })).toBe("restringida");
    expect(nivelLicencia({ licencia: "by-nc-sa" })).toBe("restringida");
  });

  it("by-nd → restringida", () => {
    expect(nivelLicencia({ licencia: "by-nd" })).toBe("restringida");
    expect(nivelLicencia({ licencia: "by-nc-nd" })).toBe("restringida");
  });

  it("proveedor Pexels/Pixabay → libre (por proveedor)", () => {
    expect(nivelLicencia({ proveedor: "pexels", licencia: "Pexels License" })).toBe("libre");
    expect(nivelLicencia({ proveedor: "pixabay" })).toBe("libre");
  });

  it("licencia vacía → restringida (prudencia)", () => {
    expect(nivelLicencia({ licencia: "" })).toBe("restringida");
    expect(nivelLicencia({})).toBe("restringida");
  });

  it("genérico (Wikimedia/Openverse) → restringida", () => {
    expect(nivelLicencia({ licencia: "Wikimedia Commons" })).toBe("restringida");
    expect(nivelLicencia({ licencia: "Openverse" })).toBe("restringida");
  });
});

describe("esLicenciada (foto de agencia publicable con crédito)", () => {
  it("true solo para imagen_origen 'licenciada'", () => {
    expect(esLicenciada({ imagen_origen: "licenciada" })).toBe(true);
    expect(esLicenciada({ imagen_origen: "stock" })).toBe(false);
    expect(esLicenciada({ imagen_origen: "" })).toBe(false);
    expect(esLicenciada({})).toBe(false);
  });

  it("una foto licenciada NO es stock ni dispara el bloqueo de stock", () => {
    const licenciada = { imagen_origen: "licenciada", imagen_autorizada: true };
    expect(esStock(licenciada)).toBe(false);
    expect(stockNoAutorizado(licenciada)).toBe(false);
  });
});

describe("esShareAlike", () => {
  it("true solo para BY-SA", () => {
    expect(esShareAlike("CC BY-SA 4.0")).toBe(true);
    expect(esShareAlike("by sa")).toBe(true);
    expect(esShareAlike("CC BY 4.0")).toBe(false);
    expect(esShareAlike("CC0")).toBe(false);
    expect(esShareAlike(undefined)).toBe(false);
  });
});

describe("helpers de UI basados en el nivel", () => {
  it("etiquetaOverlayStock: usables Autorizar, restringida Sin licencia", () => {
    expect(etiquetaOverlayStock({ licencia: "CC0" })).toBe("Autorizar");
    expect(etiquetaOverlayStock({ licencia: "CC BY 4.0" })).toBe("Autorizar");
    expect(etiquetaOverlayStock({ licencia: "by-nc" })).toBe("Sin licencia");
    expect(etiquetaOverlayStock({ licencia: "" })).toBe("Sin licencia");
  });

  it("mensajeBloqueoStock: restringida usa el mensaje SIN LICENCIA", () => {
    expect(mensajeBloqueoStock({ licencia: "" })).toBe(MENSAJE_BLOQUEO_STOCK);
    expect(mensajeBloqueoStock({ licencia: "CC0" })).not.toBe(MENSAJE_BLOQUEO_STOCK);
  });

  it("tituloAutorizarStock: restringida 'imagen', usable 'foto'", () => {
    expect(tituloAutorizarStock({ licencia: "by-nc" })).toBe("Autorizar imagen de stock");
    expect(tituloAutorizarStock({ licencia: "CC BY 4.0" })).toBe("Autorizar foto de stock");
  });
});
