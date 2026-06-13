// Edición de texto EN LÍNEA WYSIWYG (patrón Canva): overlay HTML que vive dentro del TABLERO (px del
// canvas) para que el scroll lo arrastre consigo, en la MISMA caja que la capa (posición, valign y
// rotación) y con el MISMO estilo que el texto pintado (el nodo Konva queda oculto mientras tanto; el
// Transformer conserva el marco). Doble clic selecciona todo, Enter guarda (Shift+Enter = salto de
// línea), Escape cancela, clic fuera guarda. Extraído como subcomponente; la lógica vive en
// `useEdicionTexto`.

import type { CapaTexto, Documento } from "../documento";
import { estiloCajaEdicion, estiloTextoEdicion } from "./edicionInline";

export function OverlayEdicionTexto({
  editando,
  documento,
  escala,
  textoEdit,
  setTextoEdit,
  ajustarAltoEdicion,
  cerrarEdicion,
}: {
  editando: { id: string; destino: unknown };
  documento: Documento;
  escala: number;
  textoEdit: string;
  setTextoEdit: (v: string) => void;
  ajustarAltoEdicion: (el: HTMLTextAreaElement) => void;
  cerrarEdicion: (guardar: boolean) => void;
}) {
  const c = documento.capas.find((x) => x.id === editando.id) as CapaTexto | undefined;
  if (!c) return null;
  return (
    <div style={estiloCajaEdicion(c, escala)} className="z-20">
      <textarea
        autoFocus
        rows={1}
        value={textoEdit}
        spellCheck={false}
        onChange={(e) => { setTextoEdit(e.target.value); ajustarAltoEdicion(e.currentTarget); }}
        onFocus={(e) => { e.currentTarget.select(); ajustarAltoEdicion(e.currentTarget); }}
        onBlur={() => cerrarEdicion(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); cerrarEdicion(true); }
          if (e.key === "Escape") { e.preventDefault(); cerrarEdicion(false); }
        }}
        className="block w-full resize-none overflow-hidden border-0 bg-transparent p-0 outline-none"
        style={estiloTextoEdicion(c, escala)}
      />
    </div>
  );
}
