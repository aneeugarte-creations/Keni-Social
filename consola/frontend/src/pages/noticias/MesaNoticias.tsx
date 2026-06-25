/**
 * MesaNoticias — la vista de CANDIDATAS segmentada por las líneas del plan.
 *
 * El layout ES el plan del día: una sección por línea con sus top candidatas rankeadas.
 * Última hora va primero con sus tarjetas en rojo; lo que el plan no contempla queda
 * plegado en "Fuera del plan". Una sección con cupo sin cubrir y pocas candidatas ES la
 * alerta visual: ahí hay que mirar.
 *
 * Datos: GET /api/noticias/mesa (un solo payload con líneas + cupos + progreso + top-N).
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronDown, ChevronRight, Layers, Newspaper, X } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { api, mensajeError } from "@/lib/api";
import { etiquetaCategoria } from "@/lib/categorias";
import { cn } from "@/lib/utils";
import type { CategoriaGrupo, GrupoMesa, Historia, MesaCategoria } from "@/types";

import { TarjetaHistoria } from "./TarjetaHistoria";

/** Refresco automático de la mesa (sensación "live", igual que la lista clásica). */
const REFETCH_INTERVAL_MS = 45_000;

/** Candidatas visibles por sección en el resumen de la Mesa (el resto se recorre paginado). */
const POR_LINEA_PLEGADO = 5;

/** Candidatas por página en la lista paginada de una línea (igual que la lista plana admin). */
const PAGE_SIZE = 30;

/** Clave del reparto de la Mesa para «Fuera del plan» (el back acepta este alias). */
const LINEA_FUERA = "__fuera__";

export const CLAVE_MESA = (marca: string, porLinea: number) =>
  ["noticias", "mesa", marca, porLinea] as const;

export const CLAVE_MESA_LINEA = (marca: string, linea: string, offset: number) =>
  ["noticias", "mesa", "linea", marca, linea, offset] as const;

// ── Barra de navegación por GRUPO (con 2º nivel de LÍNEAS) ─────────────────────

const ANCHO_MENU = 352; // ancho del desplegable de líneas (px), para acotar su anclaje

/** Un chip de la barra de categorías: nombre + conteo (+ chevron si despliega líneas). */
function ChipGrupo({
  etiqueta,
  n,
  activo,
  abierto,
  despliega,
  onClick,
}: {
  etiqueta: string;
  n: number;
  activo: boolean;
  abierto?: boolean;
  despliega?: boolean;
  onClick: (e: React.MouseEvent<HTMLButtonElement>) => void;
}) {
  return (
    <button
      type="button"
      aria-haspopup={despliega ? "menu" : undefined}
      aria-expanded={despliega ? abierto : undefined}
      onClick={onClick}
      data-testid={`chip-grupo-${etiqueta}`}
      className={cn(
        // Texto plano: sin borde, fondo ni píldora en ningún estado; el activo se distingue solo
        // por oscurecer y engrosar la etiqueta. Lo más sobrio (estética Geist gris/negro).
        "flex shrink-0 items-center gap-1 whitespace-nowrap py-1 text-sm transition-colors",
        activo ? "font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
      )}
    >
      <span>{etiqueta}</span>
      {n > 0 && (
        <span
          className="tabular-nums text-xs text-muted-foreground/55"
          title={`${n} en el pool`}
        >
          {n}
        </span>
      )}
      {despliega && (
        <ChevronDown
          className={cn(
            "h-3 w-3 text-muted-foreground/40 transition-transform",
            abierto && "rotate-180",
          )}
        />
      )}
    </button>
  );
}

/** Un ítem del desplegable de líneas: nombre + conteo; atenuado si no tiene candidatas. */
function ItemLinea({
  etiqueta,
  n,
  activo,
  atenuada,
  full,
  onClick,
}: {
  etiqueta: string;
  n: number;
  activo: boolean;
  atenuada?: boolean;
  full?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={activo}
      onClick={onClick}
      className={cn(
        "flex w-full items-center justify-between gap-3 rounded-md px-2.5 py-1.5 text-left text-xs transition-colors",
        full && "col-span-2",
        activo
          ? "bg-muted font-medium text-foreground"
          : atenuada
            ? "text-muted-foreground/45 hover:bg-muted/60"
            : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
      )}
    >
      <span className="truncate">{etiqueta}</span>
      {n > 0 && <span className="shrink-0 tabular-nums text-[11px] text-muted-foreground">{n}</span>}
    </button>
  );
}

/** Desplegable con las líneas de un grupo (2º nivel): "Todas" + una por línea, en rejilla. */
function MenuLineas({
  grupo,
  lineas,
  total,
  lineaSel,
  left,
  panelRef,
  onSel,
}: {
  grupo: string;
  lineas: CategoriaGrupo[];
  total: number;
  lineaSel: string;
  left: number;
  panelRef: React.RefObject<HTMLDivElement>;
  onSel: (linea: string) => void;
}) {
  return (
    <div
      ref={panelRef}
      role="menu"
      aria-label={`Líneas de ${grupo}`}
      data-testid={`menu-lineas-${grupo}`}
      className="absolute top-full z-20 mt-1 w-[22rem] max-w-[88vw] rounded-xl border border-border bg-card p-1 shadow-lg"
      style={{ left }}
    >
      <div className="px-2 pb-1 pt-1 text-[11px] uppercase tracking-wide text-muted-foreground/60">
        {grupo}
      </div>
      <div className="grid max-h-[60vh] grid-cols-2 gap-0.5 overflow-y-auto">
        <ItemLinea etiqueta={`Todas las de ${grupo}`} n={total} activo={lineaSel === ""} full onClick={() => onSel("")} />
        {lineas.map((l) => (
          <ItemLinea
            key={l.linea}
            etiqueta={l.nombre}
            n={l.en_pool}
            activo={lineaSel === l.linea}
            atenuada={l.en_pool === 0}
            onClick={() => onSel(l.linea)}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * Navegación por chips de la Mesa (todas las marcas): chip "Todas" + uno por categoría. Una
 * categoría con líneas (marca con grupos, p. ej. Claro Sports) las despliega en un menú que cae
 * bajo el chip; elegir una línea afina el filtro y deja un indicador con la línea activa. Un chip
 * SIN líneas (marca plana, p. ej. UnoTV/Fundación) solo filtra, sin desplegable. El menú se cierra
 * al pulsar fuera o con Escape (sin backdrop: los chips siguen clicables para saltar de categoría).
 */
export function NavGruposLineas({
  grupos,
  total,
  grupoSel,
  lineaSel,
  onSelGrupo,
  onSelLinea,
}: {
  grupos: GrupoMesa[];
  total: number;
  grupoSel: string;
  lineaSel: string;
  onSelGrupo: (g: string) => void;
  onSelLinea: (g: string, linea: string) => void;
}) {
  const [menu, setMenu] = React.useState<string | null>(null);
  const [left, setLeft] = React.useState(0);
  const wrapRef = React.useRef<HTMLDivElement>(null);
  const navRef = React.useRef<HTMLDivElement>(null);
  const panelRef = React.useRef<HTMLDivElement>(null);

  // Cierre por click-fuera / Escape. Sin elemento backdrop para que un clic en otro chip cambie de
  // grupo directamente (el listener ignora lo que cae dentro de la barra o del propio menú).
  React.useEffect(() => {
    if (!menu) return;
    const fuera = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!panelRef.current?.contains(t) && !navRef.current?.contains(t)) setMenu(null);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenu(null);
    };
    document.addEventListener("mousedown", fuera);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fuera);
      document.removeEventListener("keydown", esc);
    };
  }, [menu]);

  // Pulsar un chip: si despliega líneas (marca con grupos) abre/cierra su menú; si es un chip plano
  // (marca sin grupos) solo filtra por esa categoría, sin desplegable.
  const onChip = (g: string, tieneLineas: boolean, e: React.MouseEvent<HTMLButtonElement>) => {
    if (!tieneLineas) {
      setMenu(null);
      onSelGrupo(g);
      return;
    }
    if (menu === g) {
      setMenu(null); // segundo clic en el grupo abierto: solo cierra el menú (mantiene el filtro)
      return;
    }
    const wrap = wrapRef.current;
    if (wrap) {
      const x = e.currentTarget.getBoundingClientRect().left - wrap.getBoundingClientRect().left;
      const tope = Math.max(0, wrap.clientWidth - Math.min(ANCHO_MENU, wrap.clientWidth));
      setLeft(Math.min(Math.max(0, x), tope));
    }
    onSelGrupo(g);
    setMenu(g);
  };

  const grupoMenu = grupos.find((g) => g.grupo === menu) ?? null;
  const grupoFiltro = grupos.find((g) => g.grupo === grupoSel) ?? null;
  const nombreLineaSel = grupoFiltro?.lineas?.find((l) => l.linea === lineaSel)?.nombre ?? lineaSel;

  return (
    <div className="space-y-2">
      <div ref={wrapRef} className="relative">
        <div
          ref={navRef}
          className="flex flex-nowrap gap-x-5 overflow-x-auto pb-1"
          aria-label="Categorías"
        >
          <ChipGrupo
            etiqueta="Todas"
            n={total}
            activo={grupoSel === ""}
            onClick={() => {
              setMenu(null);
              onSelGrupo("");
            }}
          />
          {grupos.map((g) => {
            const tieneLineas = (g.lineas?.length ?? 0) > 0;
            return (
              <ChipGrupo
                key={g.grupo}
                etiqueta={g.grupo}
                n={g.en_pool}
                activo={grupoSel === g.grupo}
                abierto={menu === g.grupo}
                despliega={tieneLineas}
                onClick={(e) => onChip(g.grupo, tieneLineas, e)}
              />
            );
          })}
        </div>
        {grupoMenu && (
          <MenuLineas
            grupo={grupoMenu.grupo}
            lineas={grupoMenu.lineas ?? []}
            total={grupoMenu.en_pool}
            lineaSel={grupoSel === grupoMenu.grupo ? lineaSel : ""}
            left={left}
            panelRef={panelRef}
            onSel={(linea) => {
              onSelLinea(grupoMenu.grupo, linea);
              setMenu(null);
            }}
          />
        )}
      </div>
      {lineaSel && grupoFiltro && (
        <div className="flex items-center gap-1.5 text-xs" data-testid="filtro-linea">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-0.5 text-foreground">
            <span className="text-muted-foreground">{grupoFiltro.grupo} ›</span>
            {nombreLineaSel}
            <button
              type="button"
              className="ml-0.5 text-muted-foreground hover:text-foreground"
              aria-label="Quitar filtro de línea"
              onClick={() => onSelLinea(grupoFiltro.grupo, "")}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        </div>
      )}
    </div>
  );
}

/**
 * Ordena por SCORE descendente (mayor relevancia primero). La lista plana de "Todas" concatena
 * las líneas una tras otra, así que sin esto quedaría en orden de línea, no de score. Copia (no
 * muta) y desempata por `ultimo_visto` para un orden estable.
 */
export function ordenarPorScore(historias: Historia[]): Historia[] {
  return [...historias].sort(
    (a, b) =>
      (b.score ?? 0) - (a.score ?? 0) ||
      (b.ultimo_visto ?? "").localeCompare(a.ultimo_visto ?? ""),
  );
}

/** Candidatas visibles según el chip y la línea elegidos ('' = sin filtrar en ese nivel). */
export function historiasDelGrupo(
  historias: Historia[],
  grupoSel: string,
  lineaSel = "",
): Historia[] {
  return historias.filter(
    (h) => (!grupoSel || h.grupo === grupoSel) && (!lineaSel || h.linea === lineaSel),
  );
}

/**
 * Para una marca SIN grupos (UnoTV, Fundación…), deriva los chips de navegación de las LÍNEAS del
 * plan: cada línea (+ «Fuera del plan» si tiene candidatas) es un chip PLANO (sin desplegable), y
 * cada candidata se etiqueta con su línea para que el filtro funcione igual que con los grupos.
 * Así la barra de chips es la misma en todas las marcas. Un chip aparece si la línea tiene
 * cupo o candidatas.
 */
export function chipsDeLineas(
  lineas: MesaCategoria[],
  fuera: { en_pool: number; historias: Historia[] },
): { chips: GrupoMesa[]; browse: Historia[] } {
  const chips: GrupoMesa[] = [];
  const browse: Historia[] = [];
  for (const l of lineas) {
    const etiqueta = l.etiqueta || etiquetaCategoria(l.linea);
    if (l.en_pool > 0 || l.cupo > 0)
      chips.push({ grupo: etiqueta, en_pool: l.en_pool, lineaId: l.linea });
    for (const h of l.historias) browse.push({ ...h, grupo: etiqueta });
  }
  if (fuera.en_pool > 0) {
    chips.push({ grupo: "Fuera del plan", en_pool: fuera.en_pool, lineaId: LINEA_FUERA });
    for (const h of fuera.historias) browse.push({ ...h, grupo: "Fuera del plan" });
  }
  return { chips, browse };
}

// ── Agrupamiento por macro-evento ──────────────────────────────────────────────

/**
 * Un bloque de la lista: o una historia suelta (sin `tema_macro`), o un grupo de
 * sub-historias que comparten el mismo macro-evento.
 */
export type BloqueLista =
  | { tipo: "suelta"; historia: Historia }
  | { tipo: "grupo"; tema: string; historias: Historia[] };

/**
 * Reparte la lista en bloques conservando el orden de ranking: las historias sin
 * macro-evento quedan sueltas en su sitio; las que comparten `tema_macro` se juntan en
 * un grupo anclado en la POSICIÓN de la primera que aparece (no se reordena el resto).
 * Un macro con una sola historia NO forma grupo: se muestra como tarjeta suelta normal.
 */
export function agruparPorMacro(historias: Historia[]): BloqueLista[] {
  const conteo = new Map<string, number>();
  for (const h of historias) {
    const t = h.tema_macro?.trim();
    if (t) conteo.set(t, (conteo.get(t) ?? 0) + 1);
  }
  const bloques: BloqueLista[] = [];
  const indiceGrupo = new Map<string, number>();
  for (const h of historias) {
    const t = h.tema_macro?.trim();
    if (t && (conteo.get(t) ?? 0) > 1) {
      const yaVisto = indiceGrupo.get(t);
      if (yaVisto === undefined) {
        indiceGrupo.set(t, bloques.length);
        bloques.push({ tipo: "grupo", tema: t, historias: [h] });
      } else {
        (bloques[yaVisto] as { historias: Historia[] }).historias.push(h);
      }
    } else {
      bloques.push({ tipo: "suelta", historia: h });
    }
  }
  return bloques;
}

/**
 * Caja de un macro-evento: cabecera colapsable con su nombre y un conteo ("Cumbre del G7 ·
 * 4 historias"). Plegada por defecto (solo la cabecera); al abrir lista sus sub-historias,
 * que a su vez salen en su forma compacta (titular/hora/fuente) y se expanden una a una.
 */
function GrupoMacro({
  tema,
  historias,
}: {
  tema: string;
  historias: Historia[];
}) {
  const [abierto, setAbierto] = React.useState(false);
  return (
    <div className="space-y-2" data-testid="grupo-macro" data-tema-macro={tema}>
      {/* Cabecera con el MISMO peso visual que una tarjeta de historia: misma Card, mismo
          padding y tamaño de título, para que el macro-evento no pase desapercibido. */}
      <Card className="text-sm transition hover:border-keni-300 focus-within:border-keni-300">
        <CardContent className="pt-3 pb-3">
          <button
            type="button"
            className="flex w-full items-center gap-2 text-left"
            onClick={() => setAbierto((v) => !v)}
            aria-expanded={abierto}
          >
            {abierto ? (
              <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            )}
            <Layers className="h-4 w-4 shrink-0 text-muted-foreground" />
            <span className="font-medium leading-snug">{tema}</span>
            <span className="font-normal tabular-nums text-muted-foreground">
              · {historias.length} historias
            </span>
          </button>
        </CardContent>
      </Card>
      {abierto && (
        <div className="space-y-2 rounded-lg border border-border bg-muted/30 p-2">
          {historias.map((h) => (
            <TarjetaHistoria key={h.id} historia={h} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Renderiza una lista de historias agrupando las que comparten macro-evento en una caja
 * colapsable (`GrupoMacro`); las historias sin macro-evento salen como tarjetas sueltas.
 */
function ListaHistorias({ historias }: { historias: Historia[] }) {
  const bloques = React.useMemo(() => agruparPorMacro(historias), [historias]);
  return (
    <div className="space-y-2">
      {bloques.map((b) =>
        b.tipo === "suelta" ? (
          <TarjetaHistoria key={b.historia.id} historia={b.historia} />
        ) : (
          <GrupoMacro key={`macro:${b.tema}`} tema={b.tema} historias={b.historias} />
        ),
      )}
    </div>
  );
}

// ── Lista paginada de UNA línea (recorre TODO el pool de la línea) ─────────────

/**
 * La LÍNEA al completo, PAGINADA: recorre TODAS las candidatas de la marca+línea (no el top-N
 * del resumen), 30 por página con anterior/siguiente y «X–Y de N» real. Reusa el patrón de
 * paginación de la lista plana admin contra el endpoint `mesa/linea`. `linea` es la clave del
 * reparto de la Mesa (id de etiqueta categoria, 'breaking'/'evergreen' o '__fuera__').
 */
function LineaPaginada({
  marca,
  linea,
  etiqueta,
  onVolver,
}: {
  marca: string;
  linea: string;
  etiqueta: string;
  onVolver: () => void;
}) {
  const [offset, setOffset] = React.useState(0);
  // Cambiar de línea reinicia la paginación (otra lista, otro total).
  React.useEffect(() => {
    setOffset(0);
  }, [marca, linea]);

  const query = useQuery({
    queryKey: CLAVE_MESA_LINEA(marca, linea, offset),
    queryFn: ({ signal }) =>
      api.noticias.mesaLinea({ marca, linea, offset, limit: PAGE_SIZE }, signal),
    staleTime: 20_000,
    refetchInterval: REFETCH_INTERVAL_MS,
    placeholderData: keepPreviousData,
  });

  const historias = query.data?.historias ?? [];
  const total = query.data?.total ?? 0;
  const hayMas = offset + PAGE_SIZE < total;
  const hayAnterior = offset > 0;

  return (
    <div className="space-y-4" data-testid={`linea-paginada-${linea}`}>
      <div className="flex flex-wrap items-baseline gap-2 border-b pb-1">
        <button
          type="button"
          className="flex items-center gap-1 text-sm font-semibold text-muted-foreground hover:text-foreground"
          onClick={onVolver}
        >
          <ArrowLeft className="h-4 w-4" />
          {etiqueta}
        </button>
        {query.data && (
          <span className="text-xs tabular-nums text-muted-foreground">
            {total.toLocaleString("es-MX")} en el pool
          </span>
        )}
        {query.isFetching && !query.isPending && (
          <Spinner className="h-3 w-3 text-muted-foreground" label="Actualizando" />
        )}
      </div>

      {query.isError ? (
        <BloqueError
          titulo="No se pudo cargar la línea"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
        />
      ) : query.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-lg" />
          ))}
        </div>
      ) : historias.length === 0 ? (
        <EstadoVacio icono={Newspaper} titulo="Sin candidatas en esta línea" />
      ) : (
        <ListaHistorias historias={historias} />
      )}

      {(hayAnterior || hayMas) && (
        <div className="flex items-center justify-between gap-3">
          <Button
            variant="outline"
            size="sm"
            disabled={!hayAnterior}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            aria-label="Página anterior de la línea"
          >
            Anterior
          </Button>
          <span className="text-xs text-muted-foreground">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} de {total.toLocaleString("es-MX")}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={!hayMas}
            onClick={() => setOffset(offset + PAGE_SIZE)}
            aria-label="Página siguiente de la línea"
            data-testid="btn-siguiente-linea"
          >
            Siguiente
          </Button>
        </div>
      )}
    </div>
  );
}

// ── Sección por línea ─────────────────────────────────────────────────────────

function SeccionLinea({
  linea,
  onAbrirLinea,
}: {
  linea: MesaCategoria;
  onAbrirLinea: (linea: string, etiqueta: string) => void;
}) {
  const etiqueta = linea.etiqueta || etiquetaCategoria(linea.linea);
  // La sección resume las top candidatas; el botón abre la lista paginada con TODO el pool de la
  // línea (cuando hay más candidatas que las visibles del resumen).
  const visibles = Math.min(linea.historias.length, linea.en_pool);
  const hayMas = linea.en_pool > linea.historias.length;
  return (
    <section className="space-y-2" data-testid={`seccion-${linea.linea}`}>
      <div className="flex flex-wrap items-baseline gap-2 border-b pb-1">
        <h3 className="text-sm font-semibold">{etiqueta}</h3>
        <span className="text-xs tabular-nums text-muted-foreground">
          {linea.generados} de {linea.cupo} hoy
        </span>
        {linea.en_pool > 0 && (
          <span className="text-xs tabular-nums text-muted-foreground/70">
            · {visibles} de {linea.en_pool} en el pool
          </span>
        )}
        {hayMas && (
          <button
            type="button"
            className="ml-auto text-xs text-muted-foreground hover:text-foreground hover:underline"
            onClick={() => onAbrirLinea(linea.linea, etiqueta)}
          >
            {`Ver las ${linea.en_pool} del pool`}
          </button>
        )}
      </div>
      {linea.historias.length === 0 ? (
        <p className="text-xs text-muted-foreground">Sin candidatas por ahora.</p>
      ) : (
        <ListaHistorias historias={linea.historias} />
      )}
    </section>
  );
}

// ── La mesa ───────────────────────────────────────────────────────────────────

export function MesaNoticias({ marca }: { marca: string; nombre: string | null }) {
  // Línea abierta en su lista PAGINADA (`{ linea, etiqueta }` = clave de reparto + rótulo) o null
  // = el resumen de la Mesa. La abre «Ver las N del pool» / un chip de línea / una línea del menú.
  const [lineaAbierta, setLineaAbierta] = React.useState<{ linea: string; etiqueta: string } | null>(
    null,
  );
  const [fueraAbierto, setFueraAbierto] = React.useState(false);
  // Categoría seleccionada en la barra de grupos ('' = Todas) y línea dentro de ella ('' = todas
  // las del grupo). Solo aplican a marcas con grupos.
  const [grupoSel, setGrupoSel] = React.useState<string>("");
  const [lineaSel, setLineaSel] = React.useState<string>("");
  // Al cambiar de marca, los filtros de la marca anterior no aplican (sus grupos/líneas no existen
  // aquí): resetéalos para no mostrar "Sin candidatas" sobre una selección huérfana.
  React.useEffect(() => {
    setGrupoSel("");
    setLineaSel("");
    setLineaAbierta(null);
    setFueraAbierto(false);
  }, [marca]);
  const clave = CLAVE_MESA(marca, POR_LINEA_PLEGADO);

  const query = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => api.noticias.mesa({ marca, porLinea: POR_LINEA_PLEGADO }, signal),
    staleTime: 20_000,
    refetchInterval: REFETCH_INTERVAL_MS,
    // El refetch no debe "bailar" las tarjetas bajo el cursor: conserva el dato anterior.
    placeholderData: keepPreviousData,
  });

  // La lista paginada de una línea es una vista de takeover: se monta sobre cualquier layout
  // (resumen del plan o navegación por chips) y vuelve con su botón.
  if (lineaAbierta) {
    return (
      <LineaPaginada
        marca={marca}
        linea={lineaAbierta.linea}
        etiqueta={lineaAbierta.etiqueta}
        onVolver={() => setLineaAbierta(null)}
      />
    );
  }

  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudo cargar la mesa"
        mensaje={mensajeError(query.error)}
        onReintentar={() => void query.refetch()}
      />
    );
  }
  if (query.isPending) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  const data = query.data;

  // NAVEGACIÓN POR CHIPS (todas las marcas): barra de categorías + lista filtrada. Los chips son los
  // GRUPOS si la marca los usa (Claro Sports: con desplegable de líneas) o las LÍNEAS del plan
  // directamente si no (UnoTV/Fundación: chips planos, sin desplegable).
  const grupos = data.grupos ?? [];
  const { chips, browse } =
    grupos.length > 0
      ? { chips: grupos, browse: data.historias_grupo ?? [] }
      : data.plan
        ? chipsDeLineas(data.categorias, data.fuera_de_plan)
        : { chips: [] as GrupoMesa[], browse: [] as Historia[] };
  if (chips.length > 0) {
    const total = chips.reduce((acc, g) => acc + g.en_pool, 0);
    const visibles = ordenarPorScore(historiasDelGrupo(browse, grupoSel, lineaSel));
    // ¿La selección actual es UNA línea concreta? Entonces se recorre PAGINADA (todo su pool), no
    // el browse en memoria. Marca con grupos: la línea del menú (`lineaSel` = id). Marca sin grupos:
    // el chip seleccionado ES una línea (`chip.lineaId`).
    const chipSel = chips.find((g) => g.grupo === grupoSel);
    let lineaActiva: { linea: string; etiqueta: string } | null = null;
    if (grupos.length > 0) {
      if (lineaSel)
        lineaActiva = {
          linea: lineaSel,
          etiqueta: chipSel?.lineas?.find((l) => l.linea === lineaSel)?.nombre ?? lineaSel,
        };
    } else if (chipSel?.lineaId) {
      lineaActiva = { linea: chipSel.lineaId, etiqueta: chipSel.grupo };
    }
    return (
      <div className="space-y-4" data-testid="mesa-grupos">
        <NavGruposLineas
          grupos={chips}
          total={total}
          grupoSel={grupoSel}
          lineaSel={lineaSel}
          onSelGrupo={(g) => {
            setGrupoSel(g);
            setLineaSel("");
          }}
          onSelLinea={(g, linea) => {
            setGrupoSel(g);
            setLineaSel(linea);
          }}
        />
        {lineaActiva ? (
          <LineaPaginada
            marca={marca}
            linea={lineaActiva.linea}
            etiqueta={lineaActiva.etiqueta}
            onVolver={() => {
              setGrupoSel("");
              setLineaSel("");
            }}
          />
        ) : (
          <>
            {query.isFetching && !query.isPending && (
              <Spinner className="h-3 w-3 text-muted-foreground" label="Actualizando" />
            )}
            {visibles.length === 0 ? (
              <EstadoVacio
                icono={Newspaper}
                titulo="Sin candidatas en esta categoría"
                texto="Prueba con otra categoría o espera a que lleguen nuevas."
              />
            ) : (
              <ListaHistorias historias={visibles} />
            )}
          </>
        )}
      </div>
    );
  }

  const fuera = data.fuera_de_plan;
  const vacia =
    data.categorias.every((l) => l.en_pool === 0) && fuera.en_pool === 0;

  return (
    <div className="space-y-6">
      {query.isFetching && !query.isPending && (
        <Spinner className="h-3 w-3 text-muted-foreground" label="Actualizando" />
      )}

      {vacia && (
        <EstadoVacio
          icono={Newspaper}
          titulo="Sin candidatas por ahora"
          texto="Las candidatas aparecerán aquí"
        />
      )}

      {data.categorias
        .filter((l) => l.cupo > 0 || l.en_pool > 0)
        .map((l) => (
          <SeccionLinea
            key={l.linea}
            linea={l}
            onAbrirLinea={(linea, etiqueta) => setLineaAbierta({ linea, etiqueta })}
          />
        ))}

      {/* Fuera del plan (plegado por defecto): líneas de feed que el plan no contempla. */}
      {fuera.en_pool > 0 && (
        <section data-testid="seccion-fuera-de-plan">
          <div className="flex items-center justify-between gap-2">
            <button
              type="button"
              className="flex items-center gap-1 text-sm font-semibold text-muted-foreground hover:text-foreground"
              onClick={() => setFueraAbierto((v) => !v)}
              aria-expanded={fueraAbierto}
            >
              {fueraAbierto ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              Fuera del plan · {fuera.en_pool} candidata{fuera.en_pool !== 1 ? "s" : ""}
            </button>
            <button
              type="button"
              className="text-xs text-muted-foreground hover:text-foreground hover:underline"
              onClick={() => setLineaAbierta({ linea: LINEA_FUERA, etiqueta: "Fuera del plan" })}
            >
              {`Ver las ${fuera.en_pool} del pool`}
            </button>
          </div>
          {fueraAbierto && (
            <div className="mt-2">
              <ListaHistorias historias={fuera.historias} />
            </div>
          )}
        </section>
      )}
    </div>
  );
}
