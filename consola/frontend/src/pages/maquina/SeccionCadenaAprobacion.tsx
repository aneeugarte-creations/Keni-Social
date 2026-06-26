/**
 * «Cadena de aprobación» (sección del Contexto › Producción): ajusta cuántos OK ("likes") de
 * personas distintas necesita una pieza de la MARCA ACTIVA antes de programarse (cuatro ojos).
 *
 * Es un ajuste POR MARCA: la autoridad para cambiarlo es el admin de esa marca (o un superadmin);
 * el backend lo enforce (`PUT /api/marcas/catalogo/{id}` con `likes_aprobacion`). Solo aplica a una
 * marca concreta: en la vista agregada "Todas" (marcaActiva null) no se muestra.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { Campo } from "@/components/comunes/Campo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { api, mensajeError } from "@/lib/api";

export function SeccionCadenaAprobacion({ marcaActiva }: { marcaActiva: string | null }) {
  const qc = useQueryClient();
  const catalogo = useQuery({
    queryKey: ["marcas-catalogo"],
    queryFn: ({ signal }) => api.catalogoMarcas(signal),
    staleTime: 60_000,
  });
  const marca = React.useMemo(
    () => catalogo.data?.marcas.find((m) => m.id === marcaActiva) ?? null,
    [catalogo.data, marcaActiva],
  );
  const actual = marca?.likes_aprobacion ?? 2;
  const [likes, setLikes] = React.useState(actual);
  React.useEffect(() => setLikes(actual), [actual]);

  const guardar = useMutation({
    mutationFn: (n: number) => api.editarMarca(marcaActiva!, { likes_aprobacion: n }),
    onSuccess: () => {
      toast.success("Likes de aprobación actualizados.");
      void qc.invalidateQueries({ queryKey: ["marcas-catalogo"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Vista agregada "Todas": no hay una marca concreta cuyo umbral ajustar.
  if (marcaActiva === null) return null;

  return (
    <div className="mt-6">
      <hr className="mb-4 border-border/60" />
      <h3 className="mb-1 text-sm font-semibold">Cadena de aprobación</h3>
      <p className="mb-3 max-w-prose text-xs text-muted-foreground">
        Cuántos OK de personas distintas necesita una pieza de{" "}
        <span className="font-medium text-foreground">{marca?.etiqueta ?? marcaActiva}</span> antes
        de programarse (cuatro ojos). Por defecto 2.
      </p>
      <div className="flex items-end gap-2">
        <Campo etiqueta="Likes para aprobar" htmlFor="cadena-likes">
          <Input
            id="cadena-likes"
            type="number"
            min={1}
            className="w-24"
            value={likes}
            onChange={(e) => setLikes(Math.max(1, Math.floor(Number(e.target.value) || 1)))}
            disabled={guardar.isPending || catalogo.isPending}
          />
        </Campo>
        <Button
          onClick={() => guardar.mutate(likes)}
          disabled={guardar.isPending || catalogo.isPending || likes === actual}
        >
          {guardar.isPending ? <Spinner className="h-4 w-4" /> : null}
          Guardar
        </Button>
      </div>
    </div>
  );
}
