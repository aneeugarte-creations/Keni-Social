/**
 * Lógica PURA del rediseño "Estrategia de marca": catálogo de pilares, extracto de
 * prosa y las dos rutas de datos —normalizar la respuesta del endpoint nuevo
 * (`GET /api/texto/estrategia`) o construir el MISMO estado desde el listado clásico
 * (`GET /api/texto` + `/validacion`) mientras el backend nuevo se despliega en paralelo.
 *
 * Sin React ni fetch: todo testeable en unitario.
 */
import type { DocumentoTexto, ValidacionEditorial } from "@/types";

import { separarFrontmatter } from "../lib";
import type {
  EstrategiaNormalizada,
  PilarEstrategiaApi,
  PilarNormalizado,
  RespuestaEstrategia,
} from "./tipos";

/** Los 5 pilares, en el ORDEN FIJO del contrato (y de la tarjeta-grid). */
export const CLASES_PILAR = ["marca", "voz", "tropicalizacion", "plataforma", "reglas"] as const;
export type ClasePilar = (typeof CLASES_PILAR)[number];

/** Pilares OBLIGATORIOS de la completitud (los 4 que valida `/api/texto/validacion`). */
export const PILARES_OBLIGATORIOS = ["marca", "voz", "tropicalizacion", "plataforma"] as const;
export const TOTAL_OBLIGATORIOS = PILARES_OBLIGATORIOS.length;

/** Título humano + guía de cada pilar (la cara editorial de la tarjeta). */
export const META_PILAR: Record<ClasePilar, { titulo: string; guia: string }> = {
  marca: {
    titulo: "Identidad de marca",
    guia: "Quién es la marca: misión, audiencia y territorio editorial.",
  },
  voz: {
    titulo: "Voz",
    guia: "Cómo escribe: registro, tono y estilo propios.",
  },
  tropicalizacion: {
    titulo: "Tropicalización MX",
    guia: "Adaptación al español de México: léxico, giros y registro local.",
  },
  plataforma: {
    titulo: "Plataformas",
    guia: "Formato y reglas de juego por red social.",
  },
  reglas: {
    titulo: "Reglas legales",
    guia: "Líneas rojas y obligaciones: lo que nunca se publica.",
  },
};

/** Nombre humano de un pilar (fallback: capitalizar la clase). */
export function tituloPilar(clase: string): string {
  const meta = META_PILAR[clase as ClasePilar];
  if (meta) return meta.titulo;
  return clase ? clase.charAt(0).toUpperCase() + clase.slice(1) : "Documento";
}

/**
 * Primeras líneas de un cuerpo markdown como TEXTO PLANO (para el extracto de la
 * tarjeta): quita el frontmatter, el marcado ligero y colapsa espacios. "" si no
 * queda nada con sustancia.
 */
export function extracto(cuerpo: string | null | undefined, max = 240): string {
  if (!cuerpo) return "";
  const { visible } = separarFrontmatter(cuerpo);
  const plano = visible
    .replace(/^#{1,6}\s+/gm, "") // títulos
    .replace(/^[-*+]\s+/gm, "") // viñetas
    .replace(/^\d+\.\s+/gm, "") // listas numeradas
    .replace(/^>\s?/gm, "") // citas
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1") // enlaces -> texto
    .replace(/[*_`~]+/g, "") // énfasis / código
    .replace(/\{\{\s*([\w.-]+)\s*\}\}/g, "$1") // {{VARIABLES}} -> nombre
    .replace(/\s+/g, " ")
    .trim();
  if (!plano) return "";
  if (plano.length <= max) return plano;
  // Corta en el último espacio antes del tope (sin partir palabras).
  const corte = plano.slice(0, max);
  return `${corte.slice(0, Math.max(corte.lastIndexOf(" "), max - 30))}…`;
}

/** Pilar normalizado "vacío" (sin documento) para una clase. */
function pilarVacio(clase: string): PilarNormalizado {
  return {
    clase,
    titulo: tituloPilar(clase),
    tituloDoc: "",
    docId: null,
    vacio: true,
    global: false,
    publicado: false,
    sinPublicar: false,
    actualizado: "",
    extracto: "",
  };
}

/** Normaliza un item del endpoint nuevo (defensivo: todo opcional). */
function normalizarItem(p: PilarEstrategiaApi): PilarNormalizado {
  const clase = p.clase ?? "";
  return {
    clase,
    titulo: tituloPilar(clase),
    tituloDoc: p.titulo ?? "",
    docId: p.doc_id ?? null,
    vacio: p.vacio ?? !p.doc_id,
    global: p.global ?? false,
    publicado: !!p.produccion,
    sinPublicar: p.sin_publicar ?? false,
    actualizado: p.actualizado ?? "",
    extracto: p.extracto || extracto(p.cuerpo) || p.descripcion || "",
  };
}

/** Completitud normalizada a partir de `{completa, faltan, recomendacion}` parciales. */
function normalizarCompletitud(c?: {
  completa?: boolean;
  faltan?: string[];
  recomendacion?: string;
}): Pick<EstrategiaNormalizada, "completa" | "faltan" | "recomendacion" | "cubiertos" | "total"> {
  const faltan = c?.faltan ?? [];
  const completa = c?.completa ?? faltan.length === 0;
  const cubiertos = completa
    ? TOTAL_OBLIGATORIOS
    : Math.max(0, TOTAL_OBLIGATORIOS - faltan.length);
  return {
    completa,
    faltan,
    recomendacion: c?.recomendacion ?? "",
    cubiertos,
    total: TOTAL_OBLIGATORIOS,
  };
}

/** Etiqueta legible de un doc_id del orden de inyección (lookup en pilares/extras). */
function etiquetaDeDoc(docId: string, conocidos: PilarNormalizado[]): string {
  const p = conocidos.find((x) => x.docId === docId);
  if (p) return p.clase ? p.titulo : p.tituloDoc || p.titulo;
  // Fallback: el último segmento del id ("editorial/rrss/unotv/voz" -> "voz").
  const segmento = docId.split("/").filter(Boolean).pop() ?? docId;
  return segmento.charAt(0).toUpperCase() + segmento.slice(1);
}

/**
 * Normaliza la respuesta del endpoint NUEVO. Garantiza los 5 pilares en el orden fijo
 * aunque el backend mande menos, más o desordenados (lo que sobre cae a extras).
 */
export function normalizar(r: RespuestaEstrategia): EstrategiaNormalizada {
  const recibidos = (r.pilares ?? []).map(normalizarItem);
  const pilares: PilarNormalizado[] = CLASES_PILAR.map(
    (clase) => recibidos.find((p) => p.clase === clase) ?? pilarVacio(clase),
  );
  const sobrantes = recibidos.filter((p) => !CLASES_PILAR.includes(p.clase as ClasePilar));
  const extras = [...sobrantes, ...(r.extras ?? []).map(normalizarItem)];
  const conocidos = [...pilares, ...extras];
  return {
    ...normalizarCompletitud(r.completitud),
    pilares,
    extras,
    orden: (r.orden_inyeccion ?? []).map((docId) => ({
      docId,
      etiqueta: etiquetaDeDoc(docId, conocidos),
    })),
  };
}

/** Orden de una clase dentro del ensamblaje (los pilares antes que el resto). */
function ordenClase(clase: string): number {
  const i = CLASES_PILAR.indexOf(clase as ClasePilar);
  return i === -1 ? CLASES_PILAR.length : i;
}

/** ¿El doc es una capa GLOBAL (compartida entre marcas)? Mismo criterio que el backend. */
function esGlobal(d: DocumentoTexto): boolean {
  if ((d.marcas ?? []).length === 0) return true;
  const segmentos = (d.carpeta || "").split("/");
  return segmentos.some((s) => ["global", "comun", "general", "todas"].includes(s));
}

/**
 * FALLBACK: construye el mismo estado desde el listado clásico
 * (`GET /api/texto?marca=&tipo=editorial`) + el diagnóstico (`GET /api/texto/validacion`),
 * para que la vista funcione mientras `GET /api/texto/estrategia` no exista.
 */
export function desdeFallback(
  documentos: DocumentoTexto[],
  validacion?: ValidacionEditorial,
): EstrategiaNormalizada {
  const editoriales = documentos.filter((d) => d.tipo === "editorial");
  const activos = editoriales.filter((d) => (d.estado ?? "activo") === "activo");

  const usados = new Set<string>();
  const pilares: PilarNormalizado[] = CLASES_PILAR.map((clase) => {
    // Candidato por clase: activos primero, marca-específico antes que global.
    const candidatos = [...editoriales]
      .filter((d) => d.clase === clase)
      .sort(
        (a, b) =>
          Number((b.estado ?? "activo") === "activo") - Number((a.estado ?? "activo") === "activo") ||
          Number(esGlobal(a)) - Number(esGlobal(b)) ||
          (a.prioridad ?? 0) - (b.prioridad ?? 0) ||
          a.id.localeCompare(b.id),
      );
    const doc = candidatos[0];
    if (!doc) return pilarVacio(clase);
    usados.add(doc.id);
    const cuerpo = extracto(doc.cuerpo);
    return {
      clase,
      titulo: tituloPilar(clase),
      tituloDoc: doc.titulo,
      docId: doc.id,
      // El diagnóstico del backend manda; sin él, vacío = sin prosa con sustancia.
      vacio: validacion?.pilares?.[clase] === false || !cuerpo,
      global: esGlobal(doc),
      publicado: !!doc.produccion,
      sinPublicar: doc.sin_publicar ?? false,
      actualizado: doc.actualizado ?? "",
      extracto: cuerpo || doc.descripcion || "",
    };
  });

  const extras: PilarNormalizado[] = editoriales
    .filter((d) => !usados.has(d.id))
    .map((d) => ({
      clase: d.clase ?? "",
      titulo: d.titulo,
      tituloDoc: d.titulo,
      docId: d.id,
      vacio: !extracto(d.cuerpo),
      global: esGlobal(d),
      publicado: !!d.produccion,
      sinPublicar: d.sin_publicar ?? false,
      actualizado: d.actualizado ?? "",
      extracto: extracto(d.cuerpo) || d.descripcion || "",
    }));

  // Orden de inyección aproximado al del backend (`editoriales_de_marca`):
  // prioridad (menor antes), luego pilar, luego id. Solo docs ACTIVOS (los que inyectan).
  const conocidos = [...pilares, ...extras];
  const orden = [...activos]
    .sort(
      (a, b) =>
        (a.prioridad ?? 0) - (b.prioridad ?? 0) ||
        ordenClase(a.clase) - ordenClase(b.clase) ||
        a.id.localeCompare(b.id),
    )
    .map((d) => ({ docId: d.id, etiqueta: etiquetaDeDoc(d.id, conocidos) }));

  // Sin diagnóstico del backend: deriva la completitud de los pilares obligatorios vacíos.
  const completitud = validacion ?? {
    faltan: PILARES_OBLIGATORIOS.filter(
      (clase) => pilares.find((p) => p.clase === clase)?.vacio ?? true,
    ),
  };
  return { ...normalizarCompletitud(completitud), pilares, extras, orden };
}
