import { Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { hexAlpha, iniciales, metaZona, nombreVisible } from "@/lib/organigrama";
import { type CargoUsuario, etiquetaCargo, type UsuarioAdmin } from "@/types";

/** Tarjeta-fila de una persona. Clic = abrir el panel de edición. */
export function TarjetaMiembro({
  usuario,
  tieneReportes,
  esYoMismo,
  onAbrir,
}: {
  usuario: UsuarioAdmin;
  /** Tiene personas a su cargo → muestra el icono de coordinación/dirección. */
  tieneReportes: boolean;
  esYoMismo: boolean;
  onAbrir: (id: string) => void;
}) {
  const marcas = usuario.marcas ?? [];
  const nombre = nombreVisible(usuario);

  return (
    <button
      type="button"
      onClick={() => onAbrir(usuario.id)}
      className="org-tarjeta flex w-full items-start gap-2.5 rounded-md border bg-card py-2 pl-2.5 pr-2 text-left shadow-sm transition-shadow transition-colors hover:shadow-md hover:border-keni-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      aria-label={`Editar a ${nombre}`}
    >
      <span
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground"
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

      {/* Insignias en columnas alineadas entre filas: las marcas (variables, borde
          derecho fijo pegado a las columnas de rol) a la izquierda y luego
          Coord./Turnos/Admin en huecos fijos —misma posición en todas las filas,
          hueco vacío si la persona no tiene esa insignia—. El bloque se centra en
          vertical contra el nombre+cargo para no quedar pegado arriba. */}
      <span className="flex shrink-0 items-center gap-1 self-center">
        {marcas.length > 0 && (
          <span className="flex max-w-[14rem] flex-wrap items-center justify-end gap-1">
            {marcas.map((m) => {
              const meta = metaZona(m);
              // Tinte por equipo: color de marca en texto y borde, con un fondo
              // suave (mismo patrón que las variantes ok/aviso/error del Badge).
              return (
                <Badge
                  key={m}
                  variant="outline"
                  className="h-5 shrink-0 whitespace-nowrap px-1.5 text-[10px] font-medium"
                  style={{
                    color: meta.color,
                    borderColor: hexAlpha(meta.color, 0.35),
                    backgroundColor: hexAlpha(meta.color, 0.12),
                  }}
                >
                  {meta.etiqueta}
                </Badge>
              );
            })}
          </span>
        )}
        <span className="flex w-14 justify-center">
          {usuario.puede_coordinar && (
            <Badge variant="secondary" className="h-5 px-1.5 text-[10px] font-normal">
              Coord.
            </Badge>
          )}
        </span>
        <span className="flex w-14 justify-center">
          {usuario.cobertura && (
            <Badge variant="secondary" className="h-5 px-1.5 text-[10px] font-normal">
              Turnos
            </Badge>
          )}
        </span>
        <span className="flex w-14 justify-center">
          {usuario.rol === "admin" && (
            <Badge variant="default" className="h-5 px-1.5 text-[10px] font-medium">
              Admin
            </Badge>
          )}
        </span>
      </span>
    </button>
  );
}
