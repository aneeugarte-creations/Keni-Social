/**
 * Reencuadre manual de la foto dentro del marco 4:5 (espejo de `dominio.estudio_imagen`).
 *
 * Modela el recorte que el humano elige sobre una foto que NO es 4:5: `foco` posiciona la imagen
 * (cover) dentro del marco como fracción [0,1]² (igual que `dibujarImagenEnCaja`: fx/fy), y `zoom`
 * la acerca (≥1). Se persiste por pieza como JSON en `foto_encuadre` ("" = sin reencuadre = encuadre
 * por defecto del path) y se aplica tanto en el canvas en vivo como en el render por plantilla.
 */
export interface EncuadreFoto {
  /** Posición de la foto dentro del marco (cover), por eje, en [0,1]. Centrado = [0.5, 0.5]. */
  foco: [number, number];
  /** Acercamiento dentro del marco (≥1). 1 = sin acercar. */
  zoom: number;
}

/** Encuadre por defecto: foto centrada, sin acercar. */
export const ENCUADRE_DEFECTO: EncuadreFoto = { foco: [0.5, 0.5], zoom: 1 };

/** Recorta un número a un rango. */
function pinza(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

/** Normaliza un encuadre a rangos válidos (foco en [0,1]², zoom en [1, 6]). */
export function normalizarEncuadre(e: EncuadreFoto): EncuadreFoto {
  return {
    foco: [pinza(e.foco[0], 0, 1), pinza(e.foco[1], 0, 1)],
    zoom: pinza(e.zoom || 1, 1, 6),
  };
}

/** ¿El encuadre es el por defecto (centrado, sin zoom)? Entonces NO hace falta persistirlo. */
export function esEncuadreDefecto(e: EncuadreFoto): boolean {
  return e.foco[0] === 0.5 && e.foco[1] === 0.5 && (e.zoom || 1) === 1;
}

/** Parsea el JSON persistido (`foto_encuadre`) a un encuadre, o null si está vacío/es inválido. */
export function parsearEncuadre(json: string | undefined | null): EncuadreFoto | null {
  if (!json || !json.trim()) return null;
  try {
    const datos = JSON.parse(json) as { foco?: unknown; zoom?: unknown };
    const foco = Array.isArray(datos.foco) && datos.foco.length === 2 ? datos.foco : null;
    if (!foco) return null;
    return normalizarEncuadre({
      foco: [Number(foco[0]) || 0.5, Number(foco[1]) || 0.5],
      zoom: Number(datos.zoom) || 1,
    });
  } catch {
    return null;
  }
}

/** Serializa un encuadre a JSON para persistir (`""` si es el por defecto: no ensucia la pieza). */
export function serializarEncuadre(e: EncuadreFoto | null): string {
  if (!e || esEncuadreDefecto(e)) return "";
  const n = normalizarEncuadre(e);
  return JSON.stringify({ foco: n.foco, zoom: n.zoom });
}
