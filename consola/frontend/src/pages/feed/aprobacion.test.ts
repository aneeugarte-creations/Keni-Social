import { describe, expect, it } from "vitest";

import type { CadenaAprobacion, NivelAprobacion } from "@/types";

import { elegibilidadOK, esDislikeDecisivo, umbralDislikes } from "./aprobacion";

function nivel(over: Partial<NivelAprobacion>): NivelAprobacion {
  return {
    id: "n?",
    plataforma_id: "p1",
    contenido_id: "c1",
    nivel: 1,
    etiqueta: "Edición",
    decision: "pendiente",
    decisor_id: "",
    decisor_nombre: "",
    comentario: "",
    creado: "",
    decidido_en: "",
    cargo_requerido: "",
    ...over,
  };
}

/** Cadena de los dos OK: Edición (OK de Ana) → Coordinación (el OK que toca ahora). */
function cadenaOK(over: Partial<CadenaAprobacion> = {}): CadenaAprobacion {
  return {
    niveles: [
      nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "aprobado", decisor_id: "ana", decisor_nombre: "Ana" }),
      nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación" }),
    ],
    estado: "pendiente",
    nivel_actual: "n2",
    aprobados: 1,
    minimo_aprobaciones: 0,
    comentarios_sin_resolver: 0,
    ...over,
  };
}

describe("elegibilidadOK · quién puede dar el OK (me gusta)", () => {
  it("sin cadena (o vacía) no se puede dar OK, sin motivo (aún no aplica)", () => {
    expect(elegibilidadOK(undefined, { id: "u1", rol: "editor" }, "autorX")).toEqual({
      puedeDar: false,
      motivo: "",
    });
  });

  it("una persona distinta del autor que no ha dado OK SÍ puede", () => {
    const e = elegibilidadOK(cadenaOK(), { id: "u1", rol: "editor" }, "autorX");
    expect(e.puedeDar).toBe(true);
  });

  it("el autor (no admin) NO puede dar OK a su propia pieza", () => {
    const e = elegibilidadOK(cadenaOK(), { id: "u1", rol: "editor" }, "u1");
    expect(e.puedeDar).toBe(false);
    expect(e.motivo).toMatch(/tu propia pieza/i);
  });

  it("quien ya dio un OK NO puede dar el otro", () => {
    const c = cadenaOK({
      niveles: [
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "aprobado", decisor_id: "u1", decisor_nombre: "Yo" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación" }),
      ],
    });
    const e = elegibilidadOK(c, { id: "u1", rol: "editor" }, "autorX");
    expect(e.puedeDar).toBe(false);
    expect(e.motivo).toMatch(/ya diste tu ok/i);
  });

  it("un admin SÍ puede aunque sea el autor (desatascar)", () => {
    expect(elegibilidadOK(cadenaOK(), { id: "u1", rol: "admin" }, "u1").puedeDar).toBe(true);
  });

  it("un admin que YA dio un OK TAMPOCO puede dar el otro (segundo par de ojos)", () => {
    const c = cadenaOK({
      niveles: [
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "aprobado", decisor_id: "u1", decisor_nombre: "Yo" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación" }),
      ],
    });
    const e = elegibilidadOK(c, { id: "u1", rol: "admin" }, "autorX");
    expect(e.puedeDar).toBe(false);
    expect(e.motivo).toMatch(/ya diste tu ok/i);
  });

  it("si el nivel que toca es el de IA (QA), el OK humano espera", () => {
    const c = cadenaOK({
      niveles: [
        nivel({ id: "qa", nivel: 1, etiqueta: "QA Editorial" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Edición" }),
      ],
      nivel_actual: "qa",
    });
    const e = elegibilidadOK(c, { id: "u1", rol: "editor" }, "autorX");
    expect(e.puedeDar).toBe(false);
    expect(e.motivo).toMatch(/verificación de la IA/i);
  });
});

describe("umbralDislikes / esDislikeDecisivo · cuándo el dislike rechaza la pieza", () => {
  it("umbral 2 con dos (o más) niveles humanos; 1 en cadenas de un solo humano", () => {
    expect(umbralDislikes(cadenaOK())).toBe(2);
    expect(umbralDislikes({ niveles: [nivel({ id: "n1" })] })).toBe(1);
  });

  it("el nivel de IA (QA Editorial) no cuenta como humano para el umbral", () => {
    const c = {
      niveles: [
        nivel({ id: "qa", etiqueta: "QA Editorial" }),
        nivel({ id: "n1", nivel: 2, etiqueta: "Edición" }),
      ],
    };
    expect(umbralDislikes(c)).toBe(1);
    // Y al ser umbral 1, el primer dislike ya es decisivo.
    expect(esDislikeDecisivo(c)).toBe(true);
  });

  it("con dos humanos y sin dislikes, el PRIMER dislike no es decisivo", () => {
    expect(esDislikeDecisivo(cadenaOK())).toBe(false);
  });

  it("con un dislike ya puesto (dos humanos), el siguiente ES decisivo", () => {
    const c = cadenaOK({
      niveles: [
        nivel({ id: "n1", etiqueta: "Edición", decision: "rechazado", decisor_id: "ana" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación" }),
      ],
    });
    expect(esDislikeDecisivo(c)).toBe(true);
  });

  it("cadena de UN nivel humano: el primer dislike ya es decisivo", () => {
    expect(esDislikeDecisivo({ niveles: [nivel({ id: "n1" })] })).toBe(true);
  });
});
