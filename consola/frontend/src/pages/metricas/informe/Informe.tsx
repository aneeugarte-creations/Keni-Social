/**
 * Deck del informe de Métricas listo para rasterizar a PDF: una PILA VERTICAL de
 * diapositivas 1280×720 a tamaño real (sin escalar, sin toolbar, sin selectores). Lienzo
 * gris claro, marca protagonista, una idea por diapositiva. La regla del deck: el TÍTULO de
 * cada lámina es el INSIGHT (qué pasó), no la categoría; el gráfico debajo lo respalda.
 * Dirigido EXCLUSIVAMENTE por `InformeProps` (los insights se calculan en `desdeEntradas`).
 */
import { AreaChart } from "@tremor/react";
import * as React from "react";

import { nombreRed, numeroCompacto } from "@/lib/formato";

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
  pie: "text-neutral-300",
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
const MARCAS_PORTFOLIO = ["unotv", "claro-sports", "nacion-gamer", "piso-15", "fundacion"];

/** Color de la dirección de una variación (verde sube, rojo baja, gris neutro). */
function colorSigno(signo?: "sube" | "baja" | "igual" | "nuevo" | "neutral"): string {
  if (signo === "sube") return "text-emerald-600";
  if (signo === "baja") return "text-red-600";
  return "text-neutral-400";
}
function flechaSigno(signo?: string): string {
  return signo === "sube" ? "↑" : signo === "baja" ? "↓" : "";
}
/** Espacio fino entre cifra y unidad (M / %) para que el dato lea como uno solo. */
const finos = (s: string): string => s.replace(/ /g, "\u202f");

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
            <h2 className={`mt-3 max-w-4xl text-[28px] font-light leading-tight tracking-[-0.01em] ${TONO.titulo}`}>
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
function TileKpi({ kpi, mesAnterior, conDivisor }: { kpi: KpiInforme; mesAnterior: string; conDivisor: boolean }) {
  return (
    <div className={`flex min-h-[124px] flex-col ${conDivisor ? "border-l border-neutral-100 pl-8" : ""}`}>
      <p className={`${EYEBROW} ${TONO.kpiLabel}`}>{kpi.etiqueta}</p>
      <p className={`mt-4 text-[44px] font-light leading-none tracking-[-0.02em] tabular-nums ${TONO.kpiValor}`} title={kpi.titulo}>
        {finos(kpi.valor)}
      </p>
      {kpi.delta ? (
        <p className={`mt-3 text-xs font-medium tabular-nums ${colorSigno(kpi.delta.signo)}`}>
          {flechaSigno(kpi.delta.signo) && <span className="mr-1">{flechaSigno(kpi.delta.signo)}</span>}
          {kpi.delta.texto}
          <span className="ml-1.5 font-normal text-neutral-400">vs. {mesAnterior}</span>
        </p>
      ) : kpi.secundario ? (
        <p className="mt-3 text-xs font-normal tabular-nums text-neutral-400">{finos(kpi.secundario)}</p>
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
        <span className="shrink-0 text-sm tabular-nums text-neutral-500">
          {numeroCompacto(fila.valor)}
          <span className="ml-2 text-xs text-neutral-400">{fila.pct}&#8239;%</span>
        </span>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-neutral-100">
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

/** Un AreaChart Tremor ya domado (sin grid/ejes/tooltip/animación), color por hex. */
function AreaSerena({
  data,
  categoria,
  color,
  alto,
  conEjeX,
}: {
  data: PuntoTendencia[];
  categoria: "Vistas" | "Interacciones";
  /** Nombre de color Tremor (mapea a clase Tailwind safelisteada; el hex no lo está). */
  color: string;
  alto: number;
  conEjeX: boolean;
}) {
  return (
    <AreaChart
      data={data}
      index="fecha"
      categories={[categoria]}
      colors={[color]}
      valueFormatter={numeroCompacto}
      showLegend={false}
      showGridLines={false}
      showYAxis={false}
      showXAxis={conEjeX}
      showTooltip={false}
      showAnimation={false}
      startEndOnly
      curveType="monotone"
      className={`w-full ${CHART_SERENO}`}
      style={{ height: alto }}
    />
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
            <div className="flex max-w-2xl flex-wrap items-center justify-center gap-x-16 gap-y-12">
              {MARCAS_PORTFOLIO.filter((id) => LOGOS_MARCA[id]).map((id) => (
                <img key={id} src={LOGOS_MARCA[id]} alt="" className="h-[84px] w-auto max-w-[240px] object-contain" />
              ))}
            </div>
          ) : (
            <LogoOWordmark id={marcaId} nombre={marcaLabel} box={{ h: 300, w: 940 }} />
          )}
          <p className={`mt-16 ${EYEBROW} tracking-[0.24em] ${coverBg ? "text-white/70" : TONO.coverCaption}`}>
            Informe de métricas · {esTodas ? "Todas las marcas · " : ""}
            {periodo}
          </p>
        </div>
      </Marco>
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
        <div className="grid h-full grid-cols-5 place-content-center gap-x-8">
          {kpis.map((k, i) => (
            <TileKpi key={k.etiqueta} kpi={k} mesAnterior={mesAnterior} conDivisor={i > 0} />
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
            ? `El ${picoVistas.fecha} concentró el ${picoVistas.pct}\u202f% de las vistas del mes`
            : "Tendencia diaria"
        }
        subtitulo="Visualizaciones e interacciones por día"
      >
        <div className="flex h-full flex-col justify-center gap-6">
          <div>
            <p className={`mb-1 ${EYEBROW} ${TONO.kpiLabel}`}>
              Visualizaciones
              <span className="ml-3 font-normal normal-case tracking-normal text-neutral-400">
                {mediaVistas > 0 && <>media {finos(numeroCompacto(Math.round(mediaVistas)))} / día</>}
                {picoVistas && (
                  <>
                    {mediaVistas > 0 && " · "}
                    pico {finos(numeroCompacto(picoVistas.valor))} el {picoVistas.fecha}
                  </>
                )}
              </span>
            </p>
            <AreaSerena data={tendencia} categoria="Vistas" color="orange" alto={210} conEjeX={false} />
          </div>
          <div>
            <p className={`mb-1 ${EYEBROW} ${TONO.kpiLabel}`}>Interacciones</p>
            <AreaSerena data={tendencia} categoria="Interacciones" color="violet" alto={150} conEjeX />
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
          <div className="w-full max-w-3xl">
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
            <div className="w-full max-w-3xl">
              <ul className="grid gap-y-8">
                {engPorRed.map((r) => (
                  <li key={r.clave}>
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="flex items-center gap-2.5 text-sm text-neutral-700">
                        <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: r.color }} />
                        {r.nombre}
                      </span>
                      <span className="shrink-0 text-sm tabular-nums text-neutral-500">{r.rate}&#8239;%</span>
                    </div>
                    <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-neutral-100">
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
              ? `${cuentas[0].nombre} lidera con el ${cuentas[0].pct}\u202f% de las vistas`
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
          seguidoresNeto
            ? `${finos(seguidoresNeto.texto)} seguidores ${seguidoresNeto.signo === "baja" ? "menos" : "nuevos"} este mes`
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
                <p className={`mt-3 ${EYEBROW} text-neutral-400`}>Seguidores netos</p>
                <p className="mt-4 text-sm tabular-nums text-neutral-600">
                  {finos(seguidoresNeto.pct)}
                  <span className="ml-2 text-neutral-400">· {seguidoresNeto.porDia}</span>
                </p>
              </>
            ) : (
              <p className="text-sm text-neutral-400">Sin datos de seguidores en el periodo.</p>
            )}
          </div>
          <div className="col-span-3">
            <AreaChart
              data={seguidores}
              index="fecha"
              categories={["Ganados"]}
              colors={["emerald"]}
              valueFormatter={numeroCompacto}
              showLegend={false}
              showGridLines={false}
              showYAxis={false}
              showTooltip={false}
              showAnimation={false}
              startEndOnly
              curveType="linear"
              minValue={0}
              className={`w-full ${CHART_SERENO} [&_.recharts-area-area]:opacity-[0.2]`}
              style={{ height: 300 }}
            />
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
            ? `El ${desgloseMix.altoValorPct}\u202f% de las interacciones se comparte o se guarda`
            : "Mezcla de interacciones"
        }
        subtitulo={
          desgloseMix.total > 0
            ? `Sobre ${finos(numeroCompacto(desgloseMix.total))} interacciones del periodo`
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
                <span className="mt-1.5 text-xs tabular-nums text-neutral-400">{finos(numeroCompacto(s.valor))}</span>
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
            ? `Una pieza valió el ${pctEstrella}\u202f% de las vistas del mes`
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
              <tr key={i} className="border-b border-neutral-100">
                <td className={`py-3 text-left tabular-nums ${i === 0 ? "font-medium text-orange-600" : "text-neutral-400"}`}>
                  {i + 1}
                </td>
                <td className={`max-w-[380px] truncate py-3 pr-4 ${i === 0 ? "font-medium text-neutral-900" : TONO.tablaCelda}`}>
                  {p.titulo}
                </td>
                <td className="px-4 py-3 text-neutral-500">{nombreRed(p.red)}</td>
                <td className="px-4 py-3 tabular-nums text-neutral-500">{p.publicado}</td>
                <td className={`px-4 py-3 text-right tabular-nums ${i === 0 ? "font-medium text-neutral-900" : TONO.tablaCelda}`}>
                  {finos(numeroCompacto(p.vistas))}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-neutral-600">{finos(numeroCompacto(p.interacciones))}</td>
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
          <div className="grid grid-cols-3 gap-10">
            {conclusiones.map((c: ConclusionInforme, i) => (
              <div key={c.label} className={`flex flex-col ${i === 0 ? "" : "border-l border-neutral-100 pl-10"}`}>
                {/* Cifra neutra en tinta firme (neutral-800), no gris-400: dato, no "deshabilitado". */}
                <p
                  className={`text-[52px] font-light leading-none tracking-[-0.02em] tabular-nums ${
                    c.signo === "sube" ? "text-emerald-600" : c.signo === "baja" ? "text-red-600" : "text-neutral-800"
                  }`}
                >
                  {finos(c.valor)}
                </p>
                <p className={`mt-3 ${EYEBROW} text-neutral-400`}>{c.label}</p>
                <p className="mt-3 text-[13px] leading-snug text-neutral-600">{c.nota}</p>
              </div>
            ))}
          </div>
          <div className="border-t border-neutral-100 pt-6">
            <p className={`${EYEBROW} text-neutral-400`}>Foco del próximo periodo</p>
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
