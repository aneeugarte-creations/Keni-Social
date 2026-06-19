import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { startRegistration } from "@simplewebauthn/browser";
import {
  Info,
  KeyRound,
  ShieldAlert,
  ShieldOff,
  Smartphone,
  Trash2,
  UserCog,
} from "lucide-react";
import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { MedidorPassword } from "@/components/auth/MedidorPassword";
import { confirmar } from "@/components/comunes/confirmar";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { TituloPagina } from "@/components/layout/encabezado";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { Tooltip } from "@/components/ui/tooltip";
import { useSesion } from "@/hooks/sesion-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";
import {
  descendientes,
  hijosPorManager,
  indexarPorId,
  nombreVisible,
} from "@/lib/organigrama";
import {
  CARGOS_ORDENADOS,
  type CargoUsuario,
  type CredencialPasskey,
  ETIQUETA_CARGO,
  etiquetaCargo,
  type RolUsuario,
} from "@/types";

import { formatearFecha } from "./lib";
import { SelectorMarcas } from "./SelectorMarcas";
import {
  CLAVE_CONFIG_USUARIOS,
  CLAVE_MFA_ADMIN,
  CLAVE_OPCIONES_MARCAS,
  CLAVE_PASSWORD_MIN,
  CLAVE_USUARIOS,
  MIN_PASSWORD,
  SIN_CARGO,
  SIN_SUPERIOR,
} from "./tipos";

/** Centinela de rol en el Select: superadmin es un rol más (= admin + flag superadmin). */
const ROL_SUPERADMIN = "superadmin";
const ROL_OPCIONES: { valor: string; etiqueta: string }[] = [
  { valor: "editor", etiqueta: "Editor" },
  { valor: "admin", etiqueta: "Administrador" },
  { valor: ROL_SUPERADMIN, etiqueta: "Superadmin" },
];

/** Pequeño icono de ayuda con tooltip (para explicaciones que antes iban como subtexto). */
function Ayuda({ texto }: { texto: string }) {
  return (
    <Tooltip label={texto}>
      <button
        type="button"
        className="inline-flex rounded-full text-muted-foreground hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={texto}
      >
        <Info className="h-3.5 w-3.5" aria-hidden />
      </button>
    </Tooltip>
  );
}

/**
 * Subpágina de detalle de UNA persona (`/usuarios/:id`), a ancho completo. Cada control guarda al
 * instante (PATCH del campo que cambia) e invalida la lista. El rol es un único selector donde
 * superadmin es un rol más (admin + flag). El selector de SUPERIOR excluye a la persona y a sus
 * descendientes (evita ciclos; el backend también lo rechaza). Al final, una zona de acciones
 * sensibles: resetear contraseña, resetear las llaves de acceso y eliminar. Solo superadmin.
 */
export default function UsuarioDetalle() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { usuario: actual, cargando } = useSesion();
  const esSuperadmin = actual?.es_superadmin === true;
  const volver = () => navigate("/usuarios");

  const query = useQuery({
    queryKey: CLAVE_USUARIOS,
    queryFn: ({ signal }) => api.usuarios(signal),
    enabled: esSuperadmin,
  });

  const marcasQuery = useQuery({
    queryKey: CLAVE_OPCIONES_MARCAS,
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    select: (data) => data.marcas,
    staleTime: 5 * 60 * 1000,
    enabled: esSuperadmin,
  });

  // Mínimo de contraseña efectivo (config global). Cae a MIN_PASSWORD si aún no llegó.
  const configQuery = useQuery({
    queryKey: CLAVE_CONFIG_USUARIOS,
    queryFn: ({ signal }) => api.configuracionUsuarios(signal),
    select: (data) => data.ajustes,
    staleTime: 5 * 60 * 1000,
    enabled: esSuperadmin,
  });
  const minPassword = React.useMemo(() => {
    const ajuste = configQuery.data?.find((a) => a.clave === CLAVE_PASSWORD_MIN);
    return typeof ajuste?.valor === "number" ? ajuste.valor : MIN_PASSWORD;
  }, [configQuery.data]);
  // Política de ADMINS: si está activa, a un administrador se le exige passkey y su toggle se
  // muestra exigido y bloqueado (no se le puede eximir mientras la política esté activa). El
  // «passkey para todo el equipo» ya NO bloquea: es una acción masiva y el flag individual manda.
  const mfaAdmin = React.useMemo(
    () => configQuery.data?.find((a) => a.clave === CLAVE_MFA_ADMIN)?.valor === true,
    [configQuery.data],
  );

  // Llaves de acceso (passkeys) registradas por ESTA persona: el superadmin las ve para borrar
  // una concreta (rescate cuando no puede usarla en un equipo). La lista no trae secretos.
  const passkeysQuery = useQuery({
    queryKey: ["usuario-passkeys", id],
    queryFn: ({ signal }) => api.usuarioPasskeys(id, signal),
    enabled: esSuperadmin && Boolean(id),
    select: (data) => data.credenciales,
  });

  const usuarios = query.data?.usuarios ?? [];
  const porId = React.useMemo(() => indexarPorId(usuarios), [usuarios]);
  const hijos = React.useMemo(() => hijosPorManager(usuarios), [usuarios]);
  const usuario = porId.get(id) ?? null;
  const catalogoMarcas = marcasQuery.data ?? [];

  const invalidar = () => void queryClient.invalidateQueries({ queryKey: CLAVE_USUARIOS });

  // --- Estado local de los campos de texto (se guardan al salir del campo). ---
  const [nombre, setNombre] = React.useState("");
  const [login, setLogin] = React.useState("");
  const [password, setPassword] = React.useState("");
  React.useEffect(() => {
    setNombre((usuario?.nombre ?? "").trim());
    setLogin(usuario?.usuario ?? "");
    setPassword("");
  }, [usuario]);

  const guardar = useMutation({
    mutationFn: (cuerpo: Parameters<typeof api.actualizarUsuario>[1]) =>
      api.actualizarUsuario(usuario!.id, cuerpo),
    onSuccess: () => {
      invalidar();
      toast.success("Cambios guardados");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Cambio del login: mutación propia para REVERTIR el campo si falla (409 duplicado, 400 vacío).
  const guardarUsuario = useMutation({
    mutationFn: (nuevoUsuario: string) =>
      api.actualizarUsuario(usuario!.id, { usuario: nuevoUsuario }),
    onSuccess: () => {
      invalidar();
      toast.success("Nombre de usuario actualizado");
    },
    onError: (e) => {
      setLogin(usuario?.usuario ?? "");
      toast.error(mensajeError(e));
    },
  });

  const eliminar = useMutation({
    mutationFn: () => api.eliminarUsuario(usuario!.id),
    onSuccess: () => {
      invalidar();
      toast.success(`${usuario ? nombreVisible(usuario) : "Usuario"} eliminado`);
      volver();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const resetear = useMutation({
    mutationFn: (pwd: string) => api.actualizarUsuario(usuario!.id, { password: pwd }),
    onSuccess: () => toast.success("Contraseña restablecida"),
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Reset del segundo factor: borra todas las llaves de acceso de la persona (rescate cuando
  // pierde sus dispositivos y queda fuera; la recuperación de cuenta es solo por este reset).
  const resetearMfa = useMutation({
    mutationFn: () => api.actualizarUsuario(usuario!.id, { mfa_reset: true }),
    onSuccess: () => {
      void passkeysQuery.refetch();
      invalidar();
      toast.success("Llaves de acceso restablecidas");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Borrado de UNA llave concreta (no todas): para cuando una persona perdió un dispositivo o no
  // puede usar esa passkey en un equipo, pero conserva otra. Si era la última, el backend apaga
  // `mfa_activo`.
  const borrarLlave = useMutation({
    mutationFn: (credId: string) => api.borrarPasskeyUsuario(usuario!.id, credId),
    onSuccess: () => {
      void passkeysQuery.refetch();
      invalidar();
      toast.success("Llave de acceso eliminada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Alta ASISTIDA: el superadmin LANZA la ceremonia (QR) para registrar una passkey en el TELÉFONO
  // de la persona. El navegador del superadmin muestra el QR; la persona lo escanea con su móvil y
  // confirma con Face ID/huella. La clave nace y se queda en SU teléfono; aquí solo se persiste su
  // parte pública contra la cuenta destino.
  const registrarAsistida = useMutation({
    mutationFn: async () => {
      const optionsJSON = await api.usuarioPasskeyAsistidaOpciones(usuario!.id);
      const credential = await startRegistration({
        optionsJSON: optionsJSON as unknown as Parameters<
          typeof startRegistration
        >[0]["optionsJSON"],
      });
      await api.usuarioPasskeyAsistidaVerificar(usuario!.id, credential, "Teléfono");
    },
    onSuccess: () => {
      void passkeysQuery.refetch();
      invalidar();
      toast.success("Llave de acceso registrada en el teléfono de la persona");
    },
    onError: (e) => {
      if (e instanceof DOMException && e.name === "NotAllowedError") {
        toast.error("Registro cancelado o no se escaneó el QR a tiempo.");
      } else {
        toast.error(mensajeError(e));
      }
    },
  });

  const pedirRegistrarAsistida = async () => {
    if (!usuario) return;
    if (
      await confirmar({
        titulo: "Registrar llave en el teléfono de la persona",
        mensaje: `Se abrirá un código QR. Pide a ${nombreVisible(usuario)} que lo escanee con su teléfono y confirme con Face ID o huella: la llave quedará en SU teléfono y en su cuenta. El teléfono y este equipo deben tener Bluetooth activado y estar cerca.`,
        textoConfirmar: "Mostrar QR",
      })
    )
      registrarAsistida.mutate();
  };

  const pedirResetMfa = async () => {
    if (!usuario) return;
    if (
      await confirmar({
        titulo: "Resetear las llaves de acceso",
        mensaje: `Se eliminarán todas las llaves de acceso de ${nombreVisible(usuario)}. Úsalo cuando la persona pierde sus dispositivos y queda fuera de su cuenta. Tendrá que registrar una llave nueva.`,
        destructivo: true,
        textoConfirmar: "Resetear",
      })
    )
      resetearMfa.mutate();
  };

  const pedirBorrarLlave = async (cred: CredencialPasskey) => {
    const etiqueta = cred.nombre?.trim() || "esta llave de acceso";
    if (
      await confirmar({
        titulo: "Eliminar llave de acceso",
        mensaje: `Se eliminará «${etiqueta}» de ${usuario ? nombreVisible(usuario) : "esta persona"}. Si es la única, dejará de pedírsele la passkey al iniciar sesión.`,
        destructivo: true,
        textoConfirmar: "Eliminar",
      })
    )
      borrarLlave.mutate(cred.id);
  };

  const pedirEliminar = async () => {
    if (!usuario) return;
    if (
      await confirmar({
        titulo: "Eliminar persona",
        mensaje: `¿Eliminar a ${nombreVisible(usuario)}? Esta acción no se puede deshacer.`,
        destructivo: true,
        textoConfirmar: "Eliminar",
      })
    )
      eliminar.mutate();
  };

  // --- Guards: superadmin, 403, carga, no encontrado. ---
  if (!cargando && !esSuperadmin) {
    return (
      <>
        <TituloPagina titulo="Usuario" icono={UserCog} onAtras={volver} />
        <EstadoVacio icono={ShieldAlert} titulo="No tienes permiso" />
      </>
    );
  }

  const esProhibido =
    query.isError && query.error instanceof ApiError && query.error.status === 403;
  if (esProhibido) {
    return (
      <>
        <TituloPagina titulo="Usuario" icono={UserCog} onAtras={volver} />
        <EstadoVacio icono={ShieldAlert} titulo="No tienes permiso" />
      </>
    );
  }

  if (query.isPending) {
    return (
      <>
        <TituloPagina titulo="Usuario" icono={UserCog} onAtras={volver} />
        <Skeleton className="h-96 w-full rounded-md" />
      </>
    );
  }

  if (!usuario) {
    return (
      <>
        <TituloPagina titulo="Usuario" icono={UserCog} onAtras={volver} />
        <EstadoVacio
          icono={UserCog}
          titulo="No se encontró la persona"
          texto="Puede que se haya eliminado."
          accion={
            <Button variant="outline" onClick={volver}>
              Volver a usuarios
            </Button>
          }
        />
      </>
    );
  }

  const esYoMismo = usuario.id === actual?.id;
  const cargoActual = (usuario.cargo ?? "") as CargoUsuario;
  const superiorActual = (usuario.manager_id ?? "") || SIN_SUPERIOR;
  const rolActual = usuario.superadmin ? ROL_SUPERADMIN : usuario.rol;

  // El flag individual MANDA siempre (también para admins): un superadmin puede eximir a quien no
  // pueda usar passkey en su equipo. A los admins se les recuerda que tenerla es lo recomendado.
  const notaPasskey =
    usuario.rol === "admin" && mfaAdmin
      ? "Recomendado para administradores; puedes eximir a esta persona si no puede usar passkey."
      : null;

  // Candidatos a superior: todos menos uno mismo y sus descendientes (evita ciclos).
  const prohibidos = descendientes(usuario.id, hijos);
  const candidatos = usuarios
    .filter((u) => u.id !== usuario.id && !prohibidos.has(u.id))
    .sort((a, b) => nombreVisible(a).localeCompare(nombreVisible(b), "es"));

  const guardarNombre = () => {
    const limpio = nombre.trim();
    if (limpio !== (usuario.nombre ?? "").trim()) guardar.mutate({ nombre: limpio });
  };

  const guardarLogin = () => {
    const limpio = login.trim();
    if (limpio === usuario.usuario) return;
    if (!limpio) {
      setLogin(usuario.usuario); // vacío no es válido: revertimos sin llamar al backend
      return;
    }
    guardarUsuario.mutate(limpio);
  };

  // Superadmin es un rol más: "superadmin" => admin + flag; los otros => su rol, sin flag.
  const cambiarRol = (valor: string) => {
    if (valor === ROL_SUPERADMIN) guardar.mutate({ rol: "admin", superadmin: true });
    else guardar.mutate({ rol: valor as RolUsuario, superadmin: false });
  };

  return (
    <>
      <TituloPagina titulo={nombreVisible(usuario)} icono={UserCog} onAtras={volver} />

      <div className="w-full space-y-6 pb-12">
        {/* Perfil */}
        <Card>
          <CardHeader>
            <CardTitle>Perfil</CardTitle>
            <CardDescription>@{usuario.usuario}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-6 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="d-nombre">Nombre</Label>
                <Input
                  id="d-nombre"
                  value={nombre}
                  placeholder={usuario.usuario}
                  maxLength={120}
                  onChange={(e) => setNombre(e.target.value)}
                  onBlur={guardarNombre}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                  }}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="d-usuario">Usuario</Label>
                <Input
                  id="d-usuario"
                  value={login}
                  maxLength={64}
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  onChange={(e) => setLogin(e.target.value)}
                  onBlur={guardarLogin}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                  }}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Cargo</Label>
                <Select
                  value={cargoActual === "" ? SIN_CARGO : cargoActual}
                  onValueChange={(v) =>
                    guardar.mutate({ cargo: (v === SIN_CARGO ? "" : v) as CargoUsuario })
                  }
                >
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder={etiquetaCargo("")} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={SIN_CARGO}>{etiquetaCargo("")}</SelectItem>
                    {CARGOS_ORDENADOS.map((c) => (
                      <SelectItem key={c} value={c}>
                        {ETIQUETA_CARGO[c]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Organización */}
        <Card>
          <CardHeader>
            <CardTitle>Organización</CardTitle>
            <CardDescription>Reporte, verticales y disponibilidad operativa.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-6 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Reporta a</Label>
                <Select
                  value={superiorActual}
                  onValueChange={(v) =>
                    guardar.mutate({ manager_id: v === SIN_SUPERIOR ? "" : v })
                  }
                >
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={SIN_SUPERIOR}>Sin superior (raíz)</SelectItem>
                    {candidatos.map((u) => (
                      <SelectItem key={u.id} value={u.id}>
                        {nombreVisible(u)}
                        {u.cargo ? ` · ${etiquetaCargo(u.cargo)}` : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Marcas</Label>
                <div>
                  <SelectorMarcas
                    marcas={usuario.marcas ?? []}
                    catalogo={catalogoMarcas}
                    onChange={(marcas) => guardar.mutate({ marcas })}
                  />
                </div>
              </div>
            </div>

            <div className="flex flex-wrap gap-x-8 gap-y-3">
              <label className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={Boolean(usuario.cobertura)}
                  onCheckedChange={(v) => guardar.mutate({ cobertura: Boolean(v) })}
                />
                Entra en la rota de turnos
              </label>
              <label className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={Boolean(usuario.puede_coordinar)}
                  onCheckedChange={(v) => guardar.mutate({ puede_coordinar: Boolean(v) })}
                />
                Puede coordinar
              </label>
            </div>
          </CardContent>
        </Card>

        {/* Permisos y seguridad */}
        <Card>
          <CardHeader>
            <CardTitle>Permisos y seguridad</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5">
                <Label>Rol</Label>
                <Ayuda texto="Superadmin es el único rol que puede gestionar usuarios; un administrador tiene el resto de permisos." />
              </div>
              <Select value={rolActual} onValueChange={cambiarRol} disabled={esYoMismo}>
                <SelectTrigger className="h-9 sm:max-w-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROL_OPCIONES.map((r) => (
                    <SelectItem key={r.valor} value={r.valor}>
                      {r.etiqueta}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-start justify-between gap-3">
              <div className="space-y-0.5">
                <div className="flex items-center gap-1.5">
                  <Label htmlFor="d-passkey" className="text-sm font-normal">
                    Requerir llave de acceso (passkey)
                  </Label>
                  <Ayuda texto="Si se exige y la persona aún no tiene una, deberá registrar una llave de acceso (Face ID, huella o llave de seguridad) la próxima vez que inicie sesión." />
                </div>
                <p className="text-xs text-muted-foreground">
                  {usuario.mfa_activo ? "Llave registrada." : "Sin llave aún."}
                  {notaPasskey ? ` ${notaPasskey}` : ""}
                </p>
              </div>
              <Switch
                id="d-passkey"
                aria-label="Requerir llave de acceso"
                checked={Boolean(usuario.mfa_requerido)}
                onCheckedChange={(v) => guardar.mutate({ mfa_requerido: v })}
              />
            </div>

            <p className="text-xs text-muted-foreground">
              Alta: {formatearFecha(usuario.creado)} · Último acceso:{" "}
              {formatearFecha(usuario.ultimo_acceso)}
            </p>
          </CardContent>
        </Card>

        {/* Llaves de acceso (passkeys) */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="h-4 w-4" aria-hidden />
              Llaves de acceso
            </CardTitle>
            <CardDescription>
              Passkeys con las que esta persona inicia sesión (Face ID, huella, Windows Hello o su
              teléfono). Puedes registrar una en su teléfono mostrando un QR, eliminar una concreta
              o todas. La clave siempre se genera en el dispositivo de la persona.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {passkeysQuery.isPending ? (
              <Skeleton className="h-12 w-full rounded-md" />
            ) : (passkeysQuery.data?.length ?? 0) === 0 ? (
              <p className="text-sm text-muted-foreground">Sin llaves de acceso registradas.</p>
            ) : (
              <ul className="divide-y rounded-md border">
                {passkeysQuery.data!.map((cred) => (
                  <li
                    key={cred.id}
                    className="flex items-center justify-between gap-3 px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm">
                        {cred.nombre?.trim() || "Llave sin nombre"}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Alta: {formatearFecha(cred.creada)}
                        {cred.ultimo_uso
                          ? ` · Último uso: ${formatearFecha(cred.ultimo_uso)}`
                          : ""}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      disabled={borrarLlave.isPending}
                      onClick={() => void pedirBorrarLlave(cred)}
                    >
                      <Trash2 className="h-4 w-4" />
                      Eliminar
                    </Button>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs text-muted-foreground">
              Para que el inicio de sesión DEJE de pedir la passkey hay que eliminar sus llaves;
              quitar «Requerir llave de acceso» solo evita que se le obligue a registrar una nueva.
            </p>
            <div className="flex flex-wrap gap-3">
              {actual?.mfa_habilitado && (
                <Button
                  size="sm"
                  disabled={registrarAsistida.isPending}
                  onClick={() => void pedirRegistrarAsistida()}
                >
                  {registrarAsistida.isPending ? (
                    <Spinner className="h-4 w-4" />
                  ) : (
                    <Smartphone className="h-4 w-4" />
                  )}
                  Registrar en su teléfono (QR)
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                disabled={resetearMfa.isPending || (passkeysQuery.data?.length ?? 0) === 0}
                onClick={pedirResetMfa}
              >
                {resetearMfa.isPending ? (
                  <Spinner className="h-4 w-4" />
                ) : (
                  <ShieldOff className="h-4 w-4" />
                )}
                Eliminar todas las llaves
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Acciones sensibles */}
        <Card className="border-destructive/30 bg-destructive/5">
          <CardHeader>
            <CardTitle>Acciones sensibles</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-0 flex-1 space-y-1 sm:max-w-sm">
                <Label htmlFor="d-pass" className="text-xs">
                  Nueva contraseña
                </Label>
                <Input
                  id="d-pass"
                  type="password"
                  value={password}
                  autoComplete="new-password"
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={`Mín. ${minPassword} caracteres`}
                />
                <MedidorPassword password={password} />
              </div>
              <Button
                variant="outline"
                disabled={password.length < minPassword || resetear.isPending}
                onClick={() => {
                  resetear.mutate(password);
                  setPassword("");
                }}
              >
                {resetear.isPending ? <Spinner className="h-4 w-4" /> : null}
                Resetear
              </Button>
            </div>

            <div>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                disabled={esYoMismo || eliminar.isPending}
                onClick={pedirEliminar}
              >
                {eliminar.isPending ? (
                  <Spinner className="h-4 w-4" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
                {esYoMismo ? "No puedes eliminar tu propia cuenta" : "Eliminar persona"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
