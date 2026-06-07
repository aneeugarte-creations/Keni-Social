/**
 * Pista de OVERLAY: reutiliza el EDITOR DE CAPAS del Estudio de imagen para añadir logos,
 * marcos, image-in-video y textos como capas `Documento`. El render server-side rasteriza
 * estas capas a un PNG transparente (`renderizar_documento_bytes`) y lo compone con `overlay`
 * en FFmpeg sobre el video (contrato G-video-engine §1).
 *
 * Monta `EditorDocumento` sobre un store cuyo lienzo coincide con el formato de la composición
 * (fondo TRANSPARENTE, sin hueco de foto: aquí no se sustituye foto, se sobreimprime sobre el
 * video). Cada cambio del documento sincroniza `documento.capas` hacia la composición.
 */
import * as React from "react";

import type { Capa, Documento } from "@/editor/documento";
import { EditorDocumento } from "@/editor/EditorDocumento";
import { crearStoreEditor, type StoreEditor } from "@/editor/store";
import type { ComposicionVideo } from "@/lib/video";

export interface PanelOverlayProps {
  doc: ComposicionVideo;
  marca: string;
  /** Capas actuales de la pista overlay. */
  capas: Capa[];
  /** Notifica el nuevo conjunto de capas tras cada edición. */
  onCapas: (capas: Capa[]) => void;
}

/** Construye un Documento transparente del tamaño de la composición con las capas dadas. */
function documentoOverlay(doc: ComposicionVideo, marca: string, capas: Capa[]): Documento {
  const safeTop = 0;
  return {
    version: 1,
    marca,
    fuentes: { sans: "Barlow", condensada: "Barlow Condensed" },
    formato: { w: doc.formato.w, h: doc.formato.h, safe_top: safeTop, safe_bottom: 0 },
    fondo: { tipo: "color", color: "#00000000" },
    capas,
  };
}

export function PanelOverlay({ doc, marca, capas, onCapas }: PanelOverlayProps) {
  // Un store POR montaje, sembrado con las capas actuales. Se recrea si cambia el formato del
  // lienzo (las capas se preservan vía el documento).
  const storeRef = React.useRef<StoreEditor | null>(null);
  const formatoClave = `${doc.formato.w}x${doc.formato.h}`;
  const formatoPrev = React.useRef(formatoClave);

  if (!storeRef.current || formatoPrev.current !== formatoClave) {
    storeRef.current = crearStoreEditor(documentoOverlay(doc, marca, capas));
    formatoPrev.current = formatoClave;
  }
  const store = storeRef.current;

  // Sincroniza las capas del store hacia el padre en cada cambio (debounced por microtask vía
  // la suscripción de zustand). El padre es la fuente de verdad de la composición.
  React.useEffect(() => {
    const unsub = store.subscribe(() => {
      onCapas(store.getState().documento.capas);
    });
    return unsub;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store]);

  return (
    <div className="h-[60vh] min-h-[420px] overflow-hidden rounded-md border border-border">
      <EditorDocumento store={store} marca={marca} />
    </div>
  );
}
