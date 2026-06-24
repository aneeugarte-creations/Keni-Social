import { describe, expect, it } from "vitest";

import { origenFondoPropio } from "./lib";

describe("origenFondoPropio", () => {
  // Solo el hueco 0 (el FONDO de la placa) porta el `foto`/metadata de licencia de la pieza:
  // reemplazarlo por una propia (subir/galería/IA) declara el origen para limpiar el stock heredado.
  it("declara el origen al reemplazar el FONDO (hueco 0)", () => {
    expect(origenFondoPropio(0, "subida")).toBe("subida");
    expect(origenFondoPropio(0, "galeria")).toBe("galeria");
    expect(origenFondoPropio(0, "ia")).toBe("ia");
  });

  // Un hueco SECUNDARIO del collage no toca la metadata de stock del fondo: no declara origen
  // (declararlo borraría el crédito de un fondo de stock que sigue en pie y lo desbloquearía).
  it("NO declara origen al tocar un hueco secundario del collage", () => {
    expect(origenFondoPropio(1, "subida")).toBeNull();
    expect(origenFondoPropio(2, "ia")).toBeNull();
  });
});
