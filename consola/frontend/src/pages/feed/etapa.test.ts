import { describe, expect, it } from "vitest";

import type { Publicacion } from "@/types";

import { etapaDePublicacion, META_ETAPA } from "./etapa";

/** Base mínima de una `Publicacion` para variar solo lo relevante a la etapa. */
function pub(overrides: Partial<Publicacion>): Publicacion {
  return {
    id: "p1",
    contenido_id: "c1",
    titulo: "Tema",
    marca: "unotv",
    marca_nombre: "Uno TV",
    red: "x",
    red_nombre: "X",
    contenido: "copy",
    copy_in: "",
    estado: "borrador",
    veredicto: "",
    autor_id: "u1",
    autor_nombre: "Ana",
    enviado_a_revision_en: "",
    revisor_id: "",
    revisor_nombre: "",
    revisado_en: "",
    preparado_en: "",
    id_post_metricool: "",
    tipo_contenido: "",
    imagen_fuente: "",
    foto: "",
    falta_copy: false,
    falta_imagen: false,
    falta_revision: false,
    falta_publicar: false,
    fecha_creacion: "",
    fecha_actualizacion: "",
    fecha_programada: "",
    origen: "equipo",
    imagen: "",
    imagen_url: "",
    evergreen: false,
    ...overrides,
  };
}

describe("etapaDePublicacion · etapa IA derivada", () => {
  it("aún sin copy → generando_copy", () => {
    expect(etapaDePublicacion(pub({ estado: "borrador", falta_copy: true }))).toBe("generando_copy");
  });

  it("con copy pero sin imagen → generando_arte", () => {
    expect(
      etapaDePublicacion(pub({ estado: "borrador", falta_copy: false, falta_imagen: true })),
    ).toBe("generando_arte");
  });

  it("en revisión → lista_para_revisar (gate humano)", () => {
    expect(etapaDePublicacion(pub({ estado: "en_revision" }))).toBe("lista_para_revisar");
  });

  it("aprobado / programado / publicado mapean a sus etapas", () => {
    expect(etapaDePublicacion(pub({ estado: "aprobado" }))).toBe("aprobada");
    expect(etapaDePublicacion(pub({ estado: "programado" }))).toBe("programada");
    expect(etapaDePublicacion(pub({ estado: "publicado" }))).toBe("publicada");
  });

  it("prefiere el campo explícito `etapa_ia` (contrato asumido con Flujo C)", () => {
    // Aunque el estado diría 'generando_copy', un campo explícito manda.
    const conEtapa = { ...pub({ estado: "borrador", falta_copy: true }), etapa_ia: "generando_arte" };
    expect(etapaDePublicacion(conEtapa as Publicacion)).toBe("generando_arte");
  });

  it("ignora un `etapa_ia` desconocido y cae a la derivación", () => {
    const conBasura = { ...pub({ estado: "en_revision" }), etapa_ia: "no_existe" };
    expect(etapaDePublicacion(conBasura as Publicacion)).toBe("lista_para_revisar");
  });

  it("toda etapa derivable tiene metadatos", () => {
    for (const etapa of [
      "generando_copy",
      "generando_arte",
      "lista_para_revisar",
      "aprobada",
      "programada",
      "publicada",
    ] as const) {
      expect(META_ETAPA[etapa]).toBeTruthy();
    }
  });
});
