import { ArrowRight, Send } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AgenteDetalle } from "@/types";

/**
 * Pestaña «Contenido»: enlace a las publicaciones de esta marca. El agente `id`
 * es el id canónico de la marca, así que enlazamos a `/publicaciones?marca={id}`
 * (la página de Publicaciones preselecciona esa marca).
 */
export function PestanaContenido({
  agente,
  nPublicaciones,
}: {
  agente: AgenteDetalle;
  /** Conteo mostrado en la tarjeta (del listado de agentes). */
  nPublicaciones: number;
}) {
  const enlace = `/publicaciones?marca=${encodeURIComponent(agente.id)}`;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Send className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          Publicaciones de {agente.nombre}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col items-start gap-4 pt-0">
        <p className="text-sm text-muted-foreground">
          Este agente tiene{" "}
          <span className="font-medium text-foreground">{nPublicaciones}</span>{" "}
          {nPublicaciones === 1 ? "publicación" : "publicaciones"}. Gestiónalas (aprobar, programar,
          publicar) en la sección Publicaciones, ya filtrada por esta marca.
        </p>
        <Button asChild>
          <Link to={enlace}>
            Ver publicaciones
            <ArrowRight className="h-4 w-4" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
