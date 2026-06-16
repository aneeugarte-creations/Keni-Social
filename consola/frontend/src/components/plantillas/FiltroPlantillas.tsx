// Piezas COMPARTIDAS de la organización de plantillas estilo Canva (galería inline del editor y
// galería modal): barra de búsqueda + chips de categoría horizontales + badge de categoría en
// tarjeta + rejilla MASONRY con carga perezosa por lotes. El catálogo y la normalización viven
// en `lib/categoriasPlantilla.ts`.

import { Check, ChevronDown, Plus, Search, Tag } from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import type { PlantillaDiseno } from "@/lib/api";
import {
  CATEGORIAS_PLANTILLA,
  categoriasPresentes,
  coincideBusqueda,
  etiquetaCategoria,
  normalizarCategoria,
} from "@/lib/categoriasPlantilla";

/**
 * Estado de filtrado client-side de una galería: búsqueda (nombre/categoría, acento-insensible) +
 * chip de categoría activa. Los chips salen de las categorías PRESENTES en los datos (lista
 * completa, no la filtrada: así no desaparecen al buscar).
 */
export function useFiltroPlantillas(plantillas: PlantillaDiseno[]) {
  const [q, setQ] = useState("");
  const [categoria, setCategoria] = useState(""); // "" = chip «Todas»
  const presentes = useMemo(() => categoriasPresentes(plantillas), [plantillas]);
  const filtradas = useMemo(
    () =>
      plantillas.filter(
        (p) =>
          (!categoria || normalizarCategoria(p.categoria) === categoria) && coincideBusqueda(p, q),
      ),
    [plantillas, q, categoria],
  );
  return { q, setQ, categoria, setCategoria, presentes, filtradas };
}

// ── Masonry + carga perezosa (patrón Canva) ─────────────────────────────────────────────────────

/**
 * Relación de aspecto REAL (ancho/alto) de la miniatura de una plantilla, leída del formato del
 * documento (la miniatura se renderiza del documento, así que comparten proporción). Si el
 * documento no trae formato (legado/corrupto) cae al 4/5 histórico de la galería.
 */
export function ratioPlantilla(p: PlantillaDiseno): number {
  const formato = (p.documento as { formato?: { w?: unknown; h?: unknown } } | null | undefined)
    ?.formato;
  const w = formato?.w;
  const h = formato?.h;
  if (typeof w === "number" && typeof h === "number" && w > 0 && h > 0) return w / h;
  return 4 / 5;
}

// Coste vertical estimado de la "carrocería" de una tarjeta (fila de título + fila de rotación)
// en unidades de ANCHO de columna: como todas las columnas miden lo mismo, para repartir basta
// con proporciones (alto/ancho), sin medir el DOM.
const ALTURA_CHROME = 0.3;

/**
 * Reparto masonry SIN medir el DOM: cada plantilla cae en la columna más corta según su altura
 * estimada (1/ratio + carrocería). El reparto es estable por prefijo: añadir elementos al final
 * NUNCA recoloca los anteriores — clave para la carga perezosa sin saltos de scroll (CSS
 * `columns` rebalancea todo el flujo al crecer; por eso no sirve aquí).
 */
export function repartirMasonry(
  plantillas: PlantillaDiseno[],
  columnas: number,
): PlantillaDiseno[][] {
  const cols: PlantillaDiseno[][] = Array.from({ length: Math.max(1, columnas) }, () => []);
  const alturas = new Array<number>(cols.length).fill(0);
  for (const p of plantillas) {
    let corta = 0;
    for (let i = 1; i < cols.length; i += 1) if (alturas[i] < alturas[corta]) corta = i;
    cols[corta].push(p);
    alturas[corta] += 1 / ratioPlantilla(p) + ALTURA_CHROME;
  }
  return cols;
}

/**
 * Rejilla masonry de tarjetas de plantilla: N columnas verticales de igual ancho; cada tarjeta
 * conserva la relación de aspecto real de su documento. `render` debe devolver un elemento con
 * `key` propia (las tarjetas de los llamantes ya la llevan).
 */
export function MasonryPlantillas({
  plantillas,
  columnas,
  render,
}: {
  plantillas: PlantillaDiseno[];
  columnas: number;
  render: (p: PlantillaDiseno) => ReactNode;
}) {
  const cols = repartirMasonry(plantillas, columnas);
  return (
    <div data-masonry={cols.length} className="flex items-start gap-3">
      {cols.map((col, i) => (
        <div key={i} data-col className="flex min-w-0 flex-1 flex-col gap-3">
          {col.map((p) => render(p))}
        </div>
      ))}
    </div>
  );
}

/**
 * Carga PEREZOSA por lotes de una lista que YA está en memoria (virtualización ligera de DOM, no
 * paginación de API): se renderizan `lote` elementos y, si quedan más, el llamante pinta un
 * sentinel con `refSentinela` al final; cuando el sentinel se acerca al viewport
 * (IntersectionObserver con margen) se suelta el siguiente lote — siempre APPEND al final, sin
 * saltos de scroll. `claveFiltro` reinicia el contador al cambiar búsqueda/chip/tipo.
 */
export function useLotes(total: number, claveFiltro: string, lote = 24) {
  const [visibles, setVisibles] = useState(lote);
  useEffect(() => {
    setVisibles(lote);
  }, [claveFiltro, lote]);
  const [sentinela, setSentinela] = useState<HTMLElement | null>(null);
  useEffect(() => {
    if (!sentinela || typeof IntersectionObserver === "undefined") return;
    const observador = new IntersectionObserver(
      (entradas) => {
        if (entradas.some((e) => e.isIntersecting)) setVisibles((v) => v + lote);
      },
      // Margen generoso: el siguiente lote entra ANTES de que el usuario llegue al final.
      { rootMargin: "300px 0px" },
    );
    observador.observe(sentinela);
    return () => observador.disconnect();
  }, [sentinela, lote]);
  return { visibles, hayMas: visibles < total, refSentinela: setSentinela };
}

/**
 * Columnas de una galería de plantillas a página completa según el ancho de ventana (2 base,
 * 3 ≥sm, 4 ≥md, 5 ≥xl, 6 ≥1700px): a página completa la galería ocupa todo el ancho y en pantallas
 * grandes mete más columnas para que las tarjetas no queden enormes. El masonry reparte por JS, así
 * que el responsive también va por JS (matchMedia), no por clases. (La modal capa este número con
 * `maxColumnas` para no amontonar en su ancho fijo.)
 */
const _MQS_GALERIA = ["(min-width: 1700px)", "(min-width: 1280px)", "(min-width: 768px)", "(min-width: 640px)"];
function _columnasViewport(): number {
  if (typeof window.matchMedia !== "function") return 2; // jsdom sin matchMedia
  if (window.matchMedia("(min-width: 1700px)").matches) return 6;
  if (window.matchMedia("(min-width: 1280px)").matches) return 5;
  if (window.matchMedia("(min-width: 768px)").matches) return 4;
  if (window.matchMedia("(min-width: 640px)").matches) return 3;
  return 2;
}

export function useColumnasGaleria(): number {
  const [columnas, setColumnas] = useState(_columnasViewport);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mqs = _MQS_GALERIA.map((q) => window.matchMedia(q));
    const alCambiar = () => setColumnas(_columnasViewport());
    mqs.forEach((m) => m.addEventListener("change", alCambiar));
    return () => mqs.forEach((m) => m.removeEventListener("change", alCambiar));
  }, []);
  return columnas;
}

/** Barra de búsqueda de plantillas (por nombre o categoría). */
export function BuscadorPlantillas({
  valor,
  onCambiar,
  placeholder = "Buscar plantillas…",
}: {
  valor: string;
  onCambiar: (q: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <input
        type="search"
        role="searchbox"
        aria-label="Buscar plantillas"
        value={valor}
        onChange={(e) => onCambiar(e.target.value)}
        placeholder={placeholder}
        className="h-8 w-full rounded-md border border-input bg-background pl-8 pr-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring"
      />
    </div>
  );
}

/**
 * Chips de categoría en carrusel horizontal (estilo Canva): «Todas» primero y después SOLO las
 * categorías presentes en los datos. Con menos de 2 categorías no se renderiza (sería irrelevante).
 */
export function ChipsCategoria({
  categorias,
  activa,
  onCambiar,
}: {
  categorias: string[];
  activa: string; // "" = todas
  onCambiar: (slug: string) => void;
}) {
  if (categorias.length < 2) return null;
  const chip = (slug: string, etiqueta: string) => {
    const activo = activa === slug;
    return (
      <button
        key={slug || "__todas__"}
        type="button"
        aria-pressed={activo}
        onClick={() => onCambiar(slug)}
        className={`shrink-0 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
          activo
            ? "border-primary bg-primary text-primary-foreground"
            : "border-border text-muted-foreground hover:bg-accent hover:text-foreground"
        }`}
      >
        {etiqueta}
      </button>
    );
  };
  return (
    <div className="flex gap-1.5 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {chip("", "Todas")}
      {categorias.map((slug) => chip(slug, etiquetaCategoria(slug)))}
    </div>
  );
}

/** Quita acentos y baja a minúsculas (para filtrar acento-insensible). */
function _sinAcentos(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

/**
 * Selector EDITABLE de categoría con el diseño de la plataforma (NO el `<select>` nativo del SO):
 * un panel portaleado —para que no lo recorte el `overflow` de la galería— con buscador arriba que
 * FILTRA el catálogo y, como la categoría es texto libre, permite CREAR una etiqueta nueva
 * escribiéndola. Teclado completo (flechas/Enter/Esc) y cierre por clic-fuera/scroll. Mismos tokens
 * visuales que `ui/select` (`bg-popover`, `border`, `shadow-md`, check de la activa).
 */
function SelectorCategoria({
  slug,
  etiqueta,
  onCambiar,
  children,
}: {
  slug: string;
  etiqueta: string;
  onCambiar: (valor: string) => void;
  children: ReactNode;
}) {
  const [abierto, setAbierto] = useState(false);
  const [query, setQuery] = useState("");
  const [activo, setActivo] = useState(0);
  const [pos, setPos] = useState<{ left: number; top?: number; bottom?: number; maxH: number } | null>(
    null,
  );
  const refTrigger = useRef<HTMLButtonElement>(null);
  const refPanel = useRef<HTMLDivElement>(null);
  const refInput = useRef<HTMLInputElement>(null);

  // Opciones: catálogo completo + el valor libre actual (si no está en el catálogo), filtradas por
  // el buscador (acento-insensible, por etiqueta y por slug).
  const opciones = useMemo(() => {
    const enCatalogo = CATEGORIAS_PLANTILLA.some((c) => c.slug === slug);
    const base = enCatalogo ? CATEGORIAS_PLANTILLA : [{ slug, etiqueta }, ...CATEGORIAS_PLANTILLA];
    const q = _sinAcentos(query);
    if (!q) return base;
    const qSlug = normalizarCategoria(query);
    return base.filter((c) => _sinAcentos(c.etiqueta).includes(q) || c.slug.includes(qSlug));
  }, [slug, etiqueta, query]);

  const queryTrim = query.trim();
  const slugNuevo = normalizarCategoria(queryTrim);
  const existe =
    !slugNuevo ||
    slugNuevo === slug ||
    CATEGORIAS_PLANTILLA.some((c) => c.slug === slugNuevo);
  const mostrarCrear = !!queryTrim && !existe;
  // Lista navegable por teclado: opciones + (fila «Crear» si procede).
  const navegables = mostrarCrear ? [...opciones.map((o) => o.slug), " crear"] : opciones.map((o) => o.slug);

  function abrir() {
    const r = refTrigger.current?.getBoundingClientRect();
    if (!r) return;
    const W = 240;
    let left = r.left;
    if (left + W > window.innerWidth - 8) left = window.innerWidth - W - 8;
    if (left < 8) left = 8;
    const abajo = window.innerHeight - r.bottom;
    const arriba = r.top;
    if (abajo >= 240 || abajo >= arriba) {
      setPos({ left, top: r.bottom + 4, maxH: Math.max(180, abajo - 12) });
    } else {
      setPos({ left, bottom: window.innerHeight - r.top + 4, maxH: Math.max(180, arriba - 12) });
    }
    setQuery("");
    setActivo(0);
    setAbierto(true);
  }
  function cerrar() {
    setAbierto(false);
  }
  function elegir(valor: string) {
    onCambiar(valor);
    cerrar();
  }

  // Reinicia el resaltado al cambiar el filtro.
  useEffect(() => {
    setActivo(0);
  }, [query]);

  // Enfoca el buscador al abrir.
  useEffect(() => {
    if (abierto) refInput.current?.focus();
  }, [abierto]);

  // Cierre por clic-fuera / scroll / resize mientras está abierto.
  useEffect(() => {
    if (!abierto) return;
    const fuera = (e: MouseEvent) => {
      const t = e.target as Node;
      if (refPanel.current?.contains(t) || refTrigger.current?.contains(t)) return;
      cerrar();
    };
    // El scroll DENTRO de la propia lista de opciones no debe cerrar (la lista desborda y se
    // desplaza); solo cierra el scroll de la página/galería bajo el panel.
    const alScroll = (e: Event) => {
      if (e.target instanceof Node && refPanel.current?.contains(e.target)) return;
      cerrar();
    };
    document.addEventListener("mousedown", fuera, true);
    window.addEventListener("scroll", alScroll, true);
    window.addEventListener("resize", cerrar);
    return () => {
      document.removeEventListener("mousedown", fuera, true);
      window.removeEventListener("scroll", alScroll, true);
      window.removeEventListener("resize", cerrar);
    };
  }, [abierto]);

  function alTeclear(e: ReactKeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActivo((i) => Math.min(i + 1, navegables.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActivo((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const sel = navegables[activo];
      if (sel === " crear") elegir(queryTrim);
      else if (sel) elegir(sel);
      else if (mostrarCrear) elegir(queryTrim);
    } else if (e.key === "Escape") {
      e.preventDefault();
      cerrar();
    }
  }

  const idxCrear = opciones.length; // posición de la fila «Crear» en la lista navegable

  return (
    <>
      <button
        ref={refTrigger}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={abierto}
        title="Cambiar categoría"
        onClick={(e) => {
          e.stopPropagation();
          if (abierto) cerrar();
          else abrir();
        }}
      >
        {children}
      </button>
      {abierto &&
        pos &&
        createPortal(
          <div
            ref={refPanel}
            role="listbox"
            onClick={(e) => e.stopPropagation()}
            className="fixed z-50 flex w-60 flex-col overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-md"
            style={{ left: pos.left, top: pos.top, bottom: pos.bottom, maxHeight: pos.maxH }}
          >
            <div className="relative border-b border-border p-1.5">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                ref={refInput}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={alTeclear}
                placeholder="Buscar o crear etiqueta…"
                className="h-8 w-full rounded-sm bg-transparent pl-7 pr-2 text-sm outline-none placeholder:text-muted-foreground"
              />
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-1">
              {opciones.map((c, i) => {
                const sel = c.slug === slug;
                return (
                  <button
                    key={c.slug}
                    type="button"
                    role="option"
                    aria-selected={sel}
                    onMouseEnter={() => setActivo(i)}
                    onClick={() => elegir(c.slug)}
                    className={`flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm ${
                      activo === i ? "bg-accent text-accent-foreground" : ""
                    }`}
                  >
                    <Check className={`h-3.5 w-3.5 shrink-0 ${sel ? "opacity-100" : "opacity-0"}`} />
                    <span className="truncate">{c.etiqueta}</span>
                  </button>
                );
              })}
              {mostrarCrear && (
                <button
                  type="button"
                  role="option"
                  onMouseEnter={() => setActivo(idxCrear)}
                  onClick={() => elegir(queryTrim)}
                  className={`flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm ${
                    activo === idxCrear ? "bg-accent text-accent-foreground" : ""
                  }`}
                >
                  <Plus className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">
                    Crear «{etiquetaCategoria(queryTrim)}»
                  </span>
                </button>
              )}
              {opciones.length === 0 && !mostrarCrear && (
                <p className="px-2 py-1.5 text-sm text-muted-foreground">Sin coincidencias</p>
              )}
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

/**
 * Badge de categoría en la tarjeta. Con `onCambiar` (modo GESTIÓN) el badge es el disparador de un
 * selector EDITABLE con el diseño de la plataforma ({@link SelectorCategoria}): elegir del catálogo
 * o escribir una etiqueta nueva, sin el `<select>` nativo del SO.
 */
export function BadgeCategoria({
  categoria,
  onCambiar,
}: {
  categoria?: string | null;
  onCambiar?: (slug: string) => void;
}) {
  const slug = normalizarCategoria(categoria);
  const etiqueta = etiquetaCategoria(slug);
  const badge = (
    <span
      className={`inline-flex max-w-full shrink items-center gap-0.5 truncate rounded bg-muted px-1 py-0.5 text-[10px] font-medium text-muted-foreground ${
        onCambiar ? "group-hover/badge:text-foreground" : ""
      }`}
    >
      <Tag className="h-2.5 w-2.5 shrink-0" />
      <span className="truncate">{etiqueta}</span>
      {onCambiar && <ChevronDown className="h-2.5 w-2.5 shrink-0 opacity-60" />}
    </span>
  );
  if (!onCambiar) return badge;
  return (
    <span className="group/badge inline-flex min-w-0">
      <SelectorCategoria slug={slug} etiqueta={etiqueta} onCambiar={onCambiar}>
        {badge}
      </SelectorCategoria>
    </span>
  );
}
