/**
 * Editor WYSIWYG de markdown (estilo Notion): escribes con el formato YA aplicado
 * (títulos, negritas, listas) y el cuerpo se guarda como markdown. Sin toggle "Editar/Vista".
 *
 * Tiptap (ProseMirror) + `tiptap-markdown`:
 *  - StarterKit trae las reglas de entrada markdown (`## ` -> H2, `- ` -> viñeta, `**x**`
 *    -> negrita, etc.), así que se escribe en markdown y se ve renderizado al instante.
 *  - `Markdown` (de tiptap-markdown) parsea el markdown de entrada y SERIALIZA de vuelta a
 *    markdown (`editor.storage.markdown.getMarkdown()`), que es lo que persistimos.
 *
 * SINCRONÍA SIN BUCLES: `value` es la fuente externa (cambia al cambiar de documento). Al
 * teclear emitimos markdown por `onContenido` y guardamos el último emitido en un ref; el
 * efecto que sincroniza `value -> editor` se SALTA cuando `value` coincide con ese ref, así
 * el propio tecleo no provoca un `setContent` (que movería el cursor).
 */
import StarterKit from "@tiptap/starter-kit";
import { EditorContent, useEditor } from "@tiptap/react";
import * as React from "react";
import { Markdown } from "tiptap-markdown";

import type { Editor } from "@tiptap/react";

import { cn } from "@/lib/utils";

/** tiptap-markdown añade `storage.markdown.getMarkdown()` en runtime pero no lo tipa. */
function aMarkdown(editor: Editor): string {
  const storage = editor.storage as { markdown?: { getMarkdown: () => string } };
  return storage.markdown?.getMarkdown() ?? "";
}

// Estilo del contenido editable (no hay plugin `prose`): mapeo elemento->clases coherente
// con el tema, vía selectores hijos de Tailwind sobre el área `.tiptap` (contentEditable).
const ESTILO_CONTENIDO = cn(
  "[&_.tiptap]:min-h-[300px] [&_.tiptap]:outline-none [&_.tiptap]:text-sm [&_.tiptap]:leading-relaxed",
  "[&_h1]:mb-2 [&_h1]:mt-3 [&_h1]:text-xl [&_h1]:font-bold",
  "[&_h2]:mb-2 [&_h2]:mt-3 [&_h2]:text-lg [&_h2]:font-semibold",
  "[&_h3]:mb-1 [&_h3]:mt-2 [&_h3]:text-base [&_h3]:font-semibold",
  "[&_p]:mb-2 [&_p]:last:mb-0",
  "[&_strong]:font-semibold [&_em]:italic",
  "[&_ul]:mb-2 [&_ul]:ml-5 [&_ul]:list-disc [&_ul]:space-y-1",
  "[&_ol]:mb-2 [&_ol]:ml-5 [&_ol]:list-decimal [&_ol]:space-y-1",
  "[&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground",
  "[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-xs",
  "[&_pre]:mb-2 [&_pre]:rounded [&_pre]:bg-muted [&_pre]:p-3 [&_pre]:text-xs",
  "[&_pre_code]:bg-transparent [&_pre_code]:p-0",
  "[&_hr]:my-3 [&_hr]:border-border",
  "[&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2",
);

export function EditorWysiwyg({
  value,
  onContenido,
  placeholder,
}: {
  value: string;
  onContenido: (markdown: string) => void;
  placeholder?: string;
}) {
  // `null` fuerza la carga inicial (el primer efecto hace setContent). Luego guarda lo último
  // emitido al teclear para no re-cargar (evita bucle setContent->salto de cursor).
  const ultimoEmitido = React.useRef<string | null>(null);
  // `onContenido` por REF: `useEditor` fija `onUpdate` UNA sola vez (deps []); sin esto el
  // handler llamaría al callback VIEJO (capturado al montar) -> al cambiar de documento se
  // guardaba en el ANTERIOR y la selección saltaba ("aparece y desaparece"). El ref apunta al actual.
  const onContenidoRef = React.useRef(onContenido);
  onContenidoRef.current = onContenido;
  // Marca el `onUpdate` que dispara NUESTRO setContent programático (cargar/cambiar de doc).
  // ProseMirror lo emite SÍNCRONO dentro de setContent, así que basta un flag a su alrededor.
  const cargando = React.useRef(false);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Markdown.configure({ html: false, linkify: true, breaks: true, transformPastedText: true }),
    ],
    content: "",
    editorProps: {
      attributes: { class: "tiptap", "data-placeholder": placeholder ?? "" },
    },
    onUpdate: ({ editor }) => {
      if (cargando.current) return; // update provocado por el setContent de carga, no por el usuario
      const md = aMarkdown(editor);
      ultimoEmitido.current = md;
      onContenidoRef.current(md);
    },
  });

  // Carga inicial + cambios EXTERNOS de `value` (cambio de documento) vía `setContent`, que
  // tiptap-markdown parchea para PARSEAR markdown. Se salta si `value` es lo último que
  // emitimos al teclear (no recargamos nuestro propio cambio). El flag `cargando` evita que el
  // `onUpdate` de este setContent se trate como edición (y guarde el doc solo por abrirlo).
  React.useEffect(() => {
    if (!editor) return;
    if (value === ultimoEmitido.current) return;
    ultimoEmitido.current = value;
    cargando.current = true;
    editor.commands.setContent(value);
    cargando.current = false;
  }, [value, editor]);

  return <EditorContent editor={editor} className={ESTILO_CONTENIDO} />;
}
