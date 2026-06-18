import { Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { hexAlpha, iniciales, metaZona, nombreVisible } from "@/lib/organigrama";
import { type CargoUsuario, etiquetaCargo, type UsuarioAdmin } from "@/types";

/** Tarjeta-fila de una persona. Clic = abrir el panel de edición. */
export function TarjetaMiembro({
  usuario,
  zona,
  tieneReportes,
  esYoMismo,
  onAbrir,
}: {
  usuario: UsuarioAdmin;
  /** Zona (marca/transversal/dirección) de la persona: de aquí sale el color del avatar. */
  zona: string;
  /** Tiene personas a su cargo → muestra el icono de coordinación/dirección. */
  tieneReportes: boolean;
  esYoMismo: boolean;
  onAbrir: (id: string) => void;
}) {
  const marcas = usuario.marcas ?? [];
  const nombre = nombreVisible(usuario);
  const colorZona = metaZona(zona).color;

  return (
    <button
      type="button"
      onClick={() => onAbrir(usuario.id)}
      className="org-tarjeta flex w-full items-start gap-2.5 rounded-md border bg-card py-2 pl-2.5 pr-2 text-left shadow-sm transition-shadow transition-colors hover:shadow-md hover:border-keni-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      aria-label={`Editar a ${nombre}`}
    >
      {/* Avatar tintado con el color de la zona de la persona: es el único elemento
          con color de la fila (las insignias quedan neutras). */}
      <span
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
        style={{ color: colorZona, backgroundColor: hexAlpha(colorZona, 0.14) }}
        aria-hidden
      >
        {iniciales(nombre)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1 text-sm font-semibold leading-tight">
          {tieneReportes && (
            <Users
              className="h-3.5 w-3.5 shrink-0 text-muted-foreground"
              aria-label="Tiene personas a su cargo"
            />
          )}
          <span className="truncate">{nombre}</span>
          {esYoMismo && (
            <span className="text-xs font-normal text-muted-foreground">(tú)</span>
          )}
        </span>
        <span className="block truncate text-xs text-muted-foreground">
          {etiquetaCargo((usuario.cargo ?? "") as CargoUsuario)}
        </span>
      </span>

      {/* Insignias empaquetadas una detrás de otra (sin columnas fijas): primero
          las marcas y luego Coord./Turnos/Admin, todas pegadas con el mismo hueco
          y alineadas a la derecha. Envuelven en varias líneas si no caben. El
          bloque se centra en vertical contra el nombre+cargo. */}
      <span className="flex max-w-[20rem] shrink-0 flex-wrap items-center justify-end gap-1 self-center">
        {marcas.map((m) => (
          // Insignia de marca neutra: el color de equipo vive ahora en el avatar.
          <Badge
            key={m}
            variant="outline"
            className="h-5 shrink-0 whitespace-nowrap px-1.5 text-[10px] font-medium"
          >
            {metaZona(m).etiqueta}
          </Badge>
        ))}
        {usuario.puede_coordinar && (
          <Badge variant="secondary" className="h-5 shrink-0 px-1.5 text-[10px] font-normal">
            Coord.
          </Badge>
        )}
        {usuario.cobertura && (
          <Badge variant="secondary" className="h-5 shrink-0 px-1.5 text-[10px] font-normal">
            Turnos
          </Badge>
        )}
        {usuario.rol === "admin" && (
          <Badge variant="default" className="h-5 shrink-0 px-1.5 text-[10px] font-medium">
            Admin
          </Badge>
        )}
        {usuario.superadmin && (
          <Badge variant="default" className="h-5 shrink-0 px-1.5 text-[10px] font-medium">
            Superadmin
          </Badge>
        )}
      </span>
    </button>
  );
}
