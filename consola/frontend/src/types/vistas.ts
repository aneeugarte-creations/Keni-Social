// --- Vistas guardadas de Analíticas (presets nombrados) -----------------------
// Tipos a mano (como las rutas ad-hoc): el backend de vistas no está en el
// subconjunto estable generado, así que estos no salen de `types.gen`.

import type { VistaConfig } from "@/pages/metricas/vistaConfig";

/** Una vista guardada: preset nombrado que congela config + marca + periodo. */
export interface VistaGuardada {
  id: string;
  nombre: string;
  /** Marca objetivo (id canónico). '' = todas las marcas. */
  marca: string;
  /** Nombre legible de `marca`, o '' si la vista es de "todas". */
  marca_nombre: string;
  /** Periodo congelado (token de `?periodo=`: un preset del backend o `mes:`/`rango:`). */
  periodo: string;
  /** Configuración de presentación serializada (la recupera el store `vistaConfig`). */
  config: VistaConfig;
  /** Atribución: quién la creó (id estable / nombre). Vacío si se creó sin sesión. */
  autor_id: string;
  autor_nombre: string;
  fecha_creacion: string;
  fecha_actualizacion: string;
}

export interface RespuestaVistas {
  vistas: VistaGuardada[];
}

export interface RespuestaVista {
  vista: VistaGuardada;
}

/** Cuerpo para crear una vista. */
export interface CuerpoCrearVista {
  nombre: string;
  marca: string;
  periodo: string;
  config: VistaConfig;
}

/** Cuerpo para editar una vista (parcial). */
export interface CuerpoActualizarVista {
  nombre?: string;
  marca?: string;
  periodo?: string;
  config?: VistaConfig;
}
