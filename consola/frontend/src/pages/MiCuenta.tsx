/**
 * Página "Mi cuenta": configuración de la PROPIA cuenta (cualquier rol).
 *
 * Reúne en una pantalla:
 *   1. Tu cuenta — nombre editable, usuario, rol, fecha de creación y último acceso.
 *   2. Cambiar contraseña — cambio VOLUNTARIO (distinto del forzado al primer acceso): pide la
 *      actual + la nueva (×2) y llama `POST /api/auth/cambiar-password`. El backend invalida el
 *      resto de sesiones y re-emite la de este dispositivo, así que no hay que volver a entrar.
 *   3. Llaves de acceso (passkeys) — CRUD de las llaves propias: registrar, renombrar y eliminar.
 *
 * La gestión de OTRAS cuentas (alta, rol, reset, baja) y la política de seguridad del equipo
 * viven en `/usuarios` y son solo de superadmin; aquí cada quien opera únicamente sobre su propia
 * cuenta (tema, datos, nombre, contraseña y sus llaves de acceso).
 */
import { startRegistration } from "@simplewebauthn/browser";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fingerprint, KeyRound, Loader2, Pencil, Trash2, User } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { MedidorPassword } from "@/components/auth/MedidorPassword";
import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { TituloPagina } from "@/components/layout/encabezado";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearFechaHora as fmtFechaHoraCdmx } from "@/lib/fecha";
import { MIN_PASSWORD } from "@/lib/password";
import { SeccionApariencia } from "@/pages/configuracion/SeccionApariencia";
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

/** Fila de dato (etiqueta → valor). Sin caja propia: vive en una lista `divide-y`. */
function FilaDato({ etiqueta, valor }: { etiqueta: string; valor: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <dt className="text-sm text-muted-foreground">{etiqueta}</dt>
      <dd className="text-sm font-medium">{valor}</dd>
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
      <CardHeader>
        <CardTitle>Tu cuenta</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {isPending ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full rounded-md" />
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
            <div className="space-y-1.5">
              <Label htmlFor="cuenta-nombre">Nombre</Label>
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
            <dl className="divide-y">
              <FilaDato etiqueta="Usuario" valor={data.usuario.usuario} />
              <FilaDato etiqueta="Rol" valor={ROL_LABEL[data.usuario.rol] ?? data.usuario.rol} />
              <FilaDato etiqueta="Creada" valor={formatearFechaHora(data.usuario.creado)} />
              <FilaDato
                etiqueta="Último acceso"
                valor={formatearFechaHora(data.usuario.ultimo_acceso)}
              />
            </dl>
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
      // El backend re-emitió la sesión de este dispositivo: refrescamos el usuario y los datos
      // de cuenta sin forzar re-login.
      await refrescar();
      void queryClient.invalidateQueries({ queryKey: CLAVE_ME });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeEnviar =
    actual.length > 0 && suficiente && coincide && distinta && !cambiar.isPending;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Cambiar contraseña</CardTitle>
        <CardDescription>Se cierran las demás sesiones; esta se mantiene.</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
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

/** Clave de caché de las passkeys propias; se recarga al añadir, renombrar o borrar una. */
const CLAVE_CREDENCIALES = ["sesion", "mfa", "credenciales"] as const;

function FilaCredencial({
  credencial,
  onRenombrar,
  onBorrar,
  ocupado,
}: {
  credencial: CredencialPasskey;
  onRenombrar: (nombre: string) => void;
  onBorrar: () => void;
  ocupado: boolean;
}) {
  const [editando, setEditando] = React.useState(false);
  const [nombre, setNombre] = React.useState(credencial.nombre ?? "");
  React.useEffect(() => {
    setNombre(credencial.nombre ?? "");
  }, [credencial.nombre]);

  const guardar = () => {
    setEditando(false);
    const limpio = nombre.trim();
    if (limpio !== (credencial.nombre ?? "")) onRenombrar(limpio);
  };

  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <div className="min-w-0 flex-1">
        {editando ? (
          <Input
            autoFocus
            value={nombre}
            maxLength={80}
            placeholder="iPhone, laptop…"
            className="h-8"
            onChange={(e) => setNombre(e.target.value)}
            onBlur={guardar}
            onKeyDown={(e) => {
              if (e.key === "Enter") (e.target as HTMLInputElement).blur();
              if (e.key === "Escape") {
                setNombre(credencial.nombre ?? "");
                setEditando(false);
              }
            }}
          />
        ) : (
          <p className="truncate text-sm font-medium">
            {credencial.nombre || "Llave de acceso"}
          </p>
        )}
        <p className="mt-0.5 text-xs text-muted-foreground">
          Creada {formatearFechaHora(credencial.creada)} · Último uso{" "}
          {formatearFechaHora(credencial.ultimo_uso)}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-0.5">
        {!editando && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="text-muted-foreground hover:text-foreground"
            onClick={() => setEditando(true)}
            aria-label={`Renombrar ${credencial.nombre || "llave de acceso"}`}
          >
            <Pencil className="h-4 w-4" />
          </Button>
        )}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="text-muted-foreground hover:text-destructive"
          disabled={ocupado}
          onClick={onBorrar}
          aria-label={`Eliminar ${credencial.nombre || "llave de acceso"}`}
        >
          {ocupado ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  );
}

function SeccionLlavesAcceso() {
  const queryClient = useQueryClient();
  const [nombre, setNombre] = React.useState("");

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
    onSuccess: async () => {
      toast.success("Llave de acceso registrada.");
      setNombre("");
      await recargar();
    },
    onError: (e) => {
      if (e instanceof DOMException && e.name === "InvalidStateError") {
        // El autenticador de ESTE equipo ya tiene una llave para el sitio (o la passkey está
        // sincronizada y ya está presente). Para sumar OTRO dispositivo se usa el QR.
        toast.error(
          "Este dispositivo ya tiene una llave registrada. Para añadir tu teléfono, elige " +
            "“usar otro dispositivo” en el diálogo y escanea el QR.",
        );
      } else if (e instanceof DOMException && e.name === "NotAllowedError") {
        toast.error("Registro cancelado o agotado. Vuelve a intentarlo.");
      } else {
        toast.error(mensajeError(e));
      }
    },
  });

  const renombrar = useMutation({
    mutationFn: ({ id, nombre: n }: { id: string; nombre: string }) =>
      api.mfaRenombrarCredencial(id, n),
    onSuccess: async () => {
      toast.success("Llave renombrada.");
      await recargar();
    },
    onError: (e) => toast.error(mensajeError(e)),
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
      <CardHeader>
        <CardTitle>Llaves de acceso (passkeys)</CardTitle>
        <CardDescription>
          Entra sin contraseña con Face ID, huella o tu teléfono. Registra al menos dos llaves —tu
          móvil y tu ordenador— para no quedarte fuera si pierdes una.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full rounded-md" />
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
          <p className="rounded-md border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
            Aún no tienes ninguna llave de acceso registrada.
          </p>
        ) : (
          <div className="divide-y rounded-md border">
            {credenciales.map((c) => (
              <div key={c.id} className="px-3">
                <FilaCredencial
                  credencial={c}
                  ocupado={borrar.isPending && borrar.variables === c.id}
                  onRenombrar={(n) => renombrar.mutate({ id: c.id, nombre: n })}
                  onBorrar={() => void alBorrar(c)}
                />
              </div>
            ))}
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

        <p className="text-xs text-muted-foreground">
          ¿Registrar otro dispositivo? El navegador lo gestiona: al pulsar “Añadir llave”, elige{" "}
          <span className="font-medium">“usar otro dispositivo / teléfono”</span> y escanea el QR
          con él para crear ahí su llave. Si usas iCloud Llavero o Google, tu passkey se sincroniza
          sola entre tus dispositivos del mismo ecosistema (Apple↔Apple, Google↔Google).
        </p>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Página                                                             */
/* ------------------------------------------------------------------ */

export default function MiCuenta() {
  const { usuario } = useSesion();
  return (
    <>
      <TituloPagina titulo="Mi cuenta" icono={User} />
      <div className="w-full space-y-6 pb-12">
        {/* Preferencia PERSONAL (tema claro/oscuro): vive con la cuenta. */}
        <SeccionApariencia />
        <div className="grid items-start gap-6 lg:grid-cols-2">
          <SeccionTuCuenta />
          <SeccionCambiarPassword />
        </div>
        {usuario?.mfa_habilitado && <SeccionLlavesAcceso />}
      </div>
    </>
  );
}
