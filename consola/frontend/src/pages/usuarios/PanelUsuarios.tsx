import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, Settings, ShieldAlert, UserPlus, Users } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
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
import { useSesion } from "@/hooks/sesion-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";
import { nombreVisible } from "@/lib/organigrama";
import { type CargoUsuario, etiquetaCargo, type RolUsuario, type UsuarioAdmin } from "@/types";

import { formatearFecha } from "./lib";
import { SelectorMarcas } from "./SelectorMarcas";
import { CLAVE_OPCIONES_MARCAS, CLAVE_USUARIOS, ROL_LABEL } from "./tipos";

/** Centinela del filtro de rol: "todos". */
const ROL_TODOS = "__todos__";

/** Insignia del rol EFECTIVO (superadmin es un rol más: gana sobre admin/editor). */
function BadgeRol({ usuario }: { usuario: UsuarioAdmin }) {
  if (usuario.superadmin) {
    return <Badge className="h-5 px-1.5 text-[10px] font-medium">Superadmin</Badge>;
  }
  if (usuario.rol === "admin") {
    return (
      <Badge variant="secondary" className="h-5 px-1.5 text-[10px] font-medium">
        Administrador
      </Badge>
    );
  }
  return <span className="text-sm text-muted-foreground">Editor</span>;
}

/**
 * Panel de administración de usuarios. Pinta el equipo como una TABLA con buscador y filtro de rol;
 * cada fila lleva a la subpágina de detalle (`/usuarios/:id`). La columna Marcas es un checklist
 * desplegable que edita en línea. Las acciones globales —alta y configuración de seguridad— viven
 * en el menú de la cabecera. Gestionar usuarios es SOLO superadmin (el backend devuelve 403 como
 * red de seguridad si se llega por URL).
 */
export default function PanelUsuarios() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { usuario: actual, cargando } = useSesion();
  const esSuperadmin = actual?.es_superadmin === true;

  const query = useQuery({
    queryKey: CLAVE_USUARIOS,
    queryFn: ({ signal }) => api.usuarios(signal),
    enabled: esSuperadmin,
  });

  // Catálogo de marcas (canónico) para el checklist por fila.
  const marcasQuery = useQuery({
    queryKey: CLAVE_OPCIONES_MARCAS,
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    select: (data) => data.marcas,
    staleTime: 5 * 60 * 1000,
    enabled: esSuperadmin,
  });
  const catalogoMarcas = marcasQuery.data ?? [];

  const guardarMarcas = useMutation({
    mutationFn: ({ id, marcas }: { id: string; marcas: string[] }) =>
      api.actualizarUsuario(id, { marcas }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_USUARIOS });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const [busqueda, setBusqueda] = React.useState("");
  const [rolFiltro, setRolFiltro] = React.useState<string>(ROL_TODOS);

  const usuarios = query.data?.usuarios ?? [];

  const filtrados = React.useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return usuarios.filter((u) => {
      if (rolFiltro !== ROL_TODOS && u.rol !== rolFiltro) return false;
      if (!q) return true;
      return (
        nombreVisible(u).toLowerCase().includes(q) || u.usuario.toLowerCase().includes(q)
      );
    });
  }, [usuarios, busqueda, rolFiltro]);

  // Gestionar usuarios es solo superadmin: resuelta la sesión, sin el flag mostramos el aviso
  // (mientras carga la sesión dejamos pasar al esqueleto de abajo).
  if (!cargando && !esSuperadmin) {
    return (
      <>
        <TituloPagina titulo="Usuarios" icono={Users} />
        <EstadoVacio icono={ShieldAlert} titulo="No tienes permiso" />
      </>
    );
  }

  const esProhibido =
    query.isError && query.error instanceof ApiError && query.error.status === 403;
  const puedeAccionar = !esProhibido && !query.isError;

  return (
    <>
      <TituloPagina titulo="Usuarios" icono={Users} />
      {puedeAccionar && (
        <AccionesPagina>
          <MenuAcciones>
            <ItemMenu icono={UserPlus} onClick={() => navigate("/usuarios/nuevo")}>
              Nueva persona
            </ItemMenu>
            <ItemMenu icono={Settings} onClick={() => navigate("/usuarios/configuracion")}>
              Configuración global
            </ItemMenu>
          </MenuAcciones>
        </AccionesPagina>
      )}

      {esProhibido ? (
        <EstadoVacio icono={ShieldAlert} titulo="No tienes permiso" />
      ) : query.isPending ? (
        <Skeleton className="h-80 w-full rounded-md" />
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudo cargar la lista de usuarios"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : usuarios.length === 0 ? (
        <EstadoVacio icono={Users} titulo="No hay personas" texto="Crea la primera cuenta." />
      ) : (
        <div className="space-y-4">
          {/* Buscador + filtro de rol. */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
                placeholder="Buscar por nombre o usuario"
                aria-label="Buscar usuarios"
                className="pl-8"
              />
            </div>
            <Select value={rolFiltro} onValueChange={setRolFiltro}>
              <SelectTrigger className="h-9 w-44" aria-label="Filtrar por rol">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ROL_TODOS}>Todos los roles</SelectItem>
                {(Object.keys(ROL_LABEL) as RolUsuario[]).map((r) => (
                  <SelectItem key={r} value={r}>
                    {ROL_LABEL[r]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {filtrados.length === 0 ? (
            <EstadoVacio
              icono={Search}
              titulo="Sin resultados"
              texto="Ninguna persona coincide con el filtro."
            />
          ) : (
            <div className="rounded-xl border bg-card">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Persona</TableHead>
                    <TableHead>Cargo</TableHead>
                    <TableHead>Permisos</TableHead>
                    <TableHead>Marcas</TableHead>
                    <TableHead>Passkey</TableHead>
                    <TableHead>Último acceso</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtrados.map((u) => {
                    const mfaTexto = u.mfa_activo
                      ? "Activa"
                      : u.mfa_requerido
                        ? "Requerida"
                        : "—";
                    return (
                      <TableRow
                        key={u.id}
                        className="cursor-pointer"
                        onClick={() => navigate(`/usuarios/${u.id}`)}
                      >
                        <TableCell>
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5 text-sm font-medium leading-tight">
                              <span className="truncate">{nombreVisible(u)}</span>
                              {u.id === actual?.id && (
                                <span className="text-xs font-normal text-muted-foreground">
                                  (tú)
                                </span>
                              )}
                            </div>
                            <span className="block truncate text-xs text-muted-foreground">
                              @{u.usuario}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {etiquetaCargo((u.cargo ?? "") as CargoUsuario)}
                        </TableCell>
                        <TableCell>
                          <BadgeRol usuario={u} />
                        </TableCell>
                        <TableCell>
                          <SelectorMarcas
                            marcas={u.marcas ?? []}
                            catalogo={catalogoMarcas}
                            disabled={guardarMarcas.isPending}
                            onChange={(marcas) => guardarMarcas.mutate({ id: u.id, marcas })}
                          />
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {mfaTexto}
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                          {formatearFecha(u.ultimo_acceso)}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      )}
    </>
  );
}
