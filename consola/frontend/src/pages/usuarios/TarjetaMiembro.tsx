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
  zona: string;
  /** Tiene personas a su cargo → muestra el icono de coordinación/dirección. */
  tieneReportes: boolean;
  esYoMismo: boolean;
  onAbrir: (id: string) => void;
}) {
  const meta = metaZona(zona);
  const marcas = usuario.marcas ?? [];
  const nombre = nombreVisible(usuario);

  return (
    <button
      type="button"
      onClick={() => onAbrir(usuario.id)}
      className="org-tarjeta flex w-full items-start gap-2.5 rounded-md border bg-card py-2 pl-2.5 pr-2 text-left shadow-sm transition-shadow hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      style={{ borderLeftColor: meta.color, borderLeftWidth: 4 }}
      aria-label={`Editar a ${nombre}`}
    >
      <span
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
        style={{ backgroundColor: meta.color }}
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

      <span className="flex shrink-0 flex-wrap justify-end gap-1">
        {usuario.rol === "admin" && (
          <Badge variant="default" className="h-5 px-1.5 text-[10px] font-medium">
            Admin
          </Badge>
        )}
        {usuario.cobertura && (
          <Badge variant="secondary" className="h-5 px-1.5 text-[10px] font-normal">
            Turnos
          </Badge>
        )}
        {usuario.puede_coordinar && (
          <Badge variant="secondary" className="h-5 px-1.5 text-[10px] font-normal">
            Coord.
          </Badge>
        )}
        {marcas.map((m) => (
          <Badge
            key={m}
            variant="outline"
            className="h-5 px-1.5 text-[10px] font-normal"
            style={{ borderColor: hexAlpha(metaZona(m).color, 0.5), color: metaZona(m).color }}
          >
            {metaZona(m).etiqueta}
          </Badge>
        ))}
      </span>
    </button>
  );
}
