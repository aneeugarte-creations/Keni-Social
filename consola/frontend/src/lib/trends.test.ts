import { describe, expect, it } from "vitest";

import { esFuenteTrends, FUENTE_ID_TRENDS, nombreFuente } from "./trends";

describe("nombreFuente", () => {
  it("marca (Google Trends) cuando la fuente es del descubridor", () => {
    expect(nombreFuente("朝日新聞", FUENTE_ID_TRENDS)).toBe("朝日新聞 (Google Trends)");
  });

  it("sin medio concreto, cae a 'Google Trends' a secas", () => {
    expect(nombreFuente("", FUENTE_ID_TRENDS)).toBe("Google Trends");
    expect(nombreFuente(null, FUENTE_ID_TRENDS)).toBe("Google Trends");
  });

  it("deja el nombre intacto para fuentes RSS normales", () => {
    expect(nombreFuente("Reuters", "reuters-world")).toBe("Reuters");
    expect(nombreFuente("Reuters")).toBe("Reuters");
  });
});

describe("esFuenteTrends", () => {
  it("solo es true para el id de Google Trends", () => {
    expect(esFuenteTrends(FUENTE_ID_TRENDS)).toBe(true);
    expect(esFuenteTrends("bbc-world")).toBe(false);
    expect(esFuenteTrends(undefined)).toBe(false);
  });
});
