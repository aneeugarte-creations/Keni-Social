/**
 * Deck del informe de Métricas listo para rasterizar a PDF: una PILA VERTICAL de
 * diapositivas 1280×720 a tamaño real (sin escalar, sin toolbar, sin selectores). Lienzo
 * blanco, marca protagonista, una idea por diapositiva; las gráficas son los MISMOS
 * componentes Tremor de la app con sus colores. Dirigido EXCLUSIVAMENTE por `InformeProps`.
 */
import { AreaChart, BarChart, LineChart } from "@tremor/react";
import * as React from "react";

import { nombreRed, numeroCompacto, numeroCompleto } from "@/lib/formato";

import { LOGOS_MARCA } from "./logos";
import type { ConclusionInforme, CuentaInforme, InformeProps, KpiInforme } from "./tipos";

import "./informe.css";

/**
 * Esquema "Sereno" fijo (jerarquía por tamaño; labels en gris MEDIO, presentes y no
 * susurrados; títulos/números en negro; pie tenue). Mapea cada rol de texto a su clase.
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
  coverCaption: "text-neutral-900",
} as const;

/**
 * Estilo del "wordmark" de cada marca: su tipografía display + color, para escribir el
 * nombre como en su logo cuando no hay imagen. En producción el servidor registra la fuente
 * real de la marca; aquí es la mejor aproximación con el catálogo de fuentes del sistema.
 */
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
      <span style={{ fontWeight: 200, fontSize: size, letterSpacing: "-0.03em" }} className="text-neutral-900">
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

/**
 * Logo real de la marca (asset de Vite, URL estable) ajustado dentro de una caja conservando
 * proporción; si la marca no tiene logo, el wordmark tipográfico. La `<img>` carga del bundle,
 * sin precarga asíncrona, para que el rasterizado a PDF la encuentre lista.
 */
function LogoOWordmark({
  id,
  nombre,
  box,
}: {
  id: string | null;
  nombre: string;
  /** Caja máxima (px): el logo se ajusta dentro conservando proporción (object-contain). */
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

/** Diapositiva 16:9: lienzo blanco con márgenes generosos, etiqueta de marca, título y pie discreto. */
function Marco({
  marca,
  periodo,
  etiqueta,
  titulo,
  subtitulo,
  children,
  portada = false,
}: {
  marca: string;
  periodo: string;
  etiqueta?: string;
  titulo?: string;
  subtitulo?: string;
  children?: React.ReactNode;
  portada?: boolean;
}) {
  return (
    <section className="informe-slide">
      <div className="flex h-full flex-col px-20 pb-12 pt-16">
        {!portada && (
          <header className="mb-9">
            <p className={`text-[11px] font-medium uppercase tracking-[0.22em] ${TONO.topLabel}`}>{etiqueta}</p>
            <h2 className={`mt-3 text-[30px] font-light leading-tight tracking-tight ${TONO.titulo}`}>{titulo}</h2>
            {subtitulo && <p className={`mt-1.5 text-sm font-normal ${TONO.subtitulo}`}>{subtitulo}</p>}
          </header>
        )}

        <div className="min-h-0 flex-1">{children}</div>

        {!portada && (
          <footer className={`mt-8 flex items-center justify-between border-t border-neutral-100 pt-4 text-[10px] tracking-wide ${TONO.pie}`}>
            <span className="uppercase tracking-[0.18em]">
              {marca} · Todas las redes · {periodo}
            </span>
            <span className="uppercase tracking-[0.25em]">keni</span>
          </footer>
        )}
      </div>
    </section>
  );
}

/** Tile de KPI: número grande y ligero, label en mayúsculas, variación discreta. Sin caja. */
function TileKpi({ kpi, mesAnterior }: { kpi: KpiInforme; mesAnterior: string }) {
  const color =
    kpi.delta?.signo === "sube"
      ? "text-emerald-600"
      : kpi.delta?.signo === "baja"
        ? "text-red-600"
        : "text-neutral-400";
  const flecha = kpi.delta?.signo === "sube" ? "↑" : kpi.delta?.signo === "baja" ? "↓" : "";
  return (
    <div className="flex flex-col">
      <p className={`text-[11px] font-medium uppercase tracking-[0.16em] ${TONO.kpiLabel}`}>{kpi.etiqueta}</p>
      <p
        className={`mt-4 text-[44px] font-light leading-none tracking-tight tabular-nums ${TONO.kpiValor}`}
        title={kpi.titulo}
      >
        {/* Espacio fino entre número y unidad (M / %) para que la cifra lea como un solo dato. */}
        {kpi.valor.replace(/\u0020/g, "\u202F")}
      </p>
      {kpi.delta && (
        <p className={`mt-3 text-xs font-medium tabular-nums ${color}`}>
          {flecha && <span className="mr-1">{flecha}</span>}
          {kpi.delta.texto}
          <span className="ml-1.5 font-normal text-neutral-400">vs. {mesAnterior}</span>
        </p>
      )}
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
    kpis,
    tendencia,
    porRed,
    seguidores,
    desglose,
    topPiezas,
    cuentas,
    conclusiones,
    foco,
  } = data;
  const etiqueta = esTodas ? "Todas las marcas" : marcaLabel;
  const slides: Slide[] = [];

  // 1 · Portada — la marca es la protagonista (escala + aire), sin cabeceros.
  slides.push({
    clave: "portada",
    nodo: (
      <Marco marca={marcaLabel} periodo={periodo} portada>
        <div className="flex h-full flex-col items-center justify-center text-center">
          <LogoOWordmark id={marcaId} nombre={marcaLabel} box={{ h: 300, w: 940 }} />
          <p className={`mt-20 text-[11px] font-medium uppercase tracking-[0.3em] ${TONO.coverCaption}`}>
            Informe de métricas · {esTodas ? "Todas las marcas · " : ""}
            {periodo}
          </p>
        </div>
      </Marco>
    ),
  });

  // 2 · Resumen del periodo — 5 KPIs con variación.
  slides.push({
    clave: "resumen",
    nodo: (
      <Marco
        marca={marcaLabel}
        periodo={periodo}
        etiqueta={etiqueta}
        titulo="Resumen del periodo"
        subtitulo="Comparado con el periodo anterior"
      >
        <div className="flex h-full items-center">
          {/* Centrado en la zona y subido un poco para que el centro óptico de la fila caiga
              en el centro de la diapositiva (compensa la altura de la cabecera). */}
          <div className="-mt-10 grid w-full grid-cols-5 gap-10">
            {kpis.map((k) => (
              <TileKpi key={k.etiqueta} kpi={k} mesAnterior={mesAnterior} />
            ))}
          </div>
        </div>
      </Marco>
    ),
  });

  // 3 · Tendencia diaria (AreaChart · Vistas, naranja) — tal cual la app.
  slides.push({
    clave: "tendencia",
    nodo: (
      <Marco
        marca={marcaLabel}
        periodo={periodo}
        etiqueta={etiqueta}
        titulo="Tendencia diaria"
        subtitulo="Visualizaciones por día"
      >
        <div className="flex h-full items-center">
          <AreaChart
            data={tendencia}
            index="fecha"
            categories={["Vistas"]}
            colors={["orange"]}
            valueFormatter={numeroCompacto}
            showLegend={false}
            startEndOnly
            curveType="monotone"
            className="h-[400px] w-full"
          />
        </div>
      </Marco>
    ),
  });

  // 4 · Reparto por red (BarChart apilado · colores por red coloresRed.ts).
  slides.push({
    clave: "por-red",
    nodo: (
      <Marco
        marca={marcaLabel}
        periodo={periodo}
        etiqueta={etiqueta}
        titulo="Reparto por red"
        subtitulo="Visualizaciones por semana y plataforma"
      >
        <div className="flex h-full items-center">
          <BarChart
            data={porRed.data}
            index="intervalo"
            categories={porRed.categorias}
            colors={porRed.colores}
            valueFormatter={numeroCompacto}
            stack
            className="h-[400px] w-full"
          />
        </div>
      </Marco>
    ),
  });

  // 5 · (solo "todas") Comparativa por marca — BarChart (naranja) + reparto.
  if (esTodas) {
    slides.push({
      clave: "por-marca",
      nodo: (
        <Marco
          marca={marcaLabel}
          periodo={periodo}
          etiqueta="Todas las marcas"
          titulo="Comparativa por marca"
          subtitulo="Visualizaciones del periodo"
        >
          <div className="grid h-full grid-cols-5 items-center gap-12">
            <div className="col-span-3">
              <BarChart
                data={cuentas.map((c) => ({ marca: c.marca, Vistas: c.Vistas }))}
                index="marca"
                categories={["Vistas"]}
                colors={["orange"]}
                valueFormatter={numeroCompacto}
                yAxisWidth={56}
                showLegend={false}
                className="h-[380px]"
              />
            </div>
            <ul className="col-span-2 space-y-5">
              {cuentas.map((c: CuentaInforme) => (
                <li key={c.marca}>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="truncate text-sm text-neutral-700">{c.marca}</span>
                    <span className="shrink-0 text-sm tabular-nums text-neutral-500">
                      {numeroCompacto(c.vistas)}
                      <span className="ml-2 text-xs text-neutral-400">{c.pct}%</span>
                    </span>
                  </div>
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-neutral-100">
                    <div className="h-full rounded-full bg-orange-500" style={{ width: `${c.pct}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </Marco>
      ),
    });
  }

  // 6 · Crecimiento de seguidores (LineChart · Total, azul) — serie de nivel.
  slides.push({
    clave: "seguidores",
    nodo: (
      <Marco
        marca={marcaLabel}
        periodo={periodo}
        etiqueta={etiqueta}
        titulo="Crecimiento de seguidores"
        subtitulo="Total acumulado en el periodo"
      >
        <div className="flex h-full items-center">
          <LineChart
            data={seguidores}
            index="fecha"
            categories={["Total"]}
            colors={["blue"]}
            valueFormatter={numeroCompacto}
            showLegend={false}
            startEndOnly
            curveType="monotone"
            autoMinValue
            className="h-[400px] w-full"
          />
        </div>
      </Marco>
    ),
  });

  // 7 · Desglose de interacciones (BarChart apilado al 100 % · rose/blue/emerald/amber).
  slides.push({
    clave: "desglose",
    nodo: (
      <Marco
        marca={marcaLabel}
        periodo={periodo}
        etiqueta={etiqueta}
        titulo="Desglose de interacciones"
        subtitulo="Composición por marca y red"
      >
        <div className="flex h-full items-center">
          <BarChart
            data={desglose.data}
            index="grupo"
            categories={desglose.categorias}
            colors={desglose.colores}
            valueFormatter={(v: number) => `${v.toFixed(0)} %`}
            maxValue={100}
            stack
            className="h-[400px] w-full"
          />
        </div>
      </Marco>
    ),
  });

  // 8 · Top piezas — tabla limpia (las más vistas del periodo).
  slides.push({
    clave: "top",
    nodo: (
      <Marco
        marca={marcaLabel}
        periodo={periodo}
        etiqueta={etiqueta}
        titulo="Top piezas"
        subtitulo="Las publicaciones más vistas del periodo"
      >
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className={`border-b border-neutral-200 text-[11px] uppercase tracking-[0.14em] ${TONO.tablaHeader}`}>
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
                <td className={`max-w-[420px] truncate py-3 pr-4 ${TONO.tablaCelda}`}>{p.titulo}</td>
                <td className="px-4 py-3 text-neutral-500">{nombreRed(p.red)}</td>
                <td className="px-4 py-3 text-neutral-500 tabular-nums">{p.publicado}</td>
                <td className={`px-4 py-3 text-right tabular-nums ${TONO.tablaCelda}`}>{numeroCompleto(p.vistas)}</td>
                <td className="px-4 py-3 text-right text-neutral-600 tabular-nums">{numeroCompleto(p.interacciones)}</td>
                <td className="py-3 pl-4 text-right text-neutral-600 tabular-nums">{p.engagement} %</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Marco>
    ),
  });

  // Cierre · Conclusiones — cifras grandes (visual) con una mini explicación + foco.
  slides.push({
    clave: "cierre",
    nodo: (
      <Marco
        marca={marcaLabel}
        periodo={periodo}
        etiqueta={etiqueta}
        titulo="Conclusiones"
        subtitulo={`Lo que dejó ${periodo} y el foco del próximo mes`}
      >
        <div className="flex h-full flex-col justify-center gap-12">
          <div className="grid grid-cols-3 gap-10">
            {conclusiones.map((c: ConclusionInforme, i) => (
              <div key={c.label} className={`flex flex-col ${i === 0 ? "" : "border-l border-neutral-100 pl-10"}`}>
                <p
                  className={`text-[52px] font-light leading-none tracking-tight tabular-nums ${
                    c.signo === "baja"
                      ? "text-red-600"
                      : c.signo === "sube"
                        ? "text-emerald-600"
                        : "text-neutral-900"
                  }`}
                >
                  {c.valor}
                </p>
                <p className="mt-3 text-[11px] font-medium uppercase tracking-[0.16em] text-neutral-400">{c.label}</p>
                <p className="mt-3 text-[13px] leading-snug text-neutral-600">{c.nota}</p>
              </div>
            ))}
          </div>
          <div className="border-t border-neutral-100 pt-6">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-neutral-400">
              Foco del próximo periodo
            </p>
            <p className="mt-3 max-w-3xl text-[18px] font-light leading-snug text-neutral-800">{foco}</p>
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
