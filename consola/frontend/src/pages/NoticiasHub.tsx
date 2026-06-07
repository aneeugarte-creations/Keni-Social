/**
 * NoticiasHub — pieza «Noticias» del hub Investigación e ÍNDICE del hub.
 *
 * Noticias = items informativos/temporales a publicar (agencias, RSS ajenos,
 * reporteros, corresponsales). Caducan. Su única superficie es el POOL persistente
 * del motor de ingesta (`Cobertura`): el flujo continuo de noticias, donde las
 * Historias ya vienen ordenadas por señal/breaking — eso ES el descubrimiento. El
 * antiguo "Descubrimiento" en vivo (Radar v1: Google Trends + plan del día) se
 * retiró; el pool persistente es la única fuente de verdad de la ingesta.
 *
 * El Termómetro (galería internacional) se arma desde el botón de receta.
 */
import { Images } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

import Cobertura from "./Cobertura";

export default function NoticiasHub() {
  return (
    <div className="space-y-4">
      {/* Receta de Noticias: armar la galería internacional (el antiguo Termómetro,
          que dejó de ser pestaña al colapsar el hub a 3 piezas). */}
      <div className="flex items-center justify-end">
        <Button asChild variant="outline" size="sm">
          <Link to="/datos/investigacion/termometro">
            <Images className="mr-2 h-4 w-4" aria-hidden="true" />
            Armar galería internacional
          </Link>
        </Button>
      </div>
      <Cobertura />
    </div>
  );
}
