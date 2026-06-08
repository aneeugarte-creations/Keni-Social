/**
 * Hook de carga de imágenes del editor de placa inline. Reúne las tres fuentes de bitmaps que el
 * render necesita, cada una con su propio efecto (mismo comportamiento que cuando vivían inline en
 * `EditorPlacaInline`):
 *  - `assets`: imágenes del documento (logos, fondos, fotos de muestra) por media id.
 *  - `mapaFotos`: una imagen por `objeto` de hueco (cargada solo cuando cambia el SET de ids, no en
 *    cada tick de arrastre).
 *  - `imgRespaldo`: imagen original (RSS) usada como respaldo del hueco 0 cuando no tiene foto.
 */
import * as React from "react";

import type { Documento } from "@/editor/documento";
import { urlMedia } from "@/lib/api";
import { mediaIdsDe } from "@/lib/placa/docPieza";
import type { FotoCollage } from "@/lib/placa/docPieza";

import { cargarImagen } from "./lib";

export interface ImagenesPlaca {
  /** Imágenes del documento (logos, fondos, fotos de muestra) por media id. */
  assets: Record<string, HTMLImageElement | null>;
  /** Imagen por `objeto` de hueco (media id -> imagen). */
  mapaFotos: Record<string, HTMLImageElement | null>;
  /** Imagen del respaldo (original) para el hueco 0 cuando aún no tiene foto propia. */
  imgRespaldo: HTMLImageElement | null;
}

export function useImagenesPlaca(
  activo: boolean,
  documento: Documento | null,
  fotos: FotoCollage[],
  respaldoHueco0: string,
): ImagenesPlaca {
  // Imágenes del documento (logos, fondos, fotos de muestra de otras capas) por media id.
  const [assets, setAssets] = React.useState<Record<string, HTMLImageElement | null>>({});
  React.useEffect(() => {
    if (!activo || !documento) {
      setAssets({});
      return;
    }
    let vivo = true;
    const ids = mediaIdsDe(documento);
    void Promise.all(
      ids.map((id) => cargarImagen(urlMedia(id)).then((img) => [id, img] as const)),
    ).then((pares) => {
      if (vivo) setAssets(Object.fromEntries(pares));
    });
    return () => {
      vivo = false;
    };
  }, [activo, documento]);

  // Fotos de la pieza POR HUECO (mapa media_id -> imagen). Cargamos cada `objeto` no vacío.
  const idsFotos = React.useMemo(() => {
    const set = new Set<string>();
    for (const f of fotos) if (f.objeto) set.add(f.objeto);
    return [...set];
  }, [fotos]);
  // Clave estable por CONTENIDO del set de ids: el reencuadre crea un `fotos` nuevo en cada tick de
  // arrastre, pero el SET de ids no cambia; así no recargamos las imágenes en cada `pointermove`,
  // solo cuando se asigna/quita una foto (el set cambia).
  const claveFotos = idsFotos.join("|");
  const [mapaFotos, setMapaFotos] = React.useState<Record<string, HTMLImageElement | null>>({});
  React.useEffect(() => {
    let vivo = true;
    const ids = claveFotos ? claveFotos.split("|") : [];
    void Promise.all(
      ids.map((id) => cargarImagen(urlMedia(id)).then((img) => [id, img] as const)),
    ).then((pares) => {
      if (vivo) setMapaFotos(Object.fromEntries(pares));
    });
    return () => {
      vivo = false;
    };
  }, [claveFotos]);

  // Imagen del respaldo (original) para el hueco 0 cuando aún no tiene foto propia.
  const [imgRespaldo, setImgRespaldo] = React.useState<HTMLImageElement | null>(null);
  React.useEffect(() => {
    let vivo = true;
    void cargarImagen(respaldoHueco0 || null).then((img) => {
      if (vivo) setImgRespaldo(img);
    });
    return () => {
      vivo = false;
    };
  }, [respaldoHueco0]);

  return { assets, mapaFotos, imgRespaldo };
}
