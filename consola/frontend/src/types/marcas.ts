/**
 * Tipos del dashboard «Marcas» (GET /api/marcas): vista única por marca × red. Por
 * marca, una fila de sumatorio y una fila por red con su estado de conexión y sus
 * números (de Postproxy). El backend construye dicts ad-hoc, así que estos tipos se
 * mantienen a mano (espejo del contrato). Metricool NO aparece (vive en Analíticas).
 */
import type { CanalPieza } from "./piezas";

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
  /** id_metricas: clave de Postproxy/canal (red, conectar, canal). */
  marca: string;
  /** id canónico: clave del catálogo (editar/borrar la marca). */
  id: string;
  etiqueta: string;
  /** 'noticias' (pasa por investigación) o 'propio' (contenido propio, sin panel de Noticias). */
  tipo: TipoMarca;
  /** Nombre del panel de investigación de esta marca (p.ej. "Curiosidades"); "Noticias" por defecto. */
  etiqueta_investigacion: string;
  /** Nº de OK ("likes") de personas distintas que una pieza de esta marca necesita para aprobarse (def 2). */
  likes_aprobacion: number;
  /** Canal por el que la marca publica sus piezas. */
  canal_publicacion: CanalPieza;
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

// --- CRUD del catálogo de marcas (fuente única editable) ------------------- //

/** Naturaleza editorial de una marca: noticias (investigación) o contenido propio. */
export type TipoMarca = "noticias" | "propio";

/** Una marca del catálogo editable. */
export interface MarcaCatalogo {
  id: string;
  etiqueta: string;
  id_metricas: string;
  tipo: TipoMarca;
  /** Nombre del panel de investigación de esta marca (p.ej. "Curiosidades"); "Noticias" por defecto. */
  etiqueta_investigacion: string;
  /** Nº de OK ("likes") de personas distintas que una pieza de esta marca necesita para aprobarse (def 2). */
  likes_aprobacion: number;
}

export interface RespuestaCatalogoMarcas {
  marcas: MarcaCatalogo[];
}

export interface CuerpoCrearMarca {
  etiqueta: string;
  id?: string;
  id_metricas?: string;
  tipo?: TipoMarca;
  etiqueta_investigacion?: string;
  likes_aprobacion?: number;
}

export interface CuerpoEditarMarca {
  etiqueta?: string;
  id_metricas?: string;
  tipo?: TipoMarca;
  etiqueta_investigacion?: string;
  likes_aprobacion?: number;
}

export interface RespuestaMarcaCatalogo {
  marca: MarcaCatalogo;
  mensaje: string;
}
