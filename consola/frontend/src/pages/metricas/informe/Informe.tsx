/**
 * Deck del informe de Métricas listo para rasterizar a PDF: una PILA VERTICAL de
 * diapositivas 1280×720 a tamaño real (sin escalar, sin toolbar, sin selectores). Lienzo
 * gris claro, marca protagonista, una idea por diapositiva. La regla del deck: el TÍTULO de
 * cada lámina es el INSIGHT (qué pasó), no la categoría; el gráfico debajo lo respalda.
 * Dirigido EXCLUSIVAMENTE por `InformeProps` (los insights se calculan en `desdeEntradas`).
 */
import * as React from "react";

import { nombreRed, numeroCompactoFijo } from "@/lib/formato";

import { AreaBold } from "./graficas";
import { LOGOS_MARCA } from "./logos";
import type {
  ConclusionInforme,
  FilaComparativaRed,
  FilaRanking,
  InformeProps,
  KpiInforme,
  MetricaRedComparada,
} from "./tipos";

import "./informe.css";

/**
 * Esquema "Sereno": jerarquía por tamaño; labels en gris MEDIO, presentes y no susurrados;
 * títulos/números en negro; pie tenue. Mapea cada rol de texto a su clase.
 */
const TONO = {
  topLabel: "text-neutral-500",
  titulo: "text-neutral-900",
  subtitulo: "text-neutral-500",
  kpiLabel: "text-neutral-500",
  kpiValor: "text-neutral-900",
  tablaHeader: "text-neutral-500",
  tablaCelda: "text-neutral-900",
  pie: "text-neutral-500",
} as const;

/** Overline / eyebrow ÚNICO del deck (mismo tracking en toda lámina). */
const EYEBROW = "text-[11px] font-medium uppercase tracking-[0.18em]";

/** Ancho útil de una lámina (1280 menos el padding horizontal px-20): las gráficas SVG lo usan
 *  como ancho fijo para rasterizar 1:1 y nítido, sin medir el contenedor. */
const ANCHO_GRAFICA = 1120;

/** Naranja de marca (acento único) y verde/rojo semánticos, como HEX para los SVG inline. */
const NARANJA = "#ea580c";
const VERDE = "#059669";
const ROJO = "#dc2626";
const GRIS_SERIE = "#525252";

/** Hex de la dirección de una serie (verde sube, rojo baja, gris neutro) para los SVG. */
function hexSigno(signo?: "sube" | "baja" | "igual"): string {
  return signo === "sube" ? VERDE : signo === "baja" ? ROJO : GRIS_SERIE;
}

/** Tinta legible sobre un fondo de color (blanco si es oscuro, gris-700 si es claro). */
function textoSobre(hex: string): string {
  const c = hex.replace("#", "");
  const r = parseInt(c.slice(0, 2), 16);
  const g = parseInt(c.slice(2, 4), 16);
  const b = parseInt(c.slice(4, 6), 16);
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return lum > 0.62 ? "#374151" : "#ffffff";
}

/** Estilo del "wordmark" de cada marca cuando no hay imagen de logo. */
interface EstiloMarca {
  texto?: string;
  familia: string;
  peso: number;
  color: string;
  tracking?: string;
  transform?: "uppercase" | "lowercase" | "none";
}
const ESTILOS: Record<string, EstiloMarca> = {
  unotv: { texto: "unotv", familia: "'Poppins'", peso: 800, color: "#E4002B", tracking: "-0.04em", transform: "lowercase" },
  "claro-sports": { texto: "Claro sports", familia: "'Montserrat'", peso: 900, color: "#DA291C", tracking: "-0.02em" },
  "nacion-gamer": { texto: "Nación Gamer", familia: "'Exo 2'", peso: 800, color: "#16A34A", tracking: "-0.01em" },
  "piso-15": { texto: "Piso 15", familia: "'Montserrat'", peso: 800, color: "#111827", tracking: "-0.01em" },
  fundacion: { texto: "Fundación", familia: "'Nunito Sans'", peso: 900, color: "#0072CE", tracking: "-0.01em" },
};

/** Nombre de la marca escrito como en su logo (tipografía + color). Sin estilo = nombre ligero neutro. */
function Wordmark({ id, nombre, size }: { id: string | null; nombre: string; size: number }) {
  const e = id ? ESTILOS[id] : undefined;
  if (!e) {
    return (
      <span style={{ fontWeight: 300, fontSize: size, letterSpacing: "-0.03em" }} className="text-neutral-900">
        {nombre}
      </span>
    );
  }
  return (
    <span
      style={{
        fontFamily: e.familia,
        fontWeight: e.peso,
        color: e.color,
        letterSpacing: e.tracking,
        textTransform: e.transform ?? "none",
        fontSize: size,
        lineHeight: 1,
        display: "inline-block",
      }}
    >
      {e.texto ?? nombre}
    </span>
  );
}

/** Logo real de la marca (asset de Vite) ajustado conservando proporción; si no hay, wordmark. */
function LogoOWordmark({
  id,
  nombre,
  box,
}: {
  id: string | null;
  nombre: string;
  box: { h: number; w: number };
}) {
  const src = id ? LOGOS_MARCA[id] : undefined;
  if (src) {
    return (
      <img
        src={src}
        alt={nombre}
        style={{ maxHeight: box.h, maxWidth: box.w, width: "auto", height: "auto", objectFit: "contain", display: "block" }}
      />
    );
  }
  return <Wordmark id={id} nombre={nombre} size={Math.round(box.h * 0.62)} />;
}

/** Portadas con fondo del color de la marca (logo en blanco + caption claro encima). */
const COVER_BG: Record<string, string> = {
  unotv: "#16273F",
  "claro-sports": "#DA291C",
  fundacion: "#0067B1",
  "nacion-gamer": "#16863E",
  "piso-15": "#0B0B0F",
};
/** Portada de "Todas las marcas": fondo oscuro neutro (no favorece el color de ninguna marca). */
const COVER_TODAS = "#17181C";
/** Orden de los logos en la portada-portfolio de "Todas las marcas". */
// Orden que reparte los emblemas altos entre las dos filas (3+2) para que ninguna fila quede
// solo con wordmarks bajos: fila 1 = Claro·UnoTV·Piso 15, fila 2 = Nación Gamer·Fundación.
const MARCAS_PORTFOLIO = ["claro-sports", "unotv", "piso-15", "nacion-gamer", "fundacion"];

/**
 * Caja del logo en la portada AIRE. El logo flota contenido en el centro del vacío con márgenes
 * generosos; `logoNudgeX` lo centra ÓPTICAMENTE (no por su caja) cuando el lockup es asimétrico.
 * Las marcas sin entrada caen al DEFAULT (caja uniforme).
 */
type CoverLayout = {
  /** Caja máxima del logo (object-contain encaja dentro manteniendo proporción). */
  box: { h: number; w: number };
  /** px que mueve el logo a la izquierda(−)/derecha(+) para centrarlo ÓPTICAMENTE (no por su caja):
   *  un lockup asimétrico (el destello de Claro sobresale a la derecha) no comparte eje con el
   *  centro del lienzo hasta corregir su centro de masa. */
  logoNudgeX?: number;
};
const COVER_LAYOUT_DEFAULT: CoverLayout = { box: { h: 150, w: 300 } };
/** Ajustes de portada por marca (sobre el DEFAULT). */
const COVER_LAYOUT: Record<string, CoverLayout> = {
  // El lockup de Claro parquea "sports" a la derecha: lo empujamos a la izquierda para que su
  // centro de masa quede sobre el eje del lienzo.
  "claro-sports": { box: { h: 150, w: 300 }, logoNudgeX: -6 },
};

/** Color de la dirección de una variación (verde sube, rojo baja, gris neutro). */
function colorSigno(signo?: "sube" | "baja" | "igual" | "nuevo" | "neutral"): string {
  if (signo === "sube") return "text-emerald-600";
  if (signo === "baja") return "text-red-600";
  return "text-neutral-500";
}
function flechaSigno(signo?: string): string {
  return signo === "sube" ? "↑" : signo === "baja" ? "↓" : "";
}
/** Espacio fino entre cifra y unidad (M / %) para que el dato lea como uno solo. */
const finos = (s: string): string => s.replace(/ /g, "\u202f");

/** Diapositiva 16:9 de contenido: lienzo gris claro, eyebrow (etiqueta · periodo), título y pie. */
function Marco({
  marca,
  periodo,
  etiqueta,
  titulo,
  subtitulo,
  children,
}: {
  marca: string;
  periodo: string;
  etiqueta?: string;
  titulo?: string;
  subtitulo?: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="informe-slide">
      <div className="flex h-full flex-col px-20 pb-12 pt-16">
        <header className="mb-9">
          <p className={`${EYEBROW} ${TONO.topLabel}`}>
            {etiqueta}
            <span className="mx-2 text-neutral-300">·</span>
            <span className="text-neutral-400">{periodo}</span>
          </p>
          <h2 className={`mt-3 max-w-4xl text-balance text-[28px] font-light leading-tight tracking-[-0.01em] ${TONO.titulo}`}>
            {titulo}
          </h2>
          {subtitulo && <p className={`mt-1.5 text-sm font-normal ${TONO.subtitulo}`}>{subtitulo}</p>}
        </header>

        <div className="min-h-0 flex-1">{children}</div>

        <footer className={`mt-8 flex items-center justify-between gap-6 border-t border-neutral-100 pt-4 text-[10px] ${TONO.pie}`}>
          <span className="whitespace-nowrap uppercase tracking-[0.18em]">
            {marca} · Todas las redes · {periodo}
          </span>
          <span className="shrink-0 uppercase tracking-[0.18em]">keni</span>
        </footer>
      </div>
    </section>
  );
}

/**
 * Diapositiva-portada AIRE: el lujo nace del vacío. Sobre el color de la marca, un eyebrow
 * susurrado arriba con el periodo, el logo contenido flotando en el centro con márgenes
 * generosos, y la firma «keni» en micrografía abajo tras una hairline finísima. Sin veredicto:
 * el titular del mes gobierna la lámina de resumen, no la portada. En "Todas las marcas" el logo
 * central cede al portfolio de las 5 marcas sobre fondo neutro. El `layout` (caja del logo) lo
 * fija COVER_LAYOUT[marcaId]; se puede pasar explícito para iterar variantes en una vista previa.
 */
export function PortadaSlide({
  marcaId,
  marcaLabel,
  esTodas,
  periodo,
  layout,
}: {
  marcaId: string | null;
  marcaLabel: string;
  esTodas: boolean;
  periodo: string;
  layout?: CoverLayout;
}) {
  const coverBg = esTodas ? COVER_TODAS : marcaId ? COVER_BG[marcaId] : undefined;
  const lay = layout ?? (marcaId ? COVER_LAYOUT[marcaId] : undefined) ?? COVER_LAYOUT_DEFAULT;
  return (
    <section className="informe-slide" style={coverBg ? { background: coverBg } : undefined}>
      {/* Eyebrow arriba: micrografía blanca al 55% con tracking amplio, anclada al margen superior. */}
      <p
        className="absolute font-medium uppercase text-[14px] text-white/55"
        style={{ top: 88, left: 108, right: 108, letterSpacing: "0.42em" }}
      >
        Informe de métricas · {esTodas ? "Todas las marcas · " : ""}
        {periodo}
      </p>

      {/* Logo contenido flotando en el centro del vacío (márgenes de 108px). */}
      <div className="flex h-full items-center justify-center" style={{ padding: "0 108px" }}>
        {esTodas ? (
          // Portfolio: cada marca en una celda de tamaño UNIFORME (equilibra el peso óptico). Todas
          // en blanco plano: los 4 logos blancos vía grayscale, y Piso 15 como wordmark blanco (su
          // emblema es un disco para fondo oscuro y no admite calado a blanco sin perder el "15").
          <div className="flex max-w-[900px] flex-wrap items-center justify-center gap-x-[72px] gap-y-[52px]">
            {MARCAS_PORTFOLIO.filter((id) => LOGOS_MARCA[id]).map((id) => (
              <div key={id} className="flex h-[88px] w-[236px] items-center justify-center">
                {id === "piso-15" ? (
                  <span
                    style={{
                      fontFamily: "'Montserrat'",
                      fontWeight: 800,
                      fontSize: 50,
                      letterSpacing: "-0.02em",
                      color: "#fff",
                      lineHeight: 1,
                    }}
                  >
                    Piso 15
                  </span>
                ) : (
                  <img
                    src={LOGOS_MARCA[id]}
                    alt=""
                    className="max-h-[60px] max-w-[212px] object-contain"
                    style={{ filter: "grayscale(1)" }}
                  />
                )}
              </div>
            ))}
          </div>
        ) : (
          // Logo de la marca contenido: object-contain lo encaja sea cual sea su proporción;
          // logoNudgeX lo centra en su eje óptico (no el geométrico).
          <div style={lay.logoNudgeX ? { transform: `translateX(${lay.logoNudgeX}px)` } : undefined}>
            <LogoOWordmark id={marcaId} nombre={marcaLabel} box={lay.box} />
          </div>
        )}
      </div>

      {/* Hairline finísima que asienta el pie del lienzo, sin voz de veredicto encima. */}
      <div className="absolute" style={{ left: 108, right: 108, bottom: 104 }}>
        <div className="h-px w-full bg-white/20" />
      </div>

      {/* Firma «keni» en micrografía, anclada al ángulo inferior derecho. */}
      <p
        className="absolute font-medium uppercase text-[12px] text-white/[.42]"
        style={{ right: 108, bottom: 52, letterSpacing: "0.30em" }}
      >
        keni
      </p>
    </section>
  );
}

/** Tile de KPI: número grande y ligero, label en mayúsculas, lectura de contexto (delta/secundario). */
function TileKpi({ kpi, mesAnterior }: { kpi: KpiInforme; mesAnterior: string }) {
  return (
    <div className="flex min-h-[124px] flex-col">
      <p className={`${EYEBROW} ${TONO.kpiLabel}`}>{kpi.etiqueta}</p>
      <p className={`mt-4 text-[44px] font-light leading-none tracking-[-0.02em] tabular-nums ${TONO.kpiValor}`} title={kpi.titulo}>
        {finos(kpi.valor)}
      </p>
      {kpi.delta ? (
        <p className={`mt-3 text-xs font-medium tabular-nums ${colorSigno(kpi.delta.signo)}`}>
          {flechaSigno(kpi.delta.signo) && <span className="mr-1">{flechaSigno(kpi.delta.signo)}</span>}
          {kpi.delta.texto}
          <span className="ml-1.5 font-normal text-neutral-500">vs. {mesAnterior}</span>
        </p>
      ) : kpi.secundario ? (
        <p className="mt-3 text-xs font-normal tabular-nums text-neutral-500">{finos(kpi.secundario)}</p>
      ) : (
        <p className="mt-3 text-xs font-normal text-neutral-300">sin comparativa</p>
      )}
    </div>
  );
}

/**
 * Fila de ranking "rotunda": la CIFRA manda (grande, editorial, tabular) y la barra es un acento
 * fino. El líder se sirve un punto mayor; el % acompaña a la cifra sin competir con ella.
 */
function FilaRankBold({
  nombre,
  cifra,
  sub,
  fraccion,
  color,
  destacado = false,
  flecha,
}: {
  nombre: string;
  /** Cifra dominante ya formateada (p. ej. "16.4 M" o "4.6 %"). */
  cifra: string;
  /** Apostilla pequeña junto a la cifra (p. ej. "34 %"); opcional. */
  sub?: string;
  /** Fracción 0..1 del valor sobre el máximo (largo de la barra). */
  fraccion: number;
  color: string;
  destacado?: boolean;
  /** Dirección frente a una referencia (verde sube, rojo baja); opcional. */
  flecha?: "sube" | "baja";
}) {
  return (
    <li>
      <div className="flex items-end justify-between gap-4">
        <span className="flex items-center gap-3 truncate pb-1 text-[15px] text-neutral-600">
          <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
          {nombre}
        </span>
        <span className="flex shrink-0 items-baseline gap-2 whitespace-nowrap">
          <span
            className={`${destacado ? "text-[34px]" : "text-[28px]"} font-light leading-none tracking-[-0.02em] tabular-nums text-neutral-900`}
          >
            {cifra}
          </span>
          {sub && <span className="text-sm tabular-nums text-neutral-400">{sub}</span>}
          {flecha && (
            <span className={`text-base ${flecha === "sube" ? "text-emerald-600" : "text-red-600"}`}>
              {flecha === "sube" ? "↑" : "↓"}
            </span>
          )}
        </span>
      </div>
      <div className="mt-3.5 h-[5px] w-full overflow-hidden rounded-full bg-neutral-100">
        <div
          className="h-full rounded-full"
          style={{ width: `${Math.max(0, Math.min(1, fraccion)) * 100}%`, background: color }}
        />
      </div>
    </li>
  );
}

/** Lista de ranking ordenada (reparto por red, comparativa por marca): cifra grande + barra fina. */
function Ranking({ filas, columnas = 1 }: { filas: FilaRanking[]; columnas?: number }) {
  const max = filas.reduce((m, f) => Math.max(m, f.valor), 0);
  return (
    <ul className={`grid gap-x-16 ${columnas === 2 ? "grid-cols-2 gap-y-8" : "grid-cols-1 gap-y-9"}`}>
      {filas.map((f, i) => (
        <FilaRankBold
          key={f.clave}
          nombre={f.nombre}
          cifra={finos(numeroCompactoFijo(f.valor))}
          sub={`${f.pct}\u202f%`}
          fraccion={max > 0 ? f.valor / max : 0}
          color={f.color}
          destacado={i === 0 && columnas === 1}
        />
      ))}
    </ul>
  );
}

/** Celda de una métrica comparada: valor actual grande + "anterior → variación" en una línea fina. */
function CeldaMetricaRed({ m }: { m: MetricaRedComparada }) {
  return (
    <td className="px-4 py-4 text-right align-middle">
      <p className="text-[26px] font-light leading-none tracking-[-0.02em] tabular-nums text-neutral-900">
        {finos(m.actual)}
      </p>
      <p className="mt-2 flex items-center justify-end gap-2 text-xs tabular-nums">
        <span className="text-neutral-400">{finos(m.anterior)}</span>
        <span className={`font-medium ${colorSigno(m.signo)}`}>
          {flechaSigno(m.signo) && <span className="mr-0.5">{flechaSigno(m.signo)}</span>}
          {finos(m.variacion)}
        </span>
      </p>
    </td>
  );
}

/**
 * Comparativa por red: una FILA por red (no por métrica, que desborda a 5 redes) con una columna
 * por métrica. Cada celda sirve la cifra ACTUAL grande + el periodo anterior y la variación con
 * dirección en una línea fina debajo. El anterior en gris, la variación con su flecha/color. Cabe
 * con aire a 1280×720 con las 4-5 redes en foco. Mismo lenguaje del deck (tabla de Top piezas).
 */
function TablaComparativaRed({
  filas,
  mesAnterior,
  periodo,
}: {
  filas: FilaComparativaRed[];
  mesAnterior: string;
  periodo: string;
}) {
  // Etiquetas de métrica del orden real (Vistas · Interacciones · Engagement); la primera fila las fija.
  const metricas = filas[0]?.metricas.map((m) => m.etiqueta) ?? [];
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr className={`border-b border-neutral-200 text-[11px] uppercase tracking-[0.14em] ${TONO.tablaHeader}`}>
          <th className="py-3 pr-4 text-left font-medium">Red</th>
          {metricas.map((etq) => (
            <th key={etq} className="px-4 py-3 text-right font-medium">
              {etq}
            </th>
          ))}
        </tr>
        <tr className="text-[10px] normal-case tracking-normal text-neutral-400">
          <th className="pb-2 pr-4 text-left font-normal" />
          {metricas.map((etq) => (
            <th key={etq} className="px-4 pb-2 text-right font-normal">
              {periodo} · {mesAnterior}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {filas.map((red) => (
          <tr key={red.clave} className="border-b border-neutral-100">
            <td className="py-4 pr-4">
              <span className="flex items-center gap-2.5 text-[15px] font-medium text-neutral-900">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: red.color }} />
                {red.nombre}
              </span>
            </td>
            {red.metricas.map((m) => (
              <CeldaMetricaRed key={m.etiqueta} m={m} />
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Rango de fechas de una serie como texto bajo la gráfica (sustituye al eje X recortado). */
function RangoFechas({ data }: { data: Array<{ fecha: string }> }) {
  if (data.length < 2) return null;
  return (
    <div className="mt-1.5 flex justify-between text-[11px] tabular-nums text-neutral-500">
      <span>{data[0].fecha}</span>
      <span>{data[data.length - 1].fecha}</span>
    </div>
  );
}

/** Una diapositiva del deck, ya posicionada en su orden. */
type Slide = { clave: string; nodo: React.ReactNode };

/** Lista ordenada de diapositivas del informe a partir de las props. */
function diapositivas(data: InformeProps): Slide[] {
  const {
    marcaId,
    marcaLabel,
    esTodas,
    periodo,
    mesAnterior,
    titularMes,
    kpis,
    tendencia,
    picoVistas,
    mediaVistas,
    mediaInteracciones,
    porRed,
    redInsight,
    comparativaRed,
    engPorRed,
    engInsight,
    engMedia,
    seguidores,
    seguidoresNeto,
    desgloseMix,
    topPiezas,
    pctEstrella,
    multiploEstrella,
    cuentas,
    conclusiones,
    recomendaciones,
  } = data;
  const etiqueta = esTodas ? "Todas las marcas" : marcaLabel;
  const slides: Slide[] = [];

  // 1 · Portada — la marca es la protagonista (logo sobre su color). En "Todas las marcas",
  // portada-portfolio: los 5 logos juntos sobre fondo oscuro neutro.
  slides.push({
    clave: "portada",
    nodo: (
      <PortadaSlide
        marcaId={marcaId}
        marcaLabel={marcaLabel}
        esTodas={esTodas}
        periodo={periodo}
      />
    ),
  });

  // 2 · Resumen ejecutivo — el TÍTULO es el titular del mes; debajo, 5 KPIs con su variación.
  slides.push({
    clave: "resumen",
    nodo: (
      <Marco
        marca={marcaLabel}
        periodo={periodo}
        etiqueta={etiqueta}
        titulo={titularMes}
        subtitulo={`El periodo en cifras · frente a ${mesAnterior}`}
      >
        <div
          className="grid h-full place-content-center gap-x-8"
          style={{ gridTemplateColumns: kpis.map(() => "1fr").join(" 1px ") }}
        >
          {kpis.map((k, i) => (
            <React.Fragment key={k.etiqueta}>
              {i > 0 && <div className="self-stretch bg-neutral-100" />}
              <TileKpi kpi={k} mesAnterior={mesAnterior} />
            </React.Fragment>
          ))}
        </div>
      </Marco>
    ),
  });

  // 2b · Comparativa por red — el desglose natural del resumen: del total a cada plataforma, con
  // el periodo actual frente al anterior y su variación. Es la lámina que el cliente presenta
  // (vistas e interacciones por red). Solo si hay redes con datos comparables.
  if (comparativaRed.length) {
    slides.push({
      clave: "comparativa-red",
      nodo: (
        <Marco
          marca={marcaLabel}
          periodo={periodo}
          etiqueta={etiqueta}
          titulo={`Comparativa por red — ${periodo} vs ${mesAnterior}`}
          subtitulo="Periodo actual frente al anterior, red a red"
        >
          <div className="flex h-full items-center">
            <TablaComparativaRed filas={comparativaRed} mesAnterior={mesAnterior} periodo={periodo} />
          </div>
        </Marco>
      ),
    });
  }

  // 3 · Tendencia diaria — el área de vistas es la estrella: gradiente rico, curva gruesa, el PICO
  // del titular marcado en la propia curva (disco + cifra + día) y la media como hairline. Las
  // interacciones la acompañan como banda fina, su media y su cierre marcados.
  const vistasSerie = tendencia.map((p) => p.Vistas);
  const interSerie = tendencia.map((p) => p.Interacciones);
  const idxPicoVistas = vistasSerie.length ? vistasSerie.indexOf(Math.max(...vistasSerie)) : -1;
  const cierreVistas =
    vistasSerie.length >= 2 ? { etiqueta: finos(numeroCompactoFijo(vistasSerie[vistasSerie.length - 1])) } : undefined;
  const cierreInter =
    interSerie.length >= 2 ? { etiqueta: finos(numeroCompactoFijo(interSerie[interSerie.length - 1])) } : undefined;
  slides.push({
    clave: "tendencia",
    nodo: (
      <Marco
        marca={marcaLabel}
        periodo={periodo}
        etiqueta={etiqueta}
        titulo={
          picoVistas
            ? `El ${picoVistas.fecha} concentró el ${picoVistas.pct} % de las vistas del mes`
            : "Tendencia diaria"
        }
        subtitulo="Visualizaciones e interacciones por día"
      >
        <div className="flex h-full flex-col justify-center gap-6">
          <div>
            <p className={`mb-2 ${EYEBROW} ${TONO.kpiLabel}`}>Visualizaciones</p>
            <AreaBold
              valores={vistasSerie}
              w={ANCHO_GRAFICA}
              h={228}
              id="grad-vistas"
              color={NARANJA}
              grosor={2.75}
              padTop={48}
              opacidadArea={0.34}
              cierre={cierreVistas}
              pico={
                picoVistas && idxPicoVistas >= 0
                  ? {
                      idx: idxPicoVistas,
                      cifra: finos(numeroCompactoFijo(picoVistas.valor)),
                      sub: `${picoVistas.fecha} · ${finos(`${picoVistas.pct} %`)} del mes`,
                    }
                  : undefined
              }
              referencia={
                mediaVistas > 0
                  ? {
                      valor: mediaVistas,
                      etiqueta: `media ${finos(numeroCompactoFijo(Math.round(mediaVistas)))} / día`,
                      lado: "izq",
                    }
                  : undefined
              }
            />
          </div>
          <div>
            <p className={`mb-2 ${EYEBROW} ${TONO.kpiLabel}`}>Interacciones</p>
            <AreaBold
              valores={interSerie}
              w={ANCHO_GRAFICA}
              h={92}
              id="grad-inter"
              color={GRIS_SERIE}
              grosor={2}
              padTop={16}
              opacidadArea={0.16}
              cierre={cierreInter}
              referencia={
                mediaInteracciones > 0
                  ? {
                      valor: mediaInteracciones,
                      etiqueta: `media ${finos(numeroCompactoFijo(Math.round(mediaInteracciones)))} / día`,
                      lado: "izq",
                    }
                  : undefined
              }
            />
            <RangoFechas data={tendencia} />
          </div>
        </div>
      </Marco>
    ),
  });

  // 4 · Reparto por red — ranking horizontal ordenado (no una barra apilada de un punto).
  slides.push({
    clave: "por-red",
    nodo: (
      <Marco
        marca={marcaLabel}
        periodo={periodo}
        etiqueta={etiqueta}
        titulo={redInsight || "Reparto por red"}
        subtitulo="Visualizaciones por plataforma"
      >
        <div className="flex h-full items-center">
          <div className="w-full">
            <Ranking filas={porRed} />
          </div>
        </div>
      </Marco>
    ),
  });

  // 4b · Dónde engancha mejor — engagement (interacción por vista) por red. Solo si hay dato:
  // alinea el cuerpo del deck con la tesis (no solo "dónde se ve", también "dónde conecta").
  if (engPorRed.length >= 2) {
    // La escala contiene también la media (el centroide ponderado nunca supera al líder, pero así
    // la línea de referencia jamás se sale aunque el dato llegara raro).
    const maxRate = Math.max(engPorRed[0].rate, engMedia) || 1;
    // Posición de la media global en la escala de las barras: las que la rebasan conectan por
    // encima de tu media; las que no, por debajo.
    const posMedia = Math.max(2, Math.min(98, (engMedia / maxRate) * 100));
    slides.push({
      clave: "eng-red",
      nodo: (
        <Marco
          marca={marcaLabel}
          periodo={periodo}
          etiqueta={etiqueta}
          titulo={engInsight || "Dónde engancha mejor"}
          subtitulo="Interacción por vista · frente a tu media global del periodo"
        >
          <div className="flex h-full flex-col justify-center">
            <div className="relative w-full">
              <ul className="grid gap-y-9 pt-8">
                {engPorRed.map((r, i) => (
                  <FilaRankBold
                    key={r.clave}
                    nombre={r.nombre}
                    cifra={`${r.rate.toFixed(1)}\u202f%`}
                    fraccion={r.rate / maxRate}
                    color={r.color}
                    destacado={i === 0}
                    flecha={engMedia > 0 ? (r.rate > engMedia ? "sube" : r.rate < engMedia ? "baja" : undefined) : undefined}
                  />
                ))}
              </ul>
              {/* Media global: una sola línea de referencia sutil + su etiqueta (mínimo, sin rejilla). */}
              {engMedia > 0 && (
                <>
                  <div
                    className="pointer-events-none absolute bottom-1 top-7 border-l border-dashed border-neutral-400"
                    style={{ left: `${posMedia}%` }}
                  />
                  <span
                    className="pointer-events-none absolute top-0 -translate-x-1/2 whitespace-nowrap text-[11px] font-medium tabular-nums text-neutral-500"
                    style={{ left: `${posMedia}%` }}
                  >
                    media {finos(`${engMedia.toFixed(1)} %`)}
                  </span>
                </>
              )}
            </div>
          </div>
        </Marco>
      ),
    });
  }

  // 5 · (solo "todas") Comparativa por marca — ranking horizontal (sin BarChart redundante).
  if (esTodas) {
    slides.push({
      clave: "por-marca",
      nodo: (
        <Marco
          marca={marcaLabel}
          periodo={periodo}
          etiqueta="Todas las marcas"
          titulo={
            cuentas.length
              ? `${cuentas[0].nombre} lidera con el ${cuentas[0].pct} % de las vistas`
              : "Comparativa por marca"
          }
          subtitulo="Visualizaciones del periodo por marca"
        >
          <div className="flex h-full items-center">
            <div className="w-full">
              <Ranking filas={cuentas} columnas={cuentas.length > 5 ? 2 : 1} />
            </div>
          </div>
        </Marco>
      ),
    });
  }

  // 6 · Crecimiento de seguidores — neto como héroe + curva de GANANCIA ACUMULADA (0→neto):
  // la pendiente cuenta el mismo dato que el titular, sin el "casi plano" del nivel absoluto.
  const ganadosSerie = seguidores.map((p) => p.Ganados);
  const colorSeguidores = hexSigno(seguidoresNeto?.signo);
  slides.push({
    clave: "seguidores",
    nodo: (
      <Marco
        marca={marcaLabel}
        periodo={periodo}
        etiqueta={etiqueta}
        titulo={
          // El título cuantifica el crecimiento RELATIVO (%); el héroe muestra el neto ABSOLUTO
          // (+k), así que no se duplica la misma cifra y el titular sigue siendo un insight.
          seguidoresNeto
            ? `La base de seguidores ${seguidoresNeto.signo === "baja" ? "cayó" : "creció"} un ${seguidoresNeto.pct.replace(/^[+−-]\s*/, "")} este mes`
            : "Crecimiento de seguidores"
        }
        subtitulo="Seguidores ganados, acumulado en el periodo"
      >
        {/* La curva ocupa la lámina entera (gana de 0 al neto); el número héroe se funde en el
            hueco que deja la pendiente arriba a la izquierda. Cero lienzo muerto. */}
        <div className="relative h-full">
          <div className="absolute inset-x-0 bottom-5">
            <AreaBold
              valores={ganadosSerie}
              w={ANCHO_GRAFICA}
              h={332}
              id="grad-seguidores"
              color={colorSeguidores}
              grosor={2.75}
              padTop={40}
              opacidadArea={0.24}
              marcarFinal
            />
            <RangoFechas data={seguidores} />
          </div>
          <div className="absolute left-0 top-2 max-w-[42%]">
            {seguidoresNeto ? (
              <>
                <p
                  className={`text-[60px] font-light leading-none tracking-[-0.02em] tabular-nums ${colorSigno(seguidoresNeto.signo)}`}
                >
                  {finos(seguidoresNeto.texto)}
                </p>
                <p className={`mt-3 ${EYEBROW} text-neutral-500`}>Seguidores netos</p>
                <p className="mt-4 text-sm tabular-nums text-neutral-600">
                  {finos(seguidoresNeto.pct)}
                  <span className="ml-2 text-neutral-500">· {seguidoresNeto.porDia}</span>
                </p>
              </>
            ) : (
              <p className="text-sm text-neutral-500">Sin datos de seguidores en el periodo.</p>
            )}
          </div>
        </div>
      </Marco>
    ),
  });

  // 7 · Mezcla de interacciones — UNA barra 100 % agregada; naranja = interacción de alto valor.
  slides.push({
    clave: "mezcla",
    nodo: (
      <Marco
        marca={marcaLabel}
        periodo={periodo}
        etiqueta={etiqueta}
        titulo={
          desgloseMix.total > 0
            ? `El ${desgloseMix.altoValorPct} % de las interacciones se comparte o se guarda`
            : "Mezcla de interacciones"
        }
        subtitulo={
          desgloseMix.total > 0
            ? `Sobre ${finos(numeroCompactoFijo(desgloseMix.total))} interacciones del periodo`
            : "Composición de las interacciones del periodo"
        }
      >
        <div className="flex h-full flex-col justify-center gap-9">
          <div>
            {/* Barra 100 % alta y confiada; el % vive DENTRO de cada tramo lo bastante ancho. */}
            <div className="flex h-[76px] w-full gap-[3px] overflow-hidden rounded-xl">
              {desgloseMix.segmentos.map((s) => (
                <div
                  key={s.label}
                  className="flex items-center justify-center"
                  style={{ width: `${s.pct}%`, background: s.color }}
                >
                  {s.pct >= 8 && (
                    <span className="text-base font-medium tabular-nums" style={{ color: textoSobre(s.color) }}>
                      {s.pct}&#8239;%
                    </span>
                  )}
                </div>
              ))}
            </div>
            {/* El corchete abraza el tramo naranja (lo de alto valor) y nombra el dato del título. */}
            {desgloseMix.altoValorPct > 0 && (
              <div className="mt-2.5 flex w-full">
                <div style={{ width: `${100 - desgloseMix.altoValorPct}%` }} />
                <div className="flex flex-col items-center" style={{ width: `${desgloseMix.altoValorPct}%` }}>
                  <div className="h-2 w-full border-x border-b border-neutral-300" />
                  <span className="mt-2 whitespace-nowrap text-[11px] font-medium tabular-nums text-orange-600">
                    Se comparte o se guarda · {desgloseMix.altoValorPct}&#8239;%
                  </span>
                </div>
              </div>
            )}
          </div>
          <ul className="grid grid-cols-4 gap-8 border-t border-neutral-100 pt-7">
            {desgloseMix.segmentos.map((s) => (
              <li key={s.label} className="flex flex-col">
                <span className="flex items-center gap-2 text-xs text-neutral-500">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: s.color }} />
                  {s.label}
                </span>
                <span className="mt-2.5 text-[26px] font-light leading-none tracking-[-0.02em] tabular-nums text-neutral-900">
                  {finos(numeroCompactoFijo(s.valor))}
                </span>
                <span className="mt-1.5 text-xs tabular-nums text-neutral-400">{s.pct}&#8239;% del total</span>
              </li>
            ))}
          </ul>
        </div>
      </Marco>
    ),
  });

  // 8 · Top piezas — tabla con la pieza estrella (fila nº 1) destacada.
  slides.push({
    clave: "top",
    nodo: (
      <Marco
        marca={marcaLabel}
        periodo={periodo}
        etiqueta={etiqueta}
        titulo={
          pctEstrella > 0
            ? `Una pieza valió el ${pctEstrella} % de las vistas del mes`
            : "Top piezas"
        }
        subtitulo={
          multiploEstrella > 1
            ? `La más vista rindió ${multiploEstrella}× la pieza media del periodo`
            : "Las publicaciones más vistas del periodo"
        }
      >
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className={`border-b border-neutral-200 text-[11px] uppercase tracking-[0.14em] ${TONO.tablaHeader}`}>
              <th className="w-8 py-3 text-left font-medium">#</th>
              <th className="py-3 pr-4 text-left font-medium">Pieza</th>
              <th className="px-4 py-3 text-left font-medium">Red</th>
              <th className="px-4 py-3 text-left font-medium">Publicado</th>
              <th className="px-4 py-3 text-right font-medium">Vistas</th>
              <th className="px-4 py-3 text-right font-medium">Interac.</th>
              <th className="py-3 pl-4 text-right font-medium">Eng.</th>
            </tr>
          </thead>
          <tbody>
            {topPiezas.map((p, i) => (
              // La fila es enlace clicable al post (toca en el móvil); el exportador lo superpone.
              <tr key={i} className="border-b border-neutral-100" data-pdf-enlace={p.url}>
                <td className={`py-3 text-left tabular-nums ${i === 0 ? "font-medium text-orange-600" : "text-neutral-500"}`}>
                  {i + 1}
                </td>
                <td className={`max-w-[380px] py-3 pr-4 ${i === 0 ? "font-medium text-neutral-900" : TONO.tablaCelda}`}>
                  <span className="flex items-center gap-1.5">
                    <span className="truncate">{p.titulo}</span>
                    {p.url && <span className="shrink-0 text-neutral-300">↗</span>}
                  </span>
                </td>
                <td className="px-4 py-3 text-neutral-500">{nombreRed(p.red)}</td>
                <td className="px-4 py-3 tabular-nums text-neutral-500">{p.publicado}</td>
                <td className={`px-4 py-3 text-right tabular-nums ${i === 0 ? "font-medium text-neutral-900" : TONO.tablaCelda}`}>
                  {finos(numeroCompactoFijo(p.vistas))}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-neutral-600">{finos(numeroCompactoFijo(p.interacciones))}</td>
                <td className="py-3 pl-4 text-right tabular-nums text-neutral-600">{p.engagement.toFixed(1)}&#8239;%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Marco>
    ),
  });

  // Cierre · lo que dejó el mes (3 cifras derivadas, NO repiten los KPIs) + recomendaciones.
  slides.push({
    clave: "cierre",
    nodo: (
      <Marco
        marca={marcaLabel}
        periodo={periodo}
        etiqueta={etiqueta}
        titulo="Conclusiones y foco"
        subtitulo={`Lo que dejó ${periodo} y qué hacer el próximo mes`}
      >
        <div className="flex h-full flex-col justify-center gap-12">
          <div
            className="grid gap-x-10"
            style={{ gridTemplateColumns: conclusiones.map(() => "1fr").join(" 1px ") }}
          >
            {conclusiones.map((c: ConclusionInforme, i) => (
              <React.Fragment key={c.label}>
                {i > 0 && <div className="self-stretch bg-neutral-100" />}
                <div className="flex flex-col">
                  {/* Cifra neutra en tinta firme (neutral-800), no gris-400: dato, no "deshabilitado". */}
                  <p
                    className={`text-[52px] font-light leading-none tracking-[-0.02em] tabular-nums ${
                      c.signo === "sube" ? "text-emerald-600" : c.signo === "baja" ? "text-red-600" : "text-neutral-800"
                    }`}
                  >
                    {finos(c.valor)}
                  </p>
                  <p className={`mt-3 ${EYEBROW} text-neutral-500`}>{c.label}</p>
                  <p className="mt-3 text-balance text-[13px] leading-snug text-neutral-600">{c.nota}</p>
                </div>
              </React.Fragment>
            ))}
          </div>
          <div className="border-t border-neutral-100 pt-6">
            <p className={`${EYEBROW} text-neutral-500`}>Foco del próximo periodo</p>
            {/* space-y-7 (28px) > interlineado (leading-relaxed ≈ 24px): la separación ENTRE viñetas
                supera la separación de líneas DENTRO de una, así una recomendación de dos líneas se
                lee como un grupo y nunca se confunde con la siguiente. El punto va en una caja de la
                altura de una línea (items-center) para alinearse a la PRIMERA línea pase lo que pase. */}
            <ul className="mt-4 space-y-7">
              {recomendaciones.map((r, i) => (
                <li
                  key={i}
                  className="flex max-w-3xl items-start gap-3 text-[15px] font-light leading-relaxed text-neutral-800"
                >
                  <span aria-hidden className="flex h-6 shrink-0 items-center">
                    <span className="h-1.5 w-1.5 rounded-full bg-orange-400" />
                  </span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Marco>
    ),
  });

  return slides;
}

/**
 * Deck completo del informe como pila vertical de diapositivas a tamaño real, para que el
 * exportador lo rasterice a PDF. No interactivo: sin toolbar, sin selectores, sin scroll propio.
 */
export function Informe({ data }: { data: InformeProps }) {
  const slides = diapositivas(data);
  return (
    <div className="flex flex-col">
      {slides.map((s) => (
        <React.Fragment key={s.clave}>{s.nodo}</React.Fragment>
      ))}
    </div>
  );
}
