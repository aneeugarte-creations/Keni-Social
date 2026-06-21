// Piezas COMPARTIDAS de la organización de plantillas estilo Canva (galería inline del editor y
// galería modal): barra de búsqueda + chips de categoría horizontales + badge de categoría en
// tarjeta + rejilla MASONRY con carga perezosa por lotes. El catálogo y la normalización viven
// en `lib/categoriasPlantilla.ts`.

import { Check, ChevronDown, Pencil, Plus, Search, Tag, Trash2, X } from "lucide-react";
import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import type { PlantillaDiseno } from "@/lib/api";
import {
  CATEGORIA_GENERAL,
  categoriasPresentes,
  coincideBusqueda,
  etiquetaCategoria,
  normalizarCategoria,
  opcionesCategoria,
  type CatalogoEtiquetas,
} from "@/lib/categoriasPlantilla";

/**
 * Estado de filtrado client-side de una galería: búsqueda (nombre/categoría, acento-insensible) +
 * chip de categoría activa. Los chips salen de las categorías PRESENTES en los datos (lista
 * completa, no la filtrada: así no desaparecen al buscar).
 */
export function useFiltroPlantillas(plantillas: PlantillaDiseno[], catalogo?: CatalogoEtiquetas) {
  const [q, setQ] = useState("");
  const [categoria, setCategoria] = useState(""); // "" = chip «Todas»
  const presentes = useMemo(() => categoriasPresentes(plantillas), [plantillas]);
  const filtradas = useMemo(
    () =>
      plantillas.filter(
        (p) =>
          (!categoria || normalizarCategoria(p.categoria) === categoria) &&
          coincideBusqueda(p, q, catalogo),
      ),
    [plantillas, q, categoria, catalogo],
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
        className="h-9 w-full rounded-lg border border-transparent bg-muted/60 pl-8 pr-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-border"
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
  catalogo,
}: {
  categorias: string[];
  activa: string; // "" = todas
  onCambiar: (slug: string) => void;
  catalogo?: CatalogoEtiquetas;
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
        className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium transition-colors ${
          activo
            ? "bg-secondary text-foreground"
            : "text-muted-foreground hover:bg-muted hover:text-foreground"
        }`}
      >
        {etiqueta}
      </button>
    );
  };
  return (
    <div className="flex gap-1.5 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {chip("", "Todas")}
      {categorias.map((slug) => chip(slug, etiquetaCategoria(slug, catalogo)))}
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
 * Mini-editor EDITABLE de tarjeta con el diseño de la plataforma (NO el `<select>` nativo del SO):
 * un panel portaleado —para que no lo recorte el `overflow` de la galería— que permite, EN EL MISMO
 * sitio, (1) editar el NOMBRE/título de la plantilla (si llega `onRenombrar`) y (2) elegir la
 * etiqueta del catálogo o CREAR una nueva escribiéndola (la categoría es texto libre). Teclado
 * completo (flechas/Enter/Esc) y cierre por clic-fuera/scroll. Mismos tokens visuales que `ui/select`
 * (`bg-popover`, `border`, `shadow-md`, check de la activa).
 */
function SelectorCategoria({
  slug,
  slugsPresentes,
  onCambiar,
  nombre,
  onRenombrar,
  catalogo,
  onRenombrarEtiqueta,
  onCrearEtiqueta,
  onBorrarEtiqueta,
  children,
}: {
  slug: string;
  slugsPresentes: string[];
  onCambiar: (valor: string) => void;
  nombre?: string;
  onRenombrar?: (nombre: string) => void;
  // Catálogo de etiquetas de la marca (rótulos personalizados + slugs gestionados).
  catalogo?: CatalogoEtiquetas;
  // Modo GESTIÓN del catálogo: renombrar el RÓTULO de una etiqueta (no mueve plantillas), crear una
  // etiqueta nueva persistiendo su rótulo, y borrar el rótulo. La marca es implícita (la de la pieza).
  onRenombrarEtiqueta?: (slug: string, etiqueta: string) => void;
  onCrearEtiqueta?: (etiqueta: string) => void;
  onBorrarEtiqueta?: (slug: string) => void;
  children: ReactNode;
}) {
  const [abierto, setAbierto] = useState(false);
  const [query, setQuery] = useState("");
  const [nombreEdit, setNombreEdit] = useState("");
  const [activo, setActivo] = useState(0);
  // Renombrado inline del RÓTULO de una etiqueta de la lista (lápiz por fila, modo gestión).
  const [renEt, setRenEt] = useState<{ slug: string; valor: string } | null>(null);
  // Creación de etiqueta: campo APARTE del buscador (botón «Crear etiqueta» → input). No se mezcla
  // con la búsqueda para que cada acción sea inequívoca.
  const [creando, setCreando] = useState(false);
  const [nuevaEtiqueta, setNuevaEtiqueta] = useState("");
  const [pos, setPos] = useState<{ left: number; top?: number; bottom?: number; maxH: number } | null>(
    null,
  );
  const refTrigger = useRef<HTMLButtonElement>(null);
  const refPanel = useRef<HTMLDivElement>(null);
  const refInput = useRef<HTMLInputElement>(null);
  const refCrear = useRef<HTMLInputElement>(null);
  // Último nombre ENVIADO en esta apertura: evita un segundo PATCH idéntico (blur + cierre).
  const refUltimoNombre = useRef<string | null>(null);
  // Siempre apunta al `cerrar` del último render: los handlers de clic-fuera/scroll se suscriben
  // solo al abrir (deps [abierto]) y, sin esto, cerrarían con un `nombreEdit` viejo (capturado al
  // abrir) → el nombre tecleado se perdería al clicar fuera. Con el ref persisten el valor actual.
  const refCerrar = useRef<() => void>(() => {});
  const idNombre = useId();
  const idEtiqueta = useId();

  // Opciones: catálogo + las etiquetas creadas en otras piezas (`slugsPresentes`) + la etiqueta de
  // la pieza actual, filtradas por el buscador (acento-insensible, por etiqueta y por slug).
  const opciones = useMemo(() => {
    const base = opcionesCategoria(slugsPresentes, slug, catalogo);
    const q = _sinAcentos(query);
    if (!q) return base;
    const qSlug = normalizarCategoria(query);
    return base.filter((c) => _sinAcentos(c.etiqueta).includes(q) || c.slug.includes(qSlug));
  }, [slug, slugsPresentes, query, catalogo]);

  // ¿Modo gestión del catálogo? (renombrar/crear/borrar el RÓTULO de las etiquetas de la lista).
  const gestionEtiquetas = !!onRenombrarEtiqueta;

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
    setNombreEdit(nombre ?? "");
    refUltimoNombre.current = null;
    setCreando(false);
    setNuevaEtiqueta("");
    setActivo(0);
    setAbierto(true);
  }
  // Persiste el nombre si cambió (no vacío, distinto del original y no reenviado). Se llama al
  // cerrar por cualquier vía, así un nombre tecleado no se pierde al clicar fuera o elegir etiqueta.
  function commitNombre() {
    if (!onRenombrar) return;
    const n = nombreEdit.trim();
    if (!n || n === (nombre ?? "") || refUltimoNombre.current === n) return;
    refUltimoNombre.current = n;
    onRenombrar(n);
  }
  function cerrar() {
    commitNombre();
    setAbierto(false);
  }
  refCerrar.current = cerrar;
  function elegir(valor: string) {
    onCambiar(valor);
    cerrar();
  }
  // Crear etiqueta nueva: acción SEPARADA del buscador. El botón abre un campo propio; confirmar
  // crea la etiqueta (el back normaliza el texto a slug) y cierra.
  function abrirCrear() {
    setNuevaEtiqueta("");
    setCreando(true);
  }
  function cancelarCrear() {
    setCreando(false);
    setNuevaEtiqueta("");
  }
  function confirmarCrear() {
    const n = nuevaEtiqueta.trim();
    if (!n) return;
    // En gestión, crear persiste el rótulo (preserva acentos/mayúsculas) y asigna; si no, solo asigna.
    if (onCrearEtiqueta) {
      onCrearEtiqueta(n);
      cerrar();
    } else {
      elegir(n);
    }
  }
  // Confirma el renombrado del RÓTULO de una etiqueta de la lista (no cierra: permite encadenar).
  function commitRenEt() {
    if (!renEt) return;
    const valor = renEt.valor.trim();
    const objetivo = renEt.slug;
    setRenEt(null);
    if (valor && valor !== etiquetaCategoria(objetivo, catalogo)) onRenombrarEtiqueta?.(objetivo, valor);
  }
  function alTeclearCrear(e: ReactKeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      e.stopPropagation();
      confirmarCrear();
    } else if (e.key === "Escape") {
      // Cancela SOLO el creador, sin cerrar el popover.
      e.preventDefault();
      e.stopPropagation();
      cancelarCrear();
    }
  }
  function alTeclearNombre(e: ReactKeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      e.stopPropagation();
      cerrar();
    } else if (e.key === "Escape") {
      // Descarta el nombre tecleado: reset al original y cierra SIN commit.
      e.preventDefault();
      e.stopPropagation();
      setNombreEdit(nombre ?? "");
      setAbierto(false);
    }
  }

  // Reinicia el resaltado al cambiar el filtro.
  useEffect(() => {
    setActivo(0);
  }, [query]);

  // Enfoca el buscador al abrir.
  useEffect(() => {
    if (abierto) refInput.current?.focus();
  }, [abierto]);

  // Enfoca el campo de creación al abrirlo.
  useEffect(() => {
    if (creando) refCrear.current?.focus();
  }, [creando]);

  // Cierre por clic-fuera / scroll / resize mientras está abierto. Cierra vía `refCerrar.current`
  // (último render) para no perder el nombre tecleado por un closure obsoleto.
  useEffect(() => {
    if (!abierto) return;
    const cerrarYa = () => refCerrar.current();
    const fuera = (e: MouseEvent) => {
      const t = e.target as Node;
      if (refPanel.current?.contains(t) || refTrigger.current?.contains(t)) return;
      cerrarYa();
    };
    // El scroll DENTRO de la propia lista de opciones no debe cerrar (la lista desborda y se
    // desplaza); solo cierra el scroll de la página/galería bajo el panel.
    const alScroll = (e: Event) => {
      if (e.target instanceof Node && refPanel.current?.contains(e.target)) return;
      cerrarYa();
    };
    document.addEventListener("mousedown", fuera, true);
    window.addEventListener("scroll", alScroll, true);
    window.addEventListener("resize", cerrarYa);
    return () => {
      document.removeEventListener("mousedown", fuera, true);
      window.removeEventListener("scroll", alScroll, true);
      window.removeEventListener("resize", cerrarYa);
    };
  }, [abierto]);

  function alTeclear(e: ReactKeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActivo((i) => Math.min(i + 1, opciones.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActivo((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const sel = opciones[activo]?.slug;
      if (sel) elegir(sel);
    } else if (e.key === "Escape") {
      e.preventDefault();
      cerrar();
    }
  }

  return (
    <>
      <button
        ref={refTrigger}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={abierto}
        title={onRenombrar ? "Editar nombre y etiqueta" : "Cambiar categoría"}
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
            role="dialog"
            aria-label="Editar plantilla"
            onClick={(e) => e.stopPropagation()}
            className="fixed z-50 flex w-60 flex-col overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-md"
            style={{ left: pos.left, top: pos.top, bottom: pos.bottom, maxHeight: pos.maxH }}
          >
            {onRenombrar && (
              <div className="border-b border-border p-2">
                <label
                  htmlFor={idNombre}
                  className="mb-1 block text-[11px] font-medium text-muted-foreground"
                >
                  Nombre
                </label>
                <input
                  id={idNombre}
                  value={nombreEdit}
                  onChange={(e) => setNombreEdit(e.target.value)}
                  onKeyDown={alTeclearNombre}
                  onBlur={commitNombre}
                  placeholder="Nombre de la plantilla"
                  className="h-8 w-full rounded-sm border border-input bg-background px-2 text-sm outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>
            )}
            <div className="border-b border-border p-1.5">
              {onRenombrar && (
                <label
                  htmlFor={idEtiqueta}
                  className="mb-1 block px-0.5 text-[11px] font-medium text-muted-foreground"
                >
                  Etiqueta
                </label>
              )}
              {/* Crear etiqueta nueva: acción APARTE del buscador (campo propio). */}
              {creando ? (
                <div className="mb-1.5 flex items-center gap-1">
                  <input
                    ref={refCrear}
                    value={nuevaEtiqueta}
                    onChange={(e) => setNuevaEtiqueta(e.target.value)}
                    onKeyDown={alTeclearCrear}
                    aria-label="Nombre de la etiqueta nueva"
                    placeholder="Nombre de la etiqueta…"
                    className="h-8 min-w-0 flex-1 rounded-sm border border-input bg-background px-2 text-sm outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                  <button
                    type="button"
                    onClick={confirmarCrear}
                    disabled={!nuevaEtiqueta.trim()}
                    title="Crear etiqueta"
                    className="grid h-8 w-8 shrink-0 place-items-center rounded-sm border border-input bg-background text-foreground hover:bg-accent disabled:opacity-40"
                  >
                    <Check className="h-4 w-4" />
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={abrirCrear}
                  className="mb-1.5 flex h-8 w-full items-center justify-center gap-1.5 rounded-sm border border-input bg-background text-sm text-foreground hover:bg-accent"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Crear etiqueta
                </button>
              )}
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  id={idEtiqueta}
                  ref={refInput}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={alTeclear}
                  placeholder="Buscar etiqueta…"
                  className="h-8 w-full rounded-sm bg-transparent pl-7 pr-2 text-sm outline-none placeholder:text-muted-foreground"
                />
              </div>
            </div>
            <div role="listbox" aria-label="Etiquetas" className="min-h-0 flex-1 overflow-y-auto p-1">
              {opciones.map((c, i) => {
                const sel = c.slug === slug;
                // Renombrado inline del rótulo (modo gestión): input + confirmar/cancelar.
                if (gestionEtiquetas && renEt?.slug === c.slug) {
                  return (
                    <div key={c.slug} className="mb-0.5 flex items-center gap-1 px-1">
                      <input
                        autoFocus
                        aria-label="Renombrar etiqueta"
                        value={renEt.valor}
                        onChange={(e) => setRenEt({ slug: c.slug, valor: e.target.value })}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); commitRenEt(); }
                          else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setRenEt(null); }
                        }}
                        className="h-7 min-w-0 flex-1 rounded-sm border border-primary bg-background px-2 text-sm outline-none"
                      />
                      <button
                        type="button"
                        onClick={commitRenEt}
                        title="Guardar nombre"
                        className="grid h-7 w-7 shrink-0 place-items-center rounded-sm border border-input bg-background hover:bg-accent"
                      >
                        <Check className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setRenEt(null)}
                        title="Cancelar"
                        className="grid h-7 w-7 shrink-0 place-items-center rounded-sm border border-input bg-background hover:bg-accent"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  );
                }
                return (
                  <div
                    key={c.slug}
                    onMouseEnter={() => setActivo(i)}
                    className={`group/opt flex items-center rounded-sm ${
                      activo === i ? "bg-accent text-accent-foreground" : ""
                    }`}
                  >
                    <button
                      type="button"
                      role="option"
                      aria-selected={sel}
                      onClick={() => elegir(c.slug)}
                      className="flex min-w-0 flex-1 items-center gap-2 px-2 py-1.5 text-left text-sm"
                    >
                      <Check className={`h-3.5 w-3.5 shrink-0 ${sel ? "opacity-100" : "opacity-0"}`} />
                      <span className="truncate">{c.etiqueta}</span>
                    </button>
                    {gestionEtiquetas && (
                      // Acciones de la etiqueta (renombrar/borrar el rótulo): visibles al hover/foco.
                      <span className="flex shrink-0 items-center gap-0.5 pr-1 opacity-0 focus-within:opacity-100 group-hover/opt:opacity-100">
                        <button
                          type="button"
                          title="Renombrar etiqueta"
                          aria-label={`Renombrar ${c.etiqueta}`}
                          onClick={(e) => { e.stopPropagation(); setRenEt({ slug: c.slug, valor: c.etiqueta }); }}
                          className="grid h-6 w-6 place-items-center rounded-sm text-muted-foreground hover:bg-background hover:text-foreground"
                        >
                          <Pencil className="h-3 w-3" />
                        </button>
                        {onBorrarEtiqueta && c.slug !== CATEGORIA_GENERAL && (
                          <button
                            type="button"
                            title="Borrar etiqueta"
                            aria-label={`Borrar ${c.etiqueta}`}
                            onClick={(e) => { e.stopPropagation(); onBorrarEtiqueta(c.slug); }}
                            className="grid h-6 w-6 place-items-center rounded-sm text-muted-foreground hover:bg-background hover:text-destructive"
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        )}
                      </span>
                    )}
                  </div>
                );
              })}
              {opciones.length === 0 && (
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
 * mini-editor con el diseño de la plataforma ({@link SelectorCategoria}): elegir del catálogo o
 * escribir una etiqueta nueva y —si llega `onRenombrar`— editar AHÍ MISMO el nombre/título de la
 * plantilla, sin el `<select>` nativo del SO.
 */
export function BadgeCategoria({
  categoria,
  onCambiar,
  nombre,
  onRenombrar,
  slugsPresentes = [],
  catalogo,
  onRenombrarEtiqueta,
  onCrearEtiqueta,
  onBorrarEtiqueta,
}: {
  categoria?: string | null;
  onCambiar?: (slug: string) => void;
  nombre?: string;
  onRenombrar?: (nombre: string) => void;
  // Etiquetas presentes en TODA la galería: para que una creada en otra pieza se pueda asignar aquí.
  slugsPresentes?: string[];
  // Catálogo de etiquetas de la marca de la pieza (rótulos personalizados) + gestión del catálogo.
  catalogo?: CatalogoEtiquetas;
  onRenombrarEtiqueta?: (slug: string, etiqueta: string) => void;
  onCrearEtiqueta?: (etiqueta: string) => void;
  onBorrarEtiqueta?: (slug: string) => void;
}) {
  const slug = normalizarCategoria(categoria);
  const etiqueta = etiquetaCategoria(slug, catalogo);
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
      <SelectorCategoria
        slug={slug}
        slugsPresentes={slugsPresentes}
        onCambiar={onCambiar}
        nombre={nombre}
        onRenombrar={onRenombrar}
        catalogo={catalogo}
        onRenombrarEtiqueta={onRenombrarEtiqueta}
        onCrearEtiqueta={onCrearEtiqueta}
        onBorrarEtiqueta={onBorrarEtiqueta}
      >
        {badge}
      </SelectorCategoria>
    </span>
  );
}
