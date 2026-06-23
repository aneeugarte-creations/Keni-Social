/**
 * Exportación COMPLETA del dashboard de Métricas a un único CSV.
 *
 * "Todo lo que está en pantalla": en vez de pedir al backend un reporte agregado, vuelca
 * los datos que el dashboard YA tiene cargados en la caché de React Query (las queries
 * ACTIVAS bajo la clave `["metricas", …]` = las secciones montadas en pantalla). Así el
 * CSV incluye KPIs, por marca, por red, cobertura, tendencia, seguidores, desglose, cruces,
 * correlación, líneas, publicidad y las LISTAS DE PIEZAS, con el filtro de marca/red/periodo
 * ya aplicado. Cada dataset se serializa como una sección etiquetada (`# Título`).
 */

/** Etiquetas legibles por dominio de query (`queryKey[1]`). Lo no listado cae al propio id. */
const TITULOS: Record<string, string> = {
  reporte: "Reporte (KPIs · por marca · por red · cobertura)",
  tendencia: "Tendencia diaria",
  analisis: "Análisis diario",
  seguidores: "Crecimiento de seguidores",
  desglose: "Desglose de interacciones",
  crosstab: "Cruce de métricas",
  correlacion: "Correlación con seguidores",
  lineas: "Rendimiento por línea",
  ads: "Publicidad pagada",
  piezas: "Piezas del periodo (top y peores)",
  "piezas-listado": "Listado de piezas",
  "piezas-rendimiento": "Rendimiento de piezas",
  "piezas-por-etiqueta": "Piezas por etiqueta",
};

const SEP = ",";

function escapar(v: unknown): string {
  if (v == null) return "";
  const s = typeof v === "object" ? JSON.stringify(v) : String(v);
  return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function filaCsv(valores: unknown[]): string {
  return valores.map(escapar).join(SEP);
}

/**
 * Aplana un objeto a un registro de escalares: objetos anidados → claves con punto; arrays
 * de escalares → "a; b"; arrays de objetos → JSON compacto (no se pierde nada).
 */
function aplanar(obj: Record<string, unknown>, prefijo = ""): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj ?? {})) {
    const clave = prefijo ? `${prefijo}.${k}` : k;
    if (v == null || typeof v !== "object") {
      out[clave] = v;
    } else if (Array.isArray(v)) {
      out[clave] = v.every((x) => x == null || typeof x !== "object")
        ? v.join("; ")
        : JSON.stringify(v);
    } else {
      Object.assign(out, aplanar(v as Record<string, unknown>, clave));
    }
  }
  return out;
}

/** Sección tabla: array de objetos → cabecera (unión de claves aplanadas) + filas. */
function seccionTabla(titulo: string, filas: Record<string, unknown>[]): string[] {
  const aplanadas = filas.map((f) => aplanar(f));
  const columnas: string[] = [];
  const visto = new Set<string>();
  for (const f of aplanadas) {
    for (const k of Object.keys(f)) {
      if (!visto.has(k)) {
        visto.add(k);
        columnas.push(k);
      }
    }
  }
  const lineas = [`# ${titulo}`, filaCsv(columnas)];
  for (const f of aplanadas) lineas.push(filaCsv(columnas.map((c) => f[c])));
  return lineas;
}

/** Sección clave/valor de un objeto de escalares. */
function seccionKV(titulo: string, obj: Record<string, unknown>): string[] {
  const plano = aplanar(obj);
  const lineas = [`# ${titulo}`];
  for (const [k, v] of Object.entries(plano)) lineas.push(filaCsv([k, v]));
  return lineas;
}

/** Serializa un dato arbitrario (array u objeto) a líneas CSV bajo un título. */
function serializarDato(titulo: string, dato: unknown): string[] {
  if (dato == null) return [];
  if (Array.isArray(dato)) {
    if (dato.length === 0) return [`# ${titulo}`, "(vacío)"];
    if (dato.every((x) => x && typeof x === "object" && !Array.isArray(x))) {
      return seccionTabla(titulo, dato as Record<string, unknown>[]);
    }
    return [`# ${titulo}`, ...dato.map((x) => escapar(x))];
  }
  if (typeof dato === "object") {
    const escalares: Record<string, unknown> = {};
    const subsecciones: Array<[string, unknown[]]> = [];
    for (const [k, v] of Object.entries(dato as Record<string, unknown>)) {
      if (Array.isArray(v) && v.some((x) => x && typeof x === "object")) {
        subsecciones.push([`${titulo} · ${k}`, v]);
      } else {
        escalares[k] = v;
      }
    }
    const lineas = seccionKV(titulo, escalares);
    for (const [t, v] of subsecciones) {
      lineas.push("");
      lineas.push(...serializarDato(t, v));
    }
    return lineas;
  }
  return [`# ${titulo}`, escapar(dato)];
}

function tituloDeKey(key: readonly unknown[]): string {
  const dominio = String(key[1] ?? "");
  return TITULOS[dominio] ?? key.slice(1).filter((k) => typeof k !== "object").join(" · ");
}

export interface ContextoCsv {
  marca: string;
  red: string;
  formato: string;
  periodo: string;
  generadoEn?: string;
}

/**
 * Construye el CSV completo a partir de las entradas de caché `[queryKey, data]` (las
 * activas bajo `["metricas", …]`). Omite la query de `opciones` (no es un dataset).
 */
export function construirCsvCompleto(
  entradas: Array<[readonly unknown[], unknown]>,
  ctx: ContextoCsv,
): string {
  const lineas: string[] = [
    "# Analíticas Keni Social",
    filaCsv(["Marca", ctx.marca]),
    filaCsv(["Red", ctx.red]),
    filaCsv(["Formato", ctx.formato]),
    filaCsv(["Periodo", ctx.periodo]),
  ];
  if (ctx.generadoEn) lineas.push(filaCsv(["Generado", ctx.generadoEn]));
  lineas.push("");

  const utiles = entradas.filter(
    ([key, dato]) => dato != null && String(key[1] ?? "") !== "opciones",
  );
  // Orden estable: por el orden de aparición en TITULOS, luego alfabético.
  const orden = Object.keys(TITULOS);
  utiles.sort((a, b) => {
    const ia = orden.indexOf(String(a[0][1]));
    const ib = orden.indexOf(String(b[0][1]));
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });

  for (const [key, dato] of utiles) {
    lineas.push(...serializarDato(tituloDeKey(key), dato));
    lineas.push("");
  }
  return lineas.join("\n");
}

/** Dispara la descarga de un texto como archivo (con BOM para que Excel lea UTF-8). */
export function descargarTexto(nombre: string, texto: string, mime: string): void {
  const blob = new Blob(["﻿", texto], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
