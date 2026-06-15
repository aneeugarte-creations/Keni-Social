/**
 * Render seguro de Markdown para LECTURA interna (vistas previas / visualización).
 *
 * Usa `react-markdown` + `remark-gfm` (listas, tablas, tachado, autolinks). NO se
 * habilita HTML crudo (sin `rehype-raw`), así que cualquier `<script>`/etiqueta
 * incrustada se muestra como texto: render seguro por defecto.
 *
 * - Negritas, cursivas, listas, citas, código y enlaces con estilos Tailwind.
 * - Los enlaces abren en pestaña nueva con `rel="noopener noreferrer"`.
 * - Saltos de línea respetados (`remark-gfm` + estilo `whitespace-pre-line` en p).
 *
 * Nota: las redes sociales NO renderizan Markdown de verdad. Esto es solo para
 * que el equipo lea el contenido cómodamente dentro de la consola; la vista
 * previa por red muestra el texto tal cual (ver `VistaPreviaRed`).
 */
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

/** Mapeo de elementos -> clases Tailwind, coherente con el tema (claro/oscuro). */
const COMPONENTES: Components = {
  p: ({ children }) => (
    <p className="mb-2 whitespace-pre-line leading-relaxed last:mb-0">{children}</p>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-primary underline underline-offset-2 hover:text-primary/80"
    >
      {children}
    </a>
  ),
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  del: ({ children }) => <del className="text-muted-foreground line-through">{children}</del>,
  ul: ({ children }) => (
    <ul className="mb-2 ml-5 list-disc space-y-1 last:mb-0">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-2 ml-5 list-decimal space-y-1 last:mb-0">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  h1: ({ children }) => <h1 className="mb-2 mt-3 text-lg font-semibold first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2 mt-3 text-base font-semibold first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-1.5 mt-2 text-sm font-semibold first:mt-0">{children}</h3>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-border pl-3 italic text-muted-foreground">
      {children}
    </blockquote>
  ),
  code: ({ children }) => (
    <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">{children}</code>
  ),
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded-md border border-border bg-muted/40 p-3 text-xs leading-relaxed">
      {children}
    </pre>
  ),
  hr: () => <hr className="my-3 border-border" />,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-border bg-muted/50 px-2 py-1 text-left font-semibold">
      {children}
    </th>
  ),
  td: ({ children }) => <td className="border border-border px-2 py-1">{children}</td>,
};

export interface MarkdownProps {
  /** Texto en Markdown a renderizar. */
  children: string;
  className?: string;
}

export function Markdown({ children, className }: MarkdownProps) {
  return (
    <div className={cn("break-words text-sm text-foreground", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTES}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
