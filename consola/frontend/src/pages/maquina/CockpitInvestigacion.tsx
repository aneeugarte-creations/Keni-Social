import { ListChecks, Search } from "lucide-react";
import { Link } from "react-router-dom";

import { TituloPagina } from "@/components/layout/encabezado";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Cockpit de INVESTIGACIÓN (`/maquina/investigacion`) — ESQUELETO (fase 2A).
 *
 * El cockpit real (el motor proactivo: descubre y verifica noticias) lo rellena la fase 2B.
 * De momento es un stub que enmarca la sección y enlaza a la Cola compartida prefiltrada al
 * loop de Investigación. El pool de noticias y su descubrimiento siguen vivos en el hub de
 * Investigación (`/datos/investigacion`) hasta que 2B los recoloque aquí.
 */
export default function CockpitInvestigacion() {
  return (
    <>
      <TituloPagina titulo="Investigación" icono={Search} />
      <Card className="border-dashed">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-sm text-muted-foreground">
            Cockpit de Investigación — en construcción (fase siguiente)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 p-4 pt-0 text-sm text-muted-foreground">
          <p>
            Aquí vivirá el motor de INVESTIGACIÓN (descubre y verifica noticias). Lo rellena la
            siguiente fase; el pool y el descubrimiento siguen, por ahora, en el hub de
            Investigación.
          </p>
          <p>
            La vista global del worker/cola está en{" "}
            <Link
              className="inline-flex items-center gap-1 font-medium text-foreground underline-offset-4 hover:underline"
              to="/maquina/cola?proceso=investigacion"
            >
              <ListChecks className="h-3.5 w-3.5" aria-hidden="true" />
              Cola (filtrada a Investigación)
            </Link>
            .
          </p>
        </CardContent>
      </Card>
    </>
  );
}
