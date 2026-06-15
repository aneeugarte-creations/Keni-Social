// "Vista con muestra": helpers de PRESENTACIÓN del editor (NO tocan el documento ni el export).
//
// Al diseñar una PLANTILLA el hueco de foto está vacío y los textos con `binding` muestran texto
// genérico, así que el equipo "diseña de memoria": no ve el recorte/encuadre/filtros/duotono sobre
// una foto real ni la longitud real de un titular. Este módulo provee:
//   · una FOTO de muestra EDITABLE: por defecto una superficie gris neutra (degradado lineal)
//     generada en cliente, pero el equipo puede subir/pegar una foto real para diseñar VIENDO el
//     recorte/encuadre/forma/filtros sobre ella. La elección se guarda en localStorage (solo
//     presentación; nunca entra al documento ni al export).
//   · un COPY de muestra EDITABLE (titular + pleca) para los bindings de texto, para ver saltos de
//     línea y el auto-encogido con un texto representativo (o el que el equipo prefiera).
//
// Foto y copy de muestra son INDEPENDIENTES (dos toggles distintos en la barra del editor) y
// EDITABLES. Persisten en localStorage; los cambios notifican a los suscriptores para que el lienzo
// se redibuje en vivo.

// ── Persistencia (localStorage) ──────────────────────────────────────────────────────────────────

const CLAVE_FOTO_SRC = "keni.editor.muestra.foto.src"; // dataURL/URL; "" => superficie gris por defecto
const CLAVE_TITULAR = "keni.editor.muestra.copy.titular";
const CLAVE_ETIQUETA = "keni.editor.muestra.copy.etiqueta";

// Valores por DEFECTO (los de siempre): titular largo para ver saltos de línea + pleca "EN VIVO".
export const TITULAR_MUESTRA_DEFECTO =
  "Tormenta histórica deja sin luz a miles de familias en el norte del país esta madrugada";
export const ETIQUETA_MUESTRA_DEFECTO = "EN VIVO";

function leer(clave: string, def: string): string {
  try {
    const v = localStorage.getItem(clave);
    return v == null ? def : v;
  } catch {
    return def;
  }
}
function guardar(clave: string, valor: string): void {
  try {
    localStorage.setItem(clave, valor);
  } catch {
    /* almacenamiento no disponible: la preferencia no se persiste, sin romper. */
  }
}

let _fotoSrc = leer(CLAVE_FOTO_SRC, "");
let _titular = leer(CLAVE_TITULAR, TITULAR_MUESTRA_DEFECTO);
let _etiqueta = leer(CLAVE_ETIQUETA, ETIQUETA_MUESTRA_DEFECTO);

// Pub/sub: el editor se suscribe para redibujar el lienzo cuando cambia la foto/copy de muestra.
const _subs = new Set<() => void>();
export function suscribirMuestra(cb: () => void): () => void {
  _subs.add(cb);
  return () => {
    _subs.delete(cb);
  };
}
function notificar(): void {
  for (const cb of _subs) {
    try {
      cb();
    } catch {
      /* un suscriptor roto no debe tumbar a los demás */
    }
  }
}

// ── Superficie gris de muestra (foto por defecto) ────────────────────────────────────────────────
//
// Degradado lineal a 45° (claro `#bababa` abajo-izquierda → oscuro `#363636` arriba-derecha), misma
// dirección/colores que el resto de superficies grises del editor. NO es una "foto" de ejemplo: es
// la superficie de trabajo NEUTRA sobre la que se diseña la plantilla cuando no hay foto real.
// Cuadrada (1280×1280) para que el `cover` de cualquier caja se vea nítido a cualquier formato.

const TAM_MUESTRA = 1280;

let _grisSrc: string | null = null;
function grisMuestraSrc(): string | null {
  if (_grisSrc) return _grisSrc;
  if (typeof document === "undefined") return null;
  const cv = document.createElement("canvas");
  cv.width = TAM_MUESTRA;
  cv.height = TAM_MUESTRA;
  const ctx = cv.getContext("2d");
  if (!ctx) return null;
  const W = TAM_MUESTRA;
  const H = TAM_MUESTRA;
  const g = ctx.createLinearGradient(0, H, W, 0);
  g.addColorStop(0, "#bababa");
  g.addColorStop(1, "#363636");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  try {
    _grisSrc = cv.toDataURL("image/png");
  } catch {
    return null;
  }
  return _grisSrc;
}

// `src` efectivo de la foto de muestra: el elegido por el equipo, o la superficie gris por defecto.
function srcEfectivo(): string | null {
  return _fotoSrc || grisMuestraSrc();
}

// ── Foto de muestra (imagen cargada, cacheada por src) ───────────────────────────────────────────

let _img: HTMLImageElement | null = null;
let _imgSrc: string | null = null; // qué `src` corresponde a `_img` (para invalidar al cambiar)
let _pendiente: Promise<HTMLImageElement> | null = null;

// Devuelve la foto de muestra YA cargada (o null si aún no lo está / no hay DOM). Dispara la carga la
// primera vez (y de nuevo si el src cambió). Cuando termina, llama a `alCargar` (para forzar un
// redibujo del lienzo). La imagen se cachea por src.
export function fotoMuestra(alCargar?: () => void): HTMLImageElement | null {
  if (typeof window === "undefined") return null;
  const src = srcEfectivo();
  if (!src) return null;
  if (_img && _imgSrc === src) return _img;
  // src nuevo (o aún sin cargar): invalida la cache y (re)carga.
  if (_imgSrc !== src) {
    _img = null;
    _imgSrc = src;
    _pendiente = null;
  }
  if (!_pendiente) {
    const objetivo = src;
    _pendiente = new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new window.Image();
      el.onload = () => {
        // Ignora si el src volvió a cambiar mientras cargaba (carrera).
        if (_imgSrc === objetivo) _img = el;
        resolve(el);
      };
      el.onerror = () => reject(new Error("carga-fallida"));
      el.src = objetivo;
    });
    _pendiente.catch(() => {
      _pendiente = null;
    });
  }
  if (alCargar) _pendiente.then(alCargar).catch(() => {});
  return _img;
}

// ── Getters/setters de la foto y el copy de muestra ──────────────────────────────────────────────

export function getFotoMuestraSrc(): string {
  return _fotoSrc;
}
// Fija la foto de muestra (dataURL o URL). "" => vuelve a la superficie gris por defecto.
export function setFotoMuestra(src: string): void {
  _fotoSrc = src;
  guardar(CLAVE_FOTO_SRC, src);
  // Invalida la imagen cacheada para forzar la recarga del nuevo src.
  _img = null;
  _imgSrc = null;
  _pendiente = null;
  _objetoExport = null; // la foto cambió: el objeto S3 horneado anterior ya no corresponde
  notificar();
}

// ── Objeto S3 de la foto de muestra para HORNEARLA en la descarga ────────────────────────────────
//
// El export es server-side y la foto de muestra vive como dataURL/URL en cliente. Para que la
// descarga sea WYSIWYG (incluya la foto que el equipo ve en el hueco), `ExportarDialogo` la sube al
// almacén una vez y CACHEA aquí su objeto, para no resubirla en cada descarga. Se invalida al
// cambiar la foto de muestra (`setFotoMuestra`). `null` = aún no subida (o sin foto real).

let _objetoExport: string | null = null;
export function getObjetoMuestraExport(): string | null {
  return _objetoExport;
}
export function setObjetoMuestraExport(objeto: string): void {
  _objetoExport = objeto;
}

export function getTitularMuestra(): string {
  return _titular;
}
export function setTitularMuestra(v: string): void {
  _titular = v;
  guardar(CLAVE_TITULAR, v);
  notificar();
}

export function getEtiquetaMuestra(): string {
  return _etiqueta;
}
export function setEtiquetaMuestra(v: string): void {
  _etiqueta = v;
  guardar(CLAVE_ETIQUETA, v);
  notificar();
}

// Texto de muestra para una capa de texto con binding, en modo "Vista con muestra (copy)". Devuelve
// null si el binding no es uno de los bindeables (el llamador usa entonces su texto normal).
export function copyMuestra(binding: "copy_in" | "etiqueta_default" | null | undefined): string | null {
  if (binding === "copy_in") return _titular;
  if (binding === "etiqueta_default") return _etiqueta;
  return null;
}
