import { describe, expect, it } from "vitest";

import type { Skill } from "@/types";

import {
  campoArchivo,
  camposTextoCompletos,
  esSkillConArchivo,
  puedeGenerarSkill,
  valoresIniciales,
  valoresRecortados,
} from "./dynamico";

/**
 * Tests de la lógica pura del formulario DINÁMICO de Generar copy: cómo se
 * inicializan los valores, cuándo se considera completo y cuándo el botón
 * "Generar" debe habilitarse para cada forma de skill.
 */

/** Skill de piezas con un textarea requerido + un texto opcional. */
const SKILL_PIEZAS: Skill = {
  id: "nota",
  nombre: "Copy desde nota",
  explicacion: "Convierte una nota en piezas por red.",
  aplica_redes: true,
  salida: "piezas",
  media: false,
  campos: [
    { id: "nota", etiqueta: "Nota", tipo: "textarea", requerido: true },
    { id: "angulo", etiqueta: "Ángulo", tipo: "texto", requerido: false },
  ],
};

/** Skill de documento sin redes y sin campos requeridos de texto. */
const SKILL_DOCUMENTO: Skill = {
  id: "brief",
  nombre: "Brief semanal",
  explicacion: "Genera un brief.",
  aplica_redes: false,
  salida: "documento",
  media: false,
  campos: [{ id: "tema", etiqueta: "Tema", tipo: "texto", requerido: true }],
};

/** Skill de medios: un campo archivo requerido (envío multipart). */
const SKILL_MEDIA: Skill = {
  id: "audio",
  nombre: "Copy desde audio",
  explicacion: "Transcribe y genera.",
  aplica_redes: true,
  salida: "piezas",
  media: true,
  campos: [
    { id: "archivo", etiqueta: "Audio", tipo: "archivo", requerido: true, media_tipos: "audio/*" },
  ],
};

const archivoFalso = new File(["x"], "audio.mp3", { type: "audio/mpeg" });

describe("valoresIniciales", () => {
  it("crea una entrada vacía por cada campo de texto y omite los de archivo", () => {
    expect(valoresIniciales(SKILL_PIEZAS)).toEqual({ nota: "", angulo: "" });
    expect(valoresIniciales(SKILL_MEDIA)).toEqual({});
  });

  it("devuelve un objeto vacío si no hay skill", () => {
    expect(valoresIniciales(undefined)).toEqual({});
  });
});

describe("campoArchivo / esSkillConArchivo", () => {
  it("detecta el campo de archivo cuando existe", () => {
    expect(campoArchivo(SKILL_MEDIA)?.id).toBe("archivo");
    expect(esSkillConArchivo(SKILL_MEDIA)).toBe(true);
  });

  it("no encuentra archivo en skills solo de texto", () => {
    expect(campoArchivo(SKILL_PIEZAS)).toBeUndefined();
    expect(esSkillConArchivo(SKILL_PIEZAS)).toBe(false);
  });
});

describe("camposTextoCompletos", () => {
  it("exige solo los campos requeridos de texto", () => {
    expect(camposTextoCompletos(SKILL_PIEZAS, { nota: "", angulo: "" })).toBe(false);
    expect(camposTextoCompletos(SKILL_PIEZAS, { nota: "   ", angulo: "" })).toBe(false);
    // Con el requerido relleno basta, aunque el opcional siga vacío.
    expect(camposTextoCompletos(SKILL_PIEZAS, { nota: "Hola", angulo: "" })).toBe(true);
  });
});

describe("puedeGenerarSkill", () => {
  const redes = new Set(["x", "instagram"]);

  it("piezas: requiere campos de texto + al menos una red", () => {
    expect(
      puedeGenerarSkill({ skill: SKILL_PIEZAS, valores: { nota: "Hola" }, archivo: null, redes }),
    ).toBe(true);
    // Sin redes seleccionadas, no se puede.
    expect(
      puedeGenerarSkill({
        skill: SKILL_PIEZAS,
        valores: { nota: "Hola" },
        archivo: null,
        redes: new Set(),
      }),
    ).toBe(false);
    // Campo requerido vacío.
    expect(
      puedeGenerarSkill({ skill: SKILL_PIEZAS, valores: { nota: "" }, archivo: null, redes }),
    ).toBe(false);
  });

  it("documento: no exige redes", () => {
    expect(
      puedeGenerarSkill({
        skill: SKILL_DOCUMENTO,
        valores: { tema: "IA" },
        archivo: null,
        redes: new Set(),
      }),
    ).toBe(true);
  });

  it("media: exige el archivo cuando el campo es requerido", () => {
    expect(
      puedeGenerarSkill({ skill: SKILL_MEDIA, valores: {}, archivo: null, redes }),
    ).toBe(false);
    expect(
      puedeGenerarSkill({ skill: SKILL_MEDIA, valores: {}, archivo: archivoFalso, redes }),
    ).toBe(true);
  });

  it("sin skill nunca habilita", () => {
    expect(
      puedeGenerarSkill({ skill: undefined, valores: {}, archivo: null, redes }),
    ).toBe(false);
  });
});

describe("valoresRecortados", () => {
  it("recorta los espacios de cada valor", () => {
    expect(valoresRecortados({ a: "  hola  ", b: "x" })).toEqual({ a: "hola", b: "x" });
  });
});
