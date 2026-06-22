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
import { ChevronDown, ChevronRight, Layers, Newspaper, X } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { api, mensajeError } from "@/lib/api";
import { etiquetaLinea } from "@/lib/lineas";
import { cn } from "@/lib/utils";
import type { GrupoMesa, Historia, LineaGrupo, MesaLinea } from "@/types";

import { TarjetaHistoria } from "./TarjetaHistoria";

/** Refresco automático de la mesa (sensación "live", igual que la lista clásica). */
const REFETCH_INTERVAL_MS = 45_000;

/** Candidatas visibles por sección, plegado/expandido ("Ver las N" pide más al back). */
const POR_LINEA_PLEGADO = 5;
const POR_LINEA_EXPANDIDO = 20;

export const CLAVE_MESA = (marca: string, porLinea: number) =>
  ["noticias", "mesa", marca, porLinea] as const;

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
      {n > 0 && <span className="tabular-nums text-xs text-muted-foreground/55">{n}</span>}
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
  lineas: LineaGrupo[];
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
  lineas: MesaLinea[],
  fuera: { en_pool: number; historias: Historia[] },
): { chips: GrupoMesa[]; browse: Historia[] } {
  const chips: GrupoMesa[] = [];
  const browse: Historia[] = [];
  for (const l of lineas) {
    const etiqueta = l.etiqueta || etiquetaLinea(l.linea);
    if (l.en_pool > 0 || l.cupo > 0) chips.push({ grupo: etiqueta, en_pool: l.en_pool });
    for (const h of l.historias) browse.push({ ...h, grupo: etiqueta });
  }
  if (fuera.en_pool > 0) {
    chips.push({ grupo: "Fuera del plan", en_pool: fuera.en_pool });
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
  clave,
}: {
  tema: string;
  historias: Historia[];
  clave: readonly unknown[];
}) {
  const [abierto, setAbierto] = React.useState(false);
  return (
    <div
      className="space-y-2 rounded-lg border border-border bg-muted/30 p-2"
      data-testid="grupo-macro"
      data-tema-macro={tema}
    >
      <button
        type="button"
        className="flex w-full items-center gap-1.5 px-1 text-xs font-semibold text-foreground"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
      >
        {abierto ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        <Layers className="h-3.5 w-3.5" />
        <span>{tema}</span>
        <span className="font-normal tabular-nums text-muted-foreground">
          · {historias.length} historias
        </span>
      </button>
      {abierto && (
        <div className="space-y-2">
          {historias.map((h) => (
            <TarjetaHistoria key={h.id} historia={h} clavesAInvalidar={[clave]} />
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
function ListaHistorias({
  historias,
  clave,
}: {
  historias: Historia[];
  clave: readonly unknown[];
}) {
  const bloques = React.useMemo(() => agruparPorMacro(historias), [historias]);
  return (
    <div className="space-y-2">
      {bloques.map((b) =>
        b.tipo === "suelta" ? (
          <TarjetaHistoria key={b.historia.id} historia={b.historia} clavesAInvalidar={[clave]} />
        ) : (
          <GrupoMacro key={`macro:${b.tema}`} tema={b.tema} historias={b.historias} clave={clave} />
        ),
      )}
    </div>
  );
}

// ── Sección por línea ─────────────────────────────────────────────────────────

function SeccionLinea({
  linea,
  clave,
  expandida,
  onToggleExpandida,
}: {
  linea: MesaLinea;
  clave: readonly unknown[];
  expandida: boolean;
  onToggleExpandida: () => void;
}) {
  const etiqueta = linea.etiqueta || etiquetaLinea(linea.linea);
  const hayMas = linea.en_pool > linea.historias.length || expandida;
  return (
    <section className="space-y-2" data-testid={`seccion-${linea.linea}`}>
      <div className="flex flex-wrap items-baseline gap-2 border-b pb-1">
        <h3 className="text-sm font-semibold">{etiqueta}</h3>
        <span className="text-xs tabular-nums text-muted-foreground">
          {linea.generados} de {linea.cupo} hoy
        </span>
        {hayMas && linea.en_pool > 0 && (
          <button
            type="button"
            className="ml-auto text-xs text-muted-foreground hover:text-foreground hover:underline"
            onClick={onToggleExpandida}
          >
            {expandida ? "Ver menos" : `Ver las ${linea.en_pool}`}
          </button>
        )}
      </div>
      {linea.historias.length === 0 ? (
        <p className="text-xs text-muted-foreground">Sin candidatas por ahora.</p>
      ) : (
        <ListaHistorias historias={linea.historias} clave={clave} />
      )}
    </section>
  );
}

// ── La mesa ───────────────────────────────────────────────────────────────────

export function MesaNoticias({ marca }: { marca: string; nombre: string | null }) {
  // "Ver las N" por sección: con cualquier sección expandida se piden más por línea (el
  // payload es uno solo; las plegadas siguen mostrando 5).
  const [expandidas, setExpandidas] = React.useState<Set<string>>(() => new Set());
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
    setExpandidas(new Set());
    setFueraAbierto(false);
  }, [marca]);
  const porLinea = expandidas.size > 0 || fueraAbierto ? POR_LINEA_EXPANDIDO : POR_LINEA_PLEGADO;
  const clave = CLAVE_MESA(marca, porLinea);

  const query = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => api.noticias.mesa({ marca, porLinea }, signal),
    staleTime: 20_000,
    refetchInterval: REFETCH_INTERVAL_MS,
    // El refetch no debe "bailar" las tarjetas bajo el cursor: conserva el dato anterior.
    placeholderData: keepPreviousData,
  });

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
        ? chipsDeLineas(data.lineas, data.fuera_de_plan)
        : { chips: [] as GrupoMesa[], browse: [] as Historia[] };
  if (chips.length > 0) {
    const total = chips.reduce((acc, g) => acc + g.en_pool, 0);
    const visibles = historiasDelGrupo(browse, grupoSel, lineaSel);
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
        {query.isFetching && !query.isPending && (
          <Spinner className="h-3 w-3 text-muted-foreground" label="Actualizando" />
        )}
        {visibles.length === 0 ? (
          <EstadoVacio
            icono={Newspaper}
            titulo={lineaSel ? "Sin candidatas en esta línea" : "Sin candidatas en esta categoría"}
            texto="Prueba con otra categoría o espera a que lleguen nuevas."
          />
        ) : (
          <ListaHistorias historias={visibles} clave={clave} />
        )}
      </div>
    );
  }

  const alternarExpandida = (linea: string) =>
    setExpandidas((prev) => {
      const next = new Set(prev);
      if (next.has(linea)) next.delete(linea);
      else next.add(linea);
      return next;
    });

  const fuera = data.fuera_de_plan;
  const vacia =
    data.lineas.every((l) => l.en_pool === 0) && fuera.en_pool === 0;

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

      {data.lineas
        .filter((l) => l.cupo > 0 || l.en_pool > 0)
        .map((l) => (
          <SeccionLinea
            key={l.linea}
            linea={l}
            clave={clave}
            expandida={expandidas.has(l.linea)}
            onToggleExpandida={() => alternarExpandida(l.linea)}
          />
        ))}

      {/* Fuera del plan (plegado por defecto): líneas de feed que el plan no contempla. */}
      {fuera.en_pool > 0 && (
        <section data-testid="seccion-fuera-de-plan">
          <button
            type="button"
            className="flex items-center gap-1 text-sm font-semibold text-muted-foreground hover:text-foreground"
            onClick={() => setFueraAbierto((v) => !v)}
            aria-expanded={fueraAbierto}
          >
            {fueraAbierto ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            Fuera del plan · {fuera.en_pool} candidata{fuera.en_pool !== 1 ? "s" : ""}
          </button>
          {fueraAbierto && (
            <div className="mt-2">
              <ListaHistorias historias={fuera.historias} clave={clave} />
            </div>
          )}
        </section>
      )}
    </div>
  );
}
