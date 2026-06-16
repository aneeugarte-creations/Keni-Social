/**
 * Unitarios de la lógica pura de "Estrategia de marca" (`datos.ts`):
 *   - `extracto`: texto plano legible desde markdown (frontmatter fuera).
 *   - `normalizar`: SIEMPRE los 5 pilares en orden fijo, defensivo ante respuestas parciales.
 *   - `desdeFallback`: el mismo estado desde el listado clásico + validación.
 */
import { describe, expect, it } from "vitest";

import type { DocumentoTexto, ValidacionEditorial } from "@/types";

import { CLASES_PILAR, desdeFallback, extracto, normalizar } from "./datos";

function docEditorial(parcial: Partial<DocumentoTexto>): DocumentoTexto {
  return {
    id: "editorial/rrss/unotv/doc",
    titulo: "Doc",
    tipo: "editorial",
    carpeta: "rrss/unotv",
    cuerpo: "Contenido.",
    creado: "2026-05-01T10:00:00",
    actualizado: "2026-06-01T10:00:00",
    clase: "",
    marcas: ["unotv"],
    ...parcial,
  };
}

describe("extracto", () => {
  it("quita frontmatter, marcado y variables; colapsa espacios", () => {
    const md =
      "---\ntipo: editorial\nclase: voz\n---\n\n# Voz\n\n- Tono **cercano** y `directo`.\n\nEscribe para {{MARCA}} con [enlaces](https://x.test).";
    expect(extracto(md)).toBe("Voz Tono cercano y directo. Escribe para MARCA con enlaces.");
  });

  it("devuelve '' sin contenido con sustancia y corta sin partir palabras", () => {
    expect(extracto("")).toBe("");
    expect(extracto("---\ntipo: editorial\n---\n\n")).toBe("");
    const largo = extracto(`${"palabra ".repeat(60)}final`, 50);
    expect(largo.endsWith("…")).toBe(true);
    expect(largo.length).toBeLessThanOrEqual(51);
  });
});

describe("normalizar", () => {
  it("garantiza los 5 pilares en orden fijo aunque la respuesta venga parcial y desordenada", () => {
    const r = normalizar({
      completitud: { completa: false, faltan: ["marca", "tropicalizacion"], recomendacion: "Define la identidad." },
      pilares: [
        { clase: "reglas", titulo: "Reglas (global)", doc_id: "editorial/rrss/global/reglas-legales", global: true, vacio: false },
        { clase: "voz", titulo: "Voz UnoTV", doc_id: "editorial/rrss/unotv/voz", vacio: false, sin_publicar: true },
      ],
      orden_inyeccion: ["editorial/rrss/unotv/voz", "editorial/rrss/global/reglas-legales"],
    });
    expect(r.pilares.map((p) => p.clase)).toEqual([...CLASES_PILAR]);
    expect(r.pilares[0].vacio).toBe(true); // marca: no vino -> vacío
    expect(r.pilares[1].sinPublicar).toBe(true); // voz
    expect(r.pilares[4].global).toBe(true); // reglas
    expect(r.cubiertos).toBe(2); // 4 obligatorios - 2 que faltan
    expect(r.total).toBe(4);
    // Etiquetas legibles del orden de inyección (título humano del pilar).
    expect(r.orden.map((o) => o.etiqueta)).toEqual(["Voz", "Reglas legales"]);
  });

  it("degrada con una respuesta vacía: 5 pilares vacíos y 0/4", () => {
    const r = normalizar({});
    expect(r.pilares).toHaveLength(5);
    expect(r.pilares.every((p) => p.vacio && p.docId === null)).toBe(true);
    expect(r.orden).toEqual([]);
    // Sin `completitud` no inventamos faltantes: el dato manda cuando llega.
    expect(r.total).toBe(4);
  });
});

describe("desdeFallback", () => {
  const docs: DocumentoTexto[] = [
    docEditorial({
      id: "editorial/rrss/unotv/voz",
      titulo: "Voz UnoTV",
      clase: "voz",
      cuerpo: "Tono cercano y directo.",
      sin_publicar: true,
      prioridad: 2,
    }),
    docEditorial({
      id: "editorial/rrss/unotv/marca",
      titulo: "Identidad UnoTV",
      clase: "marca",
      cuerpo: "UnoTV informa con rigor.",
      produccion: { sha: "a1", autor: "ana", nota: "v1", creado: "2026-06-01T09:00:00" },
      prioridad: 1,
    }),
    docEditorial({
      id: "editorial/rrss/global/reglas-legales",
      titulo: "Reglas legales (global)",
      clase: "reglas",
      carpeta: "rrss/global",
      marcas: [],
      cuerpo: "Nada de datos personales.",
      prioridad: 9,
    }),
    docEditorial({
      id: "editorial/rrss/unotv/patrones",
      titulo: "Patrones medidos · UnoTV",
      clase: "",
      cuerpo: "Bandas de rendimiento medidas.",
      prioridad: 5,
    }),
  ];
  const validacion: ValidacionEditorial = {
    completa: false,
    faltan: ["tropicalizacion", "plataforma"],
    recomendacion: "Faltan tropicalización y plataformas.",
    pilares: { marca: true, voz: true, plataforma: false, tropicalizacion: false },
  };

  it("monta los 5 pilares desde el listado + validación, con extras y orden por prioridad", () => {
    const r = desdeFallback(docs, validacion);
    expect(r.pilares.map((p) => p.clase)).toEqual([...CLASES_PILAR]);
    expect(r.pilares[0].publicado).toBe(true); // marca
    expect(r.pilares[1].sinPublicar).toBe(true); // voz
    expect(r.pilares[2].vacio).toBe(true); // tropicalización: sin doc
    expect(r.pilares[2].docId).toBeNull();
    expect(r.pilares[4].global).toBe(true); // reglas: marcas []
    expect(r.cubiertos).toBe(2);
    expect(r.recomendacion).toBe("Faltan tropicalización y plataformas.");
    // Extras: lo que no es pilar (patrones).
    expect(r.extras.map((e) => e.docId)).toEqual(["editorial/rrss/unotv/patrones"]);
    // Orden de inyección: por prioridad ascendente.
    expect(r.orden.map((o) => o.docId)).toEqual([
      "editorial/rrss/unotv/marca",
      "editorial/rrss/unotv/voz",
      "editorial/rrss/unotv/patrones",
      "editorial/rrss/global/reglas-legales",
    ]);
  });

  it("sin validación, deriva los faltantes de los pilares obligatorios vacíos", () => {
    const r = desdeFallback(docs, undefined);
    expect(r.faltan.sort()).toEqual(["plataforma", "tropicalizacion"]);
    expect(r.cubiertos).toBe(2);
    expect(r.completa).toBe(false);
  });
});
