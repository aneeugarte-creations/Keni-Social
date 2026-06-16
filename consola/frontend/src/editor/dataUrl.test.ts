import { describe, expect, it } from "vitest";

import { dataUrlAArchivo, dataUrlABlob } from "./dataUrl";

// PNG mínimo (firma) en base64; basta para verificar el decode sin `fetch`.
const PNG = "data:image/png;base64,iVBORw0KGgo=";

describe("dataUrl — decode sin fetch (CSP connect-src 'self' bloquea fetch(data:))", () => {
  it("dataUrlABlob respeta el mime y produce bytes", () => {
    const blob = dataUrlABlob(PNG);
    expect(blob.type).toBe("image/png");
    expect(blob.size).toBeGreaterThan(0);
  });

  it("dataUrlAArchivo nombra con la extensión del mime", () => {
    const f = dataUrlAArchivo(PNG, "muestra");
    expect(f.name).toBe("muestra.png");
    expect(f.type).toBe("image/png");
  });

  it("jpeg -> extensión jpg", () => {
    const f = dataUrlAArchivo("data:image/jpeg;base64,/9j/4AAQ", "x");
    expect(f.name).toBe("x.jpg");
    expect(f.type).toBe("image/jpeg");
  });
});
