/**
 * PUBLICACIÓN de la Biblioteca: a pantalla completa (estilo Pull Request, vía
 * `VistaRevisarCambios`), muestra el diff entre lo que hay en producción y la versión a
 * publicar, exige una nota de cambio y, según el rol:
 *   - admin   → "Publicar cambios" (POST /texto/{id}/publicar).
 *   - no admin → "Solicitar publicación" (POST /texto/{id}/solicitar): queda en la
 *     bandeja de solicitudes para que un admin la apruebe o rechace.
 *
 * Mantiene el nombre y las props que consume `DetalleDocumento.tsx`; solo cambia el chrome
 * (modal estrecho → vista a pantalla completa).
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { VistaRevisarCambios } from "@/components/biblioteca/VistaRevisarCambios";
import { api, mensajeError } from "@/lib/api";
import { claveSolicitudes } from "@/hooks/use-biblioteca";

export interface DialogPublicarProps {
  docId: string;
  abierto: boolean;
  onCerrar: () => void;
  /** `true` => publica directo; `false` => solo puede solicitar. Ver `useEsAdmin`. */
  esAdmin: boolean;
  /** Cuerpo (markdown) de la versión EN PRODUCCIÓN ("" si nunca se publicó). */
  antes: string;
  /** Cuerpo (markdown) de la versión A PUBLICAR. */
  despues: string;
  /** SHA de la versión a publicar; omitido = la versión actual (HEAD). */
  sha?: string;
  /** Tras publicar o solicitar con éxito (además de cerrar y refrescar queries). */
  onHecho?: () => void;
}

export function DialogPublicar({
  docId,
  abierto,
  onCerrar,
  esAdmin,
  antes,
  despues,
  sha,
  onHecho,
}: DialogPublicarProps) {
  const qc = useQueryClient();

  const alExito = (mensaje: string) => {
    toast.success(mensaje);
    qc.invalidateQueries({ queryKey: ["texto"] });
    qc.invalidateQueries({ queryKey: claveSolicitudes("abierta") });
    onCerrar();
    onHecho?.();
  };

  const publicarMut = useMutation({
    mutationFn: (nota: string) => api.publicarTexto(docId, { sha, nota }),
    onSuccess: () => alExito("Versión publicada: ya sirve todas las generaciones."),
    onError: (e) => toast.error(mensajeError(e)),
  });
  const solicitarMut = useMutation({
    mutationFn: (nota: string) => api.solicitarPublicacionTexto(docId, { sha, nota }),
    onSuccess: () =>
      alExito("Solicitud enviada: un admin la revisará antes de publicar."),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const enviando = publicarMut.isPending || solicitarMut.isPending;

  return (
    <VistaRevisarCambios
      abierto={abierto}
      onCerrar={onCerrar}
      titulo={esAdmin ? "Revisar y publicar" : "Revisar y solicitar"}
      subtitulo={
        antes
          ? "Cambios desde lo publicado hasta tu borrador"
          : "Primera publicación de este documento"
      }
      antes={antes}
      despues={despues}
      modo="publicar"
      esAdmin={esAdmin}
      enviando={enviando}
      onEnviar={(nota) => (esAdmin ? publicarMut.mutate(nota) : solicitarMut.mutate(nota))}
    />
  );
}
