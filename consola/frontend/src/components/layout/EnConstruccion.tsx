import { Construction } from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardContent } from "@/components/ui/card";

/**
 * Placeholder reutilizable para las paginas que aun no se implementan. Cada stub
 * lo renderiza con su propio titulo; otra agente reemplazara el contenido luego.
 */
export function EnConstruccion({
  titulo,
  descripcion,
}: {
  titulo: string;
  descripcion?: string;
}) {
  return (
    <>
      <PageHeader titulo={titulo} descripcion={descripcion} />
      <Card>
        <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Construction className="h-6 w-6" />
          </div>
          <p className="text-lg font-medium">🚧 En construcción</p>
          <p className="max-w-sm text-sm text-muted-foreground">
            Esta sección estará disponible pronto. Estamos trabajando en ella.
          </p>
        </CardContent>
      </Card>
    </>
  );
}
