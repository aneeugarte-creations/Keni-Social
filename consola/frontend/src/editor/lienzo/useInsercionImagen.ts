// Inserción de IMÁGENES en el lienzo (portapapeles, arrastre del escritorio y activos de la
// galería), extraída como hook. Owns la subida + inserción centrada respetando aspect-ratio, el
// `onDrop` (activo interno o ficheros del SO) y el efecto de PEGADO del portapapeles. El componente
// le pasa el store/documento/escala, el contenedor de scroll y la API del lienzo (centro del
// viewport para el pegado) y monta el `onDrop` devuelto.

import type { DragEvent as DragEventReact, RefObject } from "react";
import { useEffect } from "react";
import { toast } from "sonner";

import { api, urlMedia } from "@/lib/api";

import type { Documento } from "../documento";
import { nuevaCapaImagen, nuevaCapaLogo, zTope } from "../documento";
import type { StoreEditor } from "../store";
import { leerDimensionesUrl } from "../useImagen";
import type { LienzoApi } from "./useAtajosTeclado";

// Lee las dimensiones naturales (px) de un fichero de imagen sin subirlo, para respetar su
// aspect-ratio al insertarlo. Tolerante: devuelve `null` si el navegador no puede decodificarlo.
async function leerDimensiones(archivo: File): Promise<{ w: number; h: number } | null> {
  const url = URL.createObjectURL(archivo);
  try {
    return await leerDimensionesUrl(url);
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function useInsercionImagen({
  store,
  documento,
  escala,
  w,
  h,
  scrollRef,
  lienzoApi,
}: {
  store: StoreEditor;
  documento: Documento;
  escala: number;
  w: number;
  h: number;
  scrollRef: RefObject<HTMLDivElement | null>;
  lienzoApi: RefObject<LienzoApi>;
}) {
  // Sube un fichero de imagen (portapapeles del SO o arrastre del escritorio) reutilizando el mismo
  // cliente de media del editor y lo inserta como capa imagen centrada en `centro` (coords del
  // documento). Toast de progreso/éxito/error. Respeta el aspect-ratio real de la imagen.
  const subirEInsertarImagen = async (archivo: File, centro: { x: number; y: number }) => {
    const tid = toast.loading("Subiendo imagen…");
    try {
      const [media, dims] = await Promise.all([
        api.subirMedia(archivo, "plantillas"),
        leerDimensiones(archivo),
      ]);
      const cw = Math.round(documento.formato.w * 0.4);
      const ch = dims && dims.w > 0 ? Math.round((cw * dims.h) / dims.w) : cw;
      const st = store.getState();
      const z = zTope(st.documento);
      st.agregar(
        nuevaCapaImagen(media.id, {
          x: Math.round(centro.x - cw / 2),
          y: Math.round(centro.y - ch / 2),
          w: cw,
          h: ch,
          z,
        }),
      );
      // Estado FRESCO tras agregar (el set del store reemplaza `documento`; `st` quedó obsoleto).
      const nuevas = store.getState().documento.capas;
      st.seleccionar(nuevas[nuevas.length - 1]?.id ?? null);
      toast.success("Imagen añadida al lienzo.", { id: tid });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo subir la imagen.", { id: tid });
    }
  };

  // Inserta un activo de la galería (ya subido) como capa imagen centrada en `centro` (coords del
  // documento), adoptando el ASPECT-RATIO natural de la foto (estilo Canva): caja == foto, sin
  // letterbox ni recorte sorpresa, y el marco de selección la abraza exacto. Las dimensiones se
  // leen del propio media (normalmente ya cacheado por la miniatura de la galería); si el
  // navegador no puede decodificarlo, cae al cuadrado de antes.
  const insertarActivoImagen = async (objeto: string, centro: { x: number; y: number }) => {
    const dims = await leerDimensionesUrl(urlMedia(objeto));
    const st = store.getState();
    const cw = Math.round(documento.formato.w * 0.4);
    const ch = dims && dims.w > 0 ? Math.round((cw * dims.h) / dims.w) : cw;
    st.agregar(
      nuevaCapaImagen(objeto, {
        x: Math.round(centro.x - cw / 2),
        y: Math.round(centro.y - ch / 2),
        w: cw,
        h: ch,
        z: zTope(st.documento),
      }),
    );
    // Estado FRESCO tras agregar (el set del store reemplaza `documento`; `st` quedó obsoleto).
    const nuevas = store.getState().documento.capas;
    st.seleccionar(nuevas[nuevas.length - 1]?.id ?? null);
  };

  // Soltar en el lienzo. Dos orígenes:
  //   1) Activo interno arrastrado desde la galería (mimetype `application/x-keni-activo`): se inserta
  //      como capa DONDE se suelta (flujo intacto).
  //   2) Ficheros del ESCRITORIO (`dataTransfer.files`): si son imágenes, se suben e insertan en el
  //      punto de soltado (igual que el pegado del portapapeles).
  const onDrop = (e: DragEventReact<HTMLDivElement>) => {
    const cont = scrollRef.current;
    if (!cont) return;
    const rect = cont.getBoundingClientRect();
    const dx = (e.clientX - rect.left + cont.scrollLeft) / escala;
    const dy = (e.clientY - rect.top + cont.scrollTop) / escala;

    const raw = e.dataTransfer.getData("application/x-keni-activo");
    if (raw) {
      e.preventDefault();
      let asset: { objeto: string; tipo: string };
      try {
        asset = JSON.parse(raw);
      } catch {
        return;
      }
      if (!asset.objeto) return;
      if (asset.tipo === "logo") {
        const st = store.getState();
        const z = zTope(st.documento);
        const cw = 320, ch = 120;
        st.agregar(nuevaCapaLogo(asset.objeto, { x: Math.round(dx - cw / 2), y: Math.round(dy - ch / 2), w: cw, h: ch, z }));
        // Estado FRESCO tras agregar (el set del store reemplaza `documento`; `st` quedó obsoleto).
        const nuevas = store.getState().documento.capas;
        st.seleccionar(nuevas[nuevas.length - 1]?.id ?? null);
      } else {
        // Imagen suelta: la capa adopta el aspect-ratio real de la foto (antes: cuadrado fijo).
        void insertarActivoImagen(asset.objeto, { x: dx, y: dy });
      }
      return;
    }

    // Ficheros del escritorio: sube e inserta cada imagen (ligero offset en cascada si son varias).
    const imagenes = Array.from(e.dataTransfer.files ?? []).filter((f) => f.type.startsWith("image/"));
    if (imagenes.length === 0) return;
    e.preventDefault();
    imagenes.forEach((f, i) => void subirEInsertarImagen(f, { x: dx + i * 24, y: dy + i * 24 }));
  };

  // Pegar imagen del portapapeles del SO: si el foco no está en un input y el clipboard trae un
  // fichero de imagen, se sube e inserta centrada en el VIEWPORT visible del lienzo.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      const archivo = Array.from(e.clipboardData?.files ?? []).find((f) => f.type.startsWith("image/"));
      if (!archivo) return;
      e.preventDefault();
      void subirEInsertarImagen(archivo, lienzoApi.current!.centroViewport());
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [escala, w, h, documento]);

  return { onDrop };
}
