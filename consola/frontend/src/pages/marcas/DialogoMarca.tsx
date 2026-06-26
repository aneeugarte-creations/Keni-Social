import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Campo } from "@/components/comunes/Campo";
import { confirmar } from "@/components/comunes/confirmar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import type { TipoMarca } from "@/types";

/** Una marca tal como la edita el formulario (catálogo). */
export interface MarcaEditable {
  id: string;
  etiqueta: string;
  /** id_metricas (en el dashboard es el campo `marca`). */
  id_metricas: string;
  /** 'noticias' (pasa por investigación) o 'propio' (contenido propio, sin panel de Noticias). */
  tipo: TipoMarca;
  /** Nombre del panel de investigación de esta marca (p.ej. "Curiosidades"); "Noticias" por defecto. */
  etiqueta_investigacion: string;
}

function invalidarMarcas(qc: ReturnType<typeof useQueryClient>) {
  // El dashboard de Marcas y el catálogo canónico que alimenta los selectores globales.
  void qc.invalidateQueries({ queryKey: ["marcas", "dashboard"] });
  void qc.invalidateQueries({ queryKey: ["marcas-catalogo"] });
}

/**
 * Diálogo de CREAR o EDITAR una marca del catálogo (la fuente única editable). Al crear,
 * `id` e `id_metricas` se derivan del nombre si se dejan vacíos. Al editar, el `id`
 * canónico es inmutable (referencia el contenido); solo cambian nombre e id_metricas, y
 * desde aquí mismo se puede BORRAR la marca (con una confirmación en línea).
 */
export function DialogoMarca({
  abierto,
  inicial,
  onCerrar,
}: {
  abierto: boolean;
  /** null = crear; con valor = editar esa marca. */
  inicial: MarcaEditable | null;
  onCerrar: () => void;
}) {
  const qc = useQueryClient();
  const { usuario } = useSesion();
  // La IDENTIDAD de la marca (crear/borrar/renombrar/id_metricas/tipo/panel) es config de app:
  // solo el superadmin. Un admin de la marca solo ajusta su umbral de likes de aprobación.
  const esSuperadmin = usuario?.es_superadmin === true;
  const esEditar = inicial !== null;
  const [etiqueta, setEtiqueta] = React.useState("");
  const [id, setId] = React.useState("");
  const [idMetricas, setIdMetricas] = React.useState("");
  const [tipo, setTipo] = React.useState<TipoMarca>("noticias");
  const [etiquetaInvestigacion, setEtiquetaInvestigacion] = React.useState("Noticias");
  // El error solo se muestra tras un intento de guardar (no mientras se escribe).
  const [intentado, setIntentado] = React.useState(false);

  React.useEffect(() => {
    if (abierto) {
      setEtiqueta(inicial?.etiqueta ?? "");
      setId(inicial?.id ?? "");
      setIdMetricas(inicial?.id_metricas ?? "");
      setTipo(inicial?.tipo ?? "noticias");
      setEtiquetaInvestigacion(inicial?.etiqueta_investigacion || "Noticias");
      setIntentado(false);
    }
  }, [abierto, inicial]);

  const crear = useMutation({
    mutationFn: () =>
      api.crearMarca({
        etiqueta,
        id: id.trim() || undefined,
        id_metricas: idMetricas.trim() || undefined,
        tipo,
        etiqueta_investigacion: etiquetaInvestigacion.trim() || "Noticias",
      }),
    onSuccess: (r) => {
      toast.success(r.mensaje || "Marca creada.");
      invalidarMarcas(qc);
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const editar = useMutation({
    mutationFn: () =>
      api.editarMarca(inicial!.id, {
        etiqueta,
        id_metricas: idMetricas.trim(),
        tipo,
        etiqueta_investigacion: etiquetaInvestigacion.trim() || "Noticias",
      }),
    onSuccess: (r) => {
      toast.success(r.mensaje || "Marca actualizada.");
      invalidarMarcas(qc);
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.borrarMarca(inicial!.id),
    onSuccess: (r) => {
      toast.success(r?.mensaje ?? "Marca eliminada.");
      invalidarMarcas(qc);
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const pedirBorrar = async () => {
    if (
      await confirmar({
        titulo: "Borrar marca",
        mensaje: `¿Borrar “${inicial?.etiqueta}”? Desaparece del catálogo y de los selectores. El contenido y las credenciales ya existentes no se borran (quedan inertes).`,
        destructivo: true,
        textoConfirmar: "Borrar",
      })
    )
      borrar.mutate();
  };

  const ocupado = crear.isPending || editar.isPending || borrar.isPending;
  const errNombre = etiqueta.trim() === "" ? "El nombre es obligatorio." : null;
  const hayErrores = Boolean(errNombre);

  const onGuardar = () => {
    setIntentado(true);
    if (hayErrores) return;
    if (esEditar) editar.mutate();
    else crear.mutate();
  };

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{esEditar ? "Editar marca" : "Añadir marca"}</DialogTitle>
          <DialogDescription>
            {esEditar
              ? "Cambia el nombre o el id de métricas. El id de la marca no se cambia."
              : "El id y el id de métricas se generan del nombre si los dejas vacíos."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Campo etiqueta="Nombre" htmlFor="marca-etiqueta" error={intentado ? errNombre : null}>
            <Input
              id="marca-etiqueta"
              value={etiqueta}
              onChange={(e) => setEtiqueta(e.target.value)}
              placeholder="Ej. Claro Sports"
              disabled={ocupado}
              aria-invalid={(intentado && Boolean(errNombre)) || undefined}
              autoFocus
            />
          </Campo>
          {esEditar ? (
            <Campo etiqueta="id">
              <Input value={inicial?.id ?? ""} disabled />
            </Campo>
          ) : (
            <Campo etiqueta="id (opcional)" htmlFor="marca-id">
              <Input
                id="marca-id"
                value={id}
                onChange={(e) => setId(e.target.value)}
                placeholder="se genera del nombre (claro-sports)"
                disabled={ocupado}
              />
            </Campo>
          )}
          <Campo
            etiqueta={<>id de métricas {esEditar ? "" : "(opcional)"}</>}
            htmlFor="marca-id-metricas"
          >
            <Input
              id="marca-id-metricas"
              value={idMetricas}
              onChange={(e) => setIdMetricas(e.target.value)}
              placeholder="se genera del id (claro_sports)"
              disabled={ocupado}
            />
          </Campo>
          <Campo
            etiqueta="Tipo"
            ayuda={
              tipo === "propio"
                ? "Contenido propio: se salta la cadena de investigación y no tiene panel de Noticias."
                : "Noticias: pasa por la investigación (recolección, clasificación, Mesa de Noticias)."
            }
          >
            <div className="flex gap-2">
              {(
                [
                  { id: "noticias", etiqueta: "Noticias" },
                  { id: "propio", etiqueta: "Contenido propio" },
                ] as const
              ).map((opt) => (
                <Button
                  key={opt.id}
                  type="button"
                  variant={tipo === opt.id ? "default" : "outline"}
                  className="flex-1"
                  onClick={() => setTipo(opt.id)}
                  disabled={ocupado}
                >
                  {opt.etiqueta}
                </Button>
              ))}
            </div>
          </Campo>
          {tipo === "noticias" && (
            <Campo
              etiqueta="Nombre del panel"
              htmlFor="marca-etiqueta-investigacion"
              ayuda="Cómo se llama su panel de investigación (p.ej. “Curiosidades”, “Novedades”). Por defecto “Noticias”."
            >
              <Input
                id="marca-etiqueta-investigacion"
                value={etiquetaInvestigacion}
                onChange={(e) => setEtiquetaInvestigacion(e.target.value)}
                placeholder="Noticias"
                disabled={ocupado}
              />
            </Campo>
          )}
        </div>

        {/* Pie: en edición, «Borrar marca» a la izquierda (la confirmación va por `confirmar()`). */}
        <div className="mt-2 flex items-center justify-between gap-2">
          <div>
            {esEditar && esSuperadmin && (
              <Button
                variant="ghost"
                className="text-destructive hover:text-destructive"
                onClick={() => void pedirBorrar()}
                disabled={ocupado}
              >
                <Trash2 className="h-4 w-4" /> Borrar marca
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onCerrar} disabled={ocupado}>
              Cancelar
            </Button>
            <Button onClick={onGuardar} disabled={ocupado}>
              {crear.isPending || editar.isPending ? <Spinner className="h-4 w-4" /> : null}
              {esEditar ? "Guardar" : "Crear"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
