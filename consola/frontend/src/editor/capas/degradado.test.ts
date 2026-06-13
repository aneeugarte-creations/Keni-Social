import { describe, expect, it } from "vitest";

import type { RellenoDegradado } from "../documento";

import { colorStopsKonva, puntosGradiente } from "./degradado";

const todosFinitos = (g: { start: { x: number; y: number }; end: { x: number; y: number } }) =>
  [g.start.x, g.start.y, g.end.x, g.end.y].every((n) => Number.isFinite(n));

describe("puntosGradiente", () => {
  it("da un eje finito y NO degenerado para un ángulo normal", () => {
    const g = puntosGradiente(1080, 1080, 0);
    expect(todosFinitos(g)).toBe(true);
    expect(g.start).not.toEqual(g.end);
  });

  // REGRESIÓN del bug "el degradado desaparece al darle la vuelta": un `angulo` NO finito
  // (dato malformado de una plantilla/doc que no pasó por el control `Num`) daría puntos NaN,
  // que hacen LANZAR a `createLinearGradient` y borran el relleno. Debe caer a vertical (180).
  it.each([
    ["NaN", Number.NaN],
    ["Infinity", Number.POSITIVE_INFINITY],
    ["-Infinity", Number.NEGATIVE_INFINITY],
    ["null", null],
    ["string", "180abc"],
  ])("ante un ángulo no finito (%s) cae a vertical y NO devuelve NaN", (_etq, angulo) => {
    const g = puntosGradiente(1080, 1350, angulo as unknown as number);
    expect(todosFinitos(g)).toBe(true);
    expect(g.start).not.toEqual(g.end);
    // El respaldo es exactamente el vertical 180 (eje (w/2,0)->(w/2,h)).
    expect(puntosGradiente(1080, 1350, angulo as unknown as number)).toEqual(
      puntosGradiente(1080, 1350, 180),
    );
  });

  it("ángulo undefined usa el default 180 (vertical)", () => {
    expect(puntosGradiente(600, 800, undefined)).toEqual(puntosGradiente(600, 800, 180));
  });
});

describe("colorStopsKonva", () => {
  it("usa desde/hasta cuando no hay stops", () => {
    expect(colorStopsKonva({ desde: "#ffffff", hasta: "#000000" } as RellenoDegradado)).toEqual([
      0, "#ffffff", 1, "#000000",
    ]);
  });

  it("respalda desde/hasta ausentes (addColorStop(undefined) borraría el degradado)", () => {
    const stops = colorStopsKonva({} as RellenoDegradado);
    expect(stops).toHaveLength(4);
    expect(stops.every((x) => x !== undefined && x !== null && x !== "")).toBe(true);
  });

  it("descarta paradas sin color y normaliza una pos no finita a 0", () => {
    const deg = {
      desde: "#ffffff",
      hasta: "#000000",
      stops: [
        { pos: 0, color: "#ff0000" },
        { pos: Number.NaN, color: "#00ff00" },
        { pos: 1, color: undefined as unknown as string },
      ],
    } as RellenoDegradado;
    // La parada sin color se cae -> quedan 2 válidas; la pos NaN -> 0.
    expect(colorStopsKonva(deg)).toEqual([0, "#ff0000", 0, "#00ff00"]);
  });

  it("con <2 paradas válidas cae a desde/hasta", () => {
    const deg = {
      desde: "#111111",
      hasta: "#222222",
      stops: [{ pos: 0, color: "#ff0000" }],
    } as RellenoDegradado;
    expect(colorStopsKonva(deg)).toEqual([0, "#111111", 1, "#222222"]);
  });
});
