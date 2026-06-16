/**
 * Tipos del dashboard «Marcas» (GET /api/marcas): vista única por marca × red. Por
 * marca, una fila de sumatorio y una fila por red con su estado de conexión y sus
 * números (de Postproxy). El backend construye dicts ad-hoc, así que estos tipos se
 * mantienen a mano (espejo del contrato). Metricool NO aparece (vive en Analíticas).
 */
import type { CanalPublicacion } from "./publicaciones";

/** Estado de conexión de una red en Postproxy. */
export type EstadoRed = "active" | "expired" | "inactive";

/** Trío de conteos (seguidores / posts / posts-día); null = sin dato (no es 0). */
export interface ConteoCuenta {
  seguidores: number | null;
  posts_totales: number | null;
  posts_dia: number | null;
}

/** Una red de una marca: su estado de conexión + sus números. */
export interface RedMarca extends ConteoCuenta {
  plataforma: string;
  conectado: boolean;
  estado: EstadoRed | null;
  perfil_id: string | null;
  nombre_cuenta: string | null;
}

/** Estado de Postproxy de una marca. */
export interface PostproxyMarca {
  conectado: boolean;
  profile_group_id: string | null;
}

/** Una marca con sus redes (estado + números) y su sumatorio. */
export interface MarcaDashboard {
  marca: string;
  etiqueta: string;
  /** Canal por el que la marca publica sus piezas. */
  canal_publicacion: CanalPublicacion;
  postproxy: PostproxyMarca;
  redes: RedMarca[];
  total: ConteoCuenta;
}

/** Respuesta de `GET /api/marcas`. */
export interface RespuestaMarcas {
  generado_en: string;
  totales: ConteoCuenta;
  marcas: MarcaDashboard[];
}
