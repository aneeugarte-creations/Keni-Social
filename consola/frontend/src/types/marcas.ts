/**
 * Tipos del dashboard «Marcas» (GET /api/marcas): la foto en vivo de todas las
 * marcas × redes × cuentas. El backend construye dicts ad-hoc, así que estos
 * tipos se mantienen a mano (espejo del contrato acordado con el backend).
 */
import type { CanalPublicacion } from "./publicaciones";

/** Plataformas de red social posibles que devuelve el dashboard. */
export type PlataformaRed =
  | "facebook"
  | "instagram"
  | "tiktok"
  | "linkedin"
  | "youtube"
  | "twitter"
  | "threads"
  | "pinterest"
  | "bluesky"
  | "telegram"
  | "google_business";

/** Estado de conexión de una red en Postproxy. */
export type EstadoRed = "active" | "expired" | "inactive";

/** Una red de una marca con su estado de conexión. */
export interface RedMarca {
  plataforma: string;
  conectado: boolean;
  estado: EstadoRed | null;
  perfil_id: string | null;
  nombre_cuenta: string | null;
  post_count: number | null;
}

/** Estado de Metricool de una marca (solo conexión, sin secretos). */
export interface MetricoolMarca {
  conectado: boolean;
}

/** Estado de Postproxy de una marca. */
export interface PostproxyMarca {
  conectado: boolean;
  profile_group_id: string | null;
}

/** Una marca con su estado de conexiones y sus redes. */
export interface MarcaDashboard {
  marca: string;
  etiqueta: string;
  metricool: MetricoolMarca;
  postproxy: PostproxyMarca;
  /** Canal por el que la marca publica sus piezas. */
  canal_publicacion: CanalPublicacion;
  redes: RedMarca[];
}

/** Totales globales del dashboard (control de conexiones). */
export interface TotalesMarcas {
  marcas: number;
  redes_conectadas: number;
  cuentas: number;
}

/** Respuesta de `GET /api/marcas`. */
export interface RespuestaMarcas {
  generado_en: string;
  totales: TotalesMarcas;
  marcas: MarcaDashboard[];
}
