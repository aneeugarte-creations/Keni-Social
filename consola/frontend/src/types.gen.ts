/**
 * GENERADO — NO EDITAR A MANO.
 *
 * Tipos DERIVADOS del backend (subconjunto estable del contrato `/api/*`).
 * Fuente: `keni_consola.esquema_api` (Python). Regenerar con `npm run gen:types`.
 * El guard `npm run gen:types:check` (y el test del backend) falla si esto se
 * desincroniza del backend. El resto de tipos vive a mano en `types.ts`. Ver #101.
 */

export interface ResultadoEstado {
  estado: "ok" | "aviso" | "error";
  nombre: string;
  detalle: string;
  icono: string;
}
export interface RespuestaEstado {
  resultados: ResultadoEstado[];
  resumen: string;
  siguiente_paso: string;
}
export interface MarcaDisponible {
  id: string;
  nombre: string;
}
export interface CredencialesPresentes {
  meta: boolean;
  youtube: boolean;
  x: boolean;
  tiktok: boolean;
}
export interface RespuestaConfig {
  fuente: string;
  fuentes_validas: string[];
  marcas: string[];
  marcas_disponibles: MarcaDisponible[];
  credenciales_presentes: CredencialesPresentes;
}
export interface CuerpoGuardarConfig {
  fuente: string;
  marcas: string[];
}
/**
 * Limite de caracteres canonico de una red (fuente unica, `GET /api/limites`).
 *
 * `limite` es `null` si la red no tiene tope tecnico practico (Facebook/YouTube).
 */
export interface LimiteRed {
  id: string;
  nombre: string;
  limite: number | null;
}
/**
 * Respuesta de `GET /api/limites`: los limites por red, en orden fijo.
 */
export interface RespuestaLimites {
  limites: LimiteRed[];
}
export interface RangoMetrica {
  id: string;
  etiqueta: string;
}
export interface OpcionesMetricas {
  marcas: MarcaDisponible[];
  rangos: RangoMetrica[];
}
export interface TotalMetricas {
  visualizaciones: number;
  alcance: number;
  interacciones: number;
  engagement_pct: number;
}
export interface CuentaMetrica {
  marca_id: string;
  marca: string;
  visualizaciones: number;
  alcance: number;
  interacciones: number;
  engagement_pct: number;
}
/**
 * Respuesta de `GET /api/metricas/reporte`.
 */
export interface ReporteMetricas {
  rango: string;
  etiqueta_rango: string;
  marca: string;
  fuente: string;
  total: TotalMetricas;
  cuentas: CuentaMetrica[];
}
export interface ComparativaMetrica {
  metrica: string;
  a: number;
  b: number;
  diferencia: number;
  variacion_pct: number;
}
export interface ComparativaPorMarca {
  marca_id: string;
  marca: string;
  comparativa: ComparativaMetrica[];
}
export interface TotalComparativa {
  metricas: ComparativaMetrica[];
}
/**
 * Respuesta de `GET /api/metricas/comparar`: comparativa A vs B.
 */
export interface CompararMetricas {
  marca: string;
  rango_a: string;
  rango_b: string;
  etiqueta_a: string;
  etiqueta_b: string;
  fuente: string;
  total: TotalComparativa;
  por_marca: ComparativaPorMarca[];
}
export interface RespuestaMensaje {
  mensaje: string;
}
/**
 * Forma de error que devuelve el backend (uno u otro campo, en espanol).
 */
export interface ErrorApi {
  error?: string;
  mensaje?: string;
}
