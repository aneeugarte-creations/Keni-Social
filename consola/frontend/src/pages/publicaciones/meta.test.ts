import { describe, expect, it } from "vitest";

import { metaRevision } from "./meta";

describe("metaRevision (revision de publicación = texto libre)", () => {
  it("devuelve null si el revision está vacío", () => {
    expect(metaRevision("")).toBeNull();
  });

  it("mapea los tres revisiones canónicos del enum histórico", () => {
    expect(metaRevision("listo")).toEqual({ nombre: "Listo", variante: "ok" });
    expect(metaRevision("revisar")).toEqual({ nombre: "Revisar", variante: "aviso" });
    expect(metaRevision("no_publicar")).toEqual({ nombre: "No publicar", variante: "error" });
  });

  it("acepta TEXTO LIBRE del auto-verificador y deriva la variante por prefijo", () => {
    // Estos valores rompían el contrato cuando `revision` era un enum cerrado.
    expect(metaRevision("ok")).toEqual({ nombre: "ok", variante: "ok" });
    expect(metaRevision("ok — confirmar marcador con el equipo")).toEqual({
      nombre: "ok — confirmar marcador con el equipo",
      variante: "ok",
    });
    expect(
      metaRevision("marcar claramente como rumor/filtración — no confirmar"),
    ).toEqual({
      nombre: "marcar claramente como rumor/filtración — no confirmar",
      variante: "aviso",
    });
    expect(metaRevision("pendiente resultado real del partido")).toEqual({
      nombre: "pendiente resultado real del partido",
      variante: "aviso",
    });
  });

  it("trata 'no publicar' (con espacio o guion bajo) como error", () => {
    expect(metaRevision("no publicar")?.variante).toBe("error");
    expect(metaRevision("No Publicar: contiene un dato sin confirmar")?.variante).toBe(
      "error",
    );
  });

  it("conserva el texto íntegro como nombre (la UI lo recorta/tooltipea)", () => {
    const largo = "ok — cifras deben verificarse con el área de impacto antes de publicar";
    expect(metaRevision(largo)?.nombre).toBe(largo);
  });
});
