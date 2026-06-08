// Tipos/props compartidos por los cuerpos del inspector (uno por tipo de capa).

import type { Capa } from "../documento";

// Props comunes que el inspector pasa a cada cuerpo específico de tipo. `set` aplica cambios a la
// capa seleccionada; `familias` es la lista de tipografías disponibles (catálogo + marca).
export interface PropsCuerpoCapa<C extends Capa = Capa> {
  capa: C;
  set: (cambios: Partial<Capa>) => void;
  familias: string[];
}
