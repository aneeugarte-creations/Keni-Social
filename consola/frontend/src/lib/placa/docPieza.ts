/**
 * Aplicar un DOCUMENTO de plantilla del estudio a UNA pieza, en el cliente (espejo de
 * `dominio.estudio_imagen.componer_desde_plantilla` + `documento.capa_foto`).
 *
 * El editor de la pieza renderiza la plantilla EN VIVO con el mismo motor que el servidor
 * (`dibujarDocumento`): mete la foto de la pieza en el HUECO DE FOTO, aplica su reencuadre y
 * vincula el copy-in al titular. Aquí van las funciones PURAS (sin DOM) que preparan el documento
 * y localizan sus capas clave; la carga de imágenes y el render viven en el componente.
 */
import type { Capa, CapaImagen, CapaTexto, Documento } from "@/editor/documento";

import type { EncuadreFoto } from "./encuadre";

/** Recorre todas las capas (incluidas las de grupos) en profundidad. */
function* todasLasCapas(capas: Capa[]): Generator<Capa> {
  for (const c of capas) {
    yield c;
    if (c.tipo === "grupo") yield* todasLasCapas(c.capas);
  }
}

/**
 * Capa que es el HUECO DE FOTO del documento, o null si la plantilla no lleva foto. Mirror del
 * backend `documento.capa_foto`: preferencia `es_foto`; respaldo (plantillas legadas) = imagen a
 * sangre que cubra ≥60% del lienzo; nunca un logo pequeño.
 */
export function capaFotoDoc(doc: Documento): CapaImagen | null {
  const imagenes = doc.capas.filter((c): c is CapaImagen => c.tipo === "imagen");
  const marcada = imagenes.find((c) => c.es_foto);
  if (marcada) return marcada;
  const areaLienzo = doc.formato.w * doc.formato.h;
  if (areaLienzo <= 0) return null;
  const grandes = imagenes.filter((c) => c.w * c.h >= 0.6 * areaLienzo);
  if (!grandes.length) return null;
  return grandes.reduce((a, b) => (a.w * a.h >= b.w * b.h ? a : b));
}

/**
 * TODAS las capas que son HUECO DE FOTO (`es_foto`), en ORDEN de `capas`. Mirror del backend
 * `documento.capas_foto`: un COLLAGE declara N huecos (2..12); el orden es el contrato con el
 * almacén de fotos por hueco de la pieza (`fotos[i]` va al hueco i). Sin marcas, cae al respaldo
 * legado de `capaFotoDoc` (una sola): lista de 0 o 1.
 */
export function capasFotoDoc(doc: Documento): CapaImagen[] {
  const marcadas = doc.capas.filter((c): c is CapaImagen => c.tipo === "imagen" && !!c.es_foto);
  if (marcadas.length) return marcadas;
  const una = capaFotoDoc(doc);
  return una ? [una] : [];
}

/** Una foto del collage por hueco: media id + reencuadre (foco/zoom). Espejo del JSON `fotos`. */
export interface FotoCollage {
  objeto: string;
  foco: [number, number] | null;
  zoom: number;
}

/** Capa de texto del TITULAR (binding copy_in), o null. Para la edición in place. */
export function capaTitularDoc(doc: Documento): CapaTexto | null {
  for (const c of todasLasCapas(doc.capas)) {
    if (c.tipo === "texto" && c.binding === "copy_in") return c;
  }
  return null;
}

/** Ids de media referenciados por el documento (objetos de imagen, logos, fondo). Sin "" ni repes. */
export function mediaIdsDe(doc: Documento): string[] {
  const ids = new Set<string>();
  if (doc.fondo?.tipo === "imagen" && doc.fondo.imagen?.media_id) ids.add(doc.fondo.imagen.media_id);
  for (const c of todasLasCapas(doc.capas)) {
    if (c.tipo === "imagen" && c.objeto) ids.add(c.objeto);
    else if (c.tipo === "logo" && c.tipo_logo === "imagen" && c.media_id) ids.add(c.media_id);
  }
  return [...ids];
}

/**
 * Prepara una copia del documento para ESTA pieza: mete UNA foto por HUECO (collage), con su
 * reencuadre (foco/zoom). No muta el original. `fotos[i]` va al hueco i (orden de `capas`); los
 * huecos sin foto quedan vacíos (placeholder). Devuelve el documento listo para `dibujarDocumento`.
 */
export function prepararDocumento(
  doc: Documento,
  opts: { fotos: FotoCollage[] } | { foto: string; encuadre: EncuadreFoto | null },
): Documento {
  // Acepta el collage (`fotos`) o la foto única legada (`foto`+`encuadre` = hueco 0).
  const fotos: FotoCollage[] =
    "fotos" in opts
      ? opts.fotos
      : [{ objeto: opts.foto || "", foco: opts.encuadre?.foco ?? null, zoom: opts.encuadre?.zoom ?? 0 }];
  const copia: Documento = structuredClone(doc);
  capasFotoDoc(copia).forEach((hueco, i) => {
    const spec = fotos[i];
    if (!spec) return;
    hueco.objeto = spec.objeto || "";
    // Un hueco RELLENO debe verse. Las plantillas suelen traer el hueco de foto OCULTO
    // (`visible:false`) para no enseñar un placeholder gris en el diseño; al meterle la foto de la
    // pieza hay que MOSTRARLO o el render no-final (editor de pieza, `dibujarDocumento` sin
    // `final`) lo saltaría y la pieza saldría sin foto en el lienzo.
    if (hueco.objeto) hueco.visible = true;
    if (spec.foco) hueco.foco = [spec.foco[0], spec.foco[1]];
    if (spec.zoom && spec.zoom > 0) hueco.zoom = spec.zoom;
  });
  return copia;
}
