/**
 * Estado de CONFIGURACIÓN DE VISTA del dashboard de Métricas (capa de presentación).
 *
 * Contrato único que comparten el panel "Configurar vista", las tablas configurables y
 * las vistas guardadas:
 *   - `red`: red única en foco (`null` = todas las redes).
 *   - `secciones`: visibilidad por id de sección del dashboard (ausente = visible).
 *   - `columnas`: por tabla, el ORDEN de sus columnas y cuáles están OCULTAS.
 *
 * Persiste en `localStorage` para que la configuración sobreviva recargas. Las "vistas
 * guardadas" (backend) serializan/recuperan este mismo objeto vía `exportar()`/`aplicar()`,
 * así que esta es la fuente de verdad de la capa de presentación. El periodo viaja en la URL
 * (`?periodo=`) y la marca la manda el switch global: no viven aquí.
 */
import { create } from "zustand";

/** Configuración de una tabla: orden de columnas (por id) y columnas ocultas (por id). */
export interface ConfigColumnas {
  /** Ids de columna en el orden deseado. Las no listadas se añaden al final por su orden base. */
  orden: string[];
  /** Ids de columna ocultas. */
  ocultas: string[];
}

/** Objeto serializable de configuración de vista (lo que guarda/recupera una vista guardada). */
export interface VistaConfig {
  /** Red única en foco, o `null` = todas. Id de plataforma (instagram|youtube|facebook|tiktok|x). */
  red: string | null;
  /** Visibilidad por id de sección (true/false). Ausente = visible. */
  secciones: Record<string, boolean>;
  /** Configuración de columnas por id de tabla. */
  columnas: Record<string, ConfigColumnas>;
}

export const VISTA_POR_DEFECTO: VistaConfig = { red: null, secciones: {}, columnas: {} };

const CLAVE_LS = "keni-vista-metricas";

function leerLocal(): VistaConfig {
  try {
    const crudo = localStorage.getItem(CLAVE_LS);
    if (!crudo) return VISTA_POR_DEFECTO;
    const v = JSON.parse(crudo) as Partial<VistaConfig>;
    return {
      red: v.red ?? null,
      secciones: v.secciones ?? {},
      columnas: v.columnas ?? {},
    };
  } catch {
    return VISTA_POR_DEFECTO;
  }
}

function guardarLocal(v: VistaConfig): void {
  try {
    localStorage.setItem(CLAVE_LS, JSON.stringify(v));
  } catch {
    // localStorage puede fallar (modo privado, cuota): la config sigue en memoria.
  }
}

interface EstadoVista extends VistaConfig {
  /** Fija la red en foco (`null` = todas). */
  setRed: (red: string | null) => void;
  /** Muestra/oculta una sección por id. */
  setSeccionVisible: (id: string, visible: boolean) => void;
  /** ¿La sección `id` está visible? (ausente = visible). */
  seccionVisible: (id: string) => boolean;
  /** Sustituye la config de columnas de una tabla. */
  setColumnas: (tabla: string, cfg: ConfigColumnas) => void;
  /** Config de columnas efectiva de una tabla (con defaults si no hay nada guardado). */
  columnasDe: (tabla: string, idsPorDefecto: string[]) => ConfigColumnas;
  /** Vuelca la configuración serializable actual (para guardarla como vista). */
  exportar: () => VistaConfig;
  /** Aplica una configuración (p. ej. al cargar una vista guardada). */
  aplicar: (cfg: Partial<VistaConfig>) => void;
  /** Restaura la configuración por defecto (todo visible, orden base, todas las redes). */
  reset: () => void;
}

export const useVistaConfig = create<EstadoVista>((set, get) => {
  const inicial = leerLocal();
  const persistir = (parcial: Partial<VistaConfig>) => {
    set(parcial as Partial<EstadoVista>);
    const { red, secciones, columnas } = get();
    guardarLocal({ red, secciones, columnas });
  };
  return {
    ...inicial,
    setRed: (red) => persistir({ red }),
    setSeccionVisible: (id, visible) =>
      persistir({ secciones: { ...get().secciones, [id]: visible } }),
    seccionVisible: (id) => get().secciones[id] !== false,
    setColumnas: (tabla, cfg) =>
      persistir({ columnas: { ...get().columnas, [tabla]: cfg } }),
    columnasDe: (tabla, idsPorDefecto) => {
      const cfg = get().columnas[tabla];
      if (!cfg) return { orden: idsPorDefecto, ocultas: [] };
      return cfg;
    },
    exportar: () => {
      const { red, secciones, columnas } = get();
      return { red, secciones, columnas };
    },
    aplicar: (cfg) =>
      persistir({
        red: cfg.red ?? null,
        secciones: cfg.secciones ?? {},
        columnas: cfg.columnas ?? {},
      }),
    reset: () => persistir({ ...VISTA_POR_DEFECTO }),
  };
});

/**
 * Orden EFECTIVO de columnas visibles de una tabla: aplica `orden` (las no listadas van al
 * final por su orden base) y descarta las `ocultas`. `todas` es la lista base de ids.
 */
export function columnasVisibles(todas: string[], cfg: ConfigColumnas): string[] {
  const enOrden = [
    ...cfg.orden.filter((id) => todas.includes(id)),
    ...todas.filter((id) => !cfg.orden.includes(id)),
  ];
  return enOrden.filter((id) => !cfg.ocultas.includes(id));
}
