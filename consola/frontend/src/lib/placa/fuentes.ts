/**
 * Carga en el NAVEGADOR las fuentes embebidas (SIL OFL) que usa el render de la placa, con la
 * API `FontFace`, usando los MISMOS nombres de familia que `ctx.font` espera (los del catálogo
 * de `render_node/fuentes.mjs`). Sin esto, `measureText`/`fillText` usarían un fallback y el
 * ajuste de líneas no cuadraría con el servidor. Se cargan SOLO las familias que pide el spec.
 *
 * Los TTF se sirven desde `public/fonts/` (espejo de `motores/estudio_imagen/fuentes/`).
 */

interface ArchivoFuente {
  familia: string;
  archivo: string;
  /** Peso CSS de la cara (todas son estáticas: un TTF por peso). */
  peso: string;
  /** Estilo CSS: "italic" para las caras itálicas (ausente = normal). */
  estilo?: "italic";
}

// Familia real -> archivos por peso (espejo de `ARCHIVOS` en fuentes.mjs). TODAS las caras son
// ESTÁTICAS: Skia (el export) NO instancia el eje `wght` de un TTF variable —lo registra como una
// sola cara—, así que el servidor solo puede pintar pesos con TTF propio y aquí registramos
// EXACTAMENTE los mismos (un peso sin cara cae al vecino más cercano en ambos lados). Las caras
// *Italic* se registran con `style: italic` bajo la MISMA familia: así `ctx.font = "italic …"`
// usa la itálica REAL, igual que Skia en el servidor (que no sintetiza oblicuas).
// Montserrat trae 300..900: Light y los titulares ExtraBold/Black estilo Gotham de Claro Sports.
const ARCHIVOS: ArchivoFuente[] = [
  { familia: "Barlow", archivo: "Barlow-Regular.ttf", peso: "400" },
  { familia: "Barlow", archivo: "Barlow-SemiBold.ttf", peso: "600" },
  { familia: "Barlow", archivo: "Barlow-Bold.ttf", peso: "700" },
  { familia: "Barlow", archivo: "Barlow-Italic.ttf", peso: "400", estilo: "italic" },
  { familia: "Barlow", archivo: "Barlow-SemiBoldItalic.ttf", peso: "600", estilo: "italic" },
  { familia: "Barlow", archivo: "Barlow-BoldItalic.ttf", peso: "700", estilo: "italic" },
  { familia: "Barlow Condensed", archivo: "BarlowCondensed-SemiBold.ttf", peso: "600" },
  { familia: "Barlow Condensed", archivo: "BarlowCondensed-Bold.ttf", peso: "700" },
  { familia: "Barlow Condensed", archivo: "BarlowCondensed-ExtraBold.ttf", peso: "800" },
  { familia: "Barlow Condensed", archivo: "BarlowCondensed-SemiBoldItalic.ttf", peso: "600", estilo: "italic" },
  { familia: "Barlow Condensed", archivo: "BarlowCondensed-BoldItalic.ttf", peso: "700", estilo: "italic" },
  { familia: "Barlow Condensed", archivo: "BarlowCondensed-ExtraBoldItalic.ttf", peso: "800", estilo: "italic" },
  { familia: "Anton", archivo: "Anton-Regular.ttf", peso: "400" },
  { familia: "Archivo Black", archivo: "ArchivoBlack-Regular.ttf", peso: "400" },
  { familia: "Oswald", archivo: "Oswald-Regular.ttf", peso: "400" },
  { familia: "Oswald", archivo: "Oswald-SemiBold.ttf", peso: "600" },
  { familia: "Oswald", archivo: "Oswald-Bold.ttf", peso: "700" },
  { familia: "Montserrat", archivo: "Montserrat-Light.ttf", peso: "300" },
  { familia: "Montserrat", archivo: "Montserrat-Regular.ttf", peso: "400" },
  { familia: "Montserrat", archivo: "Montserrat-Medium.ttf", peso: "500" },
  { familia: "Montserrat", archivo: "Montserrat-SemiBold.ttf", peso: "600" },
  { familia: "Montserrat", archivo: "Montserrat-Bold.ttf", peso: "700" },
  { familia: "Montserrat", archivo: "Montserrat-ExtraBold.ttf", peso: "800" },
  { familia: "Montserrat", archivo: "Montserrat-Black.ttf", peso: "900" },
  { familia: "Montserrat", archivo: "Montserrat-LightItalic.ttf", peso: "300", estilo: "italic" },
  { familia: "Montserrat", archivo: "Montserrat-Italic.ttf", peso: "400", estilo: "italic" },
  { familia: "Montserrat", archivo: "Montserrat-MediumItalic.ttf", peso: "500", estilo: "italic" },
  { familia: "Montserrat", archivo: "Montserrat-SemiBoldItalic.ttf", peso: "600", estilo: "italic" },
  { familia: "Montserrat", archivo: "Montserrat-BoldItalic.ttf", peso: "700", estilo: "italic" },
  { familia: "Montserrat", archivo: "Montserrat-ExtraBoldItalic.ttf", peso: "800", estilo: "italic" },
  { familia: "Montserrat", archivo: "Montserrat-BlackItalic.ttf", peso: "900", estilo: "italic" },
  { familia: "Lora", archivo: "Lora-Regular.ttf", peso: "400" },
  { familia: "Lora", archivo: "Lora-Bold.ttf", peso: "700" },
  { familia: "Lora", archivo: "Lora-Italic.ttf", peso: "400", estilo: "italic" },
  { familia: "Lora", archivo: "Lora-BoldItalic.ttf", peso: "700", estilo: "italic" },
  { familia: "Exo 2", archivo: "Exo2-Regular.ttf", peso: "400" },
  { familia: "Exo 2", archivo: "Exo2-SemiBold.ttf", peso: "600" },
  { familia: "Exo 2", archivo: "Exo2-Bold.ttf", peso: "700" },
  { familia: "Exo 2", archivo: "Exo2-ExtraBold.ttf", peso: "800" },
  { familia: "Exo 2", archivo: "Exo2-Italic.ttf", peso: "400", estilo: "italic" },
  { familia: "Exo 2", archivo: "Exo2-SemiBoldItalic.ttf", peso: "600", estilo: "italic" },
  { familia: "Exo 2", archivo: "Exo2-BoldItalic.ttf", peso: "700", estilo: "italic" },
  { familia: "Exo 2", archivo: "Exo2-ExtraBoldItalic.ttf", peso: "800", estilo: "italic" },
  { familia: "Lato", archivo: "Lato-Regular.ttf", peso: "400" },
  { familia: "Lato", archivo: "Lato-Bold.ttf", peso: "700" },
  { familia: "Lato", archivo: "Lato-Black.ttf", peso: "900" },
  { familia: "Lato", archivo: "Lato-Italic.ttf", peso: "400", estilo: "italic" },
  { familia: "Lato", archivo: "Lato-BoldItalic.ttf", peso: "700", estilo: "italic" },
  { familia: "Lato", archivo: "Lato-BlackItalic.ttf", peso: "900", estilo: "italic" },
];

// Una sola promesa por familia: no recargamos en cada render.
const cargadas = new Map<string, Promise<void>>();

function cargarFamilia(familia: string): Promise<void> {
  const existente = cargadas.get(familia);
  if (existente) return existente;
  const promesa = (async () => {
    if (typeof FontFace === "undefined" || !document.fonts) return; // entorno sin Font API
    const archivos = ARCHIVOS.filter((a) => a.familia === familia);
    await Promise.all(
      archivos.map(async (a) => {
        const cara = new FontFace(familia, `url(/fonts/${a.archivo})`, { weight: a.peso, style: a.estilo ?? "normal" });
        await cara.load();
        document.fonts.add(cara);
      }),
    );
  })();
  cargadas.set(familia, promesa);
  return promesa;
}

/**
 * Carga las familias indicadas (por defecto Barlow + Barlow Condensed) y resuelve cuando están
 * listas para usarse en el canvas. Tolerante: una familia que falle no rompe el render (el
 * navegador cae a un fallback para esa familia concreta).
 */
export async function cargarFuentesPlaca(
  familias: Iterable<string> = ["Barlow", "Barlow Condensed"],
): Promise<void> {
  const set = new Set(["Barlow", "Barlow Condensed", ...familias]);
  await Promise.allSettled([...set].map(cargarFamilia));
}
