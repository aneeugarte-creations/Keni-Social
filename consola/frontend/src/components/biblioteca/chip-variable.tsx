/**
 * Chips de VARIABLES `{{NOMBRE}}` para el editor Tiptap de la Biblioteca de Prompts.
 *
 * Un `{{VARIABLE}}` es un marcador que la consola sustituye al inyectar el prompt; aquí
 * se representa como un nodo inline ATÓMICO (como un mention de Notion): pastilla
 * redondeada con el nombre (sin llaves), icono sutil y tooltip con la ficha del catálogo
 * (descripción + ejemplo + origen, vía `useVariables`). Si el catálogo aún no responde,
 * el chip se pinta igual, sin tooltip (fallback elegante).
 *
 * ROUND-TRIP SIN PÉRDIDA (crítico: el cuerpo se persiste como markdown):
 *   - ENTRADA: una regla inline de markdown-it (instalada por `storage.markdown.parse.setup`,
 *     el gancho de tiptap-markdown) convierte `{{[A-Z_]+}}` en `<span data-variable="…">`,
 *     que `parseHTML` mapea al nodo. Dentro de código (inline o bloque) markdown-it NO
 *     ejecuta reglas inline, así que un `{{VAR}}` en un bloque de código queda literal:
 *     exactamente lo que se quiere.
 *   - SALIDA: `storage.markdown.serialize` escribe `{{NOMBRE}}` EXACTO con `state.write`
 *     (sin escapado). Como el nombre es `[A-Z_]+` por construcción, no hay nada que escapar.
 *   - Además: regla de entrada en vivo (teclear `{{VAR}}` chipifica al cerrar las llaves)
 *     y autocompletado al teclear `{{` (dropdown estilo slash-command con el catálogo).
 */
import {
  InputRule,
  mergeAttributes,
  Node,
  type Editor,
  type Range,
} from "@tiptap/core";
import {
  NodeViewWrapper,
  ReactNodeViewRenderer,
  ReactRenderer,
  type NodeViewProps,
} from "@tiptap/react";
import {
  Suggestion,
  exitSuggestion,
  type SuggestionKeyDownProps,
  type SuggestionProps,
} from "@tiptap/suggestion";
import { Braces } from "lucide-react";
import { PluginKey } from "@tiptap/pm/state";
import * as React from "react";
import { createPortal } from "react-dom";

import { useVariables } from "@/hooks/use-biblioteca";
import { cn } from "@/lib/utils";
import type { VariableCatalogo } from "@/types";

// ─────────────────────────────── Aspecto del chip ───────────────────────────────
// Sobrio: pastilla neutra (muted + borde) con acento sutil; nada de naranja chillón.

const CLASE_CHIP = cn(
  "inline-flex select-none items-center gap-1 whitespace-nowrap rounded-full border border-border",
  "bg-muted/70 px-1.5 py-0 align-baseline text-[0.85em] font-medium leading-snug text-foreground/80",
);

/**
 * Chip INERTE (sin editor): para vistas estáticas que quieran pintar una variable con el
 * mismo aspecto que en el editor (leyendas, listados…). Sin tooltip.
 */
export function ChipVariableInerte({ nombre, className }: { nombre: string; className?: string }) {
  return (
    <span className={cn(CLASE_CHIP, className)}>
      <Braces className="h-3 w-3 opacity-60" aria-hidden />
      {nombre}
    </span>
  );
}

// ───────────────────────── Node view (chip + tooltip del catálogo) ─────────────────────────

/**
 * Vista React del nodo: chip con tooltip propio (ficha multilinea del catálogo; el
 * `Tooltip` común solo admite una línea). El node view se monta como portal DENTRO del
 * árbol React de `EditorContent`, así que los providers (react-query) están disponibles.
 */
function VistaChipVariable({ node, selected }: NodeViewProps) {
  const nombre = (node.attrs.nombre as string) ?? "";
  const { porNombre } = useVariables();
  const info = porNombre.get(nombre);

  const anclaRef = React.useRef<HTMLSpanElement | null>(null);
  const timerRef = React.useRef<number | null>(null);
  const [pos, setPos] = React.useState<{ x: number; y: number } | null>(null);

  React.useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    },
    [],
  );

  const mostrar = () => {
    if (!info) return; // catálogo sin cargar / variable desconocida: chip sin tooltip
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      const r = anclaRef.current?.getBoundingClientRect();
      if (r) setPos({ x: r.left + r.width / 2, y: r.top - 6 });
    }, 350);
  };
  const ocultar = () => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
    setPos(null);
  };

  return (
    <NodeViewWrapper as="span" className="inline">
      <span
        ref={anclaRef}
        data-variable={nombre}
        title={info ? undefined : nombre ? `Variable {{${nombre}}}` : undefined}
        onMouseEnter={mostrar}
        onMouseLeave={ocultar}
        className={cn(CLASE_CHIP, "cursor-default", selected && "ring-2 ring-ring")}
      >
        <Braces className="h-3 w-3 opacity-60" aria-hidden />
        {nombre}
      </span>
      {pos && info
        ? createPortal(
            <span
              role="tooltip"
              style={{ left: pos.x, top: pos.y, transform: "translate(-50%, -100%)" }}
              className="pointer-events-none fixed z-[100] block w-64 rounded-md border border-border bg-popover p-2.5 text-xs text-popover-foreground shadow-md"
            >
              <span className="block font-semibold">{`{{${info.nombre}}}`}</span>
              {info.descripcion ? (
                <span className="mt-1 block leading-relaxed">{info.descripcion}</span>
              ) : null}
              {info.ejemplo ? (
                <span className="mt-1 block text-muted-foreground">
                  Ejemplo: <span className="italic">{info.ejemplo}</span>
                </span>
              ) : null}
              {info.origen ? (
                <span className="mt-1 block text-muted-foreground">Origen: {info.origen}</span>
              ) : null}
            </span>,
            document.body,
          )
        : null}
    </NodeViewWrapper>
  );
}

// ───────────────────── Autocompletado `{{` (dropdown estilo slash-command) ─────────────────────

interface RefListaVariables {
  onKeyDown: (evento: KeyboardEvent) => boolean;
}

type PropsListaVariables = SuggestionProps<VariableCatalogo, VariableCatalogo>;

/** Dropdown del autocompletado: lista de variables del catálogo, navegable con teclado. */
const ListaVariables = React.forwardRef<RefListaVariables, PropsListaVariables>(
  function ListaVariables({ items, command }, ref) {
    const [indice, setIndice] = React.useState(0);
    React.useEffect(() => setIndice(0), [items]);

    const elegir = React.useCallback(
      (i: number) => {
        const item = items[i];
        if (item) command(item);
      },
      [items, command],
    );

    React.useImperativeHandle(
      ref,
      () => ({
        onKeyDown: (evento) => {
          if (items.length === 0) return false;
          if (evento.key === "ArrowDown") {
            setIndice((i) => (i + 1) % items.length);
            return true;
          }
          if (evento.key === "ArrowUp") {
            setIndice((i) => (i + items.length - 1) % items.length);
            return true;
          }
          if (evento.key === "Enter" || evento.key === "Tab") {
            elegir(indice);
            return true;
          }
          return false;
        },
      }),
      [items, indice, elegir],
    );

    if (items.length === 0) return null;
    return (
      <div className="max-h-64 w-72 overflow-y-auto rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md">
        {items.map((v, i) => (
          <button
            key={v.nombre}
            type="button"
            onMouseDown={(e) => {
              // mousedown (no click): no robar el foco al editor antes de insertar.
              e.preventDefault();
              elegir(i);
            }}
            onMouseEnter={() => setIndice(i)}
            className={cn(
              "flex w-full items-start gap-2 rounded-sm px-2 py-1.5 text-left text-xs",
              i === indice ? "bg-muted" : "",
            )}
          >
            <Braces className="mt-0.5 h-3 w-3 shrink-0 opacity-60" aria-hidden />
            <span className="min-w-0">
              <span className="block font-medium">{v.nombre}</span>
              {v.descripcion ? (
                <span className="mt-0.5 line-clamp-2 block text-muted-foreground">
                  {v.descripcion}
                </span>
              ) : null}
            </span>
          </button>
        ))}
      </div>
    );
  },
);

const CLAVE_SUGERENCIA = new PluginKey("sugerencia-variables");

// ─────────────────────────────── La extensión Tiptap ───────────────────────────────

export interface OpcionesChipVariable {
  /**
   * Getter del catálogo para el AUTOCOMPLETADO (`{{`). Es función (no array) porque la
   * extensión se configura una sola vez al crear el editor y el catálogo llega async:
   * el host (EditorWysiwyg) lo apunta a un ref que se actualiza con la query.
   */
  obtenerVariables: () => VariableCatalogo[];
}

// Forma mínima de markdown-it que usamos (tiptap-markdown no re-exporta sus tipos).
interface TokenMd {
  content: string;
}
interface EstadoInlineMd {
  src: string;
  pos: number;
  push: (tipo: string, etiqueta: string, anidado: number) => TokenMd;
}
interface MarkdownItMd {
  inline: {
    ruler: { push: (nombre: string, regla: (state: EstadoInlineMd, silent: boolean) => boolean) => void };
  };
  renderer: { rules: Record<string, (tokens: TokenMd[], idx: number) => string> };
}

const RE_VARIABLE_INICIO = /^\{\{([A-Z_]+)\}\}/;

/**
 * Nodo inline atómico `chipVariable`. Actívalo solo en los editores de la Biblioteca
 * (prop `conVariables` de `EditorWysiwyg`); el resto de usos del editor no lo cargan.
 */
export const ChipVariable = Node.create<OpcionesChipVariable>({
  name: "chipVariable",
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,

  addOptions() {
    return { obtenerVariables: () => [] };
  },

  addAttributes() {
    return {
      nombre: {
        default: "",
        parseHTML: (el) => el.getAttribute("data-variable") ?? "",
        renderHTML: (attrs) => ({ "data-variable": attrs.nombre as string }),
      },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-variable]" }];
  },

  // Render DOM "plano" (clipboard / sin node view): mismo aspecto base que el chip.
  renderHTML({ node, HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(HTMLAttributes, { class: CLASE_CHIP }),
      String(node.attrs.nombre ?? ""),
    ];
  },

  // El texto plano del nodo conserva las llaves (copiar como texto da `{{NOMBRE}}`).
  renderText({ node }) {
    return `{{${node.attrs.nombre}}}`;
  },

  addNodeView() {
    return ReactNodeViewRenderer(VistaChipVariable);
  },

  // Round-trip markdown (gancho de tiptap-markdown: `storage.markdown`).
  addStorage() {
    return {
      markdown: {
        serialize: (state: { write: (texto: string) => void }, node: { attrs: { nombre?: string } }) => {
          state.write(`{{${node.attrs.nombre ?? ""}}}`);
        },
        parse: {
          setup: (md: MarkdownItMd) => {
            md.inline.ruler.push("chip_variable", (state, silent) => {
              const m = RE_VARIABLE_INICIO.exec(state.src.slice(state.pos));
              if (!m) return false;
              if (!silent) {
                const token = state.push("chip_variable", "", 0);
                token.content = m[1];
              }
              state.pos += m[0].length;
              return true;
            });
            // El nombre es [A-Z_]+ por la regex: seguro para interpolar en HTML.
            md.renderer.rules.chip_variable = (tokens, idx) =>
              `<span data-variable="${tokens[idx].content}"></span>`;
          },
        },
      },
    };
  },

  // Teclear `{{NOMBRE}}` a mano chipifica al cerrar las llaves (sin pasar por el dropdown).
  addInputRules() {
    return [
      new InputRule({
        find: /\{\{([A-Z_]+)\}\}$/,
        handler: ({ state, range, match }) => {
          state.tr.replaceWith(
            range.from,
            range.to,
            this.type.create({ nombre: match[1] }),
          );
        },
      }),
    ];
  },

  // Autocompletado al teclear `{{`: dropdown con el catálogo (filtra por lo tecleado).
  addProseMirrorPlugins() {
    const tipo = this.type;
    const obtenerVariables = () => this.options.obtenerVariables();
    return [
      Suggestion<VariableCatalogo, VariableCatalogo>({
        pluginKey: CLAVE_SUGERENCIA,
        editor: this.editor,
        char: "{{",
        allowedPrefixes: null,
        items: ({ query }) => {
          const q = query.trim().toUpperCase();
          return obtenerVariables()
            .filter((v) => !q || v.nombre.includes(q))
            .slice(0, 8);
        },
        command: ({ editor, range, props }: { editor: Editor; range: Range; props: VariableCatalogo }) => {
          editor
            .chain()
            .focus()
            .insertContentAt(range, [
              { type: tipo.name, attrs: { nombre: props.nombre } },
              { type: "text", text: " " },
            ])
            .run();
        },
        render: () => {
          let renderer: ReactRenderer<RefListaVariables, PropsListaVariables> | null = null;

          const posicionar = (props: PropsListaVariables) => {
            const el = renderer?.element as HTMLElement | undefined;
            const rect = props.clientRect?.();
            if (!el || !rect) return;
            el.style.position = "fixed";
            el.style.zIndex = "100";
            el.style.left = `${rect.left}px`;
            el.style.top = `${rect.bottom + 4}px`;
          };

          return {
            onStart: (props) => {
              renderer = new ReactRenderer(ListaVariables, { props, editor: props.editor });
              document.body.appendChild(renderer.element);
              posicionar(props);
            },
            onUpdate: (props) => {
              renderer?.updateProps(props);
              posicionar(props);
            },
            onKeyDown: (props: SuggestionKeyDownProps) => {
              if (props.event.key === "Escape") {
                exitSuggestion(props.view, CLAVE_SUGERENCIA);
                return true;
              }
              return renderer?.ref?.onKeyDown(props.event) ?? false;
            },
            onExit: () => {
              renderer?.element.remove();
              renderer?.destroy();
              renderer = null;
            },
          };
        },
      }),
    ];
  },
});
