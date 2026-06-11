import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useTema } from "@/hooks/tema-contexto";

/** Selector de tema claro/oscuro. Preferencia personal e instantánea: vive ARRIBA DEL TODO y
 *  SIEMPRE visible (tarjeta compacta no colapsable, fuera de las pestañas), no enterrada entre
 *  la configuración del producto. El tema se guarda en este equipo. */
export function SeccionApariencia() {
  const { esOscuro, fijar } = useTema();

  const opciones: { id: "claro" | "oscuro"; etiqueta: string; icono: typeof Sun }[] = [
    { id: "claro", etiqueta: "Claro", icono: Sun },
    { id: "oscuro", etiqueta: "Oscuro", icono: Moon },
  ];

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
        <div className="min-w-0">
          <p className="text-sm font-medium">Apariencia</p>
          <p className="text-xs text-muted-foreground">
            Tema de la consola (guardado localmente).
          </p>
        </div>
        <div role="radiogroup" aria-label="Tema" className="flex shrink-0 flex-wrap gap-2">
          {opciones.map((opcion) => {
            const Icono = opcion.icono;
            const activa = opcion.id === "oscuro" ? esOscuro : !esOscuro;
            return (
              <Button
                key={opcion.id}
                type="button"
                role="radio"
                aria-checked={activa}
                variant={activa ? "default" : "outline"}
                onClick={() => fijar(opcion.id)}
              >
                <Icono className="h-4 w-4" />
                {opcion.etiqueta}
              </Button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
