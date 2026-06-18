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
import { Fingerprint, KeyRound, Loader2, ShieldOff, Trash2, User } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { MedidorPassword } from "@/components/auth/MedidorPassword";
import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { TituloPagina } from "@/components/layout/encabezado";
import { SeccionApariencia } from "@/pages/configuracion/SeccionApariencia";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearFechaHora as fmtFechaHoraCdmx } from "@/lib/fecha";
import { MIN_PASSWORD } from "@/lib/password";
import type { RolUsuario } from "@/types";

/** Clave de caché del usuario actual (`me`); se refresca al cambiar la contraseña. */
const CLAVE_ME = ["sesion", "me"] as const;

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
  const queryClient = useQueryClient();
  const { refrescar } = useSesion();
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_ME,
    queryFn: ({ signal }) => api.me(signal),
  });

  // Nombre humano editable (se guarda al salir del campo). Se sincroniza con el `me`.
  const nombreReal = (data?.usuario.nombre ?? "").trim();
  const [nombre, setNombre] = React.useState("");
  React.useEffect(() => {
    setNombre(nombreReal);
  }, [nombreReal]);

  const guardarNombre = useMutation({
    mutationFn: (valor: string) => api.actualizarMiPerfil(valor),
    onSuccess: async () => {
      toast.success("Nombre actualizado.");
      // El avatar y el resto de la app leen el nombre de la sesión: refrescamos.
      await refrescar();
      void queryClient.invalidateQueries({ queryKey: CLAVE_ME });
    },
    onError: (e) => {
      setNombre(nombreReal);
      toast.error(mensajeError(e));
    },
  });

  const alGuardarNombre = () => {
    const limpio = nombre.trim();
    if (limpio === nombreReal || guardarNombre.isPending) return;
    guardarNombre.mutate(limpio);
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Tu cuenta</CardTitle>
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
            <div className="space-y-1.5 rounded-lg border border-border px-3 py-2.5">
              <Label htmlFor="cuenta-nombre" className="text-sm text-muted-foreground">
                Nombre
              </Label>
              <Input
                id="cuenta-nombre"
                value={nombre}
                maxLength={120}
                placeholder={data.usuario.usuario}
                onChange={(e) => setNombre(e.target.value)}
                onBlur={alGuardarNombre}
                onKeyDown={(e) => {
                  if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                }}
                disabled={guardarNombre.isPending}
              />
              <p className="text-xs text-muted-foreground">Tu nombre visible en el equipo.</p>
            </div>
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
            <MedidorPassword password={nueva} />
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
 * Gestión del segundo factor con LLAVES DE ACCESO (passkeys). Se muestra siempre que la
 * maquinaria de MFA esté activa en el servidor (clave de firma presente,
 * `me.usuario.mfa_habilitado`); es opt-in por usuario: opcional para editores y obligatorio
 * solo para admins. Flujo:
 *   - Registrar una passkey nueva: pide opciones -> `startRegistration` (Face ID / huella /
 *     llave) -> el backend la guarda. Al registrar la PRIMERA, devuelve los códigos de
 *     recuperación (se muestran una sola vez).
 *   - Listar y borrar las llaves existentes.
 *   - Desactivar todo (pide la contraseña actual): borra todas las llaves + recovery.
 */
function SeccionMfa({ activo, debeInscribir }: { activo: boolean; debeInscribir: boolean }) {
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
      // 1) Opciones (el backend establece la cookie de challenge). 2) Ceremonia en el navegador.
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
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        {/* Aviso de inscripción OBLIGATORIA (admin sin passkey). No bloquea el acceso, pero
            empuja a registrar una llave cuanto antes (riesgo de account-takeover sin segundo
            factor en cuentas que publican a canales de marca). */}
        {debeInscribir && (
          <div
            role="alert"
            className="rounded-lg border border-amber-500/50 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-400"
          >
            <p className="font-medium">Tu cuenta de administrador necesita una llave de acceso.</p>
            <p className="mt-1 text-muted-foreground">
              Como administrador, la verificación en dos pasos es obligatoria. Registra una llave
              de acceso (Face ID, huella o llave de seguridad) ahora para proteger tu cuenta. Si
              pierdes el dispositivo, podrás entrar con los códigos de recuperación que verás al
              registrar la primera llave.
            </p>
          </div>
        )}

        {/* Invitación opt-in: usuario sin llave y no obligado (editor). Enmarca el segundo
            factor como opcional y recomendable. */}
        {!activo && !debeInscribir && (
          <p className="text-sm text-muted-foreground">
            Añade verificación en dos pasos a tu cuenta (opcional pero recomendado). Usa Face ID,
            huella o una llave de seguridad; solo tú podrás entrar aunque alguien tenga tu
            contraseña.
          </p>
        )}

        {/* Códigos de recuperación: solo tras registrar la PRIMERA llave. */}
        {recovery && (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Guarda estos códigos en lugar seguro. <span className="font-medium">No volverán a mostrarse</span>.
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
            {credenciales.map((c) => {
              const accionesLlave: EntradaMenuContextual[] = [
                {
                  etiqueta: "Eliminar llave",
                  icono: Trash2,
                  destructivo: true,
                  deshabilitado: borrar.isPending,
                  onClick: async () => {
                    if (
                      await confirmar({
                        mensaje: `¿Eliminar la llave "${c.nombre || "Llave sin nombre"}"? Esta acción no se puede deshacer.`,
                        destructivo: true,
                        textoConfirmar: "Eliminar",
                      })
                    )
                      borrar.mutate(c.id);
                  },
                },
              ];
              return (
                <FilaConAcciones
                  key={c.id}
                  como="li"
                  kebab="hover"
                  acciones={accionesLlave}
                  className="flex items-center justify-between gap-3 p-3 pr-10"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{c.nombre || "Llave sin nombre"}</p>
                    <p className="text-xs text-muted-foreground">
                      Creada {formatearFechaHora(c.creada)}
                      {c.ultimo_uso ? ` · Último uso ${formatearFechaHora(c.ultimo_uso)}` : ""}
                    </p>
                  </div>
                </FilaConAcciones>
              );
            })}
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
            <Label htmlFor="mfa-nombre-llave">Nombre de la llave</Label>
            <Input
              id="mfa-nombre-llave"
              placeholder="Opcional: iPhone, laptop…"
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
              <Label htmlFor="mfa-disable-pass">Contraseña actual</Label>
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

function PublicacionMiCuenta() {
  // Un solo `me` decide qué pintar; la sección de MFA solo aparece si el flag del servidor
  // (`mfa_habilitado`) está ON. Con el flag OFF, la UI no muestra nada de MFA.
  const { data } = useQuery({ queryKey: CLAVE_ME, queryFn: ({ signal }) => api.me(signal) });
  const mfaHabilitado = !!data?.usuario.mfa_habilitado;
  const mfaActivo = !!data?.usuario.mfa_activo;
  const debeInscribir = !!data?.usuario.debe_inscribir_mfa;
  return (
    <div className="space-y-6">
      <SeccionTuCuenta />
      <SeccionCambiarPassword />
      {mfaHabilitado && <SeccionMfa activo={mfaActivo} debeInscribir={debeInscribir} />}
    </div>
  );
}

export default function MiCuenta() {
  return (
    <>
      <TituloPagina titulo="Mi cuenta" icono={User} />
      {/* Preferencia PERSONAL (tema claro/oscuro): vive con la cuenta, no en una página
          de configuración global (reparto contextual). */}
      <div className="mb-4">
        <SeccionApariencia />
      </div>
      <PublicacionMiCuenta />
    </>
  );
}
