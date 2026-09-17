/**
 * Preview local (desechable) del diálogo «Descargar PDF»: renderiza `ComposicionInforme` con
 * datos de ejemplo y un botón que dispara `generarPdfInforme`, para validar la captura (gráfica
 * incluida) y el PDF resultante SIN backend. Borrar `src/__preview/` antes de promover.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as React from "react";
import ReactDOM from "react-dom/client";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { generarPdfInforme } from "@/lib/informe-pdf";
import { ComposicionInforme } from "@/pages/campanias/ComposicionInforme";
import type { AnaliticaCampania, PiezaCampania } from "@/types";

import "../index.css";

const PIEZAS: PiezaCampania[] = Array.from({ length: 9 }, (_, i) => ({
  id: String(i),
  red: ["instagram", "tiktok", "facebook", "x", "youtube"][i % 5],
  marca: "Claro Sports",
  titulo: [
    "Checo Pérez sube al podio en Montreal 🇲🇽",
    "El golazo de la jornada en cámara lenta",
    "Resumen NFL: las mejores atrapadas",
    "Canelo confirma su próxima pelea",
    "La afición mexicana enciende el estadio",
    "Entrevista exclusiva tras la carrera",
    "Top 5 jugadas de la semana en la NBA",
    "Calendario de la próxima jornada",
    "El dato que nadie vio del clásico",
  ][i],
  publicado: `2026-06-${String(20 - i).padStart(2, "0")}`,
  visualizaciones: 420_000 - i * 38_000,
  visualizaciones_pagadas: 0,
  interacciones: 40_000 - i * 3_500,
  engagement_pct: 12 - i * 0.6,
  url: "https://ejemplo/p",
  formato: ["reel", "video", "foto", "texto", "carrusel"][i % 5],
  por_cross_post: i === 1,
  es_inorganico: false,
}));

const puntos = Array.from({ length: 30 }, (_, i) => {
  const d = new Date("2026-05-24T12:00:00Z");
  d.setUTCDate(d.getUTCDate() + i);
  return {
    fecha: d.toISOString().slice(0, 10),
    visualizaciones: Math.round(12000 + Math.sin(i / 2) * 6000 + i * 400),
    interacciones: Math.round(1200 + Math.cos(i / 3) * 600 + i * 30),
  };
});

const MOCK: AnaliticaCampania = {
  campania: {
    id: "preview", marcas: ["claro-sports"], marcas_nombres: ["Claro Sports"], nombre: "AsClaroW",
    hashtags: ["ASClaroW", "ASClaroenW"], activa: true,
    fecha_creacion: "2026-05-20T10:00:00Z", fecha_actualizacion: "2026-06-22T10:00:00Z",
  },
  rango: "mes",
  periodo: { desde: "2026-05-24", hasta: "2026-06-22" },
  fuente: "metricool",
  kpis: { visualizaciones: 2_300_000, interacciones: 168_000, engagement_pct: 7.3, piezas: 9 },
  comparativa: {
    visualizaciones: { actual: 2_300_000, anterior: 1_900_000, delta: 400_000, variacion_pct: 21.5 },
    interacciones: { actual: 168_000, anterior: 153_000, delta: 15_000, variacion_pct: 9.8 },
    engagement_pct: { actual: 7.3, anterior: 7.7, delta: -0.4, variacion_pct: -5.2 },
    piezas: { actual: 9, anterior: 8, delta: 1, variacion_pct: 12.5 },
  },
  tendencia: { puntos },
  desglose_red: [
    { red: "instagram", piezas: 2, visualizaciones: 770_000, interacciones: 80_000, likes: 60_000, comentarios: 6_000, compartidos: 3_000, guardados: 1_700, engagement_pct: 10.3 },
    { red: "tiktok", piezas: 2, visualizaciones: 600_000, interacciones: 70_000, likes: 55_000, comentarios: 5_000, compartidos: 5_400, guardados: 1_000, engagement_pct: 11.6 },
    { red: "facebook", piezas: 2, visualizaciones: 360_000, interacciones: 14_000, likes: 11_000, comentarios: 2_000, compartidos: 1_300, guardados: 200, engagement_pct: 3.9 },
  ],
  cross_posts: 1,
  inorganico: { visualizaciones: 0, gasto: 0, clics: 0, campanias: 0, moneda: "" },
  piezas: PIEZAS,
  generado_en: "2026-06-22T12:30:00Z",
};

(api as unknown as { analiticaCampania: () => Promise<AnaliticaCampania> }).analiticaCampania =
  async () => MOCK;

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const URL_DEMO = "https://social.kenitech.io/c/9f3ad2c7b41e8a06d5f2";

function Preview() {
  const ref = React.useRef<HTMLDivElement>(null);
  return (
    <div className="h-full overflow-y-auto bg-neutral-100 p-8">
      <div className="mx-auto mb-4 flex max-w-[800px] items-center justify-between">
        <p className="text-xs text-neutral-500">Preview del PDF (datos de ejemplo).</p>
        <Button onClick={() => ref.current && void generarPdfInforme(ref.current, "demo.pdf")}>
          Descargar PDF
        </Button>
      </div>
      <div className="mx-auto w-fit shadow">
        <ComposicionInforme ref={ref} datos={MOCK} enlaceUrl={URL_DEMO} ocultarAds />
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <Preview />
    </QueryClientProvider>
  </React.StrictMode>,
);
