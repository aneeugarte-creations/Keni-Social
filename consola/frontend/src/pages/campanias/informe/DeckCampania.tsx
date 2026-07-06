/**
 * Deck de diapositivas (1280×720, mismo lienzo que el informe de Métricas) para el PDF
 * "testigo" de una campaña: portada, KPIs comparados contra el periodo anterior, tendencia
 * diaria, desglose por red y la tabla de piezas del periodo (el "testigo" que antes se armaba
 * a mano pegando capturas). Si hay un enlace público vigente para el periodo/modo actuales,
 * cierra con su QR. Puramente presentacional: los datos ya vienen resueltos de
 * `AnaliticaCampania`; `exportarPdfCampania.ts` monta esto y lo rasteriza.
 */
import * as React from "react";

import { nombreFormato, nombreRed, numeroCompacto, numeroCompleto, porcentaje } from "@/lib/formato";
import { AreaBold } from "@/pages/metricas/informe/graficas";
import type { AnaliticaCampania, ComparativaKpi, PiezaCampania } from "@/types";

import { clavePieza, fechaCorta, visEfectivas } from "../formato";

import "@/pages/metricas/informe/informe.css";

const NARANJA = "#ea580c";
const VERDE = "#059669";
const ROJO = "#dc2626";

/** Máximo de piezas por lámina de tabla: una densidad legible en una sola lámina. */
const TOPE_PIEZAS = 14;

/** Secciones del deck que se pueden encender/apagar al descargar. La portada siempre va; la
 * lámina de enlace/QR depende de si hay enlace vigente (no es una sección elegible). */
export interface SeccionesDeck {
  kpis: boolean;
  tendencia: boolean;
  desgloseRed: boolean;
  piezas: boolean;
}

/** Todas las secciones activas: el comportamiento de hoy (nada apagado). */
export const SECCIONES_TODAS: SeccionesDeck = {
  kpis: true,
  tendencia: true,
  desgloseRed: true,
  piezas: true,
};

/**
 * Piezas a pintar en la tabla y cuántas quedan fuera, según la selección:
 * - `seleccion == null` (default): TODAS ordenadas por vistas efectivas desc, cortadas al tope
 *   de una lámina; `restantes` es lo que no cabe (nota "+N más").
 * - `seleccion` (Set de claves): SOLO las elegidas por la persona (mismo orden por vistas), sin
 *   corte —se paginan en varias láminas—; no hay "+N más" (las eligió a propósito).
 */
export function piezasParaTabla(
  datos: AnaliticaCampania,
  ocultarAds: boolean,
  seleccion: Set<string> | null,
): { piezas: PiezaCampania[]; restantes: number } {
  const ordenadas = datos.piezas
    .map((p, i) => ({ p, clave: clavePieza(p, i) }))
    .sort((a, b) => visEfectivas(b.p, ocultarAds) - visEfectivas(a.p, ocultarAds));
  if (seleccion == null) {
    const piezas = ordenadas.slice(0, TOPE_PIEZAS).map((x) => x.p);
    return { piezas, restantes: datos.piezas.length - piezas.length };
  }
  const piezas = ordenadas.filter((x) => seleccion.has(x.clave)).map((x) => x.p);
  return { piezas, restantes: 0 };
}

/** Reparte una lista de piezas en páginas de hasta `TOPE_PIEZAS`. Al menos una página (vacía si
 * no hay piezas), para que la sección "Piezas" siempre aporte su lámina cuando está activa. */
function paginarPiezas(piezas: PiezaCampania[]): PiezaCampania[][] {
  if (piezas.length === 0) return [[]];
  const paginas: PiezaCampania[][] = [];
  for (let i = 0; i < piezas.length; i += TOPE_PIEZAS) {
    paginas.push(piezas.slice(i, i + TOPE_PIEZAS));
  }
  return paginas;
}

function SlideBase({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return <div className={`informe-slide px-20 py-16 ${className ?? ""}`}>{children}</div>;
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-neutral-500">
      {children}
    </p>
  );
}

function PortadaCampania({
  datos,
  periodoEtiqueta,
  generadoEn,
}: {
  datos: AnaliticaCampania;
  periodoEtiqueta: string;
  generadoEn?: string;
}) {
  const { campania } = datos;
  return (
    <SlideBase className="flex flex-col justify-between bg-white">
      <div>
        <Eyebrow>Campaña · KENI</Eyebrow>
        <h1 className="mt-4 max-w-4xl text-6xl font-light tracking-tight text-neutral-900">
          {campania.nombre}
        </h1>
        <div className="mt-8 flex flex-wrap items-center gap-2">
          {campania.marcas_nombres.map((m) => (
            <span
              key={m}
              className="rounded-full border border-neutral-300 px-3 py-1 text-sm text-neutral-700"
            >
              {m}
            </span>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {campania.hashtags.map((h) => (
            <span key={h} className="text-sm font-medium text-neutral-500">
              #{h}
            </span>
          ))}
        </div>
      </div>
      <div className="flex items-baseline justify-between text-sm text-neutral-500">
        <span>{periodoEtiqueta}</span>
        {generadoEn && <span>Generado el {fechaCorta(generadoEn)}</span>}
      </div>
    </SlideBase>
  );
}

function flechaComparativa(comp: ComparativaKpi | undefined): { texto: string; color: string } {
  if (!comp || comp.variacion_pct == null) return { texto: "", color: "#a3a3a3" };
  if (comp.anterior === 0 && comp.actual > 0) return { texto: "Nuevo", color: VERDE };
  const signo = comp.variacion_pct > 0 ? "+" : "";
  const color = comp.variacion_pct > 0 ? VERDE : comp.variacion_pct < 0 ? ROJO : "#a3a3a3";
  return { texto: `${signo}${comp.variacion_pct.toFixed(1)} %`, color };
}

function TarjetaKpiDeck({
  etiqueta,
  valor,
  comp,
}: {
  etiqueta: string;
  valor: string;
  comp?: ComparativaKpi;
}) {
  const { texto, color } = flechaComparativa(comp);
  return (
    <div className="flex-1 space-y-2 border-r border-neutral-200 pr-6 last:border-r-0">
      <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">{etiqueta}</p>
      <p className="text-4xl font-light text-neutral-900">{valor}</p>
      {texto && (
        <p className="text-sm font-medium" style={{ color }}>
          {texto}
        </p>
      )}
    </div>
  );
}

function SlideKpis({ datos }: { datos: AnaliticaCampania }) {
  const { kpis, comparativa } = datos;
  return (
    <SlideBase className="flex flex-col justify-center bg-white">
      <Eyebrow>Resultados del periodo</Eyebrow>
      <div className="mt-8 flex items-stretch gap-6">
        <TarjetaKpiDeck etiqueta="Piezas" valor={numeroCompleto(kpis.piezas)} comp={comparativa.piezas} />
        <TarjetaKpiDeck
          etiqueta="Vistas"
          valor={numeroCompacto(kpis.visualizaciones)}
          comp={comparativa.visualizaciones}
        />
        <TarjetaKpiDeck
          etiqueta="Interacciones"
          valor={numeroCompacto(kpis.interacciones)}
          comp={comparativa.interacciones}
        />
        <TarjetaKpiDeck
          etiqueta="Engagement"
          valor={porcentaje(kpis.engagement_pct)}
          comp={comparativa.engagement_pct}
        />
        <div className="flex-1 space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">Alcance</p>
          <p className="text-4xl font-light text-neutral-900">
            {kpis.alcance == null ? "n/d" : numeroCompacto(kpis.alcance)}
          </p>
        </div>
      </div>
    </SlideBase>
  );
}

function SlideTendencia({ datos }: { datos: AnaliticaCampania }) {
  const puntos = datos.tendencia.puntos;
  const valores = puntos.map((p) => p.visualizaciones);
  return (
    <SlideBase className="flex flex-col bg-white">
      <Eyebrow>Tendencia diaria · Vistas</Eyebrow>
      {puntos.length < 2 ? (
        <p className="mt-12 text-center text-neutral-500">No hay suficientes días para graficar.</p>
      ) : (
        <>
          <div className="mt-8">
            <AreaBold valores={valores} w={1120} h={340} id="tendencia-campania" color={NARANJA} marcarFinal />
          </div>
          <div className="mt-2 flex justify-between text-sm text-neutral-500">
            <span>{fechaCorta(puntos[0].fecha)}</span>
            <span>{fechaCorta(puntos[puntos.length - 1].fecha)}</span>
          </div>
        </>
      )}
    </SlideBase>
  );
}

function SlideDesgloseRed({ datos }: { datos: AnaliticaCampania }) {
  const filas = [...datos.desglose_red].sort((a, b) => b.visualizaciones - a.visualizaciones);
  return (
    <SlideBase className="flex flex-col bg-white">
      <Eyebrow>Desglose por red</Eyebrow>
      <table className="mt-8 w-full text-left text-sm">
        <thead>
          <tr className="border-b border-neutral-300 text-xs uppercase tracking-wide text-neutral-500">
            <th className="py-2">Red</th>
            <th className="py-2 text-right">Piezas</th>
            <th className="py-2 text-right">Vistas</th>
            <th className="py-2 text-right">Interacciones</th>
            <th className="py-2 text-right">Engagement</th>
          </tr>
        </thead>
        <tbody>
          {filas.map((f) => (
            <tr key={f.red} className="border-b border-neutral-100">
              <td className="py-3 font-medium text-neutral-900">{nombreRed(f.red)}</td>
              <td className="py-3 text-right tabular-nums text-neutral-700">{numeroCompleto(f.piezas)}</td>
              <td className="py-3 text-right tabular-nums text-neutral-700">
                {numeroCompacto(f.visualizaciones)}
              </td>
              <td className="py-3 text-right tabular-nums text-neutral-700">
                {numeroCompacto(f.interacciones)}
              </td>
              <td className="py-3 text-right tabular-nums text-neutral-700">
                {porcentaje(f.engagement_pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </SlideBase>
  );
}

function SlidePiezas({
  piezas,
  ocultarAds,
  restantes,
}: {
  piezas: PiezaCampania[];
  ocultarAds: boolean;
  restantes: number;
}) {
  return (
    <SlideBase className="flex flex-col bg-white">
      <Eyebrow>Piezas del periodo</Eyebrow>
      <table className="mt-6 w-full text-left text-[13px]">
        <thead>
          <tr className="border-b border-neutral-300 text-[11px] uppercase tracking-wide text-neutral-500">
            <th className="py-2 pr-3">Publicación</th>
            <th className="py-2 pr-3">Red</th>
            <th className="py-2 pr-3">Marca</th>
            <th className="py-2 pr-3">Formato</th>
            <th className="py-2 pr-3 text-right">Vistas</th>
            <th className="py-2 text-right">Interacciones</th>
          </tr>
        </thead>
        <tbody>
          {piezas.map((p: PiezaCampania) => (
            <tr key={p.id} className="border-b border-neutral-100">
              <td className="max-w-[22rem] truncate py-2 pr-3 text-neutral-900" title={p.titulo}>
                {p.titulo || "Publicación"}
              </td>
              <td className="py-2 pr-3 text-neutral-700">{nombreRed(p.red)}</td>
              <td className="py-2 pr-3 text-neutral-700">{p.marca}</td>
              <td className="py-2 pr-3 text-neutral-700">{nombreFormato(p.formato)}</td>
              <td className="py-2 pr-3 text-right tabular-nums text-neutral-700">
                {numeroCompacto(visEfectivas(p, ocultarAds))}
              </td>
              <td className="py-2 text-right tabular-nums text-neutral-700">
                {numeroCompacto(p.interacciones)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {restantes > 0 && (
        <p className="mt-3 text-xs text-neutral-500">
          + {restantes} pieza{restantes === 1 ? "" : "s"} más en el periodo (ordenadas por vistas).
        </p>
      )}
    </SlideBase>
  );
}

function SlideEnlace({ url, qrDataUrl }: { url: string; qrDataUrl: string }) {
  return (
    <SlideBase className="flex flex-col items-center justify-center gap-6 bg-white text-center">
      <Eyebrow>Informe en vivo</Eyebrow>
      <p className="max-w-lg text-neutral-600">
        Escanea el código o abre el enlace para ver este informe siempre actualizado, sin cuenta.
      </p>
      {/* `data-pdf-enlace`: el rasterizador superpone un enlace clicable sobre esta zona. */}
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        data-pdf-enlace={url}
        className="flex flex-col items-center gap-4"
      >
        <img src={qrDataUrl} alt="Código QR del informe" width={220} height={220} />
        <span className="font-mono text-sm text-neutral-500">{url}</span>
      </a>
    </SlideBase>
  );
}

export function DeckCampania({
  datos,
  periodoEtiqueta,
  generadoEn,
  ocultarAds,
  enlace,
  secciones = SECCIONES_TODAS,
  piezasSeleccionadas = null,
}: {
  datos: AnaliticaCampania;
  periodoEtiqueta: string;
  generadoEn?: string;
  /** Modo cliente: la tabla de piezas suma lo pagado a lo orgánico (sin rastro de pauta). */
  ocultarAds: boolean;
  /** Enlace público vigente para este periodo/modo, si existe (QR de cierre). */
  enlace?: { url: string; qrDataUrl: string } | null;
  /** Secciones activas. Por defecto todas (comportamiento de hoy). La portada siempre va. */
  secciones?: SeccionesDeck;
  /** Claves (`clavePieza`) de las piezas elegidas. `null` = todas ordenadas y cortadas al tope
   * (comportamiento de hoy con nota "+N más"); un Set = solo esas, paginadas sin corte. */
  piezasSeleccionadas?: Set<string> | null;
}) {
  const { piezas, restantes } = piezasParaTabla(datos, ocultarAds, piezasSeleccionadas);
  const paginas = paginarPiezas(piezas);
  return (
    <>
      <PortadaCampania datos={datos} periodoEtiqueta={periodoEtiqueta} generadoEn={generadoEn} />
      {secciones.kpis && <SlideKpis datos={datos} />}
      {secciones.tendencia && <SlideTendencia datos={datos} />}
      {secciones.desgloseRed && <SlideDesgloseRed datos={datos} />}
      {secciones.piezas &&
        paginas.map((pagina, i) => (
          <SlidePiezas
            key={i}
            piezas={pagina}
            ocultarAds={ocultarAds}
            restantes={i === paginas.length - 1 ? restantes : 0}
          />
        ))}
      {enlace && <SlideEnlace url={enlace.url} qrDataUrl={enlace.qrDataUrl} />}
    </>
  );
}
