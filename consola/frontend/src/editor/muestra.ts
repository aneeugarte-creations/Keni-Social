// "Vista con muestra": helpers de PRESENTACIÓN del editor (NO tocan el documento ni el export).
//
// Al diseñar una PLANTILLA el hueco de foto está vacío y los textos con `binding` muestran texto
// genérico, así que el equipo "diseña de memoria": no ve el recorte/encuadre/filtros/duotono sobre
// una foto real ni la longitud real de un titular. Este módulo provee:
//   · una FOTO DE MUESTRA sintética (degradado + formas + viñeta) generada en cliente y cacheada a
//     nivel de módulo, offline-safe (sin depender de assets remotos), para rellenar el hueco solo
//     visualmente en el lienzo.
//   · COPY DE MUESTRA representativo para los bindings de texto (titular largo, pleca tipo "EN
//     VIVO"), para ver saltos de línea y el auto-encogido.

// ── Foto de muestra sintética ──────────────────────────────────────────────────────────────────
//
// Generamos UNA imagen (canvas) razonablemente "fotográfica": un degradado diagonal con dos focos
// de luz, un horizonte tenue y una viñeta. Suficiente para apreciar el efecto de los filtros
// (brillo/contraste/saturación/desenfoque), el duotono (mapea por luminancia) y el encuadre
// (cover/contain/foco/zoom/crop/forma). Tamaño moderado (1280×1280) para que el cover de cualquier
// caja se vea nítido sin penalizar memoria.

const TAM_MUESTRA = 1280;

let _imgMuestra: HTMLImageElement | null = null;
let _pendiente: Promise<HTMLImageElement> | null = null;

// Dibuja la foto sintética en un canvas y devuelve su dataURL. Determinista (sin aleatoriedad), así
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

  // Cielo/fondo: degradado vertical de azul profundo a un tono cálido en el horizonte.
  const cielo = ctx.createLinearGradient(0, 0, 0, H);
  cielo.addColorStop(0, "#1b2a4a");
  cielo.addColorStop(0.55, "#2f4d7a");
  cielo.addColorStop(0.7, "#c98a5e");
  cielo.addColorStop(1, "#3a2a36");
  ctx.fillStyle = cielo;
  ctx.fillRect(0, 0, W, H);

  // Sol/foco de luz cálido (arriba-derecha): degradado radial que da relieve y satura.
  const sol = ctx.createRadialGradient(W * 0.72, H * 0.32, 0, W * 0.72, H * 0.32, W * 0.55);
  sol.addColorStop(0, "rgba(255,224,168,0.85)");
  sol.addColorStop(0.4, "rgba(255,196,120,0.35)");
  sol.addColorStop(1, "rgba(255,196,120,0)");
  ctx.fillStyle = sol;
  ctx.fillRect(0, 0, W, H);

  // "Terreno" inferior: una banda más oscura con un par de siluetas (colinas) para tener contraste
  // y formas reconocibles bajo los filtros.
  const horizonte = H * 0.66;
  ctx.fillStyle = "#243042";
  ctx.beginPath();
  ctx.moveTo(0, horizonte);
  ctx.quadraticCurveTo(W * 0.3, horizonte - H * 0.06, W * 0.55, horizonte + H * 0.02);
  ctx.quadraticCurveTo(W * 0.8, horizonte + H * 0.08, W, horizonte - H * 0.02);
  ctx.lineTo(W, H);
  ctx.lineTo(0, H);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = "rgba(20,26,38,0.85)";
  ctx.beginPath();
  ctx.moveTo(0, horizonte + H * 0.1);
  ctx.quadraticCurveTo(W * 0.45, horizonte + H * 0.02, W, horizonte + H * 0.14);
  ctx.lineTo(W, H);
  ctx.lineTo(0, H);
  ctx.closePath();
  ctx.fill();

  // Una figura/sujeto tenue (círculo difuminado) descentrada, para que el FOCO/zoom se note al
  // reencuadrar (mover el encuadre cambia qué parte del "sujeto" se ve).
  const sujeto = ctx.createRadialGradient(W * 0.4, H * 0.58, 0, W * 0.4, H * 0.58, W * 0.18);
  sujeto.addColorStop(0, "rgba(255,238,210,0.6)");
  sujeto.addColorStop(1, "rgba(255,238,210,0)");
  ctx.fillStyle = sujeto;
  ctx.fillRect(0, 0, W, H);

  // Viñeta: oscurece las esquinas, look fotográfico.
  const vineta = ctx.createRadialGradient(W / 2, H / 2, W * 0.3, W / 2, H / 2, W * 0.72);
  vineta.addColorStop(0, "rgba(0,0,0,0)");
  vineta.addColorStop(1, "rgba(0,0,0,0.55)");
  ctx.fillStyle = vineta;
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
