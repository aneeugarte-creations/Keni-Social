import { useQuery } from "@tanstack/react-query";
import { KeyRound, ShieldAlert, UserPlus, Users } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSesion } from "@/hooks/sesion-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";

import { DialogoCrearUsuario } from "./usuarios/DialogoCrearUsuario";
import { OrganigramaArbol } from "./usuarios/OrganigramaArbol";
import { CLAVE_OPCIONES_MARCAS, CLAVE_USUARIOS } from "./usuarios/tipos";

/**
 * Bloqueo duro: un admin SIN llave de acceso no puede gestionar usuarios cuando el MFA es
 * obligatorio (`me.usuario.debe_inscribir_mfa`). En vez del organigrama mostramos esta puerta
 * con un CTA a "Mi cuenta" para inscribir una passkey. Es la misma exigencia que el backend
 * impone con su 403 (`mfa_inscripcion_requerida`); aquí la anticipamos en la UI.
 */
function PuertaInscripcionMfa() {
  return (
    <div
      role="alert"
      className="mx-auto max-w-md space-y-3 rounded-lg border border-amber-500/50 bg-amber-500/10 p-5 text-center"
    >
      <ShieldAlert className="mx-auto h-8 w-8 text-amber-600 dark:text-amber-500" aria-hidden="true" />
      <p className="text-base font-medium">Inscribe una llave de acceso para administrar usuarios</p>
      <p className="text-sm text-muted-foreground">
        Como administrador, gestionar usuarios exige verificación en dos pasos. Registra una llave
        de acceso (Face ID, huella o llave de seguridad) en tu cuenta y vuelve aquí.
      </p>
      <Button asChild>
        <Link to="/mi-cuenta">
          <KeyRound className="h-4 w-4" />
          Ir a Mi cuenta
        </Link>
      </Button>
    </div>
  );
}

/**
 * Página del Organigrama (rediseño de "Usuarios"). Pinta el equipo como un árbol top-down
 * con las áreas coloreadas por marca, derivadas de la cabeza de cada área. Al hacer clic en
 * una persona se abre un panel para editar su perfil (nombre, cargo, rol, superior, marcas,
 * cobertura, coordinación), resetear su contraseña o eliminarla. El backend devuelve 403 si
 * quien entra no es admin (el nav ya oculta la página, pero avisamos si se llega por URL).
 */
export default function Usuarios() {
  const [crearAbierto, setCrearAbierto] = React.useState(false);
  const { usuario: actual } = useSesion();
  const query = useQuery({
    queryKey: CLAVE_USUARIOS,
    queryFn: ({ signal }) => api.usuarios(signal),
  });

  // Catálogo de marcas (canónico) para chips y el editor de marcas.
  const marcasQuery = useQuery({
    queryKey: CLAVE_OPCIONES_MARCAS,
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    select: (data) => data.marcas,
    staleTime: 5 * 60 * 1000,
  });
  const catalogoMarcas = marcasQuery.data ?? [];

  // Admin sin passkey con MFA obligatorio: bloqueo duro de la gestión (oculta "Nueva persona"
  // y la edición; muestra la puerta de inscripción).
  const debeInscribirMfa = actual?.debe_inscribir_mfa === true;
  const esProhibido =
    query.isError && query.error instanceof ApiError && query.error.status === 403;
  const puedeCrear = !debeInscribirMfa && !esProhibido && !query.isError;

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

      {debeInscribirMfa ? (
        <PuertaInscripcionMfa />
      ) : esProhibido ? (
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
