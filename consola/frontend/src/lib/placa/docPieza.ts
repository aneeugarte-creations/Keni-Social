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
 * Prepara una copia del documento para ESTA pieza: mete `foto` en el hueco y, si hay `encuadre`,
 * pisa su foco/zoom (reencuadre manual). No muta el original. Si la plantilla no tiene hueco
 * (solo texto/gráfica), la foto no entra. Devuelve el documento listo para `dibujarDocumento`.
 */
export function prepararDocumento(
  doc: Documento,
  opts: { foto: string; encuadre: EncuadreFoto | null },
): Documento {
  const copia: Documento = structuredClone(doc);
  const hueco = capaFotoDoc(copia);
  if (hueco) {
    hueco.objeto = opts.foto || "";
    if (opts.encuadre) {
      hueco.foco = [opts.encuadre.foco[0], opts.encuadre.foco[1]];
      hueco.zoom = opts.encuadre.zoom;
    }
  }
  return copia;
}
