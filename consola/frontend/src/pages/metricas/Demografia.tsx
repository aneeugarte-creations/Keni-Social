/**
 * Demografía de la audiencia de una marca×red (estrategia digital).
 *
 * Una SOLA ficha de audiencia por marca: quién forma la audiencia (género, edad, lugar) y con
 * qué mezcla de formatos se publica (`postsTypes`). La fuente la da por CUENTA, así que es una
 * vista marca×red: Instagram trae el reparto demográfico completo; Facebook, el país de los
 * seguidores. La marca y la red salen de los FILTROS GLOBALES de la cabecera; sin foco de red
 * (todas) la ficha muestra Instagram por defecto con un conmutador a Facebook, en vez de apilar
 * un panel por red. Las distribuciones demográficas son porcentajes; la mezcla de formatos son
 * conteos. Si la red no expone demografía (`distribuciones` vacío) se dice con honestidad en vez
 * de inventar barras. La paleta es la misma que el resto de gráficos de Métricas (sky=alcance,
 * violet=interacciones, emerald=engagement, amber=vistas): el tono fuerte marca el valor
 * dominante de cada dimensión, el suave la cola.
 */
import { useQuery } from "@tanstack/react-query";
import { Facebook, Instagram, PieChart } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { nombreFormato, nombreRed, numeroCompleto, porcentaje, redEnFoco } from "@/lib/formato";
import type { PuntoDistribucion } from "@/types";

import { MARCA_TODAS } from "./Controles";
import { Seccion } from "./Seccion";
import { useVistaConfig } from "./vistaConfig";

/** Redes que exponen demografía de cuenta (IG: reparto completo; FB: país de seguidores). */
const REDES_DEMOGRAFIA = ["instagram", "facebook"] as const;

/** Distribuciones crudas de una marca×red: `{metrica: [{clave, valor}]}` (puede venir vacío). */
type Distribuciones = Record<string, PuntoDistribucion[]>;

const GENERO: Record<string, string> = { M: "Hombres", F: "Mujeres", U: "Sin especificar" };
const generoLegible = (c: string) => GENERO[c] ?? c;

/** Copia ordenada de mayor a menor (sin mutar el original). */
const ordenar = (p?: PuntoDistribucion[]) => [...(p ?? [])].sort((a, b) => b.valor - a.valor);

/** Nombre legible de un país desde su código ISO 3166-1 alpha-2 (MX → México); si la clave no
 * es un código reconocible (ya es un nombre, o una ciudad), se devuelve tal cual. */
const PAISES_DN = new Intl.DisplayNames(["es-MX"], { type: "region" });
function nombrePais(clave: string): string {
  const c = clave.trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(c)) return clave;
  try {
    return PAISES_DN.of(c) ?? clave;
  } catch {
    return clave;
  }
}

/** Buckets de edad en orden cronológico; los desconocidos ("U") se descartan del histograma. */
const ORDEN_EDAD = ["13-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"];
const idxEdad = (c: string) => {
  const i = ORDEN_EDAD.indexOf(c.trim());
  return i === -1 ? ORDEN_EDAD.length : i;
};

/** Color por dimensión: la misma paleta Tremor con nombre que usan los demás gráficos de
 * Métricas (alcance=sky, interacciones=violet, engagement=emerald, vistas=amber). El tono fuerte
 * marca el valor dominante; el suave (mismo hue translúcido) la cola, legible en claro y oscuro. */
const C_GENERO = { fuerte: "bg-violet-500", suave: "bg-violet-500/35" };
const C_EDAD = { fuerte: "bg-sky-500", suave: "bg-sky-500/35" };
const C_LUGAR = { fuerte: "bg-emerald-500", suave: "bg-emerald-500/35" };

/** Formatos = categórico (cada formato su color), como los gráficos apilados de la página. */
const C_FORMATO_STROKE = ["stroke-amber-500", "stroke-sky-500", "stroke-emerald-500", "stroke-violet-500", "stroke-rose-500"];
const C_FORMATO_BG = ["bg-amber-500", "bg-sky-500", "bg-emerald-500", "bg-violet-500", "bg-rose-500"];
const formatoStroke = (i: number) => C_FORMATO_STROKE[i % C_FORMATO_STROKE.length];
const formatoBg = (i: number) => C_FORMATO_BG[i % C_FORMATO_BG.length];

/** "25-34" → "25 a 34"; "65+" → "65 o más". */
function rangoEdad(c: string): string {
  if (c.endsWith("+")) return `${c.slice(0, -1)} o más`;
  const [a, b] = c.split("-");
  return b ? `${a} a ${b}` : c;
}

const Em = ({ children }: { children: React.ReactNode }) => (
  <span className="font-medium text-foreground">{children}</span>
);

function Etiqueta({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{children}</p>
  );
}

function SinDatos() {
  return <p className="text-xs text-muted-foreground">Sin datos disponibles.</p>;
}

/** Une nodos en prosa con comas y una "y" final. */
function unir(piezas: React.ReactNode[]): React.ReactNode[] {
  return piezas.map((p, i) => (
    <React.Fragment key={i}>
      {i > 0 && (i === piezas.length - 1 ? " y " : ", ")}
      {p}
    </React.Fragment>
  ));
}

/** Una frase-síntesis de la audiencia (la conclusión; el detalle va debajo). */
function resumen(red: string, dist: Distribuciones): React.ReactNode {
  const paises = dist.country?.length ? dist.country : dist.page_follows_country;
  const pais = paises?.length ? ordenar(paises)[0] : null;

  if (red === "facebook") {
    if (!pais) return null;
    return (
      <>
        Seguidores concentrados en <Em>{nombrePais(pais.clave)}</Em> (
        <span className="tabular-nums">{porcentaje(pais.valor)}</span>).
      </>
    );
  }

  const piezas: React.ReactNode[] = [];
  const g = ordenar(dist.gender);
  if (g.length >= 2) {
    const gap = g[0].valor - g[1].valor;
    if (gap < 12) {
      piezas.push(<Em key="g">equilibrada en género</Em>);
    } else {
      const adj = g[0].clave === "M" ? "masculina" : g[0].clave === "F" ? "femenina" : "diversa";
      piezas.push(<Em key="g">mayoritariamente {adj}</Em>);
    }
  }
  if (dist.age?.length) {
    const a = dist.age.reduce((x, y) => (y.valor > x.valor ? y : x));
    piezas.push(
      <React.Fragment key="a">
        de <Em>{rangoEdad(a.clave)}</Em> años
      </React.Fragment>,
    );
  }
  if (pais) {
    piezas.push(
      <React.Fragment key="p">
        concentrada en <Em>{nombrePais(pais.clave)}</Em>
      </React.Fragment>,
    );
  }
  if (!piezas.length) return null;
  return <>Audiencia {unir(piezas)}.</>;
}

/** Conmutador de red segmentado, sutil; itera las redes demográficas en foco. */
function Conmutador({
  red,
  redes,
  onChange,
}: {
  red: string;
  redes: readonly string[];
  onChange: (r: string) => void;
}) {
  return (
    <div className="flex rounded-lg border border-border bg-muted p-0.5 text-xs">
      {redes.map((r) => {
        const Icono = r === "instagram" ? Instagram : Facebook;
        const activo = r === red;
        return (
          <button
            key={r}
            type="button"
            onClick={() => onChange(r)}
            aria-pressed={activo}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 transition-colors ${
              activo
                ? "bg-card font-medium text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Icono className="h-3.5 w-3.5" />
            {nombreRed(r)}
          </button>
        );
      })}
    </div>
  );
}

/** Género como UNA barra split 100% con los % inline a los extremos. */
function BarraGenero({ puntos }: { puntos: PuntoDistribucion[] }) {
  const orden = ordenar(puntos);
  if (!orden.length) return <SinDatos />;
  const aria = orden.map((p) => `${generoLegible(p.clave)} ${porcentaje(p.valor)}`).join(", ");
  return (
    <div className="space-y-2.5">
      <Etiqueta>Género</Etiqueta>
      <div className="flex items-baseline justify-between">
        {orden.map((p, i) => (
          <div key={p.clave} className={i === orden.length - 1 ? "text-right" : ""}>
            <span className="block text-base font-medium tabular-nums">{porcentaje(p.valor)}</span>
            <span className="block text-xs text-muted-foreground">{generoLegible(p.clave)}</span>
          </div>
        ))}
      </div>
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted" role="img" aria-label={`Género: ${aria}`}>
        {orden.map((p, i) => (
          <div key={p.clave} className={i === 0 ? C_GENERO.fuerte : C_GENERO.suave} style={{ width: `${p.valor}%` }} />
        ))}
      </div>
    </div>
  );
}

/** Edad como histograma de columnas finas (eje x = edad ascendente); pico en sky fuerte. */
function ColumnasEdad({ puntos }: { puntos: PuntoDistribucion[] }) {
  // Eje X cronológico (13-17 → 65+); la fuente los manda por valor y con un bucket "U"
  // (edad desconocida) que no es un tramo real y se descarta.
  const orden = [...puntos]
    .filter((b) => b.clave.trim().toUpperCase() !== "U")
    .sort((a, b) => idxEdad(a.clave) - idxEdad(b.clave));
  if (!orden.length) return <SinDatos />;
  const max = Math.max(...orden.map((b) => b.valor));
  const dom = orden.reduce((x, y) => (y.valor > x.valor ? y : x));
  const aria = orden.map((b) => `${b.clave} ${porcentaje(b.valor)}`).join(", ");
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <Etiqueta>Edad</Etiqueta>
        <span className="text-xs text-muted-foreground">
          Pico <span className="font-medium text-foreground">{dom.clave}</span>
          {" · "}
          <span className="tabular-nums text-foreground">{porcentaje(dom.valor)}</span>
        </span>
      </div>
      <div className="flex h-20 items-end gap-1.5" role="img" aria-label={`Edad: ${aria}`}>
        {orden.map((b) => {
          const dominante = b.clave === dom.clave;
          return (
            <div
              key={b.clave}
              className={`flex-1 rounded-t-[3px] ${dominante ? C_EDAD.fuerte : C_EDAD.suave}`}
              style={{ height: `${Math.max(max > 0 ? (b.valor / max) * 100 : 0, 3)}%` }}
            />
          );
        })}
      </div>
      <div className="flex gap-1.5">
        {orden.map((b) => (
          <span
            key={b.clave}
            className={`flex-1 text-center text-[10px] tabular-nums ${
              b.clave === dom.clave ? "font-medium text-foreground" : "text-muted-foreground"
            }`}
          >
            {b.clave}
          </span>
        ))}
      </div>
    </div>
  );
}

/** Lugar como ranking compacto (top 5 + "resto"); barra inline fina, #1 en emerald fuerte.
 * Las `ciudades` (cuando la red las expone) van como una línea fina debajo, sin otro gráfico. */
function ListaLugar({
  puntos,
  titulo,
  ciudades,
}: {
  puntos: PuntoDistribucion[];
  titulo: string;
  ciudades?: PuntoDistribucion[];
}) {
  const orden = ordenar(puntos);
  if (!orden.length) return <SinDatos />;
  const top = orden.slice(0, 5);
  const max = top[0].valor || 1;
  const total = orden.reduce((s, p) => s + p.valor, 0);
  const restoN = orden.length - top.length;
  const restoPct = total - top.reduce((s, p) => s + p.valor, 0);
  const topCiudades = ciudades?.length ? ordenar(ciudades).slice(0, 3) : [];
  const aria = top.map((p, i) => `${i + 1} ${p.clave} ${porcentaje(p.valor)}`).join(", ");
  return (
    <div className="space-y-3">
      <Etiqueta>{titulo}</Etiqueta>
      <ol className="space-y-2.5" role="img" aria-label={`${titulo}: ${aria}`}>
        {top.map((p, i) => (
          <li key={p.clave} className="space-y-1">
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="flex min-w-0 items-baseline gap-2">
                <span className="w-3 shrink-0 text-xs tabular-nums text-muted-foreground">{i + 1}</span>
                <span className="truncate text-foreground">{p.clave}</span>
              </span>
              <span className="shrink-0 tabular-nums text-muted-foreground">{porcentaje(p.valor)}</span>
            </div>
            <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full rounded-full ${i === 0 ? C_LUGAR.fuerte : C_LUGAR.suave}`}
                style={{ width: `${(p.valor / max) * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ol>
      {restoN > 0 && (
        <p className="text-xs text-muted-foreground">
          +{restoN} más · resto <span className="tabular-nums">{porcentaje(restoPct)}</span>
        </p>
      )}
      {topCiudades.length > 0 && (
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 border-t border-border pt-2.5 text-xs text-muted-foreground">
          <span className="text-[10px] font-medium uppercase tracking-wider">Ciudades</span>
          {topCiudades.map((c, i) => (
            <span key={c.clave} className="inline-flex items-baseline gap-1">
              {i > 0 && (
                <span aria-hidden className="text-muted-foreground/50">
                  ·
                </span>
              )}
              <span className="text-foreground/80">{c.clave}</span>
              <span className="tabular-nums">{porcentaje(c.valor)}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Formatos como donut pequeño + leyenda; cada formato su color (categórico). */
function Formatos({ puntos }: { puntos: PuntoDistribucion[] }) {
  const orden = ordenar(puntos);
  const total = orden.reduce((s, p) => s + p.valor, 0);
  if (!orden.length || total <= 0) return <SinDatos />;
  let antes = 0;
  const segmentos = orden.map((p, i) => {
    const pct = (p.valor / total) * 100;
    const seg = { ...p, pct, offset: 25 - antes, i };
    antes += pct;
    return seg;
  });
  const aria = orden
    .map((p) => `${nombreFormato(p.clave)} ${porcentaje((p.valor / total) * 100)}`)
    .join(", ");
  return (
    <div className="space-y-3">
      <Etiqueta>Formatos publicados</Etiqueta>
      <div className="flex items-center gap-5">
        <div className="relative h-24 w-24 shrink-0" role="img" aria-label={`Formatos: ${aria}`}>
          <svg viewBox="0 0 36 36" className="h-full w-full">
            <circle cx="18" cy="18" r="15.9155" fill="none" strokeWidth="4" className="stroke-muted" />
            {segmentos.map((s) => (
              <circle
                key={s.clave}
                cx="18"
                cy="18"
                r="15.9155"
                fill="none"
                strokeWidth="4"
                className={formatoStroke(s.i)}
                strokeDasharray={`${s.pct} ${100 - s.pct}`}
                strokeDashoffset={s.offset}
              />
            ))}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-sm font-medium leading-none tabular-nums">{numeroCompleto(total)}</span>
            <span className="text-[10px] text-muted-foreground">piezas</span>
          </div>
        </div>
        <ul className="min-w-0 flex-1 space-y-1.5 text-sm">
          {segmentos.map((s) => (
            <li key={s.clave} className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 shrink-0 rounded-[3px] ${formatoBg(s.i)}`} />
              <span className="truncate text-foreground">{nombreFormato(s.clave)}</span>
              <span className="ml-auto shrink-0 tabular-nums text-muted-foreground">{porcentaje(s.pct)}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** Cuerpo de la ficha: dos columnas equilibradas — género + lugar / edad + formatos. */
function Cuerpo({ red, dist }: { red: string; dist: Distribuciones }) {
  const izquierda: React.ReactNode[] = [];
  const derecha: React.ReactNode[] = [];
  const paises = (dist.country?.length ? dist.country : dist.page_follows_country)?.map((p) => ({
    ...p,
    clave: nombrePais(p.clave),
  }));

  if (red === "instagram") {
    if (dist.gender?.length) izquierda.push(<BarraGenero key="g" puntos={dist.gender} />);
    if (paises?.length)
      izquierda.push(
        <ListaLugar key="l" puntos={paises} titulo="Lugar de la audiencia" ciudades={dist.city} />,
      );
    if (dist.age?.length) derecha.push(<ColumnasEdad key="e" puntos={dist.age} />);
    if (dist.postsTypes?.length) derecha.push(<Formatos key="f" puntos={dist.postsTypes} />);
  } else {
    if (paises?.length) izquierda.push(<ListaLugar key="l" puntos={paises} titulo="Lugar de los seguidores" />);
    if (dist.postsTypes?.length) derecha.push(<Formatos key="f" puntos={dist.postsTypes} />);
  }

  if (!izquierda.length && !derecha.length) return <SinDatos />;
  return (
    <>
      <div className="grid grid-cols-1 gap-x-10 gap-y-8 sm:grid-cols-2">
        <div className="space-y-8">{izquierda}</div>
        <div className="space-y-8">{derecha}</div>
      </div>
      {red === "facebook" && (
        <p className="mt-6 border-t border-border pt-4 text-xs text-muted-foreground">
          Meta ya no expone género ni edad a nivel de página.
        </p>
      )}
    </>
  );
}

/** La ficha de audiencia de la marca: cabecera con red + conmutador, y el cuerpo de la red activa. */
function FichaAudiencia({ marca, redes }: { marca?: string; redes: readonly string[] }) {
  const [red, setRed] = React.useState<string>(redes[0] ?? REDES_DEMOGRAFIA[0]);

  // Si cambia el foco global de red y la activa ya no está disponible, vuelve a la primera.
  React.useEffect(() => {
    if (!redes.includes(red)) setRed(redes[0] ?? REDES_DEMOGRAFIA[0]);
  }, [redes, red]);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "demografia", marca ?? "todas", red],
    queryFn: ({ signal }) => api.metricasDemografia({ marca, red }, signal),
    staleTime: 5 * 60_000,
  });

  const dist: Distribuciones = data?.distribuciones ?? {};
  const vacio = Object.values(dist).every((v) => !v || v.length === 0);
  const RedIcono = red === "instagram" ? Instagram : Facebook;
  const lede = !isPending && !isError && !vacio ? resumen(red, dist) : null;

  return (
    <Card className="w-full overflow-hidden">
      <header className="space-y-2 border-b border-border px-6 py-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <RedIcono className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">{nombreRed(red)}</span>
          </div>
          {redes.length > 1 && <Conmutador red={red} redes={redes} onChange={setRed} />}
        </div>
        {lede && <p className="text-sm leading-relaxed text-muted-foreground">{lede}</p>}
      </header>
      <div className="p-6">
        {isPending ? (
          <div className="grid grid-cols-1 gap-x-10 gap-y-8 sm:grid-cols-2">
            <Skeleton className="h-40 w-full rounded-lg" />
            <Skeleton className="h-40 w-full rounded-lg" />
          </div>
        ) : isError ? (
          <p className="py-6 text-center text-sm text-muted-foreground">No se pudo cargar la demografía.</p>
        ) : vacio ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            {nombreRed(red)} no expone demografía de audiencia para esta marca.
          </p>
        ) : (
          <Cuerpo red={red} dist={dist} />
        )}
      </div>
    </Card>
  );
}

export function Demografia({ marcaActual = MARCA_TODAS }: { marcaActual?: string }) {
  // Marca y red salen de los filtros globales: la marca como `id_metricas` (o "todas", que el
  // backend resuelve al foco por defecto de la sesión) y el foco de red del selector global.
  const marca_ = marcaParam(marcaActual);
  const foco = useVistaConfig((s) => s.red);

  // Redes a ofrecer: las que exponen demografía Y están en foco. Sin foco de red (todas) → IG y
  // FB (la ficha arranca en IG); con un foco que no incluye ninguna red demográfica → ninguna.
  const redes = React.useMemo(() => REDES_DEMOGRAFIA.filter((r) => redEnFoco(foco, r)), [foco]);

  return (
    <Seccion
      id="demografia"
      titulo="Demografía de la audiencia"
      icono={PieChart}
      descripcion="Quién sigue la cuenta (género, edad, lugar) y con qué mezcla de formatos se publica. La fuente la da por cuenta: usa la marca y la red de los filtros de arriba."
    >
      {redes.length === 0 ? (
        <Card className="p-6">
          <p className="py-6 text-center text-sm text-muted-foreground">
            Las redes en foco no exponen demografía de audiencia (solo Instagram y Facebook).
          </p>
        </Card>
      ) : (
        <FichaAudiencia marca={marca_} redes={redes} />
      )}
    </Seccion>
  );
}
