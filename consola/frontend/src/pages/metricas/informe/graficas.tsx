/**
 * Primitivas SVG del deck del informe (deck PDF de Métricas), autoras a mano para tener control
 * total del trazo, el gradiente y las anotaciones — y sobre todo COLOR INLINE, inmune a la
 * rasterización de `html-to-image` (los colores por clase CSS se pierden al clonar el DOM). El
 * lenguaje es "bold minimalista": formas grandes y confiadas, una idea por gráfico, cero rejilla;
 * toda la información va en anotaciones mínimas y exactas integradas en la propia curva.
 */
import * as React from "react";

/** Punto en el espacio de píxeles del SVG. */
interface Punto {
  x: number;
  y: number;
}

/**
 * Tangentes de una spline cúbica MONÓTONA (Fritsch–Carlson): preserva la monotonía del dato
 * entre puntos, así un pico no genera lóbulos por debajo de cero ni rebotes irreales. Es el
 * interpolador honesto para series con un pico marcado (mismo criterio que `curveMonotoneX`).
 */
function tangentesMonotonas(xs: number[], ys: number[]): number[] {
  const n = xs.length;
  if (n < 2) return ys.map(() => 0);
  const d: number[] = new Array(n - 1);
  for (let i = 0; i < n - 1; i++) {
    const dx = xs[i + 1] - xs[i];
    d[i] = dx !== 0 ? (ys[i + 1] - ys[i]) / dx : 0;
  }
  const m: number[] = new Array(n);
  m[0] = d[0];
  m[n - 1] = d[n - 2];
  for (let i = 1; i < n - 1; i++) {
    m[i] = d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2;
  }
  for (let i = 0; i < n - 1; i++) {
    if (d[i] === 0) {
      m[i] = 0;
      m[i + 1] = 0;
    } else {
      const a = m[i] / d[i];
      const b = m[i + 1] / d[i];
      const s = a * a + b * b;
      if (s > 9) {
        const t = 3 / Math.sqrt(s);
        m[i] = t * a * d[i];
        m[i + 1] = t * b * d[i];
      }
    }
  }
  return m;
}

/** Path "d" de la línea como spline cúbica monótona entre los puntos (x creciente). */
function rutaLineaSuave(pts: Punto[]): string {
  const n = pts.length;
  if (n === 0) return "";
  if (n === 1) return `M${pts[0].x.toFixed(2)} ${pts[0].y.toFixed(2)}`;
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const m = tangentesMonotonas(xs, ys);
  let d = `M${xs[0].toFixed(2)} ${ys[0].toFixed(2)}`;
  for (let i = 0; i < n - 1; i++) {
    const h = (xs[i + 1] - xs[i]) / 3;
    const c1x = xs[i] + h;
    const c1y = ys[i] + m[i] * h;
    const c2x = xs[i + 1] - h;
    const c2y = ys[i + 1] - m[i + 1] * h;
    d += ` C${c1x.toFixed(2)} ${c1y.toFixed(2)} ${c2x.toFixed(2)} ${c2y.toFixed(2)} ${xs[i + 1].toFixed(2)} ${ys[i + 1].toFixed(2)}`;
  }
  return d;
}

/** Marca de pico: día con su valor; etiqueta editorial flotando sobre el punto. */
export interface MarcaPico {
  idx: number;
  /** Cifra grande de la etiqueta (p. ej. "3.6 M"). */
  cifra: string;
  /** Línea pequeña bajo la cifra (p. ej. "18 jun"). */
  sub?: string;
}

/** Línea de referencia horizontal (media, valor final…): hairline punteado + etiqueta opcional. */
export interface Referencia {
  valor: number;
  etiqueta?: string;
  /** Lado donde ancla la etiqueta. */
  lado?: "izq" | "der";
}

interface AreaBoldProps {
  valores: number[];
  /** Ancho y alto del SVG en px (el deck es de tamaño fijo, así rasteriza 1:1 y nítido). */
  w: number;
  h: number;
  /** Id único del gradiente (un `<linearGradient>` por instancia). */
  id: string;
  /** Color del trazo y del gradiente (hex INLINE, inmune a la rasterización). */
  color: string;
  grosor?: number;
  /** Headroom interno sobre la curva (para que el pico y su etiqueta no se recorten). */
  padTop?: number;
  padBottom?: number;
  /** Opacidad del gradiente en su punto más alto (rico, no lavado). */
  opacidadArea?: number;
  pico?: MarcaPico;
  referencia?: Referencia;
  /** Punto final marcado con un disco (el "valor de cierre" de la serie). */
  marcarFinal?: boolean;
  /** Punto final marcado con disco + cifra del valor de cierre (dónde acaba la serie). */
  cierre?: { etiqueta: string };
  /** Dominio máximo forzado (para alinear escalas entre dos series); por defecto el máximo del dato. */
  maxForzado?: number;
}

/**
 * Área grande y confiada: gradiente rico, curva gruesa y nítida, línea base honesta en 0, y las
 * anotaciones (pico, media, cierre) integradas en la propia gráfica — no en un pie aparte.
 */
export function AreaBold({
  valores,
  w,
  h,
  id,
  color,
  grosor = 2.5,
  padTop = 14,
  padBottom = 0,
  opacidadArea = 0.3,
  pico,
  referencia,
  marcarFinal = false,
  cierre,
  maxForzado,
}: AreaBoldProps) {
  const n = valores.length;
  if (n < 2) return null;

  const innerTop = padTop;
  const innerBottom = h - padBottom;
  const plotH = innerBottom - innerTop;
  const maxDom = Math.max(maxForzado ?? 0, ...valores, referencia?.valor ?? 0, 1);

  const px = (i: number): number => (i / (n - 1)) * w;
  const py = (v: number): number => innerBottom - (v / maxDom) * plotH;

  const pts: Punto[] = valores.map((v, i) => ({ x: px(i), y: py(v) }));
  const linea = rutaLineaSuave(pts);
  const area = `${linea} L${w.toFixed(2)} ${innerBottom.toFixed(2)} L0 ${innerBottom.toFixed(2)} Z`;

  const tabular: React.CSSProperties = { fontVariantNumeric: "tabular-nums" };

  // Pico: guía vertical tenue del punto a la base + disco (relleno blanco, anillo de color) +
  // etiqueta editorial encima, con la x recortada para que no se salga del lienzo.
  let picoNodo: React.ReactNode = null;
  if (pico && pico.idx >= 0 && pico.idx < n) {
    const cx = px(pico.idx);
    const cy = py(valores[pico.idx]);
    const lx = Math.max(70, Math.min(w - 70, cx));
    picoNodo = (
      <g>
        <line x1={cx} y1={cy} x2={cx} y2={innerBottom} stroke={color} strokeOpacity={0.28} strokeWidth={1.25} />
        <circle cx={cx} cy={cy} r={5.5} fill="#ffffff" stroke={color} strokeWidth={2.5} />
        <text x={lx} y={cy - 26} textAnchor="middle" fontSize={17} fontWeight={600} fill={color} style={tabular}>
          {pico.cifra}
        </text>
        {pico.sub && (
          <text x={lx} y={cy - 11} textAnchor="middle" fontSize={11} fontWeight={500} fill="#737373" style={tabular}>
            {pico.sub}
          </text>
        )}
      </g>
    );
  }

  // Referencia: hairline punteado a la altura del valor, con etiqueta minúscula al lado elegido.
  let refNodo: React.ReactNode = null;
  if (referencia) {
    const ry = py(referencia.valor);
    const der = referencia.lado === "der";
    refNodo = (
      <g>
        <line x1={0} y1={ry} x2={w} y2={ry} stroke="#a3a3a3" strokeWidth={1} strokeDasharray="2 5" />
        {referencia.etiqueta && (
          <text
            x={der ? w : 0}
            y={ry - 7}
            textAnchor={der ? "end" : "start"}
            fontSize={11}
            fontWeight={500}
            fill="#737373"
            style={tabular}
          >
            {referencia.etiqueta}
          </text>
        )}
      </g>
    );
  }

  // Cierre: disco en el último punto + (si hay) la cifra de cierre justo encima, a la izquierda
  // del disco para no salirse por el borde derecho. Dice DÓNDE acaba la serie.
  const dibujaFin = marcarFinal || Boolean(cierre);
  const finNodo = dibujaFin ? (
    <g>
      {cierre && (
        <text
          x={px(n - 1) - 11}
          y={Math.max(13, py(valores[n - 1]) - 13)}
          textAnchor="end"
          fontSize={13}
          fontWeight={600}
          fill={color}
          style={tabular}
        >
          {cierre.etiqueta}
        </text>
      )}
      <circle cx={px(n - 1)} cy={py(valores[n - 1])} r={5.5} fill="#ffffff" stroke={color} strokeWidth={2.5} />
    </g>
  ) : null;

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block", overflow: "visible" }} aria-hidden>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={opacidadArea} />
          <stop offset="58%" stopColor={color} stopOpacity={opacidadArea * 0.32} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      {refNodo}
      <path d={linea} fill="none" stroke={color} strokeWidth={grosor} strokeLinecap="round" strokeLinejoin="round" />
      {finNodo}
      {picoNodo}
    </svg>
  );
}
