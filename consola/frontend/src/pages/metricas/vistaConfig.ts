/**
 * Estado de CONFIGURACIÓN DE VISTA del dashboard de Métricas (capa de presentación).
 *
 * Contrato único que comparten el panel "Configurar vista", las tablas configurables y
 * las vistas guardadas:
 *   - `red`: redes en foco (`null` = todas las redes).
 *   - `formato`: formatos en foco (`null` = todos). Depende de la red en el selector.
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
  /** Redes en foco como CSV de ids (`"instagram,youtube"`), o `null` = todas. Combinación libre. */
  red: string | null;
  /** Formatos en foco como CSV de ids canónicos (`"reel,carrusel"`), o `null` = todos. */
  formato: string | null;
  /** Visibilidad por id de sección (true/false). Ausente = visible. */
  secciones: Record<string, boolean>;
  /** Configuración de columnas por id de tabla. */
  columnas: Record<string, ConfigColumnas>;
}

export const VISTA_POR_DEFECTO: VistaConfig = {
  red: null,
  formato: null,
  secciones: {},
  columnas: {},
};

const CLAVE_LS = "keni-vista-metricas";

function leerLocal(): VistaConfig {
  try {
    const crudo = localStorage.getItem(CLAVE_LS);
    if (!crudo) return VISTA_POR_DEFECTO;
    const v = JSON.parse(crudo) as Partial<VistaConfig>;
    return {
      red: v.red ?? null,
      formato: v.formato ?? null,
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
  /** Fija UNA red en foco (`null` = todas). Conveniencia; ver `setRedes` para varias. */
  setRed: (red: string | null) => void;
  /** Fija el conjunto de redes en foco (combinación a antojo). Vacío = todas. */
  setRedes: (redes: string[]) => void;
  /** Añade/quita una red del conjunto en foco. */
  toggleRed: (id: string) => void;
  /** Redes en foco como lista (vacía = todas). */
  redesSeleccionadas: () => string[];
  /** Fija el conjunto de formatos en foco (canónicos). Vacío = todos. */
  setFormatos: (formatos: string[]) => void;
  /** Añade/quita un formato del conjunto en foco. */
  toggleFormato: (id: string) => void;
  /** Formatos en foco como lista (vacía = todos). */
  formatosSeleccionados: () => string[];
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
    const { red, formato, secciones, columnas } = get();
    guardarLocal({ red, formato, secciones, columnas });
  };
  return {
    ...inicial,
    // `red` se almacena como CSV de ids (`"instagram,youtube"`) o null = todas, para que
    // los sub-componentes (que leen `s.red` y lo pasan como `?red=`) y las vistas guardadas
    // sigan tratándolo como un string opaco; el backend separa el CSV.
    setRed: (red) => persistir({ red }),
    setRedes: (redes) => persistir({ red: redes.length ? redes.join(",") : null }),
    toggleRed: (id) => {
      const actuales = get().red ? get().red!.split(",").filter(Boolean) : [];
      const siguiente = actuales.includes(id)
        ? actuales.filter((r) => r !== id)
        : [...actuales, id];
      persistir({ red: siguiente.length ? siguiente.join(",") : null });
    },
    redesSeleccionadas: () => (get().red ? get().red!.split(",").filter(Boolean) : []),
    // `formato` se almacena como CSV de ids canónicos (`"reel,carrusel"`) o null = todos,
    // espejo de `red`: los sub-componentes lo leen y lo pasan como `?formato=`.
    setFormatos: (formatos) =>
      persistir({ formato: formatos.length ? formatos.join(",") : null }),
    toggleFormato: (id) => {
      const actuales = get().formato ? get().formato!.split(",").filter(Boolean) : [];
      const siguiente = actuales.includes(id)
        ? actuales.filter((f) => f !== id)
        : [...actuales, id];
      persistir({ formato: siguiente.length ? siguiente.join(",") : null });
    },
    formatosSeleccionados: () =>
      get().formato ? get().formato!.split(",").filter(Boolean) : [],
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
      const { red, formato, secciones, columnas } = get();
      return { red, formato, secciones, columnas };
    },
    aplicar: (cfg) =>
      persistir({
        red: cfg.red ?? null,
        formato: cfg.formato ?? null,
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
