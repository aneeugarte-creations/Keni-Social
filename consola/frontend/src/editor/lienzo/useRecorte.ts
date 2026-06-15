// MODO RECORTE estilo Canva (solo imágenes), extraído como hook. Owns el id de recorte INTERNO (el
// Lienzo entra por sí mismo con doble clic, además del modo controlado por el padre vía `recorteId`)
// y la SESIÓN de recorte (instantánea al entrar para que Cancelar/Esc restaure y Hecho/Enter colapse
// los gestos en UN paso de deshacer). El componente le pasa el documento/store y el modo reencuadre
// (excluyente) y recibe la capa en recorte + los manejadores de salir/confirmar/cancelar.

import { useEffect, useRef, useState } from "react";

import type { Capa, CapaImagen, Crop, Documento } from "../documento";
import type { StoreEditor } from "../store";

export function useRecorte({
  store,
  documento,
  recorteId,
  onSalirRecorte,
  capaReencuadre,
  sinRotacion,
}: {
  store: StoreEditor;
  documento: Documento;
  recorteId: string | null;
  onSalirRecorte?: () => void;
  // Capa en modo reencuadre (excluyente con recorte: el reencuadre manda si coinciden).
  capaReencuadre: Capa | null;
  sinRotacion: (c: Capa) => boolean;
}) {
  // MODO RECORTE estilo Canva (solo imágenes): además del modo controlado por el padre (prop
  // `recorteId`, p. ej. desde el inspector), el Lienzo entra POR SÍ MISMO con DOBLE CLIC sobre una
  // capa de imagen (estado interno). Excluyente con reencuadre (el reencuadre manda si coinciden).
  const [recorteInternoId, setRecorteInternoId] = useState<string | null>(null);
  const recorteActivoId = recorteId ?? recorteInternoId;
  // Recortable = imagen (recorte de PÍXELES, `crop`) o cualquier otro objeto (recorte de CAJA, encoge
  // su recuadro). La IMAGEN exige rotación 0 (su overlay no resuelve ejes girados); el objeto SÍ admite
  // rotación (recorta a lo largo de sus ejes locales, p. ej. una línea vertical = línea rotada 90°). El
  // reencuadre manda si coinciden. El doble clic solo entra para imágenes; el botón, para cualquiera.
  const capaRecorte =
    !capaReencuadre && recorteActivoId
      ? documento.capas.find((c) => c.id === recorteActivoId && (c.tipo !== "imagen" || sinRotacion(c))) ?? null
      : null;

  // SESIÓN de recorte: instantánea al ENTRAR en el modo, para que "Cancelar"/Esc restaure el estado
  // de entrada (el `crop` de la imagen, o el RECUADRO del objeto) y para que "Hecho"/Enter colapse
  // todos los gestos del modo en UN paso de deshacer (como Canva). `pasadoLen` ancla el historial.
  const sesionRecorte = useRef<
    { id: string; crop?: Crop; caja?: { x: number; y: number; w: number; h: number }; pasadoLen: number } | null
  >(null);
  useEffect(() => {
    if (!capaRecorte) {
      sesionRecorte.current = null;
      return;
    }
    if (sesionRecorte.current?.id === capaRecorte.id) return;
    const st = store.getState();
    const c = st.documento.capas.find((x) => x.id === capaRecorte.id);
    sesionRecorte.current = {
      id: capaRecorte.id,
      crop: c?.tipo === "imagen" && c.crop ? { ...c.crop } : undefined,
      caja: c && c.tipo !== "imagen" ? { x: c.x, y: c.y, w: c.w, h: c.h } : undefined,
      pasadoLen: st.pasado.length,
    };
  }, [capaRecorte, store]);
  // Si la capa en recorte interno desaparece (deshacer/borrado), el modo se cierra solo.
  useEffect(() => {
    if (recorteInternoId && !documento.capas.some((c) => c.id === recorteInternoId && c.tipo === "imagen")) {
      setRecorteInternoId(null);
    }
  }, [recorteInternoId, documento]);

  const salirRecorte = () => {
    if (recorteInternoId) setRecorteInternoId(null);
    if (recorteId) onSalirRecorte?.();
  };
  // "Hecho"/Enter: confirma el recorte. Colapsa los gestos del modo en UN paso de deshacer
  // (deshacer tras confirmar devuelve el crop de ENTRADA, no los estados intermedios).
  const confirmarRecorte = () => {
    const ses = sesionRecorte.current;
    if (ses) {
      store.setState((s) =>
        s.pasado.length > ses.pasadoLen + 1 ? { pasado: s.pasado.slice(0, ses.pasadoLen + 1) } : {},
      );
    }
    salirRecorte();
  };
  // "Cancelar"/Esc: restaura el estado de entrada (crop de la imagen o recuadro del objeto) y
  // DESCARTA los pasos de historial del modo.
  const cancelarRecorte = () => {
    const ses = sesionRecorte.current;
    if (ses) {
      store.setState((s) => ({
        documento: {
          ...s.documento,
          capas: s.documento.capas.map((c) => {
            if (c.id !== ses.id) return c;
            if (c.tipo === "imagen") {
              if (ses.crop) return { ...c, crop: { ...ses.crop } } as Capa;
              const { crop: _omit, ...resto } = c as CapaImagen;
              return resto as Capa;
            }
            // Objeto no-imagen: restaura el RECUADRO de entrada.
            return ses.caja ? ({ ...c, ...ses.caja } as Capa) : c;
          }),
        },
        pasado: s.pasado.slice(0, ses.pasadoLen),
      }));
    }
    salirRecorte();
  };

  return {
    recorteInternoId,
    setRecorteInternoId,
    recorteActivoId,
    capaRecorte,
    salirRecorte,
    confirmarRecorte,
    cancelarRecorte,
  };
}
