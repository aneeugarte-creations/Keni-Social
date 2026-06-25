/**
 * Avatar redondo de una persona de la audiencia: la foto si la red la entrega y carga,
 * o la inicial del nombre sobre un fondo neutro como respaldo. Las URLs de avatar de
 * Instagram caducan, así que si la imagen falla se cae a la inicial (nunca el icono de
 * imagen rota). Solo lectura.
 */
import { useState } from "react";

import { cn } from "@/lib/utils";

function inicial(nombre: string | null | undefined): string {
  const t = (nombre ?? "").trim();
  return t ? t[0].toUpperCase() : "?";
}

export function AvatarPersona({
  nombre,
  avatar,
  className,
}: {
  nombre: string | null;
  avatar: string | null;
  className?: string;
}) {
  const [fallo, setFallo] = useState(false);
  const clases = cn(
    "flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-full bg-muted text-xs font-medium text-muted-foreground",
    className,
  );
  if (avatar && !fallo) {
    return (
      <img
        src={avatar}
        alt={nombre ?? "Avatar"}
        className={clases}
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFallo(true)}
      />
    );
  }
  return (
    <span className={clases} aria-hidden="true">
      {inicial(nombre)}
    </span>
  );
}
