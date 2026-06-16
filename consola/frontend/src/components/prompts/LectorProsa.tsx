/**
 * Vista de LECTURA renderizada (WYSIWYG) de un documento markdown de la Prompts.
 *
 * Sustituye conceptualmente al `<pre>` con variables en naranja: aquí el markdown se ve
 * con la MISMA tipografía que el editor (`EditorWysiwyg`) y las `{{VARIABLES}}` son los
 * mismos chips (read-only, con su tooltip del catálogo).
 *
 * Implementación: una instancia Tiptap NO editable con exactamente las mismas
 * extensiones que el editor (StarterKit + tiptap-markdown + ChipVariable). Así lectura
 * y edición son idénticas píxel a píxel y el round-trip de los chips es el mismo código,
 * en vez de mantener un segundo render de markdown que diverja.
 */
import StarterKit from "@tiptap/starter-kit";
import { EditorContent, useEditor } from "@tiptap/react";
import * as React from "react";
import { Markdown } from "tiptap-markdown";

import { ChipVariable } from "@/components/prompts/chip-variable";
import { ESTILO_CONTENIDO } from "@/components/editor/EditorWysiwyg";
import { cn } from "@/lib/utils";

export interface LectorProsaProps {
  /** Cuerpo markdown del documento. */
  cuerpo: string;
  className?: string;
}

export function LectorProsa({ cuerpo, className }: LectorProsaProps) {
  const editor = useEditor({
    editable: false,
    extensions: [
      StarterKit,
      Markdown.configure({ html: false, linkify: true, breaks: false }),
      ChipVariable,
    ],
    content: cuerpo,
  });

  // Cambios EXTERNOS de `cuerpo` (otra versión del doc): recarga vía setContent (que
  // tiptap-markdown parchea para parsear markdown). Solo lectura: no hay eco de tecleo.
  const ultimo = React.useRef(cuerpo);
  React.useEffect(() => {
    if (!editor || cuerpo === ultimo.current) return;
    ultimo.current = cuerpo;
    editor.commands.setContent(cuerpo);
  }, [cuerpo, editor]);

  return (
    <EditorContent
      editor={editor}
      className={cn(ESTILO_CONTENIDO, "[&_.tiptap]:min-h-0", className)}
    />
  );
}
