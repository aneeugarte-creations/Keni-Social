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
  /** Peso CSS (o rango para variables). */
  peso: string;
}

// Familia real -> archivos por peso (espejo de `ARCHIVOS` en fuentes.mjs). Las variables se
// registran con rango de peso (el navegador interpola por el eje).
const ARCHIVOS: ArchivoFuente[] = [
  { familia: "Barlow", archivo: "Barlow-Regular.ttf", peso: "400" },
  { familia: "Barlow", archivo: "Barlow-SemiBold.ttf", peso: "600" },
  { familia: "Barlow", archivo: "Barlow-Bold.ttf", peso: "700" },
  { familia: "Barlow Condensed", archivo: "BarlowCondensed-SemiBold.ttf", peso: "600" },
  { familia: "Barlow Condensed", archivo: "BarlowCondensed-Bold.ttf", peso: "700" },
  { familia: "Barlow Condensed", archivo: "BarlowCondensed-ExtraBold.ttf", peso: "800" },
  { familia: "Anton", archivo: "Anton-Regular.ttf", peso: "400" },
  { familia: "Archivo Black", archivo: "ArchivoBlack-Regular.ttf", peso: "400" },
  { familia: "Oswald", archivo: "Oswald-Variable.ttf", peso: "200 700" },
  { familia: "Montserrat", archivo: "Montserrat-Variable.ttf", peso: "100 900" },
  { familia: "Lora", archivo: "Lora-Variable.ttf", peso: "400 700" },
  { familia: "Exo 2", archivo: "Exo2-Variable.ttf", peso: "100 900" },
  { familia: "Lato", archivo: "Lato-Regular.ttf", peso: "400" },
  { familia: "Lato", archivo: "Lato-Bold.ttf", peso: "700" },
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
        const cara = new FontFace(familia, `url(/fonts/${a.archivo})`, { weight: a.peso });
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
