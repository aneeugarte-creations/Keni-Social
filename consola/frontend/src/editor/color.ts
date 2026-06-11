// Utilidades de COLOR del editor (sin dependencias): conversiones hex/RGB/HSV para el selector
// de espectro del ColorControl y la paleta de colores sólidos predeterminados (patrón Canva).
//
// Convención de hex en todo el editor: `#RRGGBB` (opaco) o `#RRGGBBAA` (con alfa), en MAYÚSCULAS.
// Aquí solo se manejan los 6 dígitos RGB; el alfa lo gestiona ColorControl por separado.

export interface Rgb {
  r: number; // 0..255
  g: number;
  b: number;
}

export interface Hsv {
  h: number; // tono 0..360
  s: number; // saturación 0..1
  v: number; // brillo (value) 0..1
}

// `#RRGGBB` (o `#RRGGBBAA`; el alfa se ignora) -> RGB 0..255. `null` si no es un hex válido.
export function hexARgb(hex: string): Rgb | null {
  const m = /^#([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$/.exec(hex);
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

export function rgbAHex({ r, g, b }: Rgb): string {
  const canal = (v: number) =>
    Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0");
  return `#${canal(r)}${canal(g)}${canal(b)}`.toUpperCase();
}

export function rgbAHsv({ r, g, b }: Rgb): Hsv {
  const rf = r / 255;
  const gf = g / 255;
  const bf = b / 255;
  const max = Math.max(rf, gf, bf);
  const min = Math.min(rf, gf, bf);
  const d = max - min;
  let h = 0;
  if (d !== 0) {
    if (max === rf) h = 60 * (((gf - bf) / d) % 6);
    else if (max === gf) h = 60 * ((bf - rf) / d + 2);
    else h = 60 * ((rf - gf) / d + 4);
  }
  if (h < 0) h += 360;
  return { h, s: max === 0 ? 0 : d / max, v: max };
}

export function hsvARgb({ h, s, v }: Hsv): Rgb {
  const c = v * s;
  const hp = (((h % 360) + 360) % 360) / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  let rf = 0;
  let gf = 0;
  let bf = 0;
  if (hp < 1) [rf, gf, bf] = [c, x, 0];
  else if (hp < 2) [rf, gf, bf] = [x, c, 0];
  else if (hp < 3) [rf, gf, bf] = [0, c, x];
  else if (hp < 4) [rf, gf, bf] = [0, x, c];
  else if (hp < 5) [rf, gf, bf] = [x, 0, c];
  else [rf, gf, bf] = [c, 0, x];
  const m = v - c;
  const canal = (f: number) => Math.round((f + m) * 255);
  return { r: canal(rf), g: canal(gf), b: canal(bf) };
}

// Normaliza lo TECLEADO en la entrada hexadecimal a `#RRGGBB`: admite con o sin `#`, mayúsculas o
// minúsculas y la forma corta de 3 dígitos (`fff` -> `#FFFFFF`). `null` si no es interpretable.
export function normalizaHex(entrada: string): string | null {
  let s = entrada.trim().replace(/^#/, "");
  if (/^[0-9a-fA-F]{3}$/.test(s)) s = s.split("").map((c) => c + c).join("");
  if (!/^[0-9a-fA-F]{6}$/.test(s)) return null;
  return `#${s}`.toUpperCase();
}

// Colores sólidos PREDETERMINADOS (la rejilla por defecto de Canva): una fila de grises de negro a
// blanco y tres filas de color (rojos/violetas, cianes/azules, verdes/naranjas). Complementan al
// espectro —que ya da cualquier color— con muestras de un clic.
export const COLORES_PREDETERMINADOS: string[] = [
  "#000000", "#545454", "#737373", "#A6A6A6", "#D9D9D9", "#FFFFFF",
  "#FF3131", "#FF5757", "#FF66C4", "#CB6CE6", "#8C52FF", "#5E17EB",
  "#0097B2", "#0CC0DF", "#5CE1E6", "#38B6FF", "#5271FF", "#004AAD",
  "#00BF63", "#7ED957", "#C1FF72", "#FFDE59", "#FFBD59", "#FF914D",
];
