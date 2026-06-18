import { useQuery } from "@tanstack/react-query";
import { ShieldAlert, UserPlus, Users } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Skeleton } from "@/components/ui/skeleton";
import { useSesion } from "@/hooks/sesion-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";

import { DialogoCrearUsuario } from "./usuarios/DialogoCrearUsuario";
import { OrganigramaArbol } from "./usuarios/OrganigramaArbol";
import { CLAVE_OPCIONES_MARCAS, CLAVE_USUARIOS } from "./usuarios/tipos";

/**
 * Página del Organigrama (rediseño de "Usuarios"). Pinta el equipo como un árbol top-down
 * con las áreas coloreadas por marca, derivadas de la cabeza de cada área. Al hacer clic en
 * una persona se abre un panel para editar su perfil (nombre, cargo, rol, superior, marcas,
 * cobertura, coordinación), resetear su contraseña o eliminarla. Gestionar usuarios es SOLO
 * superadmin: a quien no lo sea se le muestra el aviso de prohibición (y el backend devuelve
 * 403 como red de seguridad si se llega por URL).
 */
export default function Usuarios() {
  const [crearAbierto, setCrearAbierto] = React.useState(false);
  const { usuario: actual, cargando } = useSesion();
  const esSuperadmin = actual?.es_superadmin === true;
  const query = useQuery({
    queryKey: CLAVE_USUARIOS,
    queryFn: ({ signal }) => api.usuarios(signal),
    enabled: esSuperadmin,
  });

  // Catálogo de marcas (canónico) para chips y el editor de marcas.
  const marcasQuery = useQuery({
    queryKey: CLAVE_OPCIONES_MARCAS,
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    select: (data) => data.marcas,
    staleTime: 5 * 60 * 1000,
    enabled: esSuperadmin,
  });
  const catalogoMarcas = marcasQuery.data ?? [];

  // Gestionar usuarios es solo superadmin: resuelta la sesión, sin el flag mostramos el aviso
  // de prohibición (mientras carga la sesión dejamos pasar al esqueleto de abajo).
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
  const puedeCrear = !esProhibido && !query.isError;

  return (
    <>
      <TituloPagina titulo="Usuarios" icono={Users} />
      {puedeCrear && (
        <AccionesPagina>
          <MenuAcciones>
            <ItemMenu icono={UserPlus} onClick={() => setCrearAbierto(true)}>
              Nueva persona
            </ItemMenu>
          </MenuAcciones>
        </AccionesPagina>
      )}
      <DialogoCrearUsuario abierto={crearAbierto} onAbierto={setCrearAbierto} />

      {esProhibido ? (
        <EstadoVacio
          icono={ShieldAlert}
          titulo="No tienes permiso"
        />
      ) : query.isPending ? (
        <Skeleton className="h-80 w-full rounded-md" />
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudo cargar el organigrama"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : query.data.usuarios.length === 0 ? (
        <EstadoVacio
          icono={Users}
          titulo="No hay personas"
          texto="Crea la primera cuenta."
        />
      ) : (
        <OrganigramaArbol
          usuarios={query.data.usuarios}
          idActual={actual?.id ?? null}
          catalogoMarcas={catalogoMarcas}
        />
      )}
    </>
  );
}
