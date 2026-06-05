/**
 * Historial de VERSIONES del copy de una fila por plataforma: ver snapshots, editar el copy
 * (cada guardado registra una versión) y revertir a uno anterior. Cuelga del id de la fila
 * `contenido_plataforma` (== `publicacion.id`).
 *
 * Reutilizable por el editor de publicaciones (`DialogoEditar`) y el tablero. Antes vivía en
 * `PanelColaboracion`; se extrajo al fusionar Tablero y Publicaciones (#fusion). Invalida las
 * dos superficies (`contenido` y `publicaciones`) para que ambas reflejen el copy nuevo.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Autor } from "@/components/comunes/Autor";
import { confirmar } from "@/components/comunes/confirmar";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, mensajeError } from "@/lib/api";
import { formatearFechaHoraCorta } from "@/lib/fecha";

// Fecha+hora en CDMX (el instante del backend es UTC).
const fecha = (iso: string): string => formatearFechaHoraCorta(iso);

export function Versiones({
  plataformaId,
  copyActual,
  redNombre,
}: {
  plataformaId: string;
  copyActual: string;
  redNombre: string;
}) {
  const queryClient = useQueryClient();
  const clave = ["copy-versiones", plataformaId] as const;
  const [borrador, setBorrador] = React.useState(copyActual);

  // Si cambia la pieza (o su copy desde fuera), resembramos el borrador local.
  React.useEffect(() => setBorrador(copyActual), [plataformaId, copyActual]);

  const query = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => api.copyVersiones(plataformaId, signal),
    enabled: !!plataformaId,
  });
  const tras = () => {
    void queryClient.invalidateQueries({ queryKey: clave });
    void queryClient.invalidateQueries({ queryKey: ["contenido"] });
    void queryClient.invalidateQueries({ queryKey: ["publicaciones"] });
  };

  const guardar = useMutation({
    mutationFn: () => api.guardarCopy(plataformaId, borrador),
    onSuccess: () => {
      toast.success("Copy guardado (versión registrada).");
      tras();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const revertir = useMutation({
    mutationFn: (versionId: string) => api.revertirCopy(plataformaId, versionId),
    onSuccess: (r) => {
      setBorrador(r.plataforma.copy);
      toast.success("Copy revertido.");
      tras();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const versiones = query.data?.versiones ?? [];

  return (
    <div className="space-y-3">
      <div className="space-y-2 rounded-md border p-2">
        <p className="text-xs font-medium text-muted-foreground">Copy actual ({redNombre})</p>
        <Textarea
          value={borrador}
          onChange={(e) => setBorrador(e.target.value)}
          rows={3}
          className="text-sm"
          placeholder="Escribe el copy…"
        />
        <div className="flex justify-end">
          <Button
            size="sm"
            disabled={guardar.isPending || borrador === copyActual}
            onClick={() => guardar.mutate()}
          >
            Guardar versión
          </Button>
        </div>
      </div>

      {versiones.length === 0 ? (
        <EstadoVacio titulo="Sin versiones previas" texto="Cada cambio de copy queda aquí." />
      ) : (
        <ul className="space-y-2">
          {versiones.map((v) => {
            const acciones: EntradaMenuContextual[] = [
              {
                etiqueta: "Revertir a esta",
                icono: RotateCcw,
                onClick: async () => {
                  if (
                    await confirmar({
                      mensaje: `¿Revertir el copy a la versión v${v.version}? El copy actual se registrará como una versión nueva.`,
                      destructivo: true,
                      textoConfirmar: "Revertir",
                    })
                  )
                    revertir.mutate(v.id);
                },
                deshabilitado: revertir.isPending,
              },
            ];
            return (
              <FilaConAcciones
                key={v.id}
                como="li"
                acciones={acciones}
                etiquetaAcciones={`Acciones de la versión v${v.version}`}
                kebab="hover"
                className="rounded-md border p-2 pr-10 text-sm"
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <Badge variant="secondary" className="font-normal">
                      v{v.version}
                    </Badge>
                    <Autor nombre={v.autor_nombre} className="text-xs" />
                  </span>
                  <span className="text-xs text-muted-foreground">{fecha(v.creado)}</span>
                </div>
                {v.nota && <p className="mb-1 text-xs italic text-muted-foreground">{v.nota}</p>}
                <p className="whitespace-pre-wrap break-words text-muted-foreground">
                  {v.copy || <span className="italic">(copy vacío)</span>}
                </p>
              </FilaConAcciones>
            );
          })}
        </ul>
      )}
    </div>
  );
}
