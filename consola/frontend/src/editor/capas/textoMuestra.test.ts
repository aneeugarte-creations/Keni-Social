/**
 * `textoMuestra` debe normalizar EXACTAMENTE como el export (`dibujarTexto` hace .trim() del
 * total y `envolver` colapsa rachas de espacios POR PÁRRAFO, preservando los \n internos y las
 * líneas en blanco): sin esto un salto/espacio inicial o un espacio doble envolvían distinto en
 * la previa Konva que en el PNG (línea fantasma, puntos de corte movidos).
 */
import { describe, expect, it } from "vitest";

import { nuevaCapaTexto } from "../documento";

import { textoMuestra } from "./textoMuestra";

describe("textoMuestra — normalización espejo del export", () => {
  it("recorta espacios/saltos al inicio y al final y colapsa rachas internas por párrafo", () => {
    const c = nuevaCapaTexto({ texto: "  Hola   mundo \n\n  dos   espacios  " });
    // Las líneas en blanco INTERNAS se preservan (envolver hace out.push("")).
    expect(textoMuestra(c)).toBe("Hola mundo\n\ndos espacios");
  });

  it("aplica MAYÚSCULAS de locale es ANTES de normalizar, como dibujarTexto", () => {
    const c = nuevaCapaTexto({ texto: "  en  vivo ", mayusculas: true });
    expect(textoMuestra(c)).toBe("EN VIVO");
  });

  it("no toca un texto ya normalizado", () => {
    const c = nuevaCapaTexto({ texto: "Titular de una línea" });
    expect(textoMuestra(c)).toBe("Titular de una línea");
  });
});
