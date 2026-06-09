// "Vista con muestra": helpers de PRESENTACIÓN del editor (NO tocan el documento ni el export).
//
// Al diseñar una PLANTILLA el hueco de foto está vacío y los textos con `binding` muestran texto
// genérico, así que el equipo "diseña de memoria": no ve el recorte/encuadre/filtros/duotono sobre
// una foto real ni la longitud real de un titular. Este módulo provee:
//   · una SUPERFICIE GRIS de muestra (degradado lineal neutro) generada en cliente y cacheada a
//     nivel de módulo, offline-safe (sin depender de assets remotos), para rellenar el hueco solo
//     visualmente en el lienzo. Es una superficie de trabajo NEUTRA (no una foto sintética de
//     colores): el equipo pidió diseñar sobre gris, no sobre una "foto" de ejemplo.
//   · COPY DE MUESTRA representativo para los bindings de texto (titular largo, pleca tipo "EN
//     VIVO"), para ver saltos de línea y el auto-encogido.

// ── Superficie gris de muestra ──────────────────────────────────────────────────────────────────
//
// Generamos UNA imagen gris neutra: un degradado lineal a 45° (claro `#bababa` en la esquina
// inferior-izquierda → oscuro `#363636` en la superior-derecha). Misma dirección/colores que el
// resto de superficies grises del editor. No es una "foto" de ejemplo: es la superficie de trabajo
// sobre la que se diseña la plantilla mientras el hueco está vacío. Tamaño cuadrado (1280×1280) para
// que el `cover` de cualquier caja se vea nítido; al recortar a cualquier formato (16:9, 4:5, 9:16)
// el degradado conserva su dirección.

const TAM_MUESTRA = 1280;

let _imgMuestra: HTMLImageElement | null = null;
let _pendiente: Promise<HTMLImageElement> | null = null;

// Dibuja la superficie gris en un canvas y devuelve su dataURL. Determinista (sin aleatoriedad), así
// la imagen es estable entre renders.
function pintarMuestra(): string | null {
  if (typeof document === "undefined") return null;
  const cv = document.createElement("canvas");
  cv.width = TAM_MUESTRA;
  cv.height = TAM_MUESTRA;
  const ctx = cv.getContext("2d");
  if (!ctx) return null;
  const W = TAM_MUESTRA;
  const H = TAM_MUESTRA;

  // Degradado lineal a 45°: claro (#bababa) en la esquina inferior-izquierda → oscuro (#363636) en
  // la superior-derecha. En un cuadrado es exactamente esquina-a-esquina (start=(0,H), end=(W,0)).
  const g = ctx.createLinearGradient(0, H, W, 0);
  g.addColorStop(0, "#bababa");
  g.addColorStop(1, "#363636");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);

  try {
    return cv.toDataURL("image/png");
  } catch {
    return null;
  }
}

// Devuelve la foto de muestra YA cargada (o null si aún no lo está / no hay DOM). Dispara la
// generación/carga la primera vez. Cuando termina, llama a `alCargar` (para forzar un redibujo del
// lienzo). La imagen se cachea a nivel de módulo: se genera una sola vez por sesión.
export function fotoMuestra(alCargar?: () => void): HTMLImageElement | null {
  if (_imgMuestra) return _imgMuestra;
  if (typeof window === "undefined") return null;
  if (!_pendiente) {
    _pendiente = new Promise<HTMLImageElement>((resolve, reject) => {
      const src = pintarMuestra();
      if (!src) {
        reject(new Error("sin-canvas"));
        return;
      }
      const el = new window.Image();
      el.onload = () => {
        _imgMuestra = el;
        resolve(el);
      };
      el.onerror = () => reject(new Error("carga-fallida"));
      el.src = src;
    });
    _pendiente.catch(() => {
      // generación fallida (entorno sin canvas): se queda sin muestra, sin romper.
      _pendiente = null;
    });
  }
  if (alCargar) _pendiente.then(alCargar).catch(() => {});
  return _imgMuestra;
}

// ── Copy de muestra ─────────────────────────────────────────────────────────────────────────────

// Titular de ejemplo MÁS BIEN LARGO: hace visibles los saltos de línea y el auto-encogido del
// titular dentro de su caja, que es justo lo que no se ve al diseñar "de memoria".
export const TITULAR_MUESTRA =
  "Tormenta histórica deja sin luz a miles de familias en el norte del país esta madrugada";

// Pleca/etiqueta de ejemplo (binding etiqueta_default): banda tipo "EN VIVO" / "ÚLTIMA HORA".
export const ETIQUETA_MUESTRA = "EN VIVO";

// Texto de muestra para una capa de texto con binding, en modo "Vista con muestra". Devuelve null
// si el binding no es uno de los bindeables (el llamador usa entonces su texto normal).
export function copyMuestra(binding: "copy_in" | "etiqueta_default" | null | undefined): string | null {
  if (binding === "copy_in") return TITULAR_MUESTRA;
  if (binding === "etiqueta_default") return ETIQUETA_MUESTRA;
  return null;
}
