/**
 * Tests de la edición de texto en línea (`edicionInline.ts`, doble clic sobre el lienzo):
 *  - DESTINO: se edita lo que se VE. Binding + «Copy de muestra» activo => el copy de muestra
 *    (titular o pleca según el binding); en el resto de casos, el texto real de la capa.
 *  - TEXTO INICIAL: el que el lienzo está pintando (muestra o `capa.texto`).
 *  - ESTILO: el editable replica el texto pintado a escala (tamaño SIN recortar, alineación,
 *    interletra escalada, mayúsculas, valign de la caja y rotación con pivote arriba-izquierda).
 */
import { describe, expect, it } from "vitest";

import { nuevaCapaTexto } from "../documento";
import { setEtiquetaMuestra, setTitularMuestra } from "../muestra";

import { destinoEdicion, estiloCajaEdicion, estiloTextoEdicion, textoInicial } from "./edicionInline";

describe("edicionInline — destino y texto inicial (se edita lo que se ve)", () => {
  it("binding copy_in + muestra activa => edita el TITULAR de muestra, arrancando de él", () => {
    setTitularMuestra("Titular editado por el equipo");
    const c = nuevaCapaTexto({ binding: "copy_in", texto: "texto crudo de la capa" });
    expect(destinoEdicion(c, true)).toBe("muestra-titular");
    expect(textoInicial(c, true)).toBe("Titular editado por el equipo");
  });

  it("binding etiqueta_default + muestra activa => edita la PLECA de muestra", () => {
    setEtiquetaMuestra("ÚLTIMA HORA");
    const c = nuevaCapaTexto({ binding: "etiqueta_default", texto: "" });
    expect(destinoEdicion(c, true)).toBe("muestra-etiqueta");
    expect(textoInicial(c, true)).toBe("ÚLTIMA HORA");
  });

  it("binding con muestra APAGADA => edita el texto real de la capa (que es lo que se pinta)", () => {
    const c = nuevaCapaTexto({ binding: "copy_in", texto: "mi titular" });
    expect(destinoEdicion(c, false)).toBe("texto");
    expect(textoInicial(c, false)).toBe("mi titular");
  });

  it("sin binding => siempre el texto de la capa, con o sin muestra", () => {
    const c = nuevaCapaTexto({ texto: "texto libre" });
    expect(destinoEdicion(c, true)).toBe("texto");
    expect(textoInicial(c, true)).toBe("texto libre");
  });
});

describe("edicionInline — estilo del contenedor (caja/valign/rotación a escala)", () => {
  it("caja con alto (h>0) y valign centro: flex centrado y dimensiones escaladas", () => {
    const c = nuevaCapaTexto({ x: 100, y: 200, w: 600, h: 400, valign: "centro" });
    const st = estiloCajaEdicion(c, 0.5);
    expect(st.left).toBe(50);
    expect(st.top).toBe(100);
    expect(st.width).toBe(300);
    expect(st.height).toBe(200);
    expect(st.justifyContent).toBe("center");
  });

  it("sin caja (h<=0): el alto lo pone el texto (height undefined, contenido arriba)", () => {
    const c = nuevaCapaTexto({ h: 0 });
    const st = estiloCajaEdicion(c, 1);
    expect(st.height).toBeUndefined();
    expect(st.justifyContent).toBe("flex-start");
  });

  it("la rotación pivota arriba-izquierda (mismo pivote que Konva y el export)", () => {
    const c = nuevaCapaTexto({ rotacion: 15 });
    const st = estiloCajaEdicion(c, 1);
    expect(st.transform).toBe("rotate(15deg)");
    expect(st.transformOrigin).toBe("top left");
    expect(estiloCajaEdicion(nuevaCapaTexto({ rotacion: 0 }), 1).transform).toBeUndefined();
  });
});

describe("edicionInline — estilo del texto (espejo del render, a escala)", () => {
  it("tamaño = tamano·escala SIN recortar (el editable es WYSIWYG, no una caja genérica)", () => {
    const c = nuevaCapaTexto({ tamano: 120 });
    expect(estiloTextoEdicion(c, 0.41).fontSize).toBeCloseTo(49.2);
    expect(estiloTextoEdicion(c, 1).fontSize).toBe(120); // sin el clamp histórico de 40px
  });

  it("alineación, mayúsculas, interletra escalada y color/caret del relleno", () => {
    const c = nuevaCapaTexto({
      alineacion: "centro",
      mayusculas: true,
      interletra: 4,
      color: "#FFDE59",
    });
    const st = estiloTextoEdicion(c, 0.5);
    expect(st.textAlign).toBe("center");
    expect(st.textTransform).toBe("uppercase");
    expect(st.letterSpacing).toBe("2px");
    expect(st.color).toBe("#FFDE59");
    expect(st.caretColor).toBe("#FFDE59");
  });

  it("familia real con peso; cursiva solo si la familia la tiene registrada", () => {
    // Barlow SÍ tiene itálica registrada; Anton NO (misma regla que el render y el export).
    const conCursiva = estiloTextoEdicion(nuevaCapaTexto({ familia: "Barlow", cursiva: true, peso: 400 }), 1);
    expect(conCursiva.fontFamily).toBe('"Barlow", sans-serif');
    expect(conCursiva.fontStyle).toBe("italic");
    expect(conCursiva.fontWeight).toBe(400);
    const sinCursiva = estiloTextoEdicion(nuevaCapaTexto({ familia: "Anton", cursiva: true }), 1);
    expect(sinCursiva.fontStyle).toBe("normal");
    // Las familias lógicas legadas resuelven a la real.
    expect(estiloTextoEdicion(nuevaCapaTexto({ familia: "condensada" }), 1).fontFamily).toBe('"Barlow Condensed", sans-serif');
  });
});
