/**
 * Utilidades de DESCARGA de medios para postear a mano (donde Metricool no llega, p. ej. X):
 * dispara la descarga de un blob/URL como archivo y ofrece copiar el copy del post al portapapeles.
 * Lo comparten el editor de placa (descarga el lienzo) y el de carrusel (descarga cada slide).
 */
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { cabecerasAuth } from "@/lib/api/_core";

/** Slug seguro para nombre de archivo (minúsculas, sin acentos ni símbolos); `fallback` si queda vacío. */
export function slugNombre(base: string | undefined, fallback = "publicacion"): string {
  const s = (base || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 50);
  return s || fallback;
}

/** Dispara la descarga de `blob` como archivo `nombreArchivo` (<a download> programático). */
export function descargarBlob(blob: Blob, nombreArchivo: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombreArchivo;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Extensión de archivo a partir del mime del blob (png/jpg/mp4…); `porDefecto` si no se reconoce. */
function extDeMime(mime: string, porDefecto: string): string {
  const t = (mime.split(";")[0] || "").trim().toLowerCase();
  const mapa: Record<string, string> = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
  };
  return mapa[t] || porDefecto;
}

/** Descarga la `url` (con auth) como `nombreSinExt.<ext>`, eligiendo la extensión por el mime. */
export async function descargarUrlConAuth(
  url: string,
  nombreSinExt: string,
  extPorDefecto = "png",
): Promise<void> {
  const res = await fetch(url, { headers: cabecerasAuth() });
  if (!res.ok) throw new Error("No se pudo descargar el medio.");
  const blob = await res.blob();
  descargarBlob(blob, `${nombreSinExt}.${extDeMime(blob.type, extPorDefecto)}`);
}

/** Ofrece (pop-up) copiar el `copy` del post al portapapeles; no hace nada si está vacío o se rechaza. */
export async function ofrecerCopiarCopy(copy: string | undefined): Promise<void> {
  const texto = (copy || "").trim();
  if (!texto) return;
  const copiar = await confirmar({
    titulo: "¿Copiar el copy al portapapeles?",
    mensaje: "Pega el texto del post junto a la imagen donde vayas a publicar.",
    textoConfirmar: "Copiar copy",
    textoCancelar: "No, gracias",
  });
  if (!copiar) return;
  try {
    await navigator.clipboard.writeText(texto);
    toast.success("Copy copiado al portapapeles.");
  } catch {
    toast.error("No se pudo copiar el copy.");
  }
}
