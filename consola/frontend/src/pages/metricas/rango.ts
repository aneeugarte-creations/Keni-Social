/**
 * Helpers del "token de rango" que el dashboard de Métricas envía al backend.
 *
 * El backend (`resolver_rango`) acepta, además de los presets ("semana"|"mes"|…):
 *   - `mes:AAAA-MM`               → un mes concreto
 *   - `rango:AAAA-MM-DD_AAAA-MM-DD` → un rango personalizado (desde/hasta)
 *
 * El token viaja como string por toda la cadena (es también la clave de cache), así
 * que aquí solo construimos/parseamos ese string. La etiqueta legible la calcula el
 * backend (`etiqueta_rango`) y llega en cada respuesta.
 *
 * Los helpers de resolución (`diasDePeriodo`, `resolverPeriodo`, `periodoAnterior`,
 * `seSolapan`) replican la semántica del backend (`RANGOS_DIAS` + `resolver_rango`):
 * los presets rodantes son ventanas de N días que TERMINAN HOY, con el corte de día
 * en zona CDMX (`hoyCDMX`), NUNCA en la zona del navegador.
 */
import { hoyCDMX } from "@/lib/fecha";

export type ModoTiempo = "atajos" | "mes" | "personalizado";

/** Modo de UI implícito en un token (para inicializar el selector desde el valor actual). */
export function modoDesdeToken(token: string): ModoTiempo {
  if (token.startsWith("mes:")) return "mes";
  if (token.startsWith("rango:")) return "personalizado";
  return "atajos";
}

/** `mes:AAAA-MM` a partir de año y mes (1-12). */
export function tokenMes(anio: number, mes: number): string {
  return `mes:${anio}-${String(mes).padStart(2, "0")}`;
}

/** `rango:AAAA-MM-DD_AAAA-MM-DD` a partir de dos fechas ISO. */
export function tokenRango(desde: string, hasta: string): string {
  return `rango:${desde}_${hasta}`;
}

/** Año y mes de un token `mes:`, o null si no lo es. */
export function partesMes(token: string): { anio: number; mes: number } | null {
  const m = /^mes:(\d{4})-(\d{2})$/.exec(token);
  return m ? { anio: Number(m[1]), mes: Number(m[2]) } : null;
}

/** Fechas de un token `rango:`, o null si no lo es. */
export function partesRango(token: string): { desde: string; hasta: string } | null {
  const m = /^rango:(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})$/.exec(token);
  return m ? { desde: m[1], hasta: m[2] } : null;
}

// --- Resolución de periodos (espejo del backend) ----------------------------

/**
 * Días de cada preset (mismo mapa que `RANGOS_DIAS` del backend + semana_cerrada).
 * Los rodantes (semana/7d/mes/30d/anio) son ventanas que terminan HOY; `semana_cerrada`
 * es la última semana natural cerrada (lunes→domingo), también de 7 días.
 */
const PRESETS_DIAS: Record<string, number> = {
  semana: 7,
  "7d": 7,
  mes: 30,
  "30d": 30,
  anio: 365,
  semana_cerrada: 7,
};

/** Suma `n` días (puede ser negativo) a un día ISO `AAAA-MM-DD`. Anclado a mediodía
 * UTC para que la aritmética de días nunca desplace el día calendario. */
function sumarDias(dia: string, n: number): string {
  const d = new Date(`${dia}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/**
 * Duración en días (inclusiva) del periodo que representa un token.
 * Presets → su mapa; `mes:AAAA-MM` → días de ese mes; `rango:` → (hasta−desde)+1.
 * Token desconocido → null.
 */
export function diasDePeriodo(token: string): number | null {
  const preset = PRESETS_DIAS[token];
  if (preset != null) return preset;
  const mes = partesMes(token);
  // Date.UTC(anio, mes, 0): día 0 del mes SIGUIENTE (índice 0-based) = último día del mes.
  if (mes) return new Date(Date.UTC(mes.anio, mes.mes, 0)).getUTCDate();
  const rango = partesRango(token);
  if (rango) {
    const ms =
      Date.parse(`${rango.hasta}T12:00:00Z`) - Date.parse(`${rango.desde}T12:00:00Z`);
    if (Number.isNaN(ms)) return null;
    return Math.round(ms / 86_400_000) + 1;
  }
  return null;
}

/**
 * Resuelve un token a sus fechas `{desde, hasta}` (ISO, ambas inclusive).
 * Presets rodantes: ventana de N días que termina HOY (corte de día CDMX);
 * `semana_cerrada`: lunes→domingo de la semana natural anterior; `mes:`/`rango:`:
 * sus propias fechas. Token desconocido → null.
 */
export function resolverPeriodo(token: string): { desde: string; hasta: string } | null {
  const rango = partesRango(token);
  if (rango) return rango;
  const mes = partesMes(token);
  if (mes) {
    const ultimoDia = new Date(Date.UTC(mes.anio, mes.mes, 0)).getUTCDate();
    const mm = String(mes.mes).padStart(2, "0");
    return { desde: `${mes.anio}-${mm}-01`, hasta: `${mes.anio}-${mm}-${String(ultimoDia).padStart(2, "0")}` };
  }
  const dias = PRESETS_DIAS[token];
  if (dias == null) return null;
  const hoy = hoyCDMX();
  if (token === "semana_cerrada") {
    // Lunes→domingo de la semana natural ANTERIOR a la que contiene hoy.
    const diaSemana = new Date(`${hoy}T12:00:00Z`).getUTCDay(); // 0=domingo .. 6=sábado
    const lunesDeEstaSemana = sumarDias(hoy, -((diaSemana + 6) % 7));
    const domingoCerrado = sumarDias(lunesDeEstaSemana, -1);
    return { desde: sumarDias(domingoCerrado, -6), hasta: domingoCerrado };
  }
  return { desde: sumarDias(hoy, -(dias - 1)), hasta: hoy };
}

/**
 * El periodo inmediatamente ANTERIOR adyacente de la MISMA longitud que `token`.
 * `mes:AAAA-MM` → el token del mes anterior; resto → `rango:` con la ventana de N
 * días que termina justo antes de empezar la actual. Token desconocido → null.
 */
export function periodoAnterior(token: string): string | null {
  const mes = partesMes(token);
  if (mes) {
    return mes.mes === 1 ? tokenMes(mes.anio - 1, 12) : tokenMes(mes.anio, mes.mes - 1);
  }
  const periodo = resolverPeriodo(token);
  const dias = diasDePeriodo(token);
  if (!periodo || dias == null) return null;
  return tokenRango(sumarDias(periodo.desde, -dias), sumarDias(periodo.desde, -1));
}

/**
 * Par de periodos COMPARABLES para la insignia "vs periodo anterior" de los KPI.
 *
 * `periodoAnterior` a secas compara mal los periodos EN CURSO: a 10 de junio,
 * `mes:2026-06` solo tiene 10 días de datos y compararlo contra los 31 de mayo
 * produce desplomes espurios (~−70 %) que no son una caída real. Aquí se
 * garantiza SIEMPRE la misma duración a ambos lados de la comparación:
 *
 *  - mes EN CURSO → B = los días transcurridos (1..hoy, corte CDMX) y A = los
 *    MISMOS días del mes anterior (1–10 jun vs 1–10 may).
 *  - mes CERRADO de N días → A = los primeros N días del mes anterior
 *    (jun 30 d vs 1–30 may; feb 28 d vs 1–28 ene). Nunca 28 vs 31 días.
 *  - si el mes anterior es más corto que N (mar 31 d vs feb 28 d), A cae a la
 *    ventana adyacente de N días que termina justo antes de B (misma longitud,
 *    igual que `periodoAnterior` sobre un `rango:`).
 *  - presets rodantes / semana cerrada / `rango:` → `periodoAnterior` (ya
 *    produce ventanas de la misma longitud); un `rango:` que invade el futuro
 *    se RECORTA a hoy antes de derivar A (los días futuros no tienen datos).
 *
 * Devuelve null si el token no resuelve o si el periodo es íntegramente futuro
 * (no hay datos que comparar: mejor sin insignia que con un % espurio).
 * `enCurso` marca que B se recortó a los días transcurridos: la UI debe
 * explicitar ese contexto en la leyenda / texto accesible.
 */
export interface ParComparable {
  /** Token A (antes), de la MISMA duración que `rangoB`. */
  rangoA: string;
  /** Token B (actual), recortado a hoy si el periodo estaba en curso. */
  rangoB: string;
  /** true si B se recortó a los días transcurridos (periodo en curso). */
  enCurso: boolean;
}

export function parComparable(token: string): ParComparable | null {
  const periodo = resolverPeriodo(token);
  if (!periodo) return null;
  const hoy = hoyCDMX();
  if (periodo.desde > hoy) return null; // íntegramente futuro: nada que comparar
  const enCurso = periodo.hasta > hoy;
  const rangoB = enCurso ? tokenRango(periodo.desde, hoy) : token;
  const dias = diasDePeriodo(rangoB);
  if (dias == null) return null;

  const mes = partesMes(token);
  if (mes) {
    // Mes (en curso o cerrado): A = los mismos N días del MES ANTERIOR, que
    // conserva la alineación con el ciclo mensual (1–10 jun vs 1–10 may).
    const prev =
      mes.mes === 1 ? { anio: mes.anio - 1, mes: 12 } : { anio: mes.anio, mes: mes.mes - 1 };
    const diasPrev = new Date(Date.UTC(prev.anio, prev.mes, 0)).getUTCDate();
    if (dias <= diasPrev) {
      const mm = String(prev.mes).padStart(2, "0");
      return {
        rangoA: tokenRango(
          `${prev.anio}-${mm}-01`,
          `${prev.anio}-${mm}-${String(dias).padStart(2, "0")}`,
        ),
        rangoB,
        enCurso,
      };
    }
    // El mes anterior no llega a N días (mar 31 d vs feb 28 d): ventana
    // adyacente de N días terminando justo antes de B (misma duración).
    return {
      rangoA: tokenRango(sumarDias(periodo.desde, -dias), sumarDias(periodo.desde, -1)),
      rangoB,
      enCurso,
    };
  }

  const rangoA = periodoAnterior(rangoB);
  return rangoA ? { rangoA, rangoB, enCurso } : null;
}

/** ¿Se solapan los periodos que representan dos tokens? (false si alguno no resuelve). */
export function seSolapan(a: string, b: string): boolean {
  const pa = resolverPeriodo(a);
  const pb = resolverPeriodo(b);
  if (!pa || !pb) return false;
  // Comparación lexicográfica de ISO AAAA-MM-DD = comparación cronológica.
  return pa.desde <= pb.hasta && pb.desde <= pa.hasta;
}
