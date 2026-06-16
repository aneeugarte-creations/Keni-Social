/**
 * Vista "Todos los documentos" de la Biblioteca: tabla plana para GESTIÓN y búsqueda
 * (sustituye al antiguo finder de carpetas). Columnas útiles (título, tipo, clase,
 * carpeta, marcas, publicación, actualizado), filtros por tipo/etiqueta, filtro
 * "solo sin publicar" (enlazado desde el indicador del header) y papelera con
 * restauración. Mover/renombrar viven en la ficha del documento (panel de metadata).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FileText, RotateCcw, Trash2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, mensajeError } from "@/lib/api";
import { tiempoRelativo } from "@/lib/fecha";
import type { DocumentoTexto } from "@/types";

const TODOS = "__todos__";

/** Celda de publicación: ● producción / — , más ⚠ si hay cambios sin publicar. */
function CeldaPublicacion({ doc }: { doc: DocumentoTexto }) {
  return (
    <span className="flex items-center gap-1.5">
      {doc.produccion ? (
        <Badge variant="ok" className="rounded-full px-2 py-0 text-[11px]" title={`Producción ${doc.produccion.sha.slice(0, 8)}`}>
          ● prod
        </Badge>
      ) : (
        <span className="text-muted-foreground">—</span>
      )}
      {doc.sin_publicar ? (
        <Badge variant="aviso" className="gap-1 rounded-full px-2 py-0 text-[11px]">
          <AlertTriangle className="h-3 w-3" aria-hidden /> sin publicar
        </Badge>
      ) : null}
    </span>
  );
}

export function TablaDocumentos({
  documentos,
  cargando,
  soloSinPublicar,
  onCambioSinPublicar,
  onAbrir,
}: {
  /** Documentos ya filtrados por marca + búsqueda (los filtros finos van aquí). */
  documentos: DocumentoTexto[];
  cargando: boolean;
  /** Filtro "solo con cambios sin publicar" (lo activa el indicador del header). */
  soloSinPublicar: boolean;
  onCambioSinPublicar: (v: boolean) => void;
  onAbrir: (docId: string) => void;
}) {
  const qc = useQueryClient();
  const [tipo, setTipo] = React.useState(TODOS);
  const [etiqueta, setEtiqueta] = React.useState(TODOS);
  const [papeleraAbierta, setPapeleraAbierta] = React.useState(false);

  const etiquetas = React.useMemo(() => {
    const s = new Set<string>();
    for (const d of documentos) for (const e of d.etiquetas ?? []) s.add(e);
    return [...s].sort((a, b) => a.localeCompare(b, "es"));
  }, [documentos]);

  const visibles = React.useMemo(
    () =>
      documentos.filter(
        (d) =>
          (tipo === TODOS || d.tipo === tipo) &&
          (etiqueta === TODOS || (d.etiquetas ?? []).includes(etiqueta)) &&
          (!soloSinPublicar || d.sin_publicar),
      ),
    [documentos, tipo, etiqueta, soloSinPublicar],
  );

  // ── Papelera (listar + restaurar) y borrado desde la fila. ──
  const papeleraQuery = useQuery({
    queryKey: ["texto-papelera"],
    queryFn: ({ signal }) => api.papeleraTexto(signal),
    enabled: papeleraAbierta,
  });
  const restaurarMut = useMutation({
    mutationFn: (id: string) => api.restaurarDocumento(id),
    onSuccess: () => {
      toast.success("Documento restaurado.");
      qc.invalidateQueries({ queryKey: ["texto"] });
      qc.invalidateQueries({ queryKey: ["texto-papelera"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const eliminarMut = useMutation({
    mutationFn: (id: string) => api.eliminarDocumento(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["texto"] });
      qc.invalidateQueries({ queryKey: ["texto-papelera"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      {/* ── Filtros ── */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={tipo} onValueChange={setTipo}>
          <SelectTrigger className="h-8 w-32 text-xs" aria-label="Filtrar por tipo">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={TODOS}>Todo tipo</SelectItem>
            <SelectItem value="prompt">Prompts</SelectItem>
            <SelectItem value="editorial">Editoriales</SelectItem>
          </SelectContent>
        </Select>
        {etiquetas.length > 0 ? (
          <Select value={etiqueta} onValueChange={setEtiqueta}>
            <SelectTrigger className="h-8 w-36 text-xs" aria-label="Filtrar por etiqueta">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={TODOS}>Toda etiqueta</SelectItem>
              {etiquetas.map((e) => (
                <SelectItem key={e} value={e}>
                  {e}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}
        {soloSinPublicar ? (
          <button
            type="button"
            onClick={() => onCambioSinPublicar(false)}
            className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-700 hover:bg-amber-500/25 dark:text-amber-300"
            title="Quitar el filtro de cambios sin publicar"
          >
            <AlertTriangle className="h-3 w-3" aria-hidden /> solo sin publicar
            <X className="h-3 w-3" aria-hidden />
          </button>
        ) : null}
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto text-muted-foreground"
          onClick={() => setPapeleraAbierta(true)}
        >
          <Trash2 className="mr-1 h-3.5 w-3.5" /> Papelera
        </Button>
      </div>

      {/* ── Tabla ── */}
      {cargando ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : visibles.length === 0 ? (
        <EstadoVacio
          icono={FileText}
          titulo="Sin documentos"
          texto="No hay documentos con estos filtros."
        />
      ) : (
        <div className="min-h-0 flex-1 overflow-auto rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Título</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Clase</TableHead>
                <TableHead>Carpeta</TableHead>
                <TableHead>Marcas</TableHead>
                <TableHead>Publicación</TableHead>
                <TableHead>Actualizado</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visibles.map((d) => (
                <FilaConAcciones
                  key={d.id}
                  como="tr"
                  kebab="nunca"
                  onPrimaria={() => onAbrir(d.id)}
                  etiquetaAcciones={`Acciones de ${d.titulo}`}
                  acciones={[
                    { etiqueta: "Abrir", onClick: () => onAbrir(d.id) },
                    { separador: true },
                    {
                      etiqueta: "Mover a la papelera",
                      icono: Trash2,
                      destructivo: true,
                      onClick: () => {
                        void (async () => {
                          if (
                            await confirmar({
                              mensaje: `¿Mover «${d.titulo}» a la papelera?`,
                              destructivo: true,
                              textoConfirmar: "Mover",
                            })
                          )
                            eliminarMut.mutate(d.id);
                        })();
                      },
                    },
                  ]}
                >
                  <TableCell className="max-w-[18rem]">
                    <span className="block truncate text-sm font-medium">{d.titulo}</span>
                    {d.descripcion ? (
                      <span className="block truncate text-xs text-muted-foreground">
                        {d.descripcion}
                      </span>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{d.tipo}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{d.clase || "—"}</TableCell>
                  <TableCell className="max-w-[10rem] truncate text-xs text-muted-foreground">
                    {d.carpeta || "—"}
                  </TableCell>
                  <TableCell className="max-w-[10rem] truncate text-xs text-muted-foreground">
                    {(d.marcas ?? []).join(", ") || "—"}
                  </TableCell>
                  <TableCell>
                    <CeldaPublicacion doc={d} />
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {tiempoRelativo(d.actualizado) || d.actualizado?.slice(0, 10) || "—"}
                  </TableCell>
                </FilaConAcciones>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* ── Papelera ── */}
      <Dialog open={papeleraAbierta} onOpenChange={setPapeleraAbierta}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Trash2 className="h-4 w-4" /> Papelera
            </DialogTitle>
          </DialogHeader>
          {papeleraQuery.isPending ? (
            <Skeleton className="h-16 w-full" />
          ) : (papeleraQuery.data?.papelera ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">Vacía.</p>
          ) : (
            <ul className="max-h-72 divide-y divide-border overflow-y-auto rounded-md border border-border">
              {papeleraQuery.data?.papelera.map((p) => (
                <li key={p.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                  <span className="min-w-0 flex-1 truncate">{p.titulo}</span>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 text-xs"
                    disabled={restaurarMut.isPending}
                    onClick={() => restaurarMut.mutate(p.id)}
                  >
                    <RotateCcw className="mr-1 h-3 w-3" /> Restaurar
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
