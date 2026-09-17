/**
 * Datos de ejemplo compartidos por las vistas previas (solo localhost). Sustituye
 * `api.analiticaCampania` por un mock para que el panel real pinte sin backend.
 * Directorio desechable: borrar antes de promover.
 */
import { QueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { AnaliticaCampania, PiezaCampania } from "@/types";

function puntosTendencia() {
  const puntos = [];
  const base = new Date("2026-05-24T12:00:00Z");
  for (let i = 0; i < 30; i++) {
    const d = new Date(base);
    d.setUTCDate(base.getUTCDate() + i);
    const pico = i === 9 || i === 22 ? 3.4 : i === 16 ? 2.1 : 1;
    const vis = Math.round((12000 + Math.sin(i / 2) * 6000 + i * 350) * pico);
    puntos.push({
      fecha: d.toISOString().slice(0, 10),
      visualizaciones: vis,
      interacciones: Math.round(vis * (0.05 + (i % 5) * 0.004)),
    });
  }
  return puntos;
}

const PIEZAS: PiezaCampania[] = [
  { id: "1", red: "instagram", marca: "Claro Sports", titulo: "Checo Pérez sube al podio en Montreal 🇲🇽", publicado: "2026-06-15", visualizaciones: 412_300, visualizaciones_pagadas: 0, interacciones: 38_900, engagement_pct: 9.4, url: "https://instagram.com/p/x1", formato: "reel", por_cross_post: false, es_inorganico: false },
  { id: "2", red: "tiktok", marca: "Claro Sports", titulo: "El golazo de la jornada en cámara lenta", publicado: "2026-06-14", visualizaciones: 388_100, visualizaciones_pagadas: 0, interacciones: 51_200, engagement_pct: 13.2, url: "https://tiktok.com/@cs/1", formato: "video", por_cross_post: true, es_inorganico: false },
  { id: "3", red: "facebook", marca: "Claro Sports", titulo: "Resumen NFL: las mejores atrapadas de la semana", publicado: "2026-06-13", visualizaciones: 201_540, visualizaciones_pagadas: 0, interacciones: 12_300, engagement_pct: 6.1, url: "https://facebook.com/cs/1", formato: "video", por_cross_post: false, es_inorganico: false },
  { id: "4", red: "x", marca: "Claro Sports", titulo: "Canelo confirma su próxima pelea: fecha y rival", publicado: "2026-06-12", visualizaciones: 156_900, visualizaciones_pagadas: 0, interacciones: 9_800, engagement_pct: 6.2, url: "https://x.com/cs/1", formato: "texto", por_cross_post: false, es_inorganico: false },
  { id: "5", red: "instagram", marca: "Claro Sports", titulo: "La afición mexicana enciende el estadio", publicado: "2026-06-11", visualizaciones: 142_750, visualizaciones_pagadas: 0, interacciones: 18_400, engagement_pct: 12.9, url: "https://instagram.com/p/x5", formato: "foto", por_cross_post: false, es_inorganico: false },
  { id: "boost1", red: "facebook", marca: "Claro Sports", titulo: "Checo Pérez sube al podio en Montreal 🇲🇽", publicado: "2026-06-15", visualizaciones: 0, visualizaciones_pagadas: 520_000, interacciones: 0, engagement_pct: 0, url: "", formato: "ads", por_cross_post: false, es_inorganico: true },
  { id: "6", red: "youtube", marca: "Claro Sports", titulo: "Entrevista exclusiva tras la carrera", publicado: "2026-06-10", visualizaciones: 98_200, visualizaciones_pagadas: 0, interacciones: 5_100, engagement_pct: 5.2, url: "https://youtube.com/shorts/1", formato: "video", por_cross_post: false, es_inorganico: false },
  { id: "7", red: "tiktok", marca: "Claro Sports", titulo: "Reacciones al gol del minuto 90", publicado: "2026-06-09", visualizaciones: 87_650, visualizaciones_pagadas: 0, interacciones: 11_900, engagement_pct: 13.6, url: "https://tiktok.com/@cs/7", formato: "video", por_cross_post: false, es_inorganico: false },
  { id: "8", red: "instagram", marca: "Claro Sports", titulo: "Top 5 jugadas de la semana en la NBA", publicado: "2026-06-08", visualizaciones: 76_400, visualizaciones_pagadas: 0, interacciones: 6_800, engagement_pct: 8.9, url: "https://instagram.com/p/x8", formato: "carrusel", por_cross_post: true, es_inorganico: false },
  { id: "9", red: "facebook", marca: "Claro Sports", titulo: "Calendario de la próxima jornada", publicado: "2026-06-07", visualizaciones: 54_120, visualizaciones_pagadas: 0, interacciones: 2_300, engagement_pct: 4.3, url: "https://facebook.com/cs/9", formato: "foto", por_cross_post: false, es_inorganico: false },
  { id: "10", red: "x", marca: "Claro Sports", titulo: "Resultado final y crónica del partido", publicado: "2026-06-06", visualizaciones: 41_900, visualizaciones_pagadas: 0, interacciones: 2_100, engagement_pct: 5.0, url: "https://x.com/cs/10", formato: "texto", por_cross_post: false, es_inorganico: false },
  { id: "11", red: "instagram", marca: "Claro Sports", titulo: "Detrás de cámaras de la transmisión", publicado: "2026-06-05", visualizaciones: 38_500, visualizaciones_pagadas: 0, interacciones: 4_900, engagement_pct: 12.7, url: "https://instagram.com/p/x11", formato: "reel", por_cross_post: false, es_inorganico: false },
  { id: "12", red: "tiktok", marca: "Claro Sports", titulo: "El dato que nadie vio del clásico", publicado: "2026-06-04", visualizaciones: 33_200, visualizaciones_pagadas: 0, interacciones: 4_100, engagement_pct: 12.3, url: "https://tiktok.com/@cs/12", formato: "video", por_cross_post: false, es_inorganico: false },
];

const tendencia = puntosTendencia();
const totalVis = PIEZAS.reduce((s, p) => s + p.visualizaciones, 0);
const totalInter = PIEZAS.reduce((s, p) => s + p.interacciones, 0);

export const MOCK: AnaliticaCampania = {
  campania: {
    id: "preview",
    marcas: ["claro-sports"],
    marcas_nombres: ["Claro Sports"],
    nombre: "AsClaroW",
    hashtags: ["ASClaroW", "ASClaroenW"],
    activa: true,
    fecha_creacion: "2026-05-20T10:00:00Z",
    fecha_actualizacion: "2026-06-22T10:00:00Z",
  },
  rango: "mes",
  periodo: { desde: "2026-05-24", hasta: "2026-06-22" },
  fuente: "metricool",
  kpis: {
    visualizaciones: totalVis,
    interacciones: totalInter,
    engagement_pct: Math.round((totalInter / totalVis) * 1000) / 10,
    piezas: PIEZAS.length,
  },
  comparativa: {
    visualizaciones: { actual: totalVis, anterior: Math.round(totalVis * 0.82), delta: Math.round(totalVis * 0.18), variacion_pct: 21.5 },
    interacciones: { actual: totalInter, anterior: Math.round(totalInter * 0.91), delta: Math.round(totalInter * 0.09), variacion_pct: 9.8 },
    engagement_pct: { actual: 9.1, anterior: 9.6, delta: -0.5, variacion_pct: -5.2 },
    piezas: { actual: PIEZAS.length, anterior: 10, delta: PIEZAS.length - 10, variacion_pct: 20 },
  },
  tendencia: { puntos: tendencia },
  desglose_red: [
    { red: "instagram", piezas: 4, visualizaciones: 669_950, interacciones: 69_000, likes: 58_000, comentarios: 6_200, compartidos: 3_100, guardados: 1_700, engagement_pct: 10.3 },
    { red: "tiktok", piezas: 3, visualizaciones: 508_950, interacciones: 67_200, likes: 55_000, comentarios: 5_800, compartidos: 5_400, guardados: 1_000, engagement_pct: 13.2 },
    { red: "facebook", piezas: 2, visualizaciones: 255_660, interacciones: 14_600, likes: 11_000, comentarios: 2_100, compartidos: 1_300, guardados: 200, engagement_pct: 5.7 },
    { red: "x", piezas: 2, visualizaciones: 198_800, interacciones: 11_900, likes: 8_900, comentarios: 1_800, compartidos: 1_200, guardados: 0, engagement_pct: 6.0 },
    { red: "youtube", piezas: 1, visualizaciones: 98_200, interacciones: 5_100, likes: 4_200, comentarios: 600, compartidos: 300, guardados: 0, engagement_pct: 5.2 },
  ],
  cross_posts: 2,
  inorganico: { visualizaciones: 520_000, gasto: 18_400, clics: 9_200, campanias: 1, moneda: "MXN" },
  piezas: PIEZAS,
  generado_en: "2026-06-22T12:30:00Z",
};

/** URL de demostración del enlace público (token ficticio). */
export const URL_PUBLICA = "https://social.kenitech.io/c/9f3ad2c7b41e8a06d5f2";

// Sustituye la llamada real por el mock (sin red): el panel pinta IGUAL que en producción.
(api as unknown as { analiticaCampania: () => Promise<AnaliticaCampania> }).analiticaCampania =
  async () => MOCK;

export const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
