/**
 * Badge EXPLÍCITO del formato de una pieza: "Foto" (icono cámara) o "Video" (icono vídeo).
 *
 * Regla del dueño: una pieza FOTO va a 3 redes (instagram, x, facebook); una VIDEO a las 5.
 * El flujo automático crea piezas FOTO, así que el humano debe ver de un vistazo "esto es un
 * post de foto (3 redes)". El badge lo hace explícito; el tooltip dice a cuántas redes va.
 */
import { Camera, Video } from "lucide-react";

import { Badge } from "@/components/ui/badge";

import { etiquetaFormato, normalizarFormato, redesDeFormato } from "./formato";

/** Badge del formato de una pieza. `formato` crudo del backend (foto|video); "" -> foto. */
export function BadgeFormato({ formato, className }: { formato: string | null | undefined; className?: string }) {
  const tipo = normalizarFormato(formato);
  const Icono = tipo === "video" ? Video : Camera;
  return (
    <Badge
      variant="secondary"
      className={className}
      title={`Post de ${etiquetaFormato(formato).toLowerCase()} — ${redesDeFormato(formato)} redes`}
    >
      <Icono className="mr-1 h-3 w-3" aria-hidden="true" />
      {etiquetaFormato(formato)}
    </Badge>
  );
}
