/**
 * Deck del informe de Métricas listo para rasterizar a PDF: una PILA VERTICAL de
 * diapositivas 1280×720 a tamaño real (sin escalar, sin toolbar, sin selectores). Lienzo
 * gris claro, marca protagonista, una idea por diapositiva. La regla del deck: el TÍTULO de
 * cada lámina es el INSIGHT (qué pasó), no la categoría; el gráfico debajo lo respalda.
 * Dirigido EXCLUSIVAMENTE por `InformeProps` (los insights se calculan en `desdeEntradas`).
 */
import { AreaChart } from "@tremor/react";
import qrcode from "qrcode-generator";
import * as React from "react";

import { nombreRed, numeroCompactoFijo } from "@/lib/formato";

import { LOGOS_MARCA } from "./logos";
import type {
  ConclusionInforme,
  FilaRanking,
  InformeProps,
  KpiInforme,
  PuntoTendencia,
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
  coverCaption: "text-neutral-500",
} as const;

/** Overline / eyebrow ÚNICO del deck (mismo tracking en toda lámina). */
const EYEBROW = "text-[11px] font-medium uppercase tracking-[0.18em]";

/**
 * Doma de las gráficas Tremor (recharts por debajo) para serenidad: fuera rejilla, ejes y
 * rayitas de tick; ticks en gris fino; relleno del área a neblina. Mantiene los colores reales.
 */
const CHART_SERENO =
  "[&_.recharts-cartesian-grid]:hidden " +
  "[&_.recharts-cartesian-axis-line]:stroke-transparent " +
  "[&_.recharts-cartesian-axis-tick-line]:stroke-transparent " +
  "[&_.recharts-cartesian-axis-tick_text]:fill-neutral-400 " +
  "[&_.recharts-cartesian-axis-tick_text]:text-[11px]";

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

/** Etiqueta legible del formato del post. */
const FORMATO_LABEL: Record<string, string> = {
  reel: "Reel",
  foto: "Foto",
  carrusel: "Carrusel",
  video: "Video",
  link: "Enlace",
  texto: "Texto",
};

/**
 * QR de una URL como SVG VECTORIAL (n\u00edtido a cualquier escala al rasterizar a PDF; sin red ni
 * CORS). S\u00edncrono: genera la matriz y pinta un solo `path` con los m\u00f3dulos oscuros.
 */
function QR({ valor, size }: { valor: string; size: number }) {
  const qr = qrcode(0, "M");
  qr.addData(valor);
  qr.make();
  const n = qr.getModuleCount();
  const cell = size / n;
  let d = "";
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      if (qr.isDark(r, c)) {
        const s = cell.toFixed(2);
        d += `M${(c * cell).toFixed(2)} ${(r * cell).toFixed(2)}h${s}v${s}h-${s}z`;
      }
    }
  }
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} shapeRendering="crispEdges" aria-hidden>
      <path d={d} fill="#262626" />
    </svg>
  );
}

/** Diapositiva 16:9: lienzo (gris claro, o color de marca en portada), etiqueta, título y pie. */
function Marco({
  marca,
  periodo,
  etiqueta,
  titulo,
  subtitulo,
  children,
  portada = false,
  bg,
}: {
  marca: string;
  periodo: string;
  etiqueta?: string;
  titulo?: string;
  subtitulo?: string;
  children?: React.ReactNode;
  portada?: boolean;
  bg?: string;
}) {
  return (
    <section className="informe-slide" style={bg ? { background: bg } : undefined}>
      <div className="flex h-full flex-col px-20 pb-12 pt-16">
        {!portada && (
          <header className="mb-9">
            <p className={`${EYEBROW} ${TONO.topLabel}`}>{etiqueta}</p>
            <h2 className={`mt-3 max-w-4xl text-balance text-[28px] font-light leading-tight tracking-[-0.01em] ${TONO.titulo}`}>
              {titulo}
            </h2>
            {subtitulo && <p className={`mt-1.5 text-sm font-normal ${TONO.subtitulo}`}>{subtitulo}</p>}
          </header>
        )}

        <div className="min-h-0 flex-1">{children}</div>

        {!portada && (
          <footer className={`mt-8 flex items-center justify-between gap-6 border-t border-neutral-100 pt-4 text-[10px] ${TONO.pie}`}>
            <span className="whitespace-nowrap uppercase tracking-[0.18em]">
              {marca} · Todas las redes · {periodo}
            </span>
            <span className="shrink-0 uppercase tracking-[0.18em]">keni</span>
          </footer>
        )}
      </div>
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

/** Fila de un ranking horizontal: punto de color, nombre, valor + %, y barra de progreso. */
function FilaRank({ fila, max }: { fila: FilaRanking; max: number }) {
  return (
    <li>
      <div className="flex items-baseline justify-between gap-3">
        <span className="flex items-center gap-2.5 truncate text-sm text-neutral-700">
          <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: fila.color }} />
          {fila.nombre}
        </span>
        <span className="shrink-0 text-sm tabular-nums text-neutral-900">
          {finos(numeroCompactoFijo(fila.valor))}
          {/* El % en su propia caja de ancho fijo right-aligned: un % de un dígito ("6 %") no empuja
              la cifra principal, así las cifras forman una columna vertical limpia. */}
          <span className="ml-2 inline-block w-9 text-right text-xs text-neutral-600">{fila.pct}&#8239;%</span>
        </span>
      </div>
      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-neutral-100">
        <div
          className="h-full rounded-full"
          style={{ width: `${max > 0 ? (fila.valor / max) * 100 : 0}%`, background: fila.color }}
        />
      </div>
    </li>
  );
}

/** Lista de ranking horizontal ordenada (reparto por red, comparativa por marca). */
function Ranking({ filas, columnas = 1 }: { filas: FilaRanking[]; columnas?: number }) {
  const max = filas.reduce((m, f) => Math.max(m, f.valor), 0);
  return (
    <ul className={`grid gap-x-12 gap-y-8 ${columnas === 2 ? "grid-cols-2" : "grid-cols-1"}`}>
      {filas.map((f) => (
        <FilaRank key={f.clave} fila={f} max={max} />
      ))}
    </ul>
  );
}

/**
 * Un AreaChart Tremor ya domado (sin grid/ejes/tooltip/animación), color por hex. Sin eje X: las
 * etiquetas de los extremos las recorta el rasterizador (salían "i1 may"/"29 jui"); el rango de
 * fechas se pone como texto bajo la gráfica, donde no se corta.
 */
function AreaSerena({
  data,
  categoria,
  color,
  alto,
}: {
  data: PuntoTendencia[];
  categoria: "Vistas" | "Interacciones";
  /** Nombre de color Tremor (mapea a clase Tailwind safelisteada; el hex no lo está). */
  color: string;
  alto: number;
}) {
  return (
    <AreaChart
      data={data}
      index="fecha"
      categories={[categoria]}
      colors={[color]}
      valueFormatter={numeroCompactoFijo}
      showLegend={false}
      showGridLines={false}
      showYAxis={false}
      showXAxis={false}
      showTooltip={false}
      showAnimation={false}
      startEndOnly
      curveType="monotone"
      className={`w-full ${CHART_SERENO}`}
      style={{ height: alto }}
    />
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
function diapositivas(data: InformeProps, breve: boolean): Slide[] {
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
    engPorRed,
    engInsight,
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
  const coverBg = esTodas ? COVER_TODAS : marcaId ? COVER_BG[marcaId] : undefined;
  const slides: Slide[] = [];

  // 1 · Portada — la marca es la protagonista (logo sobre su color). En "Todas las marcas",
  // portada-portfolio: los 5 logos juntos sobre fondo oscuro neutro.
  slides.push({
    clave: "portada",
    nodo: (
      <Marco marca={marcaLabel} periodo={periodo} portada bg={coverBg}>
        <div className="flex h-full flex-col items-center justify-center text-center">
          {esTodas ? (
            // Portfolio: cada marca en una celda de tamaño UNIFORME (equilibra el peso óptico).
            // Todas en blanco plano: los 4 logos blancos vía grayscale, y Piso 15 como wordmark
            // blanco (su emblema es un disco para fondo oscuro y no admite calado a blanco sin
            // perder el "15"; el wordmark mantiene el mismo tratamiento de tinta única que el resto).
            <div className="flex max-w-3xl flex-wrap items-center justify-center gap-x-12 gap-y-10">
              {MARCAS_PORTFOLIO.filter((id) => LOGOS_MARCA[id]).map((id) => (
                <div key={id} className="flex h-[92px] w-[224px] items-center justify-center">
                  {id === "piso-15" ? (
                    <span
                      style={{
                        fontFamily: "'Montserrat'",
                        fontWeight: 800,
                        fontSize: 52,
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
                      className="max-h-[64px] max-w-[210px] object-contain"
                      style={{ filter: "grayscale(1)" }}
                    />
                  )}
                </div>
              ))}
            </div>
          ) : (
            // Logo de la marca centrado en una caja sobria y común: presencia discreta con aire
            // alrededor, no a sangre. object-contain lo encaja sea cual sea su proporción (UnoTV
            // ancho, Fundación finísimo, Claro casi cuadrado) para un tamaño óptico parejo.
            <LogoOWordmark id={marcaId} nombre={marcaLabel} box={{ h: 140, w: 250 }} />
          )}
          {/* Ancho completo (no encogido al texto): así el interletrado final nunca empuja la
              última palabra a otra línea. Cabe en una sola; text-balance reparte en dos solo si
              algún periodo llegara a ser larguísimo. */}
          <p className={`mt-16 w-full text-balance ${EYEBROW} tracking-[0.24em] ${coverBg ? "text-white/90" : TONO.coverCaption}`}>
            Informe de métricas · {esTodas ? "Todas las marcas · " : ""}
            {periodo}
          </p>
        </div>
      </Marco>
    ),
  });

  // Versión BREVE (lectura ejecutiva, SIN explicaciones): portada + 2 láminas de DATOS puros,
  // para revisar de un vistazo sin frases que leer. A = el cuadro de cifras (números + flechas
  // verde/rojo). B = el reparto en barras (por red, o por marca en "todas").
  if (breve) {
    const periodoTitulo = periodo.charAt(0).toUpperCase() + periodo.slice(1);
    // A · Las cifras del mes: Visualizaciones como héroe; el resto + seguidores netos como
    // 4 KPIs de respaldo, jerarquía 2:1. La dirección la dicen las flechas, no una frase.
    const heroKpi = kpis.find((k) => k.etiqueta === "Visualizaciones") ?? kpis[1];
    const porNombre = (n: string) => kpis.find((k) => k.etiqueta === n);
    const tileSeguidores: KpiInforme | undefined = seguidoresNeto
      ? {
          etiqueta: "Seguidores netos",
          valor: seguidoresNeto.texto,
          titulo: seguidoresNeto.texto,
          delta: { texto: seguidoresNeto.pct, signo: seguidoresNeto.signo },
        }
      : porNombre("Piezas");
    const kpisBreve = [porNombre("Alcance"), porNombre("Interacciones"), porNombre("Engagement"), tileSeguidores].filter(
      (k): k is KpiInforme => Boolean(k),
    );
    slides.push({
      clave: "breve-veredicto",
      nodo: (
        <Marco
          marca={marcaLabel}
          periodo={periodo}
          etiqueta={etiqueta}
          titulo={periodoTitulo}
        >
          <div className="flex h-full flex-col justify-center">
            {heroKpi && (
              <div>
                <div className="flex items-baseline gap-4">
                  <span className="text-[64px] font-light leading-none tracking-[-0.03em] tabular-nums text-neutral-900">
                    {finos(heroKpi.valor)}
                  </span>
                  {heroKpi.delta && (
                    <span className={`text-base font-medium tabular-nums ${colorSigno(heroKpi.delta.signo)}`}>
                      {flechaSigno(heroKpi.delta.signo) && <span className="mr-1">{flechaSigno(heroKpi.delta.signo)}</span>}
                      {heroKpi.delta.texto}
                    </span>
                  )}
                </div>
                <p className={`mt-3 ${EYEBROW} ${TONO.kpiLabel}`}>
                  {heroKpi.etiqueta}
                  <span className="ml-2 font-normal normal-case tracking-normal text-neutral-500">vs. {mesAnterior}</span>
                </p>
              </div>
            )}
            <div
              className="mt-14 grid gap-x-8"
              style={{ gridTemplateColumns: kpisBreve.map(() => "1fr").join(" 1px ") }}
            >
              {kpisBreve.map((k, i) => (
                <React.Fragment key={k.etiqueta}>
                  {i > 0 && <div className="self-stretch bg-neutral-100" />}
                  <div className="flex flex-col">
                    <p className={`${EYEBROW} ${TONO.kpiLabel}`}>{k.etiqueta}</p>
                    <p className={`mt-3 text-[30px] font-light leading-none tracking-[-0.02em] tabular-nums ${TONO.kpiValor}`}>
                      {finos(k.valor)}
                    </p>
                    {k.delta && (
                      <p className={`mt-2 text-xs font-medium tabular-nums ${colorSigno(k.delta.signo)}`}>
                        {flechaSigno(k.delta.signo) && <span className="mr-1">{flechaSigno(k.delta.signo)}</span>}
                        {k.delta.texto}
                      </p>
                    )}
                  </div>
                </React.Fragment>
              ))}
            </div>
          </div>
        </Marco>
      ),
    });

    // B · El reparto en barras: por red (marca individual) o por marca ("todas"). Visual puro,
    // sin frases: la barra más larga es la que manda.
    const filasReparto = esTodas ? cuentas : porRed;
    slides.push({
      clave: "breve-foco",
      nodo: (
        <Marco
          marca={marcaLabel}
          periodo={periodo}
          etiqueta={etiqueta}
          titulo={`Visualizaciones por ${esTodas ? "marca" : "red"}`}
        >
          <div className="flex h-full items-center pb-4">
            <div className="w-full">
              <Ranking filas={filasReparto} />
            </div>
          </div>
        </Marco>
      ),
    });

    // C · (solo si hay enlaces) Lo más visto: las piezas top como tarjetas — cifra de impacto +
    // caption + un QR que abre el post real (el backend de métricas no da la miniatura, sí el url).
    const piezasConUrl = topPiezas.filter((p) => p.url).slice(0, 3);
    if (piezasConUrl.length > 0) {
      const cols = piezasConUrl.length === 1 ? "grid-cols-1" : piezasConUrl.length === 2 ? "grid-cols-2" : "grid-cols-3";
      slides.push({
        clave: "breve-piezas",
        nodo: (
          <Marco marca={marcaLabel} periodo={periodo} etiqueta={etiqueta} titulo="Lo más visto">
            <div className="flex h-full items-center">
              <div className={`grid w-full gap-x-14 ${cols}`}>
                {piezasConUrl.map((p, i) => {
                  const caption = p.titulo.length > 90 ? `${p.titulo.slice(0, 87)}…` : p.titulo;
                  return (
                    <div key={i} className="flex flex-col items-start">
                      <p className={`${EYEBROW} ${TONO.kpiLabel}`}>
                        {nombreRed(p.red)}
                        {p.formato ? ` · ${FORMATO_LABEL[p.formato] ?? p.formato}` : ""}
                      </p>
                      <p className="mt-3 text-[40px] font-light leading-none tracking-[-0.02em] tabular-nums text-neutral-900">
                        {finos(numeroCompactoFijo(p.vistas))}
                      </p>
                      <p className="mt-1 text-xs uppercase tracking-[0.14em] text-neutral-500">Visualizaciones</p>
                      {/* Caja de 2 líneas con la cita centrada: una cita de 1 línea reparte el hueco
                          arriba/abajo (ritmo homogéneo entre columnas) y los QR siguen a la misma altura. */}
                      <div className="mt-4 flex min-h-[2.5rem] items-start">
                        <p className="text-balance text-sm leading-snug text-neutral-700">«{caption}»</p>
                      </div>
                      {/* Zona enlazable: el QR (escanear) + «Abrir el post» (tocar en el móvil).
                          `data-pdf-enlace` la convierte en enlace clicable que el exportador
                          superpone sobre la imagen rasterizada. */}
                      <a
                        href={p.url ?? ""}
                        target="_blank"
                        rel="noreferrer"
                        data-pdf-enlace={p.url}
                        className="mt-6 flex items-center gap-3.5 no-underline"
                      >
                        <div className="rounded-lg border border-neutral-200 bg-white p-2">
                          <QR valor={p.url ?? ""} size={78} />
                        </div>
                        <span className="text-[13px] font-medium leading-snug text-orange-600">
                          Abrir el post ↗
                          <span className="mt-0.5 block text-[11px] font-normal text-neutral-500">o escanea el QR</span>
                        </span>
                      </a>
                    </div>
                  );
                })}
              </div>
            </div>
          </Marco>
        ),
      });
    }

    return slides;
  }

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

  // 3 · Tendencia diaria — small-multiple vistas + interacciones; el título marca el mejor día.
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
            <p className={`mb-1 ${EYEBROW} ${TONO.kpiLabel}`}>
              Visualizaciones
              <span className="ml-3 font-normal normal-case tracking-normal text-neutral-500">
                {mediaVistas > 0 && <>media {finos(numeroCompactoFijo(Math.round(mediaVistas)))} / día</>}
                {picoVistas && (
                  <>
                    {mediaVistas > 0 && " · "}
                    pico {finos(numeroCompactoFijo(picoVistas.valor))} el {picoVistas.fecha}
                  </>
                )}
              </span>
            </p>
            <AreaSerena data={tendencia} categoria="Vistas" color="orange" alto={210} />
          </div>
          <div>
            <p className={`mb-1 ${EYEBROW} ${TONO.kpiLabel}`}>
              Interacciones
              {mediaInteracciones > 0 && (
                <span className="ml-3 font-normal normal-case tracking-normal text-neutral-500">
                  media {finos(numeroCompactoFijo(Math.round(mediaInteracciones)))} / día
                </span>
              )}
            </p>
            <AreaSerena data={tendencia} categoria="Interacciones" color="neutral" alto={150} />
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
    const maxRate = engPorRed[0].rate || 1;
    slides.push({
      clave: "eng-red",
      nodo: (
        <Marco
          marca={marcaLabel}
          periodo={periodo}
          etiqueta={etiqueta}
          titulo={engInsight || "Dónde engancha mejor"}
          subtitulo="Interacción por vista · más vistas no es más conexión"
        >
          <div className="flex h-full items-center">
            <div className="w-full">
              <ul className="grid gap-y-8">
                {engPorRed.map((r) => (
                  <li key={r.clave}>
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="flex items-center gap-2.5 text-sm text-neutral-700">
                        <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: r.color }} />
                        {r.nombre}
                      </span>
                      <span className="shrink-0 text-sm tabular-nums text-neutral-900">{r.rate.toFixed(1)}&#8239;%</span>
                    </div>
                    <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-neutral-100">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${(r.rate / maxRate) * 100}%`, background: r.color }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
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
        <div className="grid h-full grid-cols-5 items-center gap-12">
          <div className="col-span-2">
            {seguidoresNeto ? (
              <>
                <p className={`text-[56px] font-light leading-none tracking-[-0.02em] tabular-nums ${colorSigno(seguidoresNeto.signo)}`}>
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
          <div className="col-span-3">
            <AreaChart
              data={seguidores}
              index="fecha"
              categories={["Ganados"]}
              colors={["emerald"]}
              valueFormatter={numeroCompactoFijo}
              showLegend={false}
              showGridLines={false}
              showYAxis={false}
              showXAxis={false}
              showTooltip={false}
              showAnimation={false}
              startEndOnly
              curveType="linear"
              minValue={0}
              className={`w-full ${CHART_SERENO} [&_.recharts-area-area]:opacity-[0.2]`}
              style={{ height: 300 }}
            />
            <RangoFechas data={seguidores} />
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
        <div className="flex h-full flex-col justify-center gap-10">
          <div className="flex h-7 w-full gap-[2px] overflow-hidden rounded-lg">
            {desgloseMix.segmentos.map((s) => (
              <div key={s.label} style={{ width: `${s.pct}%`, background: s.color }} title={`${s.label} ${s.pct}%`} />
            ))}
          </div>
          <ul className="grid grid-cols-4 gap-8">
            {desgloseMix.segmentos.map((s) => (
              <li key={s.label} className="flex flex-col">
                <span className="flex items-center gap-2 text-xs text-neutral-500">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: s.color }} />
                  {s.label}
                </span>
                <span className="mt-2 text-[28px] font-light leading-none tracking-[-0.02em] tabular-nums text-neutral-900">
                  {s.pct}&#8239;%
                </span>
                <span className="mt-1.5 text-xs tabular-nums text-neutral-500">{finos(numeroCompactoFijo(s.valor))}</span>
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
            <ul className="mt-4 space-y-3">
              {recomendaciones.map((r, i) => (
                <li key={i} className="flex gap-3 text-[15px] font-light leading-snug text-neutral-800">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-orange-400" />
                  <span className="max-w-4xl">{r}</span>
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
export function Informe({ data, breve = false }: { data: InformeProps; breve?: boolean }) {
  const slides = diapositivas(data, breve);
  return (
    <div className="flex flex-col">
      {slides.map((s) => (
        <React.Fragment key={s.clave}>{s.nodo}</React.Fragment>
      ))}
    </div>
  );
}
