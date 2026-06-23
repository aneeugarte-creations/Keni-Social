/**
 * ETAPA de la cadena IA de una pieza, para el Feed de ideación (Flujo D, Fase 4).
 *
 * La visión de la "red social interna" pide ver el estado de la IA EN VIVO por pieza:
 * "generando copy → generando arte → lista para revisar → programada". Hoy NO existe un
 * endpoint dedicado de estado-por-etapa: lo PROVEERÁ el Flujo C (Orquestación, Fase 2),
 * que encadena los daemons con "estado visible por pieza" (ver plan §Fase 2).
 *
 * Mientras tanto, DERIVAMOS la etapa de lo que ya trae cada `Pieza`:
 *  - `estado` (borrador/en_revision/programado/publicado), y
 *  - la checklist `falta_copy` / `falta_imagen` / `falta_revision`.
 *
 * CABLEADO CON C (follow-up #3, ya en producción):
 *  El backend (Flujo C) YA expone la etapa real por pieza en `Pieza.etapa_ia`,
 *  derivada por `pipeline_estado.etapa_de_pieza` (misma lógica que la derivación de abajo,
 *  pero como FUENTE ÚNICA en servidor). `etapaDePieza` la PREFIERE cuando viene; la
 *  derivación en cliente queda solo como DEGRADACIÓN para piezas legadas/parciales que aún
 *  no la traigan. La forma de salida (`EtapaIa`) es el contrato del feed.
 */
import { parsearCarrusel } from "@/lib/carrusel";
import { contieneHashtag } from "@/pages/piezas/hashtags";
import type { Pieza } from "@/types";

/** Las etapas observables de la pipeline IA, en orden. Una pieza COMPLETA (copy + arte) está
 *  "lista para revisar" en cuanto tiene todo su contenido: el pipeline la mueve sola a la cola
 *  de revisión (etapa de avance incondicional), así que «borrador» no es un estado donde
 *  descanse — no hay etapa intermedia que mostrar. */
export type EtapaIa =
  | "generando_copy"
  | "generando_arte"
  | "faltan_fotos"
  | "falta_copy_in"
  | "falta_hashtags"
  | "falta_hashtag_editorial"
  | "lista_para_revisar"
  | "programada"
  | "publicada";

export interface MetaEtapa {
  /** Etiqueta humana corta (badge). */
  etiqueta: string;
  /** `true` mientras la IA aún trabaja la pieza (badge con spinner/pulso). */
  enCurso: boolean;
}

// GÉNERO deliberado: las etiquetas van en FEMENINO («Programada/Publicada») porque la
// unidad del feed es «la pieza». NO «corregirlas» hacia el masculino de `META_ESTADOS` (que
// califica a «el estado»): la divergencia es intencional, no un typo.
export const META_ETAPA: Record<EtapaIa, MetaEtapa> = {
  generando_copy: { etiqueta: "Generando copy", enCurso: true },
  // "Generando arte" = en realidad la pieza LLEVA imagen pero le falta la FOTO real (la IA solo
  // hace la plantilla; la foto la sube una persona en "Editar"). El label lo dice claro.
  // Ola F: para piezas video este estado significa "Falta video"; la etiqueta dinámica
  // la calcula `etiquetaEtapa` a partir del formato; aquí "Falta imagen" es el fallback foto.
  generando_arte: { etiqueta: "Falta imagen", enCurso: true },
  // CARRUSEL con portada pero algún slide de SOLO TEXTO: el equipo debe poner una foto a cada
  // tarjeta. Es acción humana (no IA), por eso sin pulso.
  faltan_fotos: { etiqueta: "Faltan fotos", enCurso: false },
  // Acciones del EQUIPO en la fase de revisión (no es la IA trabajando): el texto sobre la
  // imagen (placa) y los hashtags (clave para campañas/líneas). `enCurso:false` = sin pulso.
  falta_copy_in: { etiqueta: "Falta copy-in", enCurso: false },
  falta_hashtags: { etiqueta: "Faltan hashtags", enCurso: false },
  // Tiene hashtags pero NO el de su LÍNEA editorial (obligatorio para el desglose por sección):
  // el feed lo pide aparte y la sugerencia del editor lo ofrece en rojo.
  falta_hashtag_editorial: { etiqueta: "Falta hashtag editorial", enCurso: false },
  // "Para revisar" (no "Lista"): no colisiona con la pestaña "Lista" del hub y dice la acción.
  lista_para_revisar: { etiqueta: "Para revisar", enCurso: false },
  programada: { etiqueta: "Programada", enCurso: false },
  publicada: { etiqueta: "Publicada", enCurso: false },
};

/**
 * Etiqueta dinámica de la etapa, teniendo en cuenta el formato de la pieza (Ola F).
 * Para piezas video, "generando_arte" significa "Falta video" en vez de "Falta imagen";
 * para carruseles, lo que falta es la PORTADA (los slides extra ya vienen en crudo).
 */
export function etiquetaEtapa(etapa: EtapaIa, formato?: string): string {
  const fmt = (formato ?? "").trim().toLowerCase();
  if (etapa === "generando_arte" && fmt === "video") {
    return "Falta video";
  }
  if (etapa === "generando_arte" && fmt === "carrusel") {
    return "Falta portada";
  }
  return META_ETAPA[etapa].etiqueta;
}

// Un hashtag en el caption: '#' + letras/dígitos/_ (incluye acentos con la flag `u`). ESPEJO de
// `campanias._PAT_HASHTAG` del backend; aquí solo nos interesa SI hay alguno.
const PAT_HASHTAG = /#[\p{L}\p{N}_]+/u;

/** ¿El texto lleva al menos un hashtag? Fuente única del check (lo usan el feed y la
 *  sugerencia de hashtags del editor). ESPEJO de `_falta_hashtags` del backend. */
export function textoTieneHashtags(texto: string | null | undefined): boolean {
  return PAT_HASHTAG.test(texto ?? "");
}

/** ¿Falta el TEXTO sobre la imagen (placa, `copy_in`)? Solo en piezas de MARCA con placa
 *  (foto/carrusel), no exentas ni con placa oculta. ESPEJO de `_falta_copy_in` del backend. */
function faltaCopyIn(p: Pieza): boolean {
  if (!p.marca) return false;
  const fmt = (p.formato ?? "").trim().toLowerCase();
  if (fmt !== "foto" && fmt !== "carrusel") return false;
  if (p.copy_in_exento || (p as { placa_oculta?: boolean }).placa_oculta) return false;
  return !p.copy_in?.trim();
}

/** ¿El copy no lleva ningún hashtag? Clave para monitorizar campañas y líneas de contenido. */
function faltaHashtags(p: Pieza): boolean {
  return !textoTieneHashtags(p.contenido);
}

/** ¿El copy lleva hashtags pero NO el de su LÍNEA editorial (`hashtags_linea`)? El de la sección
 *  es obligatorio (desglose de métricas por línea). Solo aplica con ALGÚN hashtag ya puesto (si no
 *  hay ninguno manda `faltaHashtags`). ESPEJO de `_falta_hashtag_editorial` del backend. */
function faltaHashtagEditorial(p: Pieza): boolean {
  if (!textoTieneHashtags(p.contenido)) return false;
  const linea = p.hashtags_linea ?? [];
  if (linea.length === 0) return false;
  const contenido = p.contenido ?? "";
  return !linea.some((t) => contieneHashtag(contenido, t));
}

/** CARRUSEL con portada pero algún SLIDE sin foto real (placa de solo texto, horneada en `artes/`).
 *  ESPEJO de `dominio.piezas._carrusel_falta_foto`. La media cruda (`fotos/`, vídeo) sí cuenta. */
function faltanFotosEnSlides(p: Pieza): boolean {
  if ((p as { variante?: string }).variante !== "carrusel") return false;
  const slides = parsearCarrusel((p as { carrusel?: string }).carrusel);
  return slides.some((s) => {
    if (s.tipo === "video") return !s.objeto?.trim();
    const objeto = (s.objeto ?? "").trim();
    const esPlacaHorneada = objeto.startsWith("artes/");
    return !(s.foto?.trim() || (objeto !== "" && !esPlacaHorneada));
  });
}

/**
 * Deriva la etapa IA de una pieza a partir de su estado + checklist. «Revisión» NO se enseña
 * como tal (es interno): mientras la pieza no esté programada/publicada, la etapa
 * muestra la PRIMERA ACCIÓN PENDIENTE, también en revisión.
 *
 * Reglas (de "más avanzado" a "menos"):
 *  - `publicado` / `programado` → etapa terminal
 *  - falta copy                → generando_copy ("Falta copy")
 *  - falta la FOTO real (o el vídeo) → generando_arte ("Falta imagen"/"Falta video")
 *  - sin hashtags               → falta_hashtags ("Faltan hashtags")
 *  - EN REVISIÓN, falta la placa → falta_copy_in ("Falta copy-in")
 *  - nada pendiente             → lista_para_revisar (te toca el like/dislike)
 *
 * GATEA el avance: producción (copy + foto + HASHTAGS) — los hashtags se exigen SIEMPRE, igual que
 * copy/foto (no sale nada sin hashtag). La placa (`copy_in`) es acción de revisión y NO gatea.
 *
 * IMAGEN vs PLANTILLA: la placa (`imagen`) es solo la PLANTILLA, no cuenta como imagen real;
 * necesita FOTO real (`foto`, o imagen bespoke sin marca). La imagen del ARTÍCULO de origen
 * (`imagen_fuente`) es solo una URL de referencia, NO una foto inyectada: una pieza sin `foto`
 * propia sigue en "Falta imagen" aunque traiga `imagen_fuente`.
 *
 * El backend (Flujo C) trae la etapa real en `p.etapa_ia`; `etapaDePieza` la PREFIERE
 * cuando llega y es una etapa conocida. Esta derivación queda como degradación (piezas
 * legadas/parciales que no la traigan).
 */
export function etapaDePieza(p: Pieza): EtapaIa {
  return etapaBruta(p);
}

/** Etapa sin normalizar: la explícita del backend si llega, o la derivación local. */
function etapaBruta(p: Pieza): EtapaIa {
  // Etapa REAL de la pipeline (Flujo C, `pipeline_estado.etapa_de_pieza`): si llega y es una
  // etapa conocida, manda sobre la derivación local. El backend la sirve hoy en
  // `Pieza.etapa_ia`; el guard cubre respuestas legadas/parciales que la omitan.
  const explicita = (p as { etapa_ia?: string }).etapa_ia;
  if (explicita && explicita in META_ETAPA) return explicita as EtapaIa;

  if (p.estado === "publicado") return "publicada";
  if (p.estado === "programado") return "programada";
  // ESPEJO del backend. Solo "generando_copy" si DE VERDAD falta el copy.
  if (!p.contenido?.trim()) return "generando_copy";
  // Ola F: las piezas VIDEO necesitan el asset de video (no una foto).
  // Las piezas FOTO necesitan una foto real (foto cruda, imagen de fuente o imagen subida bespoke).
  const esVideo = (p.formato ?? "").trim().toLowerCase() === "video";
  if (esVideo) {
    // falta_video es la checklist de video: si falta, la pieza no está lista.
    const hayVideo = !p.falta_video || !!(p as { video?: string }).video;
    if (!hayVideo) return "generando_arte";
  } else {
    // Foto: la foto cruda propia (`foto`) o —solo en piezas SIN marca— la imagen bespoke
    // (`imagen`). La imagen del artículo de origen (`imagen_fuente`) NO cuenta: es una URL de
    // referencia, no la foto inyectada en la pieza. Una foto de STOCK no autorizada TAMPOCO cuenta
    // como imagen real: es ayuda visual no publicable hasta que un humano confirme derechos.
    const hayImagenReal =
      (!!p.foto || (!p.marca && !!p.imagen)) &&
      !(p.imagen_origen === "stock" && !p.imagen_autorizada);
    if (!hayImagenReal) return "generando_arte";
  }
  // Carrusel con portada pero slides de solo texto: faltan las fotos de las tarjetas.
  if (faltanFotosEnSlides(p)) return "faltan_fotos";
  // Hashtags: GATEA el avance igual que copy/foto (no sale nada sin hashtag). Se evalúa SIEMPRE.
  if (faltaHashtags(p)) return "falta_hashtags";
  // Tiene hashtags pero falta el de su LÍNEA editorial (obligatorio): etapa propia, gatea igual.
  if (faltaHashtagEditorial(p)) return "falta_hashtag_editorial";
  // Placa (`copy_in`): acción del equipo en revisión; solo se pide ahí y NO gatea el avance.
  if (p.estado === "en_revision" && faltaCopyIn(p)) return "falta_copy_in";
  return "lista_para_revisar";
}
