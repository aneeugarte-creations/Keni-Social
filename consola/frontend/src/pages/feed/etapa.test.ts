import { describe, expect, it } from "vitest";

import type { Pieza } from "@/types";

import { etapaDePieza, META_ETAPA } from "./etapa";

/**
 * Base mínima de una `Pieza` para variar solo lo relevante a la etapa.
 *
 * El backend YA sirve `etapa_ia` (Flujo C). Para probar la DERIVACIÓN local (el camino
 * de degradación) la limpiamos con `etapa_ia: undefined` en esos casos; para probar la
 * PREFERENCIA, se pasa un `etapa_ia` explícito en el override.
 */
function pub(overrides: Partial<Pieza>): Pieza {
  return {
    id: "p1",
    publicacion_id: "c1",
    pipeline_id: "",
    titulo: "Tema",
    marca: "unotv",
    marca_nombre: "Uno TV",
    red: "x",
    red_nombre: "X",
    contenido: "copy",
    copy_in: "",
    hashtags_sugeridos: [],
    falta_hashtags: false,
    estado: "borrador",
    revision: "",
    autor_id: "u1",
    autor_nombre: "Ana",
    responsable_id: "",
    responsable_nombre: "",
    enviado_a_revision_en: "",
    revisor_id: "",
    revisor_nombre: "",
    revisado_en: "",
    preparado_en: "",
    id_post_metricool: "",
    tipo_contenido: "",
    formato: "foto",
    espejo: true,
    imagen_fuente: "",
    foto: "",
    falta_copy: false,
    falta_imagen: false,
    falta_revision: false,
    falta_publicar: false,
    falta_video: false,
    video: "",
    fecha_creacion: "",
    fecha_actualizacion: "",
    fecha_programada: "",
    fecha_fuente: "",
    fuente_original: "",
    origen: "equipo",
    categoria: "",
    imagen: "",
    imagen_url: "",
    evergreen: false,
    // Real del backend (Flujo C). Coherente con el `estado: borrador, falta_copy:false,
    // falta_imagen:false` por defecto -> lista para revisar; los tests de DERIVACIÓN lo
    // sobrescriben con `undefined` para forzar el camino de degradación.
    etapa_ia: "lista_para_revisar",
    ...overrides,
  };
}

describe("etapaDePieza · etapa IA derivada (degradación, sin `etapa_ia`)", () => {
  // `etapa_ia: undefined` fuerza el camino de derivación local (pieza legada/parcial).
  it("aún sin copy → generando_copy", () => {
    expect(
      etapaDePieza(pub({ estado: "borrador", contenido: "", etapa_ia: undefined })),
    ).toBe("generando_copy");
  });

  it("lleva imagen (copy-in) pero sin foto real → generando_arte (falta imagen)", () => {
    expect(
      etapaDePieza(
        pub({ estado: "borrador", contenido: "copy", copy_in: "TITULAR", foto: "", etapa_ia: undefined }),
      ),
    ).toBe("generando_arte");
  });

  it("sin foto NO está lista, aunque no lleve copy-in → generando_arte (falta imagen)", () => {
    expect(
      etapaDePieza(
        pub({ estado: "borrador", contenido: "copy", copy_in: "", foto: "", imagen: "", etapa_ia: undefined }),
      ),
    ).toBe("generando_arte");
  });

  it("la imagen del ARTÍCULO de origen (imagen_fuente) NO cuenta como foto real → generando_arte", () => {
    // Pieza de marca con la imagen de la nota original pero sin foto propia inyectada: sigue
    // en "Falta imagen" (la URL de la nota es referencia, no la foto de la pieza).
    expect(
      etapaDePieza(
        pub({ estado: "en_revision", contenido: "copy #x", copy_in: "TITULAR", foto: "", imagen_fuente: "https://nota.test/o.jpg", etapa_ia: undefined }),
      ),
    ).toBe("generando_arte");
  });

  it("pieza SIN marca con imagen subida (bespoke), completa → lista_para_revisar", () => {
    // Completa de verdad (copy + imagen propia): el pipeline la mueve sola a la cola de
    // revisión, así que el feed la pinta directa como "Para revisar" (sin etapa intermedia).
    expect(
      etapaDePieza(
        pub({ estado: "borrador", marca: "", contenido: "copy", copy_in: "", foto: "", imagen: "subida.png", etapa_ia: undefined }),
      ),
    ).toBe("lista_para_revisar");
  });

  it("completa (copy + foto real) aún en borrador → lista_para_revisar (avance incondicional)", () => {
    expect(
      etapaDePieza(
        pub({ estado: "borrador", contenido: "copy", copy_in: "TITULAR", foto: "bg.png", etapa_ia: undefined }),
      ),
    ).toBe("lista_para_revisar");
  });

  it("en revisión COMPLETA (copy+foto+placa+hashtags) → lista_para_revisar (te toca el OK)", () => {
    expect(
      etapaDePieza(
        pub({ estado: "en_revision", contenido: "copy #Mundial2026", copy_in: "TITULAR", foto: "bg.png", etapa_ia: undefined }),
      ),
    ).toBe("lista_para_revisar");
  });

  it("en revisión enseña la acción pendiente (revisión es interno): sin foto / sin placa / sin hashtags", () => {
    // Sin foto real: "Falta imagen" aunque ya esté en revisión (antes cortocircuitaba a lista).
    expect(
      etapaDePieza(pub({ estado: "en_revision", contenido: "copy #x", copy_in: "TITULAR", foto: "", etapa_ia: undefined })),
    ).toBe("generando_arte");
    // Con foto pero sin el texto en la imagen (placa, marca): "Falta copy-in".
    expect(
      etapaDePieza(pub({ estado: "en_revision", contenido: "copy #x", copy_in: "", foto: "bg.png", etapa_ia: undefined })),
    ).toBe("falta_copy_in");
    // Completa pero sin hashtags: "Faltan hashtags" (clave para campañas/líneas).
    expect(
      etapaDePieza(pub({ estado: "en_revision", contenido: "copy sin tags", copy_in: "TITULAR", foto: "bg.png", etapa_ia: undefined })),
    ).toBe("falta_hashtags");
  });

  it("placa y hashtags NO bloquean en borrador (acciones de la fase de revisión)", () => {
    // Borrador con copy+foto pero sin placa ni hashtags: sigue "lista" (el avance la mueve y se
    // piden ya en revisión); no se sacan como pendientes antes de la cola.
    expect(
      etapaDePieza(pub({ estado: "borrador", contenido: "copy sin tags", copy_in: "", foto: "bg.png", etapa_ia: undefined })),
    ).toBe("lista_para_revisar");
  });

  it("respeta el `etapa_ia` explícito 'lista_para_revisar' tanto en borrador como en revisión", () => {
    // «borrador» no es un estado donde descanse una pieza completa: el pipeline la avanza sola,
    // así que "Para revisar" es honesto desde que tiene todo el contenido (sin etapa intermedia).
    expect(
      etapaDePieza(pub({ estado: "borrador", etapa_ia: "lista_para_revisar" })),
    ).toBe("lista_para_revisar");
    expect(
      etapaDePieza(pub({ estado: "en_revision", etapa_ia: "lista_para_revisar" })),
    ).toBe("lista_para_revisar");
  });

  it("programado / publicado mapean a sus etapas (ya no hay etapa 'aprobada')", () => {
    expect(etapaDePieza(pub({ estado: "programado", etapa_ia: undefined }))).toBe("programada");
    expect(etapaDePieza(pub({ estado: "publicado", etapa_ia: undefined }))).toBe("publicada");
  });

  it("prefiere el `etapa_ia` REAL del backend (Flujo C) sobre la derivación", () => {
    // Aunque el estado diría 'generando_copy', el campo real del backend manda.
    const conEtapa = pub({ estado: "borrador", falta_copy: true, etapa_ia: "generando_arte" });
    expect(etapaDePieza(conEtapa)).toBe("generando_arte");
  });

  it("ignora un `etapa_ia` desconocido y cae a la derivación", () => {
    // Pieza COMPLETA en revisión con un `etapa_ia` basura: cae a la derivación local → lista.
    const conBasura = {
      ...pub({ estado: "en_revision", contenido: "copy #x", copy_in: "TITULAR", foto: "bg.png" }),
      etapa_ia: "no_existe",
    };
    expect(etapaDePieza(conBasura as unknown as Pieza)).toBe("lista_para_revisar");
  });

  it("toda etapa derivable tiene metadatos", () => {
    for (const etapa of [
      "generando_copy",
      "generando_arte",
      "falta_copy_in",
      "falta_hashtags",
      "lista_para_revisar",
      "programada",
      "publicada",
    ] as const) {
      expect(META_ETAPA[etapa]).toBeTruthy();
    }
  });
});
