/**
 * Exportación del dashboard de Métricas a PDF "presentación" (deck horizontal).
 *
 * Usa el MOTOR DE IMPRESIÓN del navegador (Chromium): `window.print()` con una hoja de
 * estilo de impresión que aísla el cuerpo del dashboard, lo maqueta como diapositivas
 * (una por bloque `[data-slide]`) en horizontal y le antepone una portada. Frente a
 * rasterizar el DOM (html2canvas), esto:
 *   - conserva las GRÁFICAS como vectores nítidos e idénticos a la pantalla,
 *   - no corre render en JS en el hilo principal → no satura memoria ni "explota",
 *   - es instantáneo (lo hace el navegador) y el usuario guarda como PDF.
 *
 * El PDF refleja el ESTADO VIVO (marca, red, periodo, filtros y orden de columnas), porque
 * imprime lo que está pintado. La portada recibe las etiquetas legibles.
 */
import { diasDePeriodo, partesMes, partesRango } from "./rango";
import type { RangoMetrica } from "@/types";

const MESES_ES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

/** Etiqueta legible de un token de periodo (preset, `mes:` o `rango:`). */
export function etiquetaPeriodo(token: string, rangos: RangoMetrica[]): string {
  const preset = rangos.find((r) => r.id === token);
  if (preset) return preset.etiqueta;
  const mes = partesMes(token);
  if (mes) return `${MESES_ES[mes.mes - 1]} ${mes.anio}`;
  const rango = partesRango(token);
  if (rango) return `${rango.desde} – ${rango.hasta}`;
  const dias = diasDePeriodo(token);
  return dias != null ? `Últimos ${dias} días` : token;
}

const CLASE_IMPRESION = "keni-imprimiendo-metricas";
const ID_ESTILO = "keni-estilo-impresion-metricas";
const ID_PORTADA = "keni-portada-impresion";

interface OpcionesDeck {
  marca: string;
  red: string;
  periodo: string;
  generadoEn?: string;
}

/** Hoja de estilo de impresión: aísla el deck, lo pagina por diapositivas y lo pone horizontal. */
function cssImpresion(): string {
  return `
@media print {
  @page { size: A4 landscape; margin: 10mm; }
  /* Aísla el cuerpo del dashboard: oculta el chrome de la app, deja solo el deck. */
  body.${CLASE_IMPRESION} * { visibility: hidden !important; }
  body.${CLASE_IMPRESION} #${ID_PORTADA},
  body.${CLASE_IMPRESION} #${ID_PORTADA} *,
  body.${CLASE_IMPRESION} [data-deck-root],
  body.${CLASE_IMPRESION} [data-deck-root] * { visibility: visible !important; }
  body.${CLASE_IMPRESION} [data-deck-root] {
    position: absolute !important; left: 0; top: 0; width: 100% !important;
    margin: 0 !important; padding: 0 !important;
  }
  /* Una diapositiva por bloque marcado; nunca se parte a mitad. */
  body.${CLASE_IMPRESION} [data-slide] {
    break-before: page; break-inside: avoid; padding-top: 6mm;
  }
  body.${CLASE_IMPRESION} [data-slide]::before {
    content: attr(data-slide);
    display: block; font-weight: 700; font-size: 15pt; margin: 0 0 6pt;
  }
  /* Imprime fondos y colores tal cual (no los descarta el navegador). */
  body.${CLASE_IMPRESION} * {
    -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important;
  }
}
`;
}

function inyectarEstilo(): void {
  if (document.getElementById(ID_ESTILO)) return;
  const el = document.createElement("style");
  el.id = ID_ESTILO;
  el.textContent = cssImpresion();
  document.head.appendChild(el);
}

function fechaLegible(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("es-MX", {
    day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

/** Crea la portada (primera diapositiva), con los colores del tema vivo. */
function crearPortada(raiz: HTMLElement, opts: OpcionesDeck): HTMLElement {
  const estilo = getComputedStyle(document.body);
  const portada = document.createElement("div");
  portada.id = ID_PORTADA;
  portada.style.cssText = [
    "break-after: page",
    "padding: 24mm 0 0",
    `color: ${estilo.color}`,
    "font-family: inherit",
  ].join(";");
  const pie = ["Keni Social — Analíticas", fechaLegible(opts.generadoEn)]
    .filter(Boolean)
    .join("  ·  ");
  portada.innerHTML = `
    <div style="border-left:6px solid currentColor;padding-left:16px;opacity:.95">
      <div style="font-size:34pt;font-weight:800;line-height:1.1">${opts.marca}</div>
      <div style="font-size:16pt;margin-top:8px;opacity:.75">${opts.red}  ·  ${opts.periodo}</div>
      <div style="font-size:10pt;margin-top:16px;opacity:.6">${pie}</div>
    </div>`;
  raiz.insertBefore(portada, raiz.firstChild);
  return portada;
}

/**
 * Abre el diálogo "Guardar como PDF" del navegador con el dashboard maquetado como deck.
 * No descarga en silencio (eso requeriría un Chromium en servidor): el usuario elige
 * destino. Lanza si no encuentra el cuerpo del dashboard.
 */
export function imprimirPresentacion(opts: OpcionesDeck): void {
  const raiz = document.querySelector<HTMLElement>("[data-deck-root]");
  if (!raiz) throw new Error("No se encontró el contenido del dashboard.");

  inyectarEstilo();
  const portada = crearPortada(raiz, opts);
  document.body.classList.add(CLASE_IMPRESION);

  const limpiar = () => {
    document.body.classList.remove(CLASE_IMPRESION);
    portada.remove();
    window.removeEventListener("afterprint", limpiar);
  };
  window.addEventListener("afterprint", limpiar);
  // Fallback: si `afterprint` no llega (algún navegador), limpia igualmente.
  window.setTimeout(() => {
    if (document.body.classList.contains(CLASE_IMPRESION)) limpiar();
  }, 60_000);

  window.print();
}
