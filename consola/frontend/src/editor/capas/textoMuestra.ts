// Texto que el lienzo Konva PINTA para una capa de texto (presentación; el dato sigue crudo).
// Vive separado de CapaNodo para poder testearlo sin montar Konva.

import type { CapaTexto } from "../documento";
import { copyMuestra } from "../muestra";

export function textoMuestra(c: CapaTexto, muestraCopy = false): string {
  // En "Vista con muestra (copy)" los bindings usan copy de ejemplo (titular largo, pleca "EN VIVO"
  // por defecto, o el que el equipo edite) para ver saltos de línea y auto-encogido — aunque la capa
  // ya tenga `texto`. Fuera de ese modo, comportamiento de hoy: respeta `texto` y cae a un
  // placeholder genérico si está vacío.
  const ejemplo = muestraCopy ? copyMuestra(c.binding) : null;
  const base = ejemplo
    ? ejemplo
    : c.binding === "copy_in"
      ? c.texto || "Titular de ejemplo"
      : c.binding === "etiqueta_default"
        ? c.texto || "PLECA"
        : c.texto;
  // MAYÚSCULAS en render (locale es), sin destruir lo escrito, + normalización ESPEJO del export
  // (`dibujarTexto` hace .trim() del total y `envolver` colapsa rachas de espacios POR PÁRRAFO,
  // preservando los \n internos y las líneas en blanco): así un salto/espacio inicial o un espacio
  // doble envuelven igual en la previa que en el PNG (sin línea fantasma ni cortes movidos).
  // Solo render: el dato sigue crudo y la edición inline (Lienzo) muestra el `texto` tal cual.
  const texto = c.mayusculas ? base.toLocaleUpperCase("es") : base;
  return texto
    .split("\n")
    .map((p) => p.split(/\s+/).filter(Boolean).join(" "))
    .join("\n")
    .trim();
}
