// Elementos con atajo de creación estilo Canva (T texto, R rectángulo, C círculo/elipse, L línea).
// ÚNICA fuente de los defaults, compartida por el panel «Elementos» y los atajos del lienzo
// (`useAtajosTeclado`): el atajo crea EXACTAMENTE la misma capa que el botón del panel.

import type { Capa, CapaMarco, CapaTexto } from "./documento";
import { nuevaCapaMarco, nuevaCapaTexto } from "./documento";

export type ElementoRapido = "texto" | "rect" | "elipse" | "linea";

// T — caja de texto. Es el preset «Cuerpo» del panel: el equivalente del cuadro de texto sencillo
// que crea la T de Canva (los demás presets de texto del panel son variantes editoriales).
export function crearTextoCuerpo(): CapaTexto {
  return nuevaCapaTexto({ w: 760, texto: "Texto de cuerpo", tamano: 40, peso: 400 });
}

// R — rectángulo relleno (preset «Rectángulo» del panel).
export function crearRectangulo(): CapaMarco {
  return nuevaCapaMarco({ w: 360, h: 240, forma: "rect", relleno: "#E30613", borde: null });
}

// C — círculo/elipse (preset «Elipse» del panel; 320×320 = círculo).
export function crearElipse(): CapaMarco {
  return nuevaCapaMarco({ w: 320, h: 320, forma: "elipse", relleno: "#E30613", borde: null });
}

// L — línea recta (preset «Línea» del panel; trazo sin relleno, h = 0).
export function crearLinea(): CapaMarco {
  return nuevaCapaMarco({ w: 480, h: 0, forma: "linea", relleno: null, borde: { color: "#FFFFFF", grosor: 8 } });
}

export function crearElemento(tipo: ElementoRapido): Capa {
  switch (tipo) {
    case "texto":
      return crearTextoCuerpo();
    case "rect":
      return crearRectangulo();
    case "elipse":
      return crearElipse();
    case "linea":
      return crearLinea();
  }
}
