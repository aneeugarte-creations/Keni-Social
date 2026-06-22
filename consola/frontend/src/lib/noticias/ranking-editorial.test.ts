/**
 * Tests de las funciones PURAS del ranking editorial: la frase de corroboración, el nivel
 * de prioridad y los factores ("¿por qué rankea así?") que traducen el motor a lenguaje
 * de redacción.
 */

import { describe, expect, it } from "vitest";

import type { Historia } from "@/types";

import { calculoScore, factoresRanking, fraseCorroboracion, nivelPrioridad } from "./ranking-editorial";

function historia(overrides: Partial<Historia> = {}): Historia {
  return {
    id: "h1",
    titulo: "T",
    resumen: "",
    marca: "unotv",
    marca_nombre: "UnoTV",
    categoria: "mx",
    geo: "",
    n_items: 3,
    n_fuentes: 3,
    idiomas: ["es"],
    senal: 0,
    score: 0.55,
    breaking: 0,
    primer_visto: "2026-06-05T09:00:00",
    ultimo_visto: "2026-06-05T10:30:00",
    estado: "nuevo",
    publicacion_id: "",
    enlaces: [],
    fuentes: [
      { fuente: "Reuters", fuente_id: "a", peso: 2, tier: "potente", primer_visto: "2026-06-05T09:00:00", n_items: 1 },
      { fuente: "Milenio", fuente_id: "b", peso: 1, tier: "normal", primer_visto: "2026-06-05T09:40:00", n_items: 1 },
      { fuente: "El Universal", fuente_id: "c", peso: 1, tier: "normal", primer_visto: "2026-06-05T10:30:00", n_items: 1 },
    ],
    primera_fuente_nombre: "Reuters",
    ...overrides,
  };
}

describe("nivelPrioridad", () => {
  it("traduce el score a alta/media/baja", () => {
    expect(nivelPrioridad(0.7)).toBe("alta");
    expect(nivelPrioridad(0.5)).toBe("alta");
    expect(nivelPrioridad(0.35)).toBe("media");
    expect(nivelPrioridad(0.1)).toBe("baja");
  });
});

describe("fraseCorroboracion", () => {
  it("corroborada: nombra a las fuentes y a quién la abrió", () => {
    const frase = fraseCorroboracion(historia());
    expect(frase).toMatch(/Confirmada por Reuters, Milenio y El Universal/);
    expect(frase).toMatch(/la abrió Reuters/);
  });

  it("última hora con 2 fuentes de alta relevancia: «la confirmaron casi a la vez»", () => {
    const frase = fraseCorroboracion(
      historia({
        breaking: 1,
        fuentes: [
          { fuente: "Reuters", fuente_id: "a", peso: 2, tier: "potente", primer_visto: "2026-06-05T10:00:00", n_items: 1 },
          { fuente: "AP", fuente_id: "b", peso: 2, tier: "potente", primer_visto: "2026-06-05T10:10:00", n_items: 1 },
        ],
      }),
    );
    expect(frase).toBe("Reuters y AP la confirmaron casi a la vez");
  });

  it("única fuente: tono de espera de corroboración", () => {
    const frase = fraseCorroboracion(
      historia({
        n_fuentes: 1,
        fuentes: [
          { fuente: "Récord", fuente_id: "a", peso: 1, tier: "normal", primer_visto: "2026-06-05T09:00:00", n_items: 1 },
        ],
      }),
    );
    expect(frase).toMatch(/^Única fuente: Récord/);
    expect(frase).toMatch(/espera corroboración/);
  });

  it("dudosa gana a todo lo demás", () => {
    expect(fraseCorroboracion(historia({ verificacion: "dudosa" }))).toMatch(/Señal dudosa/);
  });

  it("sin timeline cae a los enlaces (degradación honesta)", () => {
    const frase = fraseCorroboracion(
      historia({
        fuentes: undefined,
        enlaces: [
          { titulo: "t1", url: "u1", fuente: "Reforma" },
          { titulo: "t2", url: "u2", fuente: "Milenio" },
        ],
        n_fuentes: 2,
      }),
    );
    expect(frase).toMatch(/Confirmada por Reforma y Milenio/);
  });
});

describe("factoresRanking", () => {
  it("traduce el desglose a frases editoriales", () => {
    const factores = factoresRanking(
      historia({
        score_desglose: {
          corroboracion: 0.6,
          velocidad: 0.8,
          frescura: 0.9,
          marca: 0.5,
          palabras: ["cdmx", "sismo"],
        },
      }),
    );
    expect(factores.join("\n")).toMatch(/La confirman 3 medios/);
    expect(factores.join("\n")).toMatch(/creciendo rápido/);
    expect(factores.join("\n")).toMatch(/Encaja con la marca por: cdmx, sismo/);
  });

  it("sin señales fuertes cae a la razón del daemon o a un texto honesto", () => {
    const factores = factoresRanking(
      historia({ n_fuentes: 1, fuentes: [], score_desglose: {}, score_razon: "historia única" }),
    );
    expect(factores).toEqual(["historia única"]);
  });
});

describe("calculoScore", () => {
  it("reconstruye la fórmula: señal × peso = aporte, Σ = score", () => {
    const { lineas, total } = calculoScore(
      historia({
        score_desglose: { corroboracion: 0.5, velocidad: 1.0, frescura: 0.5, viralidad: 0, marca: 0 },
        score_pesos: { corroboracion: 0.3, velocidad: 0.2, frescura: 0.2, viralidad: 0.1, marca: 0.2, rendimiento: 0, breaking: 0 },
      }),
    );
    const porEtiqueta = Object.fromEntries(lineas.map((l) => [l.etiqueta, l]));
    expect(porEtiqueta["Corroboración"].aporte).toBeCloseTo(0.15);
    expect(porEtiqueta["Velocidad"].aporte).toBeCloseTo(0.2);
    expect(porEtiqueta["Rendimiento"]).toBeUndefined(); // peso 0: no cuenta
    expect(total).toBeCloseTo(0.45);
  });

  it("sin pesos del back no inventa cálculo (degradación honesta)", () => {
    const { lineas } = calculoScore(historia({ score_pesos: undefined }));
    expect(lineas).toEqual([]);
  });

  it("un peso malformado (NaN) se ignora y no contamina el total con NaN", () => {
    const { lineas, total } = calculoScore(
      historia({
        score_desglose: { corroboracion: 0.5, velocidad: 1.0 },
        score_pesos: {
          corroboracion: "x" as unknown as number, // valor inválido del back
          velocidad: 0.2,
        },
      }),
    );
    const porEtiqueta = Object.fromEntries(lineas.map((l) => [l.etiqueta, l]));
    expect(porEtiqueta["Corroboración"]).toBeUndefined(); // peso NaN: no cuenta
    expect(porEtiqueta["Velocidad"].aporte).toBeCloseTo(0.2);
    expect(Number.isNaN(total)).toBe(false);
    expect(total).toBeCloseTo(0.2);
  });
});
