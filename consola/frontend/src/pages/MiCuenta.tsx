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
import { startRegistration } from "@simplewebauthn/browser";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fingerprint, KeyRound, Loader2, ShieldOff, Trash2 } from "lucide-react";
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
/* Sección: Llaves de acceso (passkeys / WebAuthn)                     */
/* ------------------------------------------------------------------ */

/** Clave de caché de la lista de passkeys del usuario. */
const CLAVE_PASSKEYS = ["sesion", "mfa-credenciales"] as const;

/**
 * Gestión del segundo factor con LLAVES DE ACCESO (passkeys). Solo se muestra si el servidor
 * tiene el flag `KENI_CONSOLA_MFA` ON (`me.usuario.mfa_habilitado`). Flujo:
 *   - Registrar una passkey nueva: pide opciones -> `startRegistration` (Face ID / huella /
 *     llave) -> el backend la guarda. Al registrar la PRIMERA, devuelve los códigos de
 *     recuperación (se muestran una sola vez).
 *   - Listar y borrar las llaves existentes.
 *   - Desactivar todo (pide la contraseña actual): borra todas las llaves + recovery.
 */
function SeccionMfa({ activo }: { activo: boolean }) {
  const queryClient = useQueryClient();
  const { refrescar } = useSesion();

  const [nombre, setNombre] = React.useState("");
  const [recovery, setRecovery] = React.useState<string[] | null>(null);
  const [passwordDisable, setPasswordDisable] = React.useState("");

  const refrescarEstado = React.useCallback(async () => {
    await refrescar();
    void queryClient.invalidateQueries({ queryKey: CLAVE_ME });
    void queryClient.invalidateQueries({ queryKey: CLAVE_PASSKEYS });
  }, [refrescar, queryClient]);

  const listado = useQuery({
    queryKey: CLAVE_PASSKEYS,
    queryFn: ({ signal }) => api.mfaCredenciales(signal),
    // Solo tiene sentido listar cuando el flag está ON (la sección ya lo garantiza).
  });

  const registrar = useMutation({
    mutationFn: async () => {
      // 1) Opciones (el backend siembra la cookie de challenge). 2) Ceremonia en el navegador.
      // 3) El backend verifica y guarda la credencial.
      const optionsJSON = await api.mfaRegistroOpciones();
      const credential = await startRegistration({
        optionsJSON: optionsJSON as unknown as Parameters<typeof startRegistration>[0]["optionsJSON"],
      });
      return api.mfaRegistroVerificar(credential, nombre.trim());
    },
    onSuccess: async (r) => {
      setNombre("");
      if (r.recovery_codes && r.recovery_codes.length > 0) {
        setRecovery(r.recovery_codes);
      }
      toast.success("Llave de acceso registrada.");
      await refrescarEstado();
    },
    onError: (e) => {
      if (e instanceof DOMException && e.name === "NotAllowedError") {
        toast.error("Registro cancelado.");
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  const borrar = useMutation({
    mutationFn: (id: string) => api.mfaBorrarCredencial(id),
    onSuccess: async () => {
      toast.success("Llave de acceso eliminada.");
      await refrescarEstado();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const desactivar = useMutation({
    mutationFn: () => api.mfaDisable(passwordDisable),
    onSuccess: async () => {
      setPasswordDisable("");
      setRecovery(null);
      toast.success("Verificación en dos pasos desactivada.");
      await refrescarEstado();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const credenciales = listado.data?.credenciales ?? [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Llaves de acceso (passkeys)</CardTitle>
        <CardDescription>
          Confirma tu identidad con Face ID, huella, Windows Hello o tu teléfono, además de la
          contraseña, al iniciar sesión.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        {/* Códigos de recuperación: solo tras registrar la PRIMERA llave. */}
        {recovery && (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Guarda estos códigos de recuperación en un lugar seguro. Cada uno sirve una sola vez
              y <span className="font-medium">no volverán a mostrarse</span>.
            </p>
            <ul className="grid grid-cols-2 gap-1 rounded-lg border border-border p-3 font-mono text-sm">
              {recovery.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Lista de llaves registradas. */}
        {activo && credenciales.length > 0 && (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {credenciales.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3 p-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{c.nombre || "Llave sin nombre"}</p>
                  <p className="text-xs text-muted-foreground">
                    Creada {formatearFechaHora(c.creada)}
                    {c.ultimo_uso ? ` · Último uso ${formatearFechaHora(c.ultimo_uso)}` : ""}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Eliminar llave"
                  disabled={borrar.isPending}
                  onClick={() => borrar.mutate(c.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}

        {/* Registrar una llave nueva. */}
        <form
          className="max-w-sm space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!registrar.isPending) registrar.mutate();
          }}
          noValidate
        >
          <div className="space-y-1.5">
            <Label htmlFor="mfa-nombre-llave">Nombre de la llave (opcional)</Label>
            <Input
              id="mfa-nombre-llave"
              placeholder="iPhone de Ana, Laptop…"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              disabled={registrar.isPending}
            />
          </div>
          <Button type="submit" disabled={registrar.isPending}>
            {registrar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Fingerprint className="h-4 w-4" />
            )}
            {activo ? "Añadir otra llave" : "Registrar llave de acceso"}
          </Button>
        </form>

        {/* Desactivar todo el segundo factor (pide la contraseña). */}
        {activo && (
          <form
            className="max-w-sm space-y-3 border-t border-border pt-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (passwordDisable.length > 0 && !desactivar.isPending) desactivar.mutate();
            }}
            noValidate
          >
            <div className="space-y-1.5">
              <Label htmlFor="mfa-disable-pass">Contraseña actual (para desactivar todo)</Label>
              <Input
                id="mfa-disable-pass"
                type="password"
                autoComplete="current-password"
                value={passwordDisable}
                onChange={(e) => setPasswordDisable(e.target.value)}
                disabled={desactivar.isPending}
              />
            </div>
            <Button
              type="submit"
              variant="destructive"
              disabled={passwordDisable.length === 0 || desactivar.isPending}
            >
              {desactivar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ShieldOff className="h-4 w-4" />
              )}
              Desactivar verificación en dos pasos
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Página                                                             */
/* ------------------------------------------------------------------ */

function ContenidoMiCuenta() {
  // Un solo `me` decide qué pintar; la sección de MFA solo aparece si el flag del servidor
  // (`mfa_habilitado`) está ON. Con el flag OFF, la UI no muestra nada de MFA.
  const { data } = useQuery({ queryKey: CLAVE_ME, queryFn: ({ signal }) => api.me(signal) });
  const mfaHabilitado = !!data?.usuario.mfa_habilitado;
  const mfaActivo = !!data?.usuario.mfa_activo;
  return (
    <div className="space-y-6">
      <SeccionTuCuenta />
      <SeccionCambiarPassword />
      {mfaHabilitado && <SeccionMfa activo={mfaActivo} />}
    </div>
  );
}

export default function MiCuenta() {
  return (
    <>
      <PageHeader titulo="Mi cuenta" descripcion="Consulta tus datos y cambia tu contraseña." />
      <ContenidoMiCuenta />
    </>
  );
}
