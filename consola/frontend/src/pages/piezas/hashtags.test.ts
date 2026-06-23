import { describe, expect, it } from "vitest";

import { agregarHashtags } from "./hashtags";

describe("agregarHashtags", () => {
  it("si el copy ya termina en hashtags, añade en la MISMA línea", () => {
    expect(agregarHashtags("Gran partido\n\n#futbol #ligamx", ["#cienciatech"])).toBe(
      "Gran partido\n\n#futbol #ligamx #cienciatech",
    );
  });

  it("si el copy termina en prosa, separa con un párrafo", () => {
    expect(agregarHashtags("Gran partido hoy", ["#cienciatech"])).toBe(
      "Gran partido hoy\n\n#cienciatech",
    );
  });

  it("sin contenido previo, los hashtags van tal cual", () => {
    expect(agregarHashtags("", ["#cienciatech", "#futbol"])).toBe("#cienciatech #futbol");
  });

  it("no duplica hashtags ya presentes (insensible a mayúsculas)", () => {
    expect(agregarHashtags("Texto #Futbol", ["#futbol", "#ligamx"])).toBe(
      "Texto #Futbol #ligamx",
    );
  });

  it("ignora espacios finales al decidir si la última línea es de hashtags", () => {
    expect(agregarHashtags("Texto\n\n#a #b   \n", ["#c"])).toBe("Texto\n\n#a #b #c");
  });
});
