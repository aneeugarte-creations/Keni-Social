/**
 * Lógica del constructor de enlaces UTM (sin UI ni dependencias de React).
 */

/** Parámetros UTM que admite el constructor. */
export interface CamposUtm {
  source: string;
  medium: string;
  campaign: string;
  term: string;
  content: string;
}

export const CAMPOS_UTM_VACIOS: CamposUtm = {
  source: "",
  medium: "",
  campaign: "",
  term: "",
  content: "",
};

/**
 * Construye la URL etiquetada. Devuelve cadena vacía si la URL base no es
 * válida. Conserva los parámetros que ya tuviera la URL y añade/sobreescribe
 * los UTM no vacíos (encodeados por `URLSearchParams`).
 */
export function construirUrlUtm(base: string, campos: CamposUtm): string {
  const limpia = base.trim();
  if (!limpia) return "";
  let url: URL;
  try {
    url = new URL(limpia);
  } catch {
    return "";
  }
  const pares: [string, string][] = [
    ["utm_source", campos.source],
    ["utm_medium", campos.medium],
    ["utm_campaign", campos.campaign],
    ["utm_term", campos.term],
    ["utm_content", campos.content],
  ];
  for (const [clave, valor] of pares) {
    const v = valor.trim();
    if (v) url.searchParams.set(clave, v);
  }
  return url.toString();
}
