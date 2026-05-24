/**
 * Contrato tipado de la API de la Consola Keni (`/api/*`).
 *
 * Estos tipos reflejan exactamente las respuestas y cuerpos documentados en el
 * contrato del backend. El frontend se construye contra estos tipos; la
 * integracion runtime contra el backend real se valida al combinar ramas.
 *
 * Todo el texto orientado al usuario (nombres, detalles, mensajes) llega ya en
 * espanol desde el backend.
 */

// --- Estado (autodiagnostico del sistema) ---

export type NivelEstado = "ok" | "aviso" | "error";

export interface ResultadoEstado {
  estado: NivelEstado;
  nombre: string;
  detalle: string;
  icono: string;
}

export interface RespuestaEstado {
  resultados: ResultadoEstado[];
  resumen: string;
  siguiente_paso: string;
}

// --- Configuracion ---

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

// --- Proyectos ---

export interface Proyecto {
  id: string;
  nombre: string;
  ruta: string;
  existe: boolean;
  tiene_claude_md: boolean;
  claude_md: string | null;
}

export interface RespuestaProyectos {
  proyectos: Proyecto[];
}

export interface CuerpoCrearProyecto {
  nombre: string;
  ruta: string;
}

export interface CuerpoGuardarClaudeMd {
  contenido: string;
}

// --- Carpetas ---

export interface PlantillaCarpeta {
  id: string;
  nombre: string;
}

export interface RespuestaCarpetas {
  raiz: string;
  plantillas: PlantillaCarpeta[];
}

export interface CuerpoCrearCarpeta {
  nombre: string;
  plantilla: string;
}

export interface RespuestaCrearCarpeta {
  mensaje: string;
  ruta: string;
}

// --- Skills (Generar copy) ---

export interface Skill {
  id: string;
  nombre: string;
  descripcion: string;
}

export interface GrupoSkills {
  etiqueta: string;
  experimental: boolean;
  skills: Skill[];
}

export interface RespuestaSkills {
  grupos: GrupoSkills[];
  marcas: MarcaDisponible[];
  skills_media: string[];
}

export interface CuerpoEjecutarSkill {
  skill: string;
  marca: string;
  texto: string;
}

export interface RespuestaEjecutarSkill {
  resultado: string;
  historial_id: string;
}

export interface EntradaHistorial {
  id: string;
  skill: string;
  skill_nombre: string;
  marca: string;
  marca_nombre: string;
  fecha: string;
  preview: string;
}

export interface RespuestaHistorial {
  historial: EntradaHistorial[];
}

export interface DetalleHistorial {
  id: string;
  skill: string;
  marca: string;
  fecha: string;
  resultado: string;
}

// --- Tareas ---

export type EstadoTarea = string;

export interface Tarea {
  id: string;
  proyecto: string;
  proyecto_nombre: string;
  titulo: string;
  detalle: string;
  estado: EstadoTarea;
  fecha: string;
}

export interface ProyectoTarea {
  id: string;
  nombre: string;
  existe: boolean;
}

export interface RespuestaTareas {
  tareas: Tarea[];
  proyectos: ProyectoTarea[];
}

export interface CuerpoCrearTarea {
  proyecto: string;
  titulo: string;
  detalle: string;
}

export interface RespuestaCrearTarea {
  tarea: Tarea;
}

export interface CuerpoActualizarTarea {
  estado: EstadoTarea;
}

// --- Metricas ---

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

export interface ReporteMetricas {
  rango: string;
  etiqueta_rango: string;
  marca: string;
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

export interface CompararMetricas {
  marca: string;
  rango_a: string;
  rango_b: string;
  etiqueta_a: string;
  etiqueta_b: string;
  total: {
    metricas: ComparativaMetrica[];
  };
  por_marca: ComparativaPorMarca[];
}

// --- Respuesta generica con mensaje ---

export interface RespuestaMensaje {
  mensaje: string;
}

/** Forma de error que devuelve el backend (uno u otro campo, en espanol). */
export interface ErrorApi {
  error?: string;
  mensaje?: string;
}
