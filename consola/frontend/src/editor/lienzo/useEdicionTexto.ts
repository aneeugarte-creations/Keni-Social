// Edición de texto EN LÍNEA WYSIWYG (doble clic), extraída como hook. Owns el estado de qué se está
// editando (id + destino: texto real o muestra titular/pleca) y el buffer del textarea, más los
// manejadores de abrir/cerrar/auto-alto. El overlay HTML lo pinta `OverlayEdicionTexto`.

import { useRef, useState } from "react";
import { toast } from "sonner";

import type { Capa, CapaTexto, Documento } from "../documento";
import { setEtiquetaMuestra, setTitularMuestra } from "../muestra";
import type { StoreEditor } from "../store";
import { type DestinoEdicion, destinoEdicion, textoInicial } from "./edicionInline";

export function useEdicionTexto({
  store,
  documento,
  muestraCopy,
}: {
  store: StoreEditor;
  documento: Documento;
  muestraCopy: boolean;
}) {
  const [editando, setEditando] = useState<{ id: string; destino: DestinoEdicion } | null>(null);
  const [textoEdit, setTextoEdit] = useState("");
  // El aviso de "texto con binding" se muestra una sola vez por vida del componente.
  const avisoBinding = useRef(false);

  // Doble clic en una capa de texto -> edición en línea WYSIWYG sobre la imagen (patrón Canva).
  // Se edita LO QUE SE VE: con binding y «Copy de muestra» activo, el copy de muestra; en el
  // resto de casos, el texto real de la capa.
  const abrirEdicionTexto = (id: string) => {
    const capa = documento.capas.find((c) => c.id === id);
    if (!capa || capa.tipo !== "texto") return;
    const c = capa as CapaTexto;
    const destino = destinoEdicion(c, muestraCopy);
    setTextoEdit(textoInicial(c, muestraCopy));
    setEditando({ id, destino });
    store.getState().seleccionar(id);
    // Aviso ÚNICO por sesión para los textos con binding: que quede claro qué se está editando.
    if (c.binding != null && !avisoBinding.current) {
      avisoBinding.current = true;
      toast.info(
        destino === "texto"
          ? "Este texto se rellena con el copy real de la pieza; lo que escribas es el texto de muestra de la plantilla."
          : "Editas el copy de MUESTRA (solo presentación): la pieza final usa su copy real.",
      );
    }
  };

  const cerrarEdicion = (guardar: boolean) => {
    if (editando && guardar) {
      // El destino se decidió al abrir: muestra (titular/pleca, módulo muestra.ts) o texto real.
      if (editando.destino === "muestra-titular") setTitularMuestra(textoEdit);
      else if (editando.destino === "muestra-etiqueta") setEtiquetaMuestra(textoEdit);
      else store.getState().actualizar(editando.id, { texto: textoEdit } as Partial<Capa>);
    }
    setEditando(null);
  };

  // Auto-alto del editable: el textarea crece con el contenido (sin scroll interno), como Canva.
  const ajustarAltoEdicion = (el: HTMLTextAreaElement) => {
    el.style.height = "0px";
    el.style.height = `${el.scrollHeight}px`;
  };

  return { editando, textoEdit, setTextoEdit, abrirEdicionTexto, cerrarEdicion, ajustarAltoEdicion };
}
