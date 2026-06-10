// Puente PLANTILLAS DE DISEÑO ⇄ pista OVERLAY de video (paridad Canva: la MISMA plantilla
// sirve para imagen y para video).
//
// - `plantillaAOverlay`: deja el documento de una plantilla listo para el editor de overlay.
//   Reutiliza `adaptarDocumento` (la heurística de «Adaptar a…» del estudio de Imagen, NO se
//   duplica) para reencuadrarlo al formato del video si difiere; fuerza fondo TRANSPARENTE (el
//   video se ve debajo) y QUITA los huecos de foto (`es_foto`): en video el propio clip base hace
//   de «foto», así que esas capas sobran (taparían el video con el placeholder).
// - `overlayAPlantilla`: el camino inverso: convierte el documento del overlay en uno persistible
//   como PlantillaDiseno. El servidor exige un hueco de foto explícito (`documento_tiene_hueco`),
//   así que —si no lo hay— se añade uno OCULTO a sangre (mismo patrón que `documentoVacio`): al
//   abrir la plantilla en Imagen, el equipo lo muestra y coloca la foto donde en video iba el clip.

import { adaptarDocumento } from "@/editor/adaptar";
import { nuevaCapaImagen, type Capa, type Documento } from "@/editor/documento";

/** ¿La capa es un hueco de foto (la imagen que la plantilla reserva para la foto del post)? */
function esHueco(c: Capa): boolean {
  return c.tipo === "imagen" && !!c.es_foto;
}

/** Quita los huecos de foto, también dentro de grupos (recursivo). */
function sinHuecos(capas: Capa[]): Capa[] {
  return capas
    .filter((c) => !esHueco(c))
    .map((c) => (c.tipo === "grupo" ? { ...c, capas: sinHuecos(c.capas) } : c));
}

/**
 * Documento de una plantilla → documento de OVERLAY de video: adaptado al lienzo `w×h` del video
 * (mismo reencuadre 1-clic que «Adaptar a…»; idempotente si el formato coincide), con fondo
 * transparente y sin huecos de foto. No muta el original.
 */
export function plantillaAOverlay(
  plantilla: Documento,
  formato: { w: number; h: number },
  marca = "",
): Documento {
  // Mismo formato que construye el editor de overlay (`documentoOverlay`): sin zonas seguras.
  const destino = { w: formato.w, h: formato.h, safe_top: 0, safe_bottom: 0 };
  const adaptado = adaptarDocumento(plantilla, destino);
  return {
    ...adaptado,
    marca: marca || adaptado.marca,
    fondo: { tipo: "color", color: "#00000000" },
    capas: sinHuecos(adaptado.capas),
  };
}

/**
 * Documento del OVERLAY de video → documento persistible como PlantillaDiseno: clona el documento
 * y, si no declara hueco de foto, añade uno oculto y bloqueado a sangre (debajo de todo), que es
 * lo que exige el servidor al guardar plantillas. No muta el original.
 */
export function overlayAPlantilla(overlay: Documento, marca = ""): Documento {
  const doc = structuredClone(overlay);
  if (marca) doc.marca = marca;
  // El servidor solo mira las capas de PRIMER nivel (`tiene_hueco_explicito`).
  if (!doc.capas.some(esHueco)) {
    const zMin = doc.capas.reduce((m, c) => Math.min(m, c.z), 0);
    doc.capas.unshift(
      nuevaCapaImagen("", {
        x: 0,
        y: 0,
        w: doc.formato.w,
        h: doc.formato.h,
        z: zMin - 1,
        es_foto: true,
        bloqueada: true,
        visible: false,
        nombre: "Foto",
      }),
    );
  }
  return doc;
}
