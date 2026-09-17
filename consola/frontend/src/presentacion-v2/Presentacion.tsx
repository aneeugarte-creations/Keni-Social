/**
 * Maqueta v2 de la presentación PDF de Métricas: misma base, con las mejoras de la auditoría
 * de diseño. Cada slide cuenta su lectura (insight), hay un cierre con conclusiones, mejor
 * equilibrio vertical, leyendas reubicadas y pulido tipográfico. Gráficas Tremor tal cual.
 */
import { AreaChart, BarChart, LineChart } from "@tremor/react";
import * as React from "react";

import { nombreRed, numeroCompacto, numeroCompleto, REDES_CANONICAS } from "@/lib/formato";

import { colorDe } from "@/pages/metricas/coloresRed";

import {
  CIERRE_CIFRAS,
  CIERRE_NOTA,
  concentracionTop2,
  cuentasPorMarca,
  CUOTA_FACEBOOK,
  desglose,
  FOCO,
  kpis,
  MARCAS,
  MES_ANTERIOR,
  netoSeguidoresPeriodo,
  PCT_ME_GUSTA,
  picoTendencia,
  PERIODO,
  porRedSemanal,
  seguidores,
  tendenciaVistas,
  topPiezas,
  vistasPiezaTop,
  vistasTotales,
  type Kpi,
} from "./datos";

const ARRIBA = "—";

/** Tono de texto por rol → clase Tailwind. Define cómo se reparte el negro frente a los grises. */
const TONO: Record<string, string> = {
  negro: "text-neutral-900",
  "gris-oscuro": "text-neutral-700",
  "gris-medio": "text-neutral-500",
  "gris-claro": "text-neutral-400",
  "gris-tenue": "text-neutral-300",
};

interface Esquema {
  nombre: string;
  topLabel: string;
  titulo: string;
  subtitulo: string;
  kpiLabel: string;
  kpiValor: string;
  tablaHeader: string;
  tablaCelda: string;
  pie: string;
  coverCaption: string;
}

const ESQUEMAS: Esquema[] = [
  {
    nombre: "Actual",
    topLabel: "gris-claro", titulo: "negro", subtitulo: "gris-medio",
    kpiLabel: "gris-claro", kpiValor: "negro",
    tablaHeader: "gris-claro", tablaCelda: "negro",
    pie: "gris-tenue", coverCaption: "negro",
  },
  {
    nombre: "Vacío Graduado",
    topLabel: "gris-claro", titulo: "gris-oscuro", subtitulo: "gris-medio",
    kpiLabel: "gris-claro", kpiValor: "negro",
    tablaHeader: "gris-claro", tablaCelda: "gris-oscuro",
    pie: "gris-tenue", coverCaption: "gris-medio",
  },
  {
    nombre: "Grid Firme",
    topLabel: "negro", titulo: "negro", subtitulo: "gris-medio",
    kpiLabel: "gris-oscuro", kpiValor: "negro",
    tablaHeader: "gris-oscuro", tablaCelda: "negro",
    pie: "gris-tenue", coverCaption: "negro",
  },
  {
    nombre: "Sereno",
    topLabel: "gris-medio", titulo: "negro", subtitulo: "gris-medio",
    kpiLabel: "gris-medio", kpiValor: "negro",
    tablaHeader: "gris-medio", tablaCelda: "negro",
    pie: "gris-tenue", coverCaption: "negro",
  },
  {
    nombre: "Ancla Negra",
    topLabel: "negro", titulo: "gris-oscuro", subtitulo: "gris-medio",
    kpiLabel: "negro", kpiValor: "gris-oscuro",
    tablaHeader: "negro", tablaCelda: "gris-oscuro",
    pie: "gris-tenue", coverCaption: "negro",
  },
];

const EsquemaCtx = React.createContext<Esquema>(ESQUEMAS[0]);
const useEsq = () => React.useContext(EsquemaCtx);

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

/** Logo real de la marca si existe (`/marcas-logos/<id>.svg|png`), si no el wordmark tipográfico. */
function LogoOWordmark({
  id,
  nombre,
  size,
  box,
}: {
  id: string;
  nombre: string;
  size?: number;
  box?: { h: number; w: number };
}) {
  const [src, setSrc] = React.useState<string | null>(null);
  React.useEffect(() => {
    let activo = true;
    const probar = (cands: string[]) => {
      if (!cands.length) return;
      const img = new Image();
      img.onload = () => activo && setSrc(cands[0]);
      img.onerror = () => activo && probar(cands.slice(1));
      img.src = cands[0];
    };
    probar([
      `/marcas-logos/${id}.svg`,
      `/marcas-logos/${id}.png`,
      `/marcas-logos/${id}.jpg`,
      `/marcas-logos/${id}.jpeg`,
      `/marcas-logos/${id}.webp`,
    ]);
    return () => {
      activo = false;
    };
  }, [id]);
  if (src) {
    const estilo: React.CSSProperties = box
      ? { maxHeight: box.h, maxWidth: box.w, width: "auto", height: "auto", objectFit: "contain", display: "block" }
      : { height: size ?? 80, width: "auto", display: "block" };
    return <img src={src} alt={nombre} style={estilo} />;
  }
  return <Wordmark id={id} nombre={nombre} size={box ? Math.round(box.h * 0.62) : (size ?? 80)} />;
}

function Wordmark({ id, nombre, size }: { id: string; nombre: string; size: number }) {
  const e = ESTILOS[id];
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

/** Fila de chips de leyenda (punto de color + nombre), reanclada a la izquierda bajo el título. */
function Chips({ items }: { items: Array<{ label: string; color: string }> }) {
  return (
    <div className="mb-5 flex flex-wrap items-center gap-x-6 gap-y-2">
      {items.map((it) => (
        <span key={it.label} className="flex items-center gap-2 text-xs text-neutral-500">
          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: it.color }} aria-hidden />
          {it.label}
        </span>
      ))}
    </div>
  );
}

const CHIPS_RED = REDES_CANONICAS.map((r) => ({ label: nombreRed(r), color: colorDe(r) }));
const CHIPS_DESGLOSE = [
  { label: "Me gusta", color: "#f43f5e" },
  { label: "Comentarios", color: "#3b82f6" },
  { label: "Compartidos", color: "#10b981" },
  { label: "Guardados", color: "#f59e0b" },
];

/** Diapositiva 16:9: lienzo blanco, cabecera (label + título + lectura) y pie discreto. */
function Marco({
  marca,
  etiqueta,
  titulo,
  cifra,
  n,
  total,
  children,
  portada = false,
}: {
  marca: string;
  etiqueta?: string;
  titulo?: string;
  /** Cifra-héroe: resume el slide visualmente, sin prosa. */
  cifra?: { valor: string; label: string; signo?: "sube" | "baja" };
  n: number;
  total: number;
  children?: React.ReactNode;
  portada?: boolean;
}) {
  const e = useEsq();
  const heroColor = cifra?.signo === "baja" ? "text-red-600" : "text-neutral-900";
  return (
    <section className="slide">
      <div className="flex h-full flex-col px-20 pb-12 pt-16">
        {!portada && (
          <header className="mb-7 flex items-start justify-between gap-10">
            <div>
              <p className={`text-[11px] font-medium uppercase tracking-[0.18em] ${TONO[e.topLabel]}`}>
                {etiqueta}
              </p>
              <h2 className={`mt-3 text-[34px] font-light leading-[1.12] ${TONO[e.titulo]}`}>{titulo}</h2>
            </div>
            {cifra && (
              <div className="shrink-0 text-right">
                <p className={`text-[46px] font-light leading-none tracking-tight tabular-nums ${heroColor}`}>
                  {cifra.valor}
                </p>
                <p className="mt-2 text-[11px] font-medium uppercase tracking-[0.16em] text-neutral-400">
                  {cifra.label}
                </p>
              </div>
            )}
          </header>
        )}

        <div className="min-h-0 flex-1">{children}</div>

        {!portada && (
          <footer className={`mt-10 flex items-center justify-between text-[10px] tracking-wide ${TONO[e.pie]}`}>
            <span className="uppercase tracking-[0.18em]">
              {marca} · Todas las redes · {PERIODO}
            </span>
            <span className="uppercase tracking-[0.18em]">keni</span>
          </footer>
        )}
      </div>
    </section>
  );
}

/** Tile de KPI: número grande, label en mayúsculas, variación discreta. Sin caja. */
function TileKpi({ kpi, primero }: { kpi: Kpi; primero: boolean }) {
  const e = useEsq();
  const color =
    kpi.delta?.signo === "sube"
      ? "text-emerald-600"
      : kpi.delta?.signo === "baja"
        ? "text-red-600"
        : "text-neutral-400";
  const flecha = kpi.delta?.signo === "sube" ? "↑" : kpi.delta?.signo === "baja" ? "↓" : "";
  return (
    <div className={`flex flex-col ${primero ? "" : "border-l border-neutral-100 pl-8"}`}>
      <p className={`text-[11px] font-medium uppercase tracking-[0.16em] ${TONO[e.kpiLabel]}`}>
        {kpi.etiqueta}
      </p>
      <p
        className={`mt-5 text-[56px] font-light leading-none tracking-tight tabular-nums ${TONO[e.kpiValor]}`}
        title={kpi.titulo}
      >
        {kpi.valor}
      </p>
      {kpi.delta && (
        <p className={`mt-4 text-xs font-medium tabular-nums ${color}`}>
          {flecha && <span className="mr-0.5">{flecha}</span>}
          {kpi.delta.texto}
          <span className="ml-1.5 font-normal text-neutral-400">vs. {MES_ANTERIOR}</span>
        </p>
      )}
    </div>
  );
}

/** Escala la diapositiva de 1280×720 para que quepa al ancho de la columna (solo se baja). */
function EscaladorSlide({ children }: { children: React.ReactNode }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [escala, setEscala] = React.useState(0.8);
  React.useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setEscala(Math.min(1, el.clientWidth / 1280)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={ref} className="w-full" style={{ height: 720 * escala }}>
      <div style={{ width: 1280, height: 720, transform: `scale(${escala})`, transformOrigin: "top left" }}>
        {children}
      </div>
    </div>
  );
}

interface Ctx {
  esTodas: boolean;
  marcaId: string;
  marcaLabel: string;
  marcaCorta: string;
  escala: number;
  esq: Esquema;
}

/** Lista ordenada de las diapositivas para un contexto (una marca o todas). */
function diapositivas(ctx: Ctx): Array<{ render: (n: number, total: number) => React.ReactNode }> {
  const { esTodas, marcaId, marcaLabel, marcaCorta, escala, esq } = ctx;
  const etq = esTodas ? "Todas las marcas" : marcaCorta;
  const slides: Array<{ render: (n: number, total: number) => React.ReactNode }> = [];

  // 1 · Portada — el logo de la marca es protagonista; en "todas", cifra-ancla del portafolio.
  slides.push({
    render: (n, total) => (
      <Marco key="portada" marca={marcaCorta} n={n} total={total} portada>
        <div className="flex h-full flex-col items-center justify-center text-center">
          {esTodas ? (
            <>
              <div className="flex max-w-5xl flex-wrap items-center justify-center gap-x-20 gap-y-14">
                {MARCAS.map((m) => (
                  <div key={m.id} className="flex items-center justify-center" style={{ height: 92, width: 220 }}>
                    <LogoOWordmark id={m.id} nombre={m.nombre} box={{ h: 92, w: 220 }} />
                  </div>
                ))}
              </div>
              <p className="mt-16 text-[26px] font-light tracking-tight text-neutral-800 tabular-nums">
                {numeroCompacto(vistasTotales())} visualizaciones · 5 marcas
              </p>
              <p className={`mt-6 text-[11px] font-medium uppercase tracking-[0.3em] ${TONO[esq.coverCaption]}`}>
                Informe de métricas · {PERIODO}
              </p>
            </>
          ) : (
            <>
              <LogoOWordmark id={marcaId} nombre={marcaLabel} box={{ h: 280, w: 920 }} />
              <p className={`mt-12 text-[11px] font-medium uppercase tracking-[0.3em] ${TONO[esq.coverCaption]}`}>
                Informe de métricas · {PERIODO}
              </p>
            </>
          )}
        </div>
      </Marco>
    ),
  });

  // 2 · Resumen del periodo — 5 KPIs + lectura-síntesis del mes.
  slides.push({
    render: (n, total) => (
      <Marco key="resumen" marca={marcaCorta} etiqueta={etq} titulo="Resumen del periodo" n={n} total={total}>
        <div className="flex h-full items-center">
          <div className="grid w-full grid-cols-5 gap-8">
            {kpis(escala).map((k, i) => (
              <TileKpi key={k.etiqueta} kpi={k} primero={i === 0} />
            ))}
          </div>
        </div>
      </Marco>
    ),
  });

  // 3 · (solo "todas") Comparativa por marca — sube tras el resumen: es el slide rey del portafolio.
  if (esTodas) {
    slides.push({
      render: (n, total) => {
        const cuentas = cuentasPorMarca();
        return (
          <Marco
            key="por-marca"
            marca={marcaCorta}
            etiqueta="Todas las marcas"
            titulo="Comparativa por marca"
            cifra={{ valor: `${concentracionTop2()} %`, label: "En 2 marcas" }}
            n={n}
            total={total}
          >
            <div className="grid h-full grid-cols-5 items-center gap-12">
              <div className="col-span-3">
                <BarChart
                  data={cuentas}
                  index="marca"
                  categories={["Vistas"]}
                  colors={["orange"]}
                  valueFormatter={numeroCompacto}
                  yAxisWidth={56}
                  showLegend={false}
                  className="h-[340px]"
                />
              </div>
              <ul className="col-span-2 space-y-5">
                {cuentas.map((c) => (
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
        );
      },
    });
  }

  // 4 · Tendencia diaria (AreaChart · Vistas, naranja).
  slides.push({
    render: (n, total) => {
      const pico = picoTendencia(escala);
      return (
        <Marco
          key="tendencia"
          marca={marcaCorta}
          etiqueta={etq}
          titulo="Tendencia diaria"
          cifra={{ valor: numeroCompacto(pico.valor), label: `Pico · ${pico.fecha}` }}
          n={n}
          total={total}
        >
          <div className="flex h-full items-center">
            <AreaChart
              data={tendenciaVistas(escala)}
              index="fecha"
              categories={["Vistas"]}
              colors={["orange"]}
              valueFormatter={numeroCompacto}
              showLegend={false}
              startEndOnly
              curveType="monotone"
              className="h-[420px] w-full"
            />
          </div>
        </Marco>
      );
    },
  });

  // 5 · Reparto por red (BarChart apilado · colores por red) — leyenda reanclada como chips.
  slides.push({
    render: (n, total) => {
      const pr = porRedSemanal(escala, nombreRed);
      return (
        <Marco
          key="por-red"
          marca={marcaCorta}
          etiqueta={etq}
          titulo="Reparto por red"
          cifra={{ valor: `${CUOTA_FACEBOOK} %`, label: "Facebook · red líder" }}
          n={n}
          total={total}
        >
          <div className="flex h-full flex-col justify-center">
            <Chips items={CHIPS_RED} />
            <BarChart
              data={pr.data}
              index="intervalo"
              categories={pr.categorias}
              colors={pr.colores}
              valueFormatter={numeroCompacto}
              stack
              showLegend={false}
              className="h-[360px] w-full"
            />
          </div>
        </Marco>
      );
    },
  });

  // 6 · Desglose de interacciones (BarChart apilado al 100 %) — leyenda como chips.
  slides.push({
    render: (n, total) => {
      const d = desglose(esTodas ? MARCAS : [MARCAS[0]], nombreRed);
      return (
        <Marco
          key="desglose"
          marca={marcaCorta}
          etiqueta={etq}
          titulo="Desglose de interacciones"
          cifra={{ valor: `${PCT_ME_GUSTA} %`, label: "Son «me gusta»" }}
          n={n}
          total={total}
        >
          <div className="flex h-full flex-col justify-center">
            <Chips items={CHIPS_DESGLOSE} />
            <BarChart
              data={d.data}
              index="grupo"
              categories={d.categorias}
              colors={d.colores}
              valueFormatter={(v: number) => `${v.toFixed(0)} %`}
              maxValue={100}
              stack
              showLegend={false}
              className="h-[360px] w-full"
            />
          </div>
        </Marco>
      );
    },
  });

  // 7 · Top piezas — tabla limpia (las más vistas); «Vistas» destacada por ser el orden.
  slides.push({
    render: (n, total) => (
      <Marco
        key="top"
        marca={marcaCorta}
        etiqueta={etq}
        titulo="Top piezas"
        cifra={{ valor: numeroCompacto(vistasPiezaTop(escala)), label: "Pieza del mes" }}
        n={n}
        total={total}
      >
        <div className="flex h-full items-center">
          <table className="w-full border-collapse text-[15px]">
            <thead>
              <tr className={`border-b border-neutral-200 text-[11px] uppercase tracking-[0.14em] ${TONO[esq.tablaHeader]}`}>
                <th className="py-3.5 pr-4 text-left font-medium">Pieza</th>
                <th className="px-4 py-3.5 text-left font-medium">Red</th>
                <th className="px-4 py-3.5 text-left font-medium">Publicado</th>
                <th className="px-4 py-3.5 text-right font-medium">Vistas</th>
                <th className="px-4 py-3.5 text-right font-medium">Interac.</th>
                <th className="py-3.5 pl-4 text-right font-medium">Eng.</th>
              </tr>
            </thead>
            <tbody>
              {topPiezas(escala).map((p, i) => (
                <tr key={i} className="border-b border-neutral-100">
                  <td className={`max-w-[440px] truncate py-3.5 pr-4 ${TONO[esq.tablaCelda]}`}>{p.titulo}</td>
                  <td className="px-4 py-3.5 text-neutral-500">{nombreRed(p.red)}</td>
                  <td className="px-4 py-3.5 text-neutral-500 tabular-nums">{p.publicado}</td>
                  <td className={`px-4 py-3.5 text-right font-medium tabular-nums ${TONO[esq.tablaCelda]}`}>
                    {numeroCompleto(p.vistas)}
                  </td>
                  <td className="px-4 py-3.5 text-right text-neutral-600 tabular-nums">
                    {numeroCompleto(p.interacciones)}
                  </td>
                  <td className="py-3.5 pl-4 text-right text-neutral-600 tabular-nums">{p.engagement.toFixed(1)} %</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Marco>
    ),
  });

  // 8 · Crecimiento de seguidores (LineChart · Total, azul) — métrica estructural, hacia el final.
  slides.push({
    render: (n, total) => (
      <Marco
        key="seguidores"
        marca={marcaCorta}
        etiqueta={etq}
        titulo="Crecimiento de seguidores"
        cifra={{ valor: `+${numeroCompacto(netoSeguidoresPeriodo(escala))}`, label: "Seguidores nuevos", signo: "sube" }}
        n={n}
        total={total}
      >
        <div className="flex h-full items-center">
          <LineChart
            data={seguidores(escala)}
            index="fecha"
            categories={["Total"]}
            colors={["blue"]}
            valueFormatter={numeroCompacto}
            showLegend={false}
            startEndOnly
            curveType="monotone"
            autoMinValue
            className="h-[420px] w-full"
          />
        </div>
      </Marco>
    ),
  });

  // 9 · Cierre — Lecturas del periodo: conclusiones + foco del próximo mes.
  slides.push({
    render: (n, total) => (
      <Marco key="cierre" marca={marcaCorta} etiqueta={etq} titulo="Lecturas del periodo" n={n} total={total}>
        <div className="flex h-full flex-col justify-center gap-12">
          <div className="grid grid-cols-3 gap-8">
            {CIERRE_CIFRAS.map((c, i) => (
              <div key={c.label} className={`flex flex-col ${i === 0 ? "" : "border-l border-neutral-100 pl-8"}`}>
                <p
                  className={`text-[56px] font-light leading-none tracking-tight tabular-nums ${c.signo === "baja" ? "text-red-600" : "text-neutral-900"}`}
                >
                  {c.valor}
                </p>
                <p className="mt-3 text-[11px] font-medium uppercase tracking-[0.16em] text-neutral-400">{c.label}</p>
              </div>
            ))}
          </div>
          <p className="text-[15px] text-neutral-600">{CIERRE_NOTA}</p>
          <div className="border-t border-neutral-100 pt-6">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-neutral-400">
              Foco del próximo periodo
            </p>
            <p className="mt-3 max-w-3xl text-[18px] font-light leading-snug text-neutral-800">{FOCO}</p>
          </div>
        </div>
      </Marco>
    ),
  });

  return slides;
}

/** Selección inicial desde el hash (#todas, #claro-sports…) para poder enlazar a una vista. */
function selInicial(): string {
  const h = typeof window !== "undefined" ? window.location.hash.slice(1) : "";
  if (h === "todas" || MARCAS.some((m) => m.id === h)) return h;
  return "unotv";
}

export function Presentacion() {
  const [sel, setSel] = React.useState<string>(selInicial);
  const [iEsq, setIEsq] = React.useState(() =>
    Math.max(0, ESQUEMAS.findIndex((e) => e.nombre === "Sereno")),
  );
  const esq = ESQUEMAS[iEsq];
  const esTodas = sel === "todas";
  const marca = MARCAS.find((m) => m.id === sel);
  const ctx: Ctx = {
    esTodas,
    marcaId: sel,
    marcaLabel: esTodas ? "Todas las marcas" : (marca?.nombre ?? ""),
    marcaCorta: esTodas ? "Todas las marcas" : (marca?.nombre ?? ""),
    escala: esTodas ? MARCAS.reduce((s, m) => s + m.escala, 0) : (marca?.escala ?? 1),
    esq,
  };
  const slides = diapositivas(ctx);

  return (
    <div className="h-screen overflow-y-auto bg-neutral-100 text-neutral-900">
      {/* Barra de control — NO forma parte del PDF. */}
      <div className="no-print sticky top-0 z-10 border-b border-neutral-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1280px] flex-col gap-2.5 px-6 py-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-neutral-400">
              Presentación PDF de métricas {ARRIBA} vista previa v2
            </span>
            <div className="ml-auto flex flex-wrap items-center gap-1.5">
              {MARCAS.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setSel(m.id)}
                  className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                    sel === m.id
                      ? "bg-neutral-900 text-white"
                      : "border border-neutral-200 text-neutral-600 hover:bg-neutral-50"
                  }`}
                >
                  {m.nombre}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setSel("todas")}
                className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                  esTodas
                    ? "bg-neutral-900 text-white"
                    : "border border-neutral-200 text-neutral-600 hover:bg-neutral-50"
                }`}
              >
                Todas las marcas
              </button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-[11px] font-medium uppercase tracking-[0.16em] text-neutral-400">
              Negro / gris
            </span>
            {ESQUEMAS.map((e, i) => (
              <button
                key={e.nombre}
                type="button"
                onClick={() => setIEsq(i)}
                className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                  iEsq === i
                    ? "bg-neutral-900 text-white"
                    : "border border-neutral-200 text-neutral-600 hover:bg-neutral-50"
                }`}
              >
                {e.nombre}
              </button>
            ))}
          </div>
        </div>
      </div>

      <EsquemaCtx.Provider value={esq}>
        <div className="mx-auto flex w-full max-w-[1040px] flex-col gap-8 px-4 py-10">
          {slides.map((s, i) => (
            <EscaladorSlide key={i}>{s.render(i + 1, slides.length)}</EscaladorSlide>
          ))}
        </div>
      </EsquemaCtx.Provider>
    </div>
  );
}
