/**
 * Datos sembrados para la maqueta de la presentación PDF de Métricas. Números plausibles,
 * deterministas (sin azar), por marca, para ver cómo se vería el informe descargado. No
 * tocan red ni backend: el objetivo es VISUAL, no de datos reales.
 */
import { numeroCompacto, numeroCompleto, porcentaje, REDES_CANONICAS } from "@/lib/formato";

import { colorDe } from "@/pages/metricas/coloresRed";

export interface MarcaSemilla {
  id: string;
  nombre: string;
  /** Escala relativa del volumen de la marca (para que cada una se sienta distinta). */
  escala: number;
}

/** Catálogo del piloto AMX (mismos nombres que el sistema; sin color ni logo, por diseño). */
export const MARCAS: MarcaSemilla[] = [
  { id: "unotv", nombre: "UnoTV", escala: 1 },
  { id: "claro-sports", nombre: "Claro Sports", escala: 0.74 },
  { id: "nacion-gamer", nombre: "Nación Gamer", escala: 0.32 },
  { id: "piso-15", nombre: "Piso 15", escala: 0.18 },
  { id: "fundacion", nombre: "Fundación", escala: 0.11 },
];

export const PERIODO = "junio 2026";

const MESES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

/** Mes anterior al del periodo, derivado de PERIODO (no hardcodeado). */
export const MES_ANTERIOR = (() => {
  const i = MESES.indexOf(PERIODO.split(" ")[0].toLowerCase());
  if (i < 0) return "el periodo anterior";
  return MESES[(i + 11) % 12];
})();

/** Lecturas (insight de una línea) por slide y conclusiones de cierre, coherentes con los datos. */
export const LECTURAS = {
  resumen: "Creció en vistas y alcance; las interacciones bajaron 3.4 %, el único indicador a vigilar.",
  tendencia: "Las vistas cerraron el mes por encima del inicio, con un valle a mitad de periodo.",
  porRed: "Facebook concentra cerca de un tercio de las vistas; TikTok es el que más crece.",
  seguidores: "Crecimiento de seguidores sostenido durante todo el periodo, sin caídas.",
  desglose: "8 de cada 10 interacciones son «me gusta»; compartir pesa más en TikTok.",
  top: "El video corto domina el podio; las galerías rinden cerca de la mitad.",
  porMarca: "UnoTV y Claro Sports concentran la mayoría de las vistas del portafolio.",
};

export const CONCLUSIONES = [
  "Las visualizaciones crecieron 14 % respecto al periodo anterior.",
  "El alcance subió 5 %, llegando a más cuentas.",
  "Las interacciones cayeron 3.4 %: más audiencia, menos conexión por pieza.",
  "La entrevista exclusiva fue la pieza del mes.",
];
export const FOCO = "Replicar el formato de video corto y revisar el engagement en Instagram.";

/** Etiquetas de día "01 jun" … "30 jun" (es-MX, mes fijo del periodo de muestra). */
export function diasDelMes(n = 30): string[] {
  return Array.from({ length: n }, (_, i) => `${String(i + 1).padStart(2, "0")} jun`);
}

/** Serie suave y determinista (base + onda), redondeada a entero. */
function serie(n: number, base: number, amplitud: number, fase = 0): number[] {
  return Array.from({ length: n }, (_, i) => {
    const onda = Math.sin((i / n) * Math.PI * 3 + fase) * amplitud;
    const tendencia = (i / n) * amplitud * 0.6;
    return Math.max(0, Math.round(base + onda + tendencia));
  });
}

/** Reparto de vistas por red para una escala dada (suma ≈ vistas totales). */
function repartoRedes(escala: number): Record<string, number> {
  const pesos: Record<string, number> = {
    facebook: 0.34,
    instagram: 0.27,
    tiktok: 0.21,
    youtube: 0.1,
    x: 0.08,
  };
  const vistas = 18_400_000 * escala;
  const out: Record<string, number> = {};
  for (const r of REDES_CANONICAS) out[r] = Math.round(vistas * pesos[r]);
  return out;
}

export interface Kpi {
  etiqueta: string;
  valor: string;
  titulo: string;
  /** Variación vs periodo anterior; null = sin comparativa. */
  delta?: { texto: string; signo: "sube" | "baja" | "igual" | "nuevo" };
}

function delta(pct: number): Kpi["delta"] {
  if (pct === 0) return { texto: "0.0 %", signo: "igual" };
  const signo = pct > 0 ? "sube" : "baja";
  const s = pct > 0 ? "+" : "−";
  return { texto: `${s}${Math.abs(pct).toFixed(1)} %`, signo };
}

/** KPIs del resumen para una escala (5 tiles: piezas, vistas, alcance, interacciones, engagement). */
export function kpis(escala: number): Kpi[] {
  const piezas = Math.round(412 * escala) + 8;
  const vistas = Math.round(18_400_000 * escala);
  const alcance = Math.round(9_700_000 * escala);
  const interacciones = Math.round(1_240_000 * escala);
  const engagement = 6.7 + escala * 0.4;
  return [
    { etiqueta: "Piezas", valor: numeroCompleto(piezas), titulo: `${piezas} piezas publicadas`, delta: delta(9.2) },
    { etiqueta: "Visualizaciones", valor: numeroCompacto(vistas), titulo: numeroCompleto(vistas), delta: delta(14.3) },
    { etiqueta: "Alcance", valor: numeroCompacto(alcance), titulo: numeroCompleto(alcance), delta: delta(5.1) },
    { etiqueta: "Interacciones", valor: numeroCompacto(interacciones), titulo: numeroCompleto(interacciones), delta: delta(-3.4) },
    { etiqueta: "Engagement", valor: porcentaje(engagement), titulo: `${engagement.toFixed(1)} % medio`, delta: { texto: "+0.4 pts", signo: "sube" } },
  ];
}

/** Tendencia diaria de vistas (Tremor AreaChart, categoría "Vistas"). */
export function tendenciaVistas(escala: number): Array<Record<string, string | number>> {
  const dias = diasDelMes();
  const vals = serie(dias.length, 520_000 * escala, 180_000 * escala, 0.6);
  return dias.map((fecha, i) => ({ fecha, Vistas: vals[i] }));
}

/** Crecimiento de seguidores: serie de NIVEL acumulada (Tremor LineChart, "Total"). */
export function seguidores(escala: number): Array<Record<string, string | number>> {
  const dias = diasDelMes();
  let acc = Math.round(1_180_000 * escala);
  return dias.map((fecha, i) => {
    acc += Math.round((1400 + Math.sin(i / 3) * 600) * escala);
    return { fecha, Total: acc };
  });
}

/** Reparto por red apilado a lo largo del periodo (semanas) — colores por red (coloresRed.ts). */
export interface PorRed {
  data: Array<Record<string, string | number>>;
  categorias: string[];
  colores: string[];
}
export function porRedSemanal(escala: number, nombreRedFn: (r: string) => string): PorRed {
  const semanas = ["Sem 1", "Sem 2", "Sem 3", "Sem 4"];
  const base = repartoRedes(escala);
  const categorias = REDES_CANONICAS.map((r) => nombreRedFn(r));
  const colores = REDES_CANONICAS.map((r) => colorDe(r));
  const data = semanas.map((intervalo, s) => {
    const fila: Record<string, string | number> = { intervalo };
    REDES_CANONICAS.forEach((r) => {
      const factor = 0.2 + 0.06 * s + Math.sin(s + REDES_CANONICAS.indexOf(r)) * 0.03;
      fila[nombreRedFn(r)] = Math.round(base[r] * factor);
    });
    return fila;
  });
  return { data, categorias, colores };
}

/** Desglose de interacciones por marca×red, en modo proporción (apilado al 100 %). */
export function desglose(
  marcas: MarcaSemilla[],
  nombreRedFn: (r: string) => string,
): { data: Array<Record<string, string | number>>; categorias: string[]; colores: string[] } {
  const categorias = ["Me gusta", "Comentarios", "Compartidos", "Guardados"];
  const colores = ["rose", "blue", "emerald", "amber"];
  const composiciones = [
    { "Me gusta": 0.72, Comentarios: 0.11, Compartidos: 0.1, Guardados: 0.07 },
    { "Me gusta": 0.64, Comentarios: 0.14, Compartidos: 0.14, Guardados: 0.08 },
    { "Me gusta": 0.58, Comentarios: 0.09, Compartidos: 0.21, Guardados: 0.12 },
  ];
  const redes = ["instagram", "facebook", "tiktok"];
  const data: Array<Record<string, string | number>> = [];
  marcas.slice(0, marcas.length === 1 ? 1 : 3).forEach((m, mi) => {
    redes.forEach((r, ri) => {
      const comp = composiciones[(mi + ri) % composiciones.length];
      data.push({
        grupo: `${m.nombre} · ${nombreRedFn(r)}`,
        "Me gusta": +(comp["Me gusta"] * 100).toFixed(1),
        Comentarios: +(comp.Comentarios * 100).toFixed(1),
        Compartidos: +(comp.Compartidos * 100).toFixed(1),
        Guardados: +(comp.Guardados * 100).toFixed(1),
      });
    });
  });
  return { data, categorias, colores };
}

export interface FilaPieza {
  titulo: string;
  red: string;
  publicado: string;
  vistas: number;
  interacciones: number;
  engagement: number;
}

/** Top piezas del periodo (las más vistas). */
export function topPiezas(escala: number): FilaPieza[] {
  const titulos = [
    "Resumen de la jornada: lo que no viste del fin de semana",
    "Entrevista exclusiva tras el partido",
    "El detrás de cámaras que se volvió viral",
    "Análisis: las claves de la semana en imágenes",
    "Lo más comentado del día en redes",
    "Reportaje especial desde el lugar de los hechos",
    "La jugada que dio la vuelta al mundo",
    "Galería: las mejores fotos de la semana",
  ];
  const redes = ["tiktok", "instagram", "youtube", "facebook", "instagram", "tiktok", "x", "facebook"];
  return titulos.map((titulo, i) => ({
    titulo,
    red: redes[i],
    publicado: `${String(28 - i * 2).padStart(2, "0")} jun`,
    vistas: Math.round((2_300_000 - i * 210_000) * escala),
    interacciones: Math.round((184_000 - i * 16_000) * escala),
    engagement: +(9.4 - i * 0.6).toFixed(1),
  }));
}

/** Total de visualizaciones del portafolio (suma de las 5 marcas) — cifra-ancla de la portada "todas". */
export function vistasTotales(): number {
  return MARCAS.reduce((s, m) => s + Math.round(18_400_000 * m.escala), 0);
}

/** Cifras-héroe que resumen cada slide (sustituyen a la frase de texto). */
export function deltaTendenciaPct(escala: number): number {
  const s = tendenciaVistas(escala);
  const a = Number(s[0].Vistas);
  const b = Number(s[s.length - 1].Vistas);
  return a > 0 ? Math.round(((b - a) / a) * 100) : 0;
}
export function picoTendencia(escala: number): { valor: number; fecha: string } {
  const s = tendenciaVistas(escala);
  let best = s[0];
  for (const p of s) if (Number(p.Vistas) > Number(best.Vistas)) best = p;
  return { valor: Number(best.Vistas), fecha: String(best.fecha) };
}
export function netoSeguidoresPeriodo(escala: number): number {
  const s = seguidores(escala);
  return Number(s[s.length - 1].Total) - Number(s[0].Total);
}
export function concentracionTop2(): number {
  const c = cuentasPorMarca();
  return (c[0]?.pct ?? 0) + (c[1]?.pct ?? 0);
}
export function vistasPiezaTop(escala: number): number {
  return topPiezas(escala)[0]?.vistas ?? 0;
}
/** Cuota de la red dominante (Facebook) y % del componente «me gusta» — estáticos del modict. */
export const CUOTA_FACEBOOK = 34;
export const PCT_ME_GUSTA = 72;

/** Cierre: tres cifras-ancla (eco de los KPIs del Resumen) + nota de la pieza del mes. */
export const CIERRE_CIFRAS: Array<{ valor: string; label: string; signo: "sube" | "baja" }> = [
  { valor: "+14 %", label: "Visualizaciones", signo: "sube" },
  { valor: "+5 %", label: "Alcance", signo: "sube" },
  { valor: "−3.4 %", label: "Interacciones", signo: "baja" },
];
export const CIERRE_NOTA = "La entrevista exclusiva fue la pieza del mes.";

/** Comparativa por marca (solo en modo "todas"): vistas e interacciones por marca. */
export function cuentasPorMarca(): Array<{ marca: string; Vistas: number; vistas: number; pct: number }> {
  const filas = MARCAS.map((m) => ({
    marca: m.nombre,
    vistas: Math.round(18_400_000 * m.escala),
  }));
  const total = filas.reduce((s, f) => s + f.vistas, 0);
  return filas
    .map((f) => ({ ...f, Vistas: f.vistas, pct: Math.round((f.vistas / total) * 100) }))
    .sort((a, b) => b.vistas - a.vistas);
}
