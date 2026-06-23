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
import {
  Clock,
  Copy,
  Fingerprint,
  KeyRound,
  Loader2,
  Pencil,
  Plug,
  Trash2,
  User,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { MedidorPassword } from "@/components/auth/MedidorPassword";
import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { TituloPagina } from "@/components/layout/encabezado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearFechaHora as fmtFechaHoraCdmx } from "@/lib/fecha";
import { MIN_PASSWORD } from "@/lib/password";
import { SeccionApariencia } from "@/pages/configuracion/SeccionApariencia";
import type { CredencialPasskey, RolUsuario, TokenMcp } from "@/types";

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
/* Sección: Zona horaria                                              */
/* ------------------------------------------------------------------ */

/** Zona por defecto del equipo del piloto; respaldo si el backend aún no manda una. */
const ZONA_DEFECTO = "America/Mexico_City";

/**
 * Catálogo de zonas para el selector: agrupado por región y con ciudad legible. No listamos las
 * ~400 zonas IANA (un muro inmanejable); cubrimos las realistas del equipo y colaboradores. Si la
 * cuenta ya tiene una zona fuera de esta lista, se añade aparte para que siga siendo elegible.
 */
const GRUPOS_ZONAS: { grupo: string; zonas: { id: string; ciudad: string }[] }[] = [
  {
    grupo: "México",
    zonas: [
      { id: "America/Mexico_City", ciudad: "Ciudad de México" },
      { id: "America/Monterrey", ciudad: "Monterrey" },
      { id: "America/Cancun", ciudad: "Cancún" },
      { id: "America/Chihuahua", ciudad: "Chihuahua" },
      { id: "America/Hermosillo", ciudad: "Hermosillo" },
      { id: "America/Tijuana", ciudad: "Tijuana" },
    ],
  },
  {
    grupo: "América",
    zonas: [
      { id: "America/New_York", ciudad: "Nueva York · Miami" },
      { id: "America/Chicago", ciudad: "Chicago" },
      { id: "America/Denver", ciudad: "Denver" },
      { id: "America/Los_Angeles", ciudad: "Los Ángeles" },
      { id: "America/Bogota", ciudad: "Bogotá · Lima" },
      { id: "America/Santiago", ciudad: "Santiago de Chile" },
      { id: "America/Argentina/Buenos_Aires", ciudad: "Buenos Aires" },
      { id: "America/Sao_Paulo", ciudad: "São Paulo" },
    ],
  },
  {
    grupo: "Europa",
    zonas: [
      { id: "Europe/Madrid", ciudad: "Madrid" },
      { id: "Europe/London", ciudad: "Londres" },
      { id: "Europe/Paris", ciudad: "París · Berlín" },
    ],
  },
  { grupo: "Otros", zonas: [{ id: "UTC", ciudad: "UTC" }] },
];

/** Offset GMT actual de una zona ("GMT-6"), robusto ante horario de verano. "" si inválida. */
function offsetZona(zona: string): string {
  try {
    const tz = new Intl.DateTimeFormat("es-MX", { timeZone: zona, timeZoneName: "shortOffset" })
      .formatToParts(new Date())
      .find((p) => p.type === "timeZoneName");
    return tz?.value ?? "";
  } catch {
    return "";
  }
}

/** Hora de pared AHORA en `zona` con su etiqueta, para previsualizar la elección. "" si inválida. */
function previsualizarZona(zona: string): string {
  try {
    return new Intl.DateTimeFormat("es-MX", {
      timeZone: zona,
      weekday: "short",
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    }).format(new Date());
  } catch {
    return "";
  }
}

function SeccionZonaHoraria() {
  const queryClient = useQueryClient();
  const { usuario, refrescar } = useSesion();
  const zonaActual = usuario?.zona_horaria || ZONA_DEFECTO;

  const [zona, setZona] = React.useState(zonaActual);
  React.useEffect(() => setZona(zonaActual), [zonaActual]);

  // Si la zona guardada no está en el catálogo, la añadimos como grupo propio para no perderla.
  const grupos = React.useMemo(() => {
    const conocidas = new Set(GRUPOS_ZONAS.flatMap((g) => g.zonas.map((z) => z.id)));
    if (conocidas.has(zonaActual)) return GRUPOS_ZONAS;
    return [...GRUPOS_ZONAS, { grupo: "Tu zona actual", zonas: [{ id: zonaActual, ciudad: zonaActual }] }];
  }, [zonaActual]);

  const preview = previsualizarZona(zona);

  const guardar = useMutation({
    mutationFn: (z: string) => api.actualizarMiZona(z),
    onSuccess: async () => {
      toast.success("Zona horaria actualizada.");
      // El resto de la app pinta las horas según la sesión: refrescamos para que toda la
      // consola adopte la nueva zona (y su etiqueta) de inmediato.
      await refrescar();
      void queryClient.invalidateQueries({ queryKey: CLAVE_ME });
    },
    onError: (e) => {
      setZona(zonaActual);
      toast.error(mensajeError(e));
    },
  });

  const puedeGuardar = zona !== zonaActual && !guardar.isPending;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Zona horaria</CardTitle>
        <CardDescription>
          Todas las horas de la consola se muestran en esta zona, siempre con su etiqueta (p. ej.
          “16:00 CDMX”), para que ninguna hora quede sin saber a qué zona pertenece.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            if (puedeGuardar) guardar.mutate(zona);
          }}
          noValidate
        >
          <Label htmlFor="cuenta-zona">Tu zona horaria</Label>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Select value={zona} onValueChange={setZona} disabled={guardar.isPending}>
              <SelectTrigger id="cuenta-zona" className="sm:flex-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {grupos.map((g) => (
                  <SelectGroup key={g.grupo}>
                    <SelectLabel>{g.grupo}</SelectLabel>
                    {g.zonas.map((z) => (
                      <SelectItem key={z.id} value={z.id}>
                        {z.ciudad} · {offsetZona(z.id)}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
            <Button type="submit" disabled={!puedeGuardar} className="shrink-0">
              {guardar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Clock className="h-4 w-4" />
              )}
              Guardar zona
            </Button>
          </div>
          {preview && (
            <p className="text-xs text-muted-foreground">Ahora mismo ahí: {preview}</p>
          )}
        </form>
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
/* Sección: Tokens MCP                                                */
/* ------------------------------------------------------------------ */

/** Clave de caché de los tokens MCP propios; se recarga al crear o revocar uno. */
const CLAVE_TOKENS_MCP = ["sesion", "tokens-mcp"] as const;

/** Opciones de caducidad (horas). `null` = sin caducidad. */
const CADUCIDADES: { valor: string; etiqueta: string; horas: number | null }[] = [
  { valor: "30d", etiqueta: "30 días", horas: 24 * 30 },
  { valor: "90d", etiqueta: "90 días", horas: 24 * 90 },
  { valor: "1y", etiqueta: "1 año", horas: 24 * 365 },
  { valor: "nunca", etiqueta: "Sin caducidad", horas: null },
];

/** Estado visible de un token: revocado / caducado / activo (en ese orden de prioridad). */
function estadoToken(t: TokenMcp): { texto: string; variante: "error" | "aviso" | "ok" } {
  if (t.revocado) return { texto: "Revocado", variante: "error" };
  if (t.expira && new Date(t.expira).getTime() <= Date.now())
    return { texto: "Caducado", variante: "aviso" };
  return { texto: "Activo", variante: "ok" };
}

/** Una fila del listado de tokens (sin el secreto): etiqueta, fechas, estado y botón de revocar. */
function FilaTokenMcp({
  token,
  onRevocar,
  ocupado,
}: {
  token: TokenMcp;
  onRevocar: () => void;
  ocupado: boolean;
}) {
  const estado = estadoToken(token);
  const vivo = estado.texto === "Activo";
  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium">{token.etiqueta}</p>
          <Badge variant={estado.variante}>{estado.texto}</Badge>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Creado {formatearFechaHora(token.creado)} · Último uso{" "}
          {formatearFechaHora(token.ultimo_uso)} ·{" "}
          {token.expira ? `Caduca ${formatearFechaHora(token.expira)}` : "Sin caducidad"}
        </p>
      </div>
      {vivo && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="shrink-0 text-muted-foreground hover:text-destructive"
          disabled={ocupado}
          onClick={onRevocar}
          aria-label={`Revocar ${token.etiqueta}`}
        >
          {ocupado ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
        </Button>
      )}
    </div>
  );
}

/** Diálogo del token recién emitido (se muestra UNA vez): un comando listo para pegar y un
 *  único botón que lo copia y cierra. Pensado para gente no técnica: cuanto más simple, mejor. */
function DialogoTokenNuevo({ token, onCerrar }: { token: string | null; onCerrar: () => void }) {
  // El MCP operativo se sirve en `/mcp` de esta misma instancia; el comando lleva el token dentro.
  const comando = token
    ? `claude mcp add --transport http keni-social ${window.location.origin}/mcp --header "Authorization: Bearer ${token}"`
    : "";

  // Único botón: copia el comando y cierra.
  const copiarYCerrar = async () => {
    if (comando) {
      try {
        await navigator.clipboard.writeText(comando);
        toast.success("Comando copiado.");
      } catch {
        toast.error("No se pudo copiar al portapapeles.");
      }
    }
    onCerrar();
  };

  return (
    <Dialog open={token !== null} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Conecta Claude Code</DialogTitle>
          <DialogDescription>
            Cópialo ahora: por seguridad no se vuelve a mostrar.
          </DialogDescription>
        </DialogHeader>

        <code className="block max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-md border bg-muted px-3 py-2 font-mono text-xs">
          {comando}
        </code>

        <ol className="list-decimal space-y-1.5 pl-5 text-sm text-muted-foreground">
          <li>Pulsa "Copiar comando y cerrar".</li>
          <li>Abre la app Terminal de tu Mac (Cmd + Espacio, escribe "Terminal" y Enter).</li>
          <li>Pega el comando (Cmd + V) y pulsa Enter.</li>
          <li>Abre Claude Code: keni-social ya estará conectado.</li>
        </ol>

        <DialogFooter>
          <Button type="button" onClick={() => void copiarYCerrar()}>
            <Copy className="h-4 w-4" />
            Copiar comando y cerrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SeccionTokensMcp() {
  const queryClient = useQueryClient();
  const [etiqueta, setEtiqueta] = React.useState("");
  const [caducidad, setCaducidad] = React.useState("90d");
  // Secreto recién emitido: se enseña UNA vez en el diálogo y luego se descarta.
  const [secreto, setSecreto] = React.useState<string | null>(null);

  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_TOKENS_MCP,
    queryFn: ({ signal }) => api.tokensMcp(signal),
  });

  const tokens = data?.tokens ?? [];

  const recargar = () => queryClient.invalidateQueries({ queryKey: CLAVE_TOKENS_MCP });

  const crear = useMutation({
    mutationFn: () => {
      const horas = CADUCIDADES.find((c) => c.valor === caducidad)?.horas ?? null;
      return api.crearTokenMcp({
        etiqueta: etiqueta.trim(),
        ...(horas !== null ? { expira_horas: horas } : {}),
      });
    },
    onSuccess: async (resp) => {
      setSecreto(resp.token);
      setEtiqueta("");
      await recargar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const revocar = useMutation({
    // El listado nunca trae el secreto: se revoca por el `id` opaco que sí expone.
    mutationFn: (id: string) => api.revocarTokenMcp(id),
    onSuccess: async () => {
      toast.success("Token revocado.");
      await recargar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeCrear = etiqueta.trim().length > 0 && !crear.isPending;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Tokens MCP</CardTitle>
        <CardDescription>
          Emite un token para conectar Claude Code (u otro cliente MCP) a la consola con tu
          identidad. Se presenta como bearer al servidor MCP. Cada token se muestra una sola vez.
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
            titulo="No se pudieron cargar tus tokens MCP"
            mensaje={mensajeError(error)}
            onReintentar={() => void refetch()}
            cargando={isFetching}
          />
        ) : tokens.length === 0 ? (
          <p className="rounded-md border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
            Aún no tienes ningún token MCP.
          </p>
        ) : (
          <div className="divide-y rounded-md border">
            {tokens.map((t) => (
              <div key={t.id} className="px-3">
                <FilaTokenMcp
                  token={t}
                  ocupado={revocar.isPending && revocar.variables === t.id}
                  onRevocar={() => void alRevocar(t)}
                />
              </div>
            ))}
          </div>
        )}

        <form
          className="flex flex-col gap-2 sm:flex-row sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            if (puedeCrear) crear.mutate();
          }}
          noValidate
        >
          <div className="flex-1 space-y-1.5">
            <Label htmlFor="token-etiqueta">Etiqueta</Label>
            <Input
              id="token-etiqueta"
              placeholder="Claude Code de mi laptop…"
              value={etiqueta}
              maxLength={120}
              onChange={(e) => setEtiqueta(e.target.value)}
              disabled={crear.isPending}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="token-caducidad">Caducidad</Label>
            <Select value={caducidad} onValueChange={setCaducidad} disabled={crear.isPending}>
              <SelectTrigger id="token-caducidad" className="sm:w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CADUCIDADES.map((c) => (
                  <SelectItem key={c.valor} value={c.valor}>
                    {c.etiqueta}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button type="submit" disabled={!puedeCrear}>
            {crear.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plug className="h-4 w-4" />
            )}
            Crear token
          </Button>
        </form>
      </CardContent>

      <DialogoTokenNuevo token={secreto} onCerrar={() => setSecreto(null)} />
    </Card>
  );

  async function alRevocar(t: TokenMcp) {
    const ok = await confirmar({
      titulo: "Revocar token MCP",
      mensaje: `¿Revocar "${t.etiqueta}"? El cliente que lo use dejará de tener acceso de inmediato.`,
      destructivo: true,
      textoConfirmar: "Revocar",
    });
    if (ok) revocar.mutate(t.id);
  }
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
        <SeccionZonaHoraria />
        {usuario?.mfa_habilitado && <SeccionLlavesAcceso />}
        <SeccionTokensMcp />
      </div>
    </>
  );
}
