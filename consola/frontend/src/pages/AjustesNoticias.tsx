/**
 * AjustesNoticias — subpágina de la pieza «Noticias» (hub Investigación), abierta desde el
 * menú "⋮" de la barra superior. Pinta los ajustes del motor que llena y ordena el pool,
 * repartidos en secciones en lenguaje editorial (qué entra → orden → rendimiento → última
 * hora → producción automática) + un bloque técnico colapsado. Los ids de sección espejan
 * `ajustes_catalogo.GRUPOS_NOTICIAS` del backend. Solo admin; los cambios aplican en caliente.
 */
import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

import { SeccionesAjustes } from "@/pages/configuracion/SeccionFuncionalidad";

const GRUPOS_NOTICIAS = new Set([
  "noticias_entrada",
  "noticias_orden",
  "noticias_rendimiento",
  "noticias_breaking",
  "noticias_produccion",
  "noticias_produccion_marca",
  "noticias_tecnico",
]);

export default function AjustesNoticias() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="space-y-1">
        <Link
          to="/datos/investigacion"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-3 w-3" aria-hidden="true" />
          Volver a Noticias
        </Link>
        <h2 className="text-base font-semibold tracking-tight">Ajustes del motor de noticias</h2>
        <p className="text-xs text-muted-foreground">
          Controlan qué noticias entran al pool, en qué orden se muestran y cuáles disparan
          producción automática. Los cambios aplican al momento (hasta ~1 minuto).
        </p>
      </div>
      <SeccionesAjustes ids={GRUPOS_NOTICIAS} />
    </div>
  );
}
