import { describe, expect, it } from "vitest";

import {
  type CajaIman,
  type ObjetivoIman,
  cajaEnvolvente,
  calcularEspaciado,
  calcularImanEje,
  huecoPerpendicular,
} from "./imanes";

describe("calcularImanEje", () => {
  const objetivos: ObjetivoIman[] = [{ t: 100 }, { t: 104 }, { t: 500 }];

  it("ajusta al objetivo MÁS CERCANO dentro del umbral", () => {
    // Borde izquierdo en 103: 104 está a 1 px y 100 a 3 px => gana 104.
    const s = calcularImanEje(103, 50, objetivos, 6);
    expect(s).not.toBeNull();
    expect(s?.pos).toBe(104);
    expect(s?.guia).toBe(104);
  });

  it("no ajusta fuera del umbral", () => {
    expect(calcularImanEje(300, 50, objetivos, 6)).toBeNull();
  });

  it("prueba también el centro y el borde final de la caja", () => {
    // Centro de la caja (200 + 100/2 = 250) cerca de un objetivo en 252.
    const s = calcularImanEje(200, 100, [{ t: 252 }], 6);
    expect(s?.pos).toBe(202);
    // Borde final (350 + 100 = 450) cerca de 447.
    const s2 = calcularImanEje(350, 100, [{ t: 447 }], 6);
    expect(s2?.pos).toBe(347);
  });

  it("devuelve la caja de referencia del objetivo (para la etiqueta de distancia)", () => {
    const ref: CajaIman = { x: 100, y: 0, w: 50, h: 50 };
    const s = calcularImanEje(98, 50, [{ t: 100, ref }], 6);
    expect(s?.ref).toBe(ref);
    // Los objetivos del lienzo (sin ref) no llevan caja.
    const s2 = calcularImanEje(98, 50, [{ t: 100 }], 6);
    expect(s2?.ref).toBeUndefined();
  });
});

describe("cajaEnvolvente (rect que se imanta en multi-selección)", () => {
  it("abraza todas las cajas del grupo", () => {
    const cajas: CajaIman[] = [
      { x: 10, y: 20, w: 100, h: 50 },
      { x: 200, y: 0, w: 50, h: 200 },
    ];
    expect(cajaEnvolvente(cajas)).toEqual({ x: 10, y: 0, w: 240, h: 200 });
  });

  it("con una sola caja devuelve esa misma geometría", () => {
    expect(cajaEnvolvente([{ x: 5, y: 7, w: 30, h: 40 }])).toEqual({ x: 5, y: 7, w: 30, h: 40 });
  });

  it("lista vacía => null (grupo degenerado, sin imán)", () => {
    expect(cajaEnvolvente([])).toBeNull();
  });

  it("la envolvente se imanta con calcularImanEje y el delta se reparte a las capas", () => {
    // Grupo de dos capas cuya envolvente es [843..1083]: el borde derecho queda a 3 px del borde
    // del lienzo (1080) => snap con delta -3, que se aplica POR IGUAL a todas las capas del grupo.
    const capas: CajaIman[] = [
      { x: 843, y: 100, w: 100, h: 50 },
      { x: 983, y: 200, w: 100, h: 50 },
    ];
    const env = cajaEnvolvente(capas);
    expect(env).toEqual({ x: 843, y: 100, w: 240, h: 150 });
    const s = calcularImanEje(env!.x, env!.w, [{ t: 0 }, { t: 540 }, { t: 1080 }], 6);
    expect(s).not.toBeNull();
    expect(s?.pos).toBe(840);
    expect(s?.guia).toBe(1080);
    const delta = s!.pos - env!.x;
    expect(capas.map((c) => c.x + delta)).toEqual([840, 980]);
  });
});

describe("huecoPerpendicular", () => {
  it("para una guía vertical (eje x) mide la separación VERTICAL entre cajas", () => {
    const a: CajaIman = { x: 0, y: 0, w: 100, h: 100 };
    const b: CajaIman = { x: 0, y: 140, w: 100, h: 50 };
    expect(huecoPerpendicular(a, b, "x")).toEqual({ gap: 40, centro: 120 });
    // Simétrico.
    expect(huecoPerpendicular(b, a, "x")).toEqual({ gap: 40, centro: 120 });
  });

  it("para una guía horizontal (eje y) mide la separación HORIZONTAL", () => {
    const a: CajaIman = { x: 0, y: 0, w: 100, h: 100 };
    const b: CajaIman = { x: 130, y: 0, w: 50, h: 100 };
    expect(huecoPerpendicular(a, b, "y")).toEqual({ gap: 30, centro: 115 });
  });

  it("si las cajas se solapan no hay distancia que etiquetar", () => {
    const a: CajaIman = { x: 0, y: 0, w: 100, h: 100 };
    const b: CajaIman = { x: 0, y: 50, w: 100, h: 100 };
    expect(huecoPerpendicular(a, b, "x")).toBeNull();
  });
});

describe("calcularEspaciado (espaciado igual estilo Canva)", () => {
  // Fila horizontal: todas con y solapada con la caja arrastrada.
  const A: CajaIman = { x: 0, y: 0, w: 100, h: 100 };
  const B: CajaIman = { x: 300, y: 0, w: 100, h: 100 };

  it("CENTRADA entre dos vecinas: ajusta a huecos iguales con sus dos segmentos", () => {
    // Hueco total entre A y B = 200; caja de 80 centrada => huecos de 60 a cada lado (pos 160).
    const caja: CajaIman = { x: 158, y: 10, w: 80, h: 80 };
    const s = calcularEspaciado(caja, [A, B], "x", 6);
    expect(s).not.toBeNull();
    expect(s?.pos).toBe(160);
    expect(s?.gap).toBe(60);
    // perp = centro del solape vertical entre las cajas de cada hueco (caja 10..90 ∩ vecina 0..100).
    expect(s?.segmentos).toEqual([
      { desde: 100, hasta: 160, perp: 50 },
      { desde: 240, hasta: 300, perp: 50 },
    ]);
  });

  it("CADENA hacia atrás: replica el hueco del par anterior", () => {
    // A [0..100] y C [150..250] guardan 50 px; la caja debe snapear a x = 300.
    const C: CajaIman = { x: 150, y: 0, w: 100, h: 100 };
    const caja: CajaIman = { x: 297, y: 10, w: 80, h: 80 };
    const s = calcularEspaciado(caja, [A, C], "x", 6);
    expect(s?.pos).toBe(300);
    expect(s?.gap).toBe(50);
    expect(s?.segmentos[0]).toMatchObject({ desde: 100, hasta: 150 });
    expect(s?.segmentos[1]).toMatchObject({ desde: 250, hasta: 300 });
  });

  it("CADENA hacia delante: replica el hueco del par siguiente", () => {
    // C [150..250] y B [300..400] guardan 50 px; arrastrando ANTES de C, snap a x = 20 (caja 80).
    const C: CajaIman = { x: 150, y: 0, w: 100, h: 100 };
    const caja: CajaIman = { x: 17, y: 10, w: 80, h: 80 };
    const s = calcularEspaciado(caja, [C, B], "x", 6);
    expect(s?.pos).toBe(20);
    expect(s?.gap).toBe(50);
    expect(s?.segmentos[0]).toMatchObject({ desde: 100, hasta: 150 });
    expect(s?.segmentos[1]).toMatchObject({ desde: 250, hasta: 300 });
  });

  it("también funciona en el eje vertical", () => {
    const arriba: CajaIman = { x: 0, y: 0, w: 100, h: 100 };
    const abajo: CajaIman = { x: 0, y: 300, w: 100, h: 100 };
    const caja: CajaIman = { x: 10, y: 161, w: 80, h: 80 };
    const s = calcularEspaciado(caja, [arriba, abajo], "y", 6);
    expect(s?.pos).toBe(160);
    expect(s?.gap).toBe(60);
  });

  it("ignora capas sin solape perpendicular (otra fila)", () => {
    const otraFila: CajaIman = { x: 300, y: 500, w: 100, h: 100 };
    const caja: CajaIman = { x: 158, y: 10, w: 80, h: 80 };
    expect(calcularEspaciado(caja, [A, otraFila], "x", 6)).toBeNull();
  });

  it("no ajusta fuera del umbral", () => {
    const caja: CajaIman = { x: 140, y: 10, w: 80, h: 80 };
    expect(calcularEspaciado(caja, [A, B], "x", 6)).toBeNull();
  });
});
