import { describe, expect, it } from "vitest";

import type { Capa, CapaGrupo } from "./documento";
import { altoVisual, bandaOverlay, cajaVisual, conFotoEnHuecosVacios, conTextosHorneados, documentoVacio, nuevaCapaImagen, nuevaCapaMarco, nuevaCapaOverlay, nuevaCapaTexto, tieneHuecoFotoVacio } from "./documento";

// Envuelve capas en un GRUPO (para probar el horneado recursivo dentro de grupos).
function grupo(capas: Capa[]): CapaGrupo {
  return { ...nuevaCapaImagen("", { es_foto: false }), tipo: "grupo", capas } as unknown as CapaGrupo;
}

describe("documentoVacio", () => {
  it("nace transparente y con el hueco de foto OCULTO (marcado y bloqueado)", () => {
    const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 }, "claro-sports");
    // Fondo transparente: se ve el tablero en el editor y exporta con alfa.
    expect(doc.fondo.tipo).toBe("color");
    expect(doc.fondo.color).toBe("#00000000");
    // Trae su hueco de foto (obligatorio para plantilla) pero OCULTO para no ensuciar el lienzo.
    const imagenes = doc.capas.filter((c) => c.tipo === "imagen");
    expect(imagenes).toHaveLength(1);
    const hueco = imagenes[0];
    expect(hueco.tipo === "imagen" && hueco.es_foto).toBe(true);
    expect(hueco.bloqueada).toBe(true);
    expect(hueco.visible).toBe(false);
  });

  it("preserva los márgenes laterales safe_left/safe_right del formato (aditivos)", () => {
    const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 60, safe_bottom: 96, safe_left: 40, safe_right: 48 });
    expect(doc.formato.safe_left).toBe(40);
    expect(doc.formato.safe_right).toBe(48);
    // Retrocompat: un formato sin laterales no los inventa (quedan undefined => 0 al consumirse).
    const doc2 = documentoVacio({ w: 1080, h: 1080, safe_top: 60, safe_bottom: 96 });
    expect(doc2.formato.safe_left).toBeUndefined();
    expect(doc2.formato.safe_right).toBeUndefined();
  });
});

describe("cajaVisual / bandaOverlay / altoVisual", () => {
  it("bandaOverlay espeja EXACTAMENTE al export (max(1, floor(h*alto_frac)))", () => {
    const ov = nuevaCapaOverlay({ h: 1350, alto_frac: 0.45 });
    // 1350*0.45 = 607.5 -> el export hace floor: 607
    expect(bandaOverlay(ov)).toBe(607);
    // Degenerados: nunca menos de 1px, como dibujarOverlayInferior.
    expect(bandaOverlay(nuevaCapaOverlay({ h: 100, alto_frac: 0 }))).toBe(1);
  });

  it("cajaVisual del overlay es su BANDA inferior (y+h-banda), no la caja del modelo", () => {
    const ov = nuevaCapaOverlay({ x: 0, y: -700, w: 1080, h: 1350, alto_frac: 0.45 });
    const vis = cajaVisual(ov);
    // Con el doc del bug real: la banda pinta arriba del lienzo aunque el modelo diga y=-700.
    expect(vis).toEqual({ x: 0, y: -700 + 1350 - 607, w: 1080, h: 607 });
  });

  it("cajaVisual del overlay con lado 'arriba' es su BANDA SUPERIOR (y), no la inferior", () => {
    const ov = nuevaCapaOverlay({ x: 0, y: 0, w: 1080, h: 1350, alto_frac: 0.45, lado: "arriba" });
    // Banda pegada al tope: y = la del modelo (no y+h-banda); mismo alto que la inferior.
    expect(cajaVisual(ov)).toEqual({ x: 0, y: 0, w: 1080, h: 607 });
  });

  it("cajaVisual del texto legado (h<=0) con ancla 'abajo' ancla el bloque por su borde INFERIOR", () => {
    const t = nuevaCapaTexto({ x: 80, y: 1254, w: 760, h: 0, tamano: 96, interlineado: 1.14, ancla: "abajo" });
    const alto = Math.round(96 * 1.14);
    expect(cajaVisual(t)).toEqual({ x: 80, y: 1254 - alto, w: 760, h: alto });
    // Con ancla 'arriba' (default) la y almacenada ya es el tope.
    const t2 = nuevaCapaTexto({ x: 80, y: 100, w: 760, h: 0, tamano: 96, interlineado: 1.14 });
    expect(cajaVisual(t2).y).toBe(100);
  });

  it("cajaVisual de las demás capas es su caja del modelo; altoVisual del overlay es la banda", () => {
    const m = nuevaCapaMarco({ x: 10, y: 20, w: 30, h: 40 });
    expect(cajaVisual(m)).toEqual({ x: 10, y: 20, w: 30, h: 40 });
    expect(altoVisual(nuevaCapaOverlay({ h: 1000, alto_frac: 0.5 }))).toBe(500);
  });
});

describe("tieneHuecoFotoVacio / conFotoEnHuecosVacios (hornear foto de muestra en la descarga)", () => {
  const fmt = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

  it("detecta el hueco de foto (`es_foto`) vacío y lo da por lleno cuando ya tiene objeto", () => {
    const doc = documentoVacio(fmt, "claro-sports"); // nace con un hueco es_foto vacío
    expect(tieneHuecoFotoVacio(doc)).toBe(true);
    // Una imagen vacía que NO es hueco no cuenta (solo el hueco recibe la muestra).
    const conImagenSuelta = { ...doc, capas: [...doc.capas, nuevaCapaImagen("")] };
    expect(tieneHuecoFotoVacio(conImagenSuelta)).toBe(true); // sigue habiendo hueco vacío
    const soloImagenSuelta = { ...doc, capas: [nuevaCapaImagen("")] };
    expect(tieneHuecoFotoVacio(soloImagenSuelta)).toBe(false); // no hay hueco es_foto
    // Hueco ya con foto real => nada que hornear.
    const lleno = conFotoEnHuecosVacios(doc, "media-123");
    expect(tieneHuecoFotoVacio(lleno)).toBe(false);
  });

  it("hornea el objeto SOLO en los huecos `es_foto` vacíos, sin mutar el documento original", () => {
    const doc = documentoVacio(fmt, "uno-tv");
    const out = conFotoEnHuecosVacios(doc, "media-xyz");
    const huecoOrig = doc.capas.find((c) => c.tipo === "imagen" && c.es_foto);
    const huecoOut = out.capas.find((c) => c.tipo === "imagen" && c.es_foto);
    expect(huecoOrig && huecoOrig.tipo === "imagen" && huecoOrig.objeto).toBe(""); // original intacto
    expect(huecoOut && huecoOut.tipo === "imagen" && huecoOut.objeto).toBe("media-xyz");
    expect(out).not.toBe(doc);
  });

  it("no pisa un hueco que ya trae foto real ni toca imágenes que no son hueco (collage)", () => {
    const base = documentoVacio(fmt, "claro-sports");
    // Collage: hueco0 vacío (heredado), hueco1 con foto real, + una imagen normal (no hueco).
    const doc = {
      ...base,
      capas: [
        ...base.capas,
        nuevaCapaImagen("foto-real", { es_foto: true }),
        nuevaCapaImagen("logo-deco"),
      ],
    };
    const out = conFotoEnHuecosVacios(doc, "muestra-1");
    const objetos = out.capas
      .filter((c) => c.tipo === "imagen")
      .map((c) => (c.tipo === "imagen" ? c.objeto : ""));
    expect(objetos).toContain("muestra-1"); // el hueco vacío recibió la muestra
    expect(objetos).toContain("foto-real"); // el hueco con foto real intacto
    expect(objetos).toContain("logo-deco"); // la imagen no-hueco intacta
    expect(objetos.filter((o) => o === "muestra-1")).toHaveLength(1); // solo un hueco rellenado
  });

  it("detecta y hornea un hueco de foto vacío ANIDADO en un grupo (WYSIWYG del export)", () => {
    const base = documentoVacio(fmt, "uno-tv");
    // El hueco de nivel superior ya tiene foto real; el único hueco VACÍO vive dentro de un grupo.
    const doc = {
      ...base,
      capas: [
        { ...(base.capas[0] as Capa), objeto: "foto-real" } as Capa,
        grupo([nuevaCapaImagen("", { es_foto: true }), nuevaCapaTexto({ texto: "pie" })]),
      ],
    };
    expect(tieneHuecoFotoVacio(doc)).toBe(true);
    const out = conFotoEnHuecosVacios(doc, "muestra-grupo");
    const g = out.capas.find((c) => c.tipo === "grupo") as CapaGrupo;
    const hueco = g.capas.find((c) => c.tipo === "imagen" && c.es_foto);
    expect(hueco && hueco.tipo === "imagen" && hueco.objeto).toBe("muestra-grupo");
    // El hueco de nivel superior con foto real no se toca, y ya no queda ninguno vacío.
    expect(tieneHuecoFotoVacio(out)).toBe(false);
  });
});

describe("conTextosHorneados (congelar el texto visible en la descarga)", () => {
  const fmt = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

  it("hornea el texto resuelto y QUITA el binding, sin tocar las capas que el resolver deja en null", () => {
    const titular = nuevaCapaTexto({ binding: "copy_in", texto: "MI TITULAR" });
    const pleca = nuevaCapaTexto({ binding: "etiqueta_default", texto: "" });
    const libre = nuevaCapaTexto({ binding: null, texto: "pie de foto" });
    const doc = { ...documentoVacio(fmt, "uno-tv"), capas: [titular, pleca, libre] };

    const out = conTextosHorneados(doc, (c) =>
      c.binding === "copy_in" ? c.texto : null,
    );
    const [t, p, l] = out.capas as typeof doc.capas;
    // El titular se congela: texto literal + binding quitado (el server pintará `texto`, no el binding).
    expect(t.tipo === "texto" && t.texto).toBe("MI TITULAR");
    expect(t.tipo === "texto" && t.binding).toBeNull();
    // La pleca (resolver -> null) y la capa libre quedan EXACTAMENTE igual (misma referencia).
    expect(p).toBe(pleca);
    expect(l).toBe(libre);
    // No muta el documento original.
    expect(titular.binding).toBe("copy_in");
  });

  it("deja intactas las capas que no son de texto", () => {
    const img = nuevaCapaImagen("foto", { es_foto: true });
    const doc = { ...documentoVacio(fmt, "claro-sports"), capas: [img] };
    const out = conTextosHorneados(doc, () => "lo que sea");
    expect(out.capas[0]).toBe(img);
  });

  it("hornea un titular con binding ANIDADO en un grupo y le quita el binding (WYSIWYG)", () => {
    const anidado = nuevaCapaTexto({ binding: "copy_in", texto: "TITULAR ANIDADO" });
    const doc = { ...documentoVacio(fmt, "uno-tv"), capas: [grupo([anidado])] };
    const out = conTextosHorneados(doc, (c) => (c.binding === "copy_in" ? c.texto : null));
    const g = out.capas[0] as CapaGrupo;
    const t = g.capas[0];
    expect(t.tipo === "texto" && t.texto).toBe("TITULAR ANIDADO");
    expect(t.tipo === "texto" && t.binding).toBeNull();
    // No muta el original.
    expect(anidado.binding).toBe("copy_in");
  });
});
