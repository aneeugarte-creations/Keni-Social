/**
 * Página "Mi cuenta": configuración de la PROPIA cuenta (cualquier rol).
 *
 * Reúne en una pantalla:
 *   1. Tu cuenta — usuario, rol, fecha de creación y último acceso (de `GET /api/auth/me`).
 *   2. Cambiar contraseña — cambio VOLUNTARIO (distinto del forzado al primer acceso):
 *      pide la actual + la nueva (×2) y llama `POST /api/auth/cambiar-password`. El
 *      backend invalida el resto de sesiones y re-emite la de este dispositivo, así que
 *      no hay que volver a iniciar sesión.
 *
 * La gestión de OTRAS cuentas (alta, rol, reset, baja) vive en `/usuarios` y es solo
 * para admin; aquí cada quien opera únicamente sobre su propia cuenta.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Loader2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearFechaHora as fmtFechaHoraCdmx } from "@/lib/fecha";
import type { RolUsuario } from "@/types";

/** Clave de caché del usuario actual (`me`); se refresca al cambiar la contraseña. */
const CLAVE_ME = ["sesion", "me"] as const;

/** Longitud mínima de contraseña (espejo del backend y de las demás pantallas). */
const MIN_PASSWORD = 8;

const ROL_LABEL: Record<RolUsuario, string> = {
  admin: "Administrador",
  editor: "Editor",
};

/** Fecha + hora legible en CDMX (instantes UTC del backend); guion si vacía/inválida. */
function formatearFechaHora(iso: string | null | undefined): string {
  return fmtFechaHoraCdmx(iso) || "—";
}

/* ------------------------------------------------------------------ */
/* Sección: Tu cuenta                                                 */
/* ------------------------------------------------------------------ */

function FilaDato({ etiqueta, valor }: { etiqueta: string; valor: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5">
      <span className="text-sm text-muted-foreground">{etiqueta}</span>
      <span className="text-sm font-medium">{valor}</span>
    </div>
  );
}

function SeccionTuCuenta() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_ME,
    queryFn: ({ signal }) => api.me(signal),
  });

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Tu cuenta</CardTitle>
        <CardDescription>Datos de la cuenta con la que tienes la sesión iniciada.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 pt-0">
        {isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-11 w-full rounded-lg" />
            ))}
          </div>
        ) : isError ? (
          <BloqueError
            titulo="No se pudo cargar tu cuenta"
            mensaje={mensajeError(error)}
            onReintentar={() => void refetch()}
            cargando={isFetching}
          />
        ) : (
          <>
            <FilaDato etiqueta="Usuario" valor={data.usuario.usuario} />
            <FilaDato etiqueta="Rol" valor={ROL_LABEL[data.usuario.rol] ?? data.usuario.rol} />
            <FilaDato etiqueta="Creada" valor={formatearFechaHora(data.usuario.creado)} />
            <FilaDato etiqueta="Último acceso" valor={formatearFechaHora(data.usuario.ultimo_acceso)} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Sección: Cambiar contraseña                                        */
/* ------------------------------------------------------------------ */

function SeccionCambiarPassword() {
  const queryClient = useQueryClient();
  const { refrescar } = useSesion();
  const [actual, setActual] = React.useState("");
  const [nueva, setNueva] = React.useState("");
  const [confirmar, setConfirmar] = React.useState("");

  const coincide = nueva.length > 0 && nueva === confirmar;
  const suficiente = nueva.length >= MIN_PASSWORD;
  const distinta = nueva !== actual;

  const cambiar = useMutation({
    mutationFn: () => api.cambiarPassword({ password_actual: actual, password_nueva: nueva }),
    onSuccess: async () => {
      toast.success("Contraseña actualizada.");
      setActual("");
      setNueva("");
      setConfirmar("");
      // El backend re-emitió la sesión de este dispositivo: refrescamos el usuario y
      // los datos de cuenta (por si cambian metadatos) sin forzar re-login.
      await refrescar();
      void queryClient.invalidateQueries({ queryKey: CLAVE_ME });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeEnviar =
    actual.length > 0 && suficiente && coincide && distinta && !cambiar.isPending;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Cambiar contraseña</CardTitle>
        <CardDescription>
          Para cambiarla necesitas tu contraseña actual. Al guardar se cerrarán las sesiones de
          otros dispositivos.
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        <form
          className="max-w-sm space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (puedeEnviar) cambiar.mutate();
          }}
          noValidate
        >
          <div className="space-y-1.5">
            <Label htmlFor="cuenta-actual">Contraseña actual</Label>
            <Input
              id="cuenta-actual"
              type="password"
              autoComplete="current-password"
              value={actual}
              onChange={(e) => setActual(e.target.value)}
              disabled={cambiar.isPending}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="cuenta-nueva">Contraseña nueva</Label>
            <Input
              id="cuenta-nueva"
              type="password"
              autoComplete="new-password"
              value={nueva}
              onChange={(e) => setNueva(e.target.value)}
              disabled={cambiar.isPending}
            />
            <p className="text-xs text-muted-foreground">Mínimo {MIN_PASSWORD} caracteres.</p>
            {nueva.length > 0 && !distinta && (
              <p className="text-xs text-destructive">La nueva debe ser distinta de la actual.</p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="cuenta-confirmar">Repite la contraseña nueva</Label>
            <Input
              id="cuenta-confirmar"
              type="password"
              autoComplete="new-password"
              value={confirmar}
              onChange={(e) => setConfirmar(e.target.value)}
              disabled={cambiar.isPending}
            />
            {confirmar.length > 0 && !coincide && (
              <p className="text-xs text-destructive">Las contraseñas no coinciden.</p>
            )}
          </div>
          <Button type="submit" disabled={!puedeEnviar}>
            {cambiar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <KeyRound className="h-4 w-4" />
            )}
            Cambiar contraseña
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Página                                                             */
/* ------------------------------------------------------------------ */

export default function MiCuenta() {
  return (
    <>
      <PageHeader titulo="Mi cuenta" descripcion="Consulta tus datos y cambia tu contraseña." />
      <div className="space-y-6">
        <SeccionTuCuenta />
        <SeccionCambiarPassword />
      </div>
    </>
  );
}
