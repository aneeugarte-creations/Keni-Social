import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, ShieldAlert, ShieldOff, Trash2, UserCog } from "lucide-react";
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
import { Switch } from "@/components/ui/switch";
import { useSesion } from "@/hooks/sesion-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";
import {
  descendientes,
  hijosPorManager,
  indexarPorId,
  metaZona,
  nombreVisible,
  zonaDe,
} from "@/lib/organigrama";
import {
  CARGOS_ORDENADOS,
  type CargoUsuario,
  ETIQUETA_CARGO,
  etiquetaCargo,
  type RolUsuario,
} from "@/types";

import { AvatarPersona } from "./AvatarPersona";
import { formatearFecha } from "./lib";
import {
  CLAVE_CONFIG_USUARIOS,
  CLAVE_OPCIONES_MARCAS,
  CLAVE_PASSWORD_MIN,
  CLAVE_USUARIOS,
  MIN_PASSWORD,
  ROL_LABEL,
  ROLES,
  SIN_CARGO,
  SIN_SUPERIOR,
} from "./tipos";

/**
 * Subpágina de detalle de UNA persona (`/usuarios/:id`). Porta a ancho completo todo lo que
 * antes vivía en el popup de edición: cada control guarda al instante (PATCH del campo que
 * cambia) e invalida la lista. El selector de SUPERIOR excluye a la propia persona y a sus
 * descendientes para no ofrecer un cambio que cerraría un ciclo (el backend también lo rechaza).
 * Al final, una zona de acciones sensibles: resetear contraseña, resetear el segundo factor y
 * eliminar. Solo superadmin (el backend devuelve 403 como red de seguridad).
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

  // Reset del segundo factor: borra todas las passkeys de la persona (rescate cuando pierde
  // sus dispositivos y queda fuera; la recuperación de cuenta es solo por este reset).
  const resetearMfa = useMutation({
    mutationFn: () => api.actualizarUsuario(usuario!.id, { mfa_reset: true }),
    onSuccess: () => {
      invalidar();
      toast.success("Verificación en dos pasos restablecida");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const pedirResetMfa = async () => {
    if (!usuario) return;
    if (
      await confirmar({
        titulo: "Resetear verificación en dos pasos",
        mensaje: `Se eliminarán todas las llaves de acceso de ${nombreVisible(usuario)}. Úsalo cuando la persona pierde sus dispositivos y queda fuera de su cuenta. Tendrá que registrar una llave nueva.`,
        destructivo: true,
        textoConfirmar: "Resetear",
      })
    )
      resetearMfa.mutate();
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
  const marcasUsuario = new Set(usuario.marcas ?? []);
  const superiorActual = (usuario.manager_id ?? "") || SIN_SUPERIOR;

  // Candidatos a superior: todos menos uno mismo y sus descendientes (evita ciclos).
  const prohibidos = descendientes(usuario.id, hijos);
  const candidatos = usuarios
    .filter((u) => u.id !== usuario.id && !prohibidos.has(u.id))
    .sort((a, b) => nombreVisible(a).localeCompare(nombreVisible(b), "es"));

  const zona = zonaDe(usuario, porId);

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

  return (
    <>
      <TituloPagina titulo={nombreVisible(usuario)} icono={UserCog} onAtras={volver} />

      <div className="mx-auto max-w-3xl space-y-4 pb-10">
        {/* Cabecera con avatar tintado por zona. */}
        <div className="flex items-center gap-3">
          <AvatarPersona usuario={usuario} zona={zona} className="h-12 w-12 text-sm" />
          <div className="min-w-0">
            <p className="truncate text-base font-medium">{nombreVisible(usuario)}</p>
            <p className="truncate text-sm text-muted-foreground">
              @{usuario.usuario} · {metaZona(zona).etiqueta}
            </p>
          </div>
        </div>

        {/* Perfil */}
        <Card>
          <CardHeader>
            <CardTitle>Perfil</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
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
              <p className="text-xs text-muted-foreground">
                Con este nombre inicia sesión. Debe ser único; cambiarlo no cierra su sesión.
              </p>
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
          </CardContent>
        </Card>

        {/* Organización */}
        <Card>
          <CardHeader>
            <CardTitle>Organización</CardTitle>
            <CardDescription>Reporte, verticales y disponibilidad operativa.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
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
              <div className="grid grid-cols-2 gap-x-3 gap-y-2 rounded-md border p-3">
                {catalogoMarcas.length === 0 ? (
                  <p className="col-span-2 text-sm text-muted-foreground">
                    No hay catálogo de marcas.
                  </p>
                ) : (
                  catalogoMarcas.map((m) => {
                    const cid = `d-marca-${m.id}`;
                    return (
                      <div key={m.id} className="flex items-center gap-2">
                        <Checkbox
                          id={cid}
                          checked={marcasUsuario.has(m.id)}
                          onCheckedChange={(v) => {
                            const nuevas = new Set(marcasUsuario);
                            if (v) nuevas.add(m.id);
                            else nuevas.delete(m.id);
                            guardar.mutate({ marcas: [...nuevas] });
                          }}
                        />
                        <Label htmlFor={cid} className="cursor-pointer text-sm font-normal">
                          {m.nombre}
                        </Label>
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            <div className="flex flex-wrap gap-x-6 gap-y-2">
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
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label>Rol</Label>
              <Select
                value={usuario.rol}
                onValueChange={(v) => guardar.mutate({ rol: v as RolUsuario })}
                disabled={esYoMismo}
              >
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => (
                    <SelectItem key={r} value={r}>
                      {ROL_LABEL[r]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-start justify-between gap-3">
              <div className="space-y-0.5">
                <Label htmlFor="d-superadmin" className="text-sm font-normal">
                  Superadmin
                </Label>
                <p className="text-xs text-muted-foreground">
                  Único rol que puede gestionar usuarios.
                </p>
              </div>
              <Switch
                id="d-superadmin"
                aria-label="Superadmin"
                checked={Boolean(usuario.superadmin)}
                onCheckedChange={(v) => guardar.mutate({ superadmin: v })}
              />
            </div>

            <div className="flex items-start justify-between gap-3">
              <div className="space-y-0.5">
                <Label htmlFor="d-mfa-requerido" className="text-sm font-normal">
                  Requerir verificación en dos pasos (MFA)
                </Label>
                <p className="text-xs text-muted-foreground">
                  {usuario.mfa_activo ? "Llave registrada." : "Sin llave aún."} Si se exige y no
                  tiene llave, deberá inscribir una al iniciar sesión.
                </p>
              </div>
              <Switch
                id="d-mfa-requerido"
                aria-label="Requerir verificación en dos pasos"
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

        {/* Acciones sensibles */}
        <Card className="border-destructive/30 bg-destructive/5">
          <CardHeader>
            <CardTitle>Acciones sensibles</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-end gap-2">
              <div className="flex-1 space-y-1">
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
                {resetear.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Resetear
              </Button>
            </div>

            <Button
              variant="outline"
              size="sm"
              disabled={resetearMfa.isPending}
              onClick={pedirResetMfa}
            >
              {resetearMfa.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ShieldOff className="h-4 w-4" />
              )}
              Resetear verificación en dos pasos
            </Button>

            <div>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                disabled={esYoMismo || eliminar.isPending}
                onClick={pedirEliminar}
              >
                {eliminar.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
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
