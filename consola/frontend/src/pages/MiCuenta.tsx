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
 * La gestión de OTRAS cuentas (alta, rol, reset, baja) y la verificación en dos pasos (MFA)
 * viven en `/usuarios` y son solo de superadmin; aquí cada quien opera únicamente sobre su
 * propia cuenta (tema, datos, nombre y contraseña).
 */
import { startRegistration } from "@simplewebauthn/browser";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fingerprint, KeyRound, Loader2, ShieldCheck, Trash2, User } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { MedidorPassword } from "@/components/auth/MedidorPassword";
import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
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
import type { CredencialPasskey, RolUsuario } from "@/types";

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
/* Sección: Llaves de acceso (passkeys)                               */
/* ------------------------------------------------------------------ */

/** Clave de caché de las passkeys propias; se recarga al añadir o borrar una. */
const CLAVE_CREDENCIALES = ["sesion", "mfa", "credenciales"] as const;

function FilaCredencial({
  credencial,
  onBorrar,
  borrando,
}: {
  credencial: CredencialPasskey;
  onBorrar: () => void;
  borrando: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{credencial.nombre || "Llave de acceso"}</p>
        <p className="text-xs text-muted-foreground">
          Creada {formatearFechaHora(credencial.creada)} · Último uso{" "}
          {formatearFechaHora(credencial.ultimo_uso)}
        </p>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="text-muted-foreground hover:text-destructive"
        disabled={borrando}
        onClick={onBorrar}
        aria-label={`Eliminar ${credencial.nombre || "llave de acceso"}`}
      >
        {borrando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
      </Button>
    </div>
  );
}

function SeccionLlavesAcceso() {
  const queryClient = useQueryClient();
  const [nombre, setNombre] = React.useState("");
  // Códigos de recuperación de la PRIMERA llave: se muestran una sola vez.
  const [recovery, setRecovery] = React.useState<string[] | null>(null);

  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_CREDENCIALES,
    queryFn: ({ signal }) => api.mfaCredenciales(signal),
  });

  const credenciales = data?.credenciales ?? [];

  const recargar = () => queryClient.invalidateQueries({ queryKey: CLAVE_CREDENCIALES });

  const anadir = useMutation({
    mutationFn: async () => {
      const optionsJSON = await api.mfaRegistroOpciones();
      const credential = await startRegistration({
        optionsJSON: optionsJSON as unknown as Parameters<typeof startRegistration>[0]["optionsJSON"],
      });
      return api.mfaRegistroVerificar(credential, nombre.trim());
    },
    onSuccess: async (r) => {
      toast.success("Llave de acceso registrada.");
      setNombre("");
      if (r.recovery_codes && r.recovery_codes.length > 0) {
        setRecovery(r.recovery_codes);
      }
      await recargar();
    },
    onError: (e) => {
      if (e instanceof DOMException && e.name === "NotAllowedError") {
        toast.error("Registro cancelado.");
      } else {
        toast.error(mensajeError(e));
      }
    },
  });

  const borrar = useMutation({
    mutationFn: (id: string) => api.mfaBorrarCredencial(id),
    onSuccess: async () => {
      toast.success("Llave de acceso eliminada.");
      await recargar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const alBorrar = async (c: CredencialPasskey) => {
    const ok = await confirmar({
      titulo: "Eliminar llave de acceso",
      mensaje: `¿Eliminar "${c.nombre || "esta llave de acceso"}"? No podrás usarla para entrar.`,
      destructivo: true,
      textoConfirmar: "Eliminar",
    });
    if (ok) borrar.mutate(c.id);
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Llaves de acceso (passkeys)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <p className="text-sm text-muted-foreground">
          Entra sin contraseña con Face ID, huella o tu teléfono. Registra al menos dos llaves
          —tu móvil y tu ordenador— para no quedarte fuera si pierdes una.
        </p>

        {isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-lg" />
            ))}
          </div>
        ) : isError ? (
          <BloqueError
            titulo="No se pudieron cargar tus llaves de acceso"
            mensaje={mensajeError(error)}
            onReintentar={() => void refetch()}
            cargando={isFetching}
          />
        ) : credenciales.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-sm text-muted-foreground">
            Aún no tienes ninguna llave de acceso registrada.
          </p>
        ) : (
          <div className="space-y-2">
            {credenciales.map((c) => (
              <FilaCredencial
                key={c.id}
                credencial={c}
                borrando={borrar.isPending && borrar.variables === c.id}
                onBorrar={() => void alBorrar(c)}
              />
            ))}
          </div>
        )}

        {recovery && (
          <div className="space-y-2 rounded-lg border border-border bg-muted/40 p-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              <ShieldCheck className="h-4 w-4" />
              Códigos de recuperación
            </div>
            <p className="text-xs text-muted-foreground">
              Guárdalos en un lugar seguro. <span className="font-medium">No volverán a
              mostrarse</span>. Te permiten entrar si pierdes tus llaves.
            </p>
            <ul className="grid grid-cols-2 gap-1 rounded-lg border border-border bg-background p-3 font-mono text-sm">
              {recovery.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
            <Button type="button" variant="outline" size="sm" onClick={() => setRecovery(null)}>
              Ya los guardé
            </Button>
          </div>
        )}

        <form
          className="flex flex-col gap-2 sm:flex-row sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            if (!anadir.isPending) anadir.mutate();
          }}
          noValidate
        >
          <div className="flex-1 space-y-1.5">
            <Label htmlFor="nombre-llave">Nombre de la llave</Label>
            <Input
              id="nombre-llave"
              placeholder="Opcional: iPhone, laptop…"
              value={nombre}
              maxLength={120}
              onChange={(e) => setNombre(e.target.value)}
              disabled={anadir.isPending}
            />
          </div>
          <Button type="submit" disabled={anadir.isPending}>
            {anadir.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Fingerprint className="h-4 w-4" />
            )}
            Añadir llave de acceso
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Página                                                             */
/* ------------------------------------------------------------------ */

function PublicacionMiCuenta() {
  const { usuario } = useSesion();
  return (
    <div className="space-y-6">
      <SeccionTuCuenta />
      <SeccionCambiarPassword />
      {usuario?.mfa_habilitado && <SeccionLlavesAcceso />}
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
