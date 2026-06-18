import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, ShieldOff, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { MedidorPassword } from "@/components/auth/MedidorPassword";
import { confirmar } from "@/components/comunes/confirmar";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, mensajeError } from "@/lib/api";
import {
  descendientes,
  type IndiceUsuarios,
  metaZona,
  nombreVisible,
  zonaDe,
} from "@/lib/organigrama";
import {
  CARGOS_ORDENADOS,
  type CargoUsuario,
  ETIQUETA_CARGO,
  etiquetaCargo,
  type MarcaDisponible,
  type RolUsuario,
  type UsuarioAdmin,
} from "@/types";

import { formatearFecha } from "./lib";
import {
  CLAVE_USUARIOS,
  MIN_PASSWORD,
  ROL_LABEL,
  ROLES,
  SIN_CARGO,
  SIN_SUPERIOR,
} from "./tipos";

/**
 * Panel para editar a una persona. Cada control guarda al instante (PATCH del campo que
 * cambia), igual que la antigua tabla, e invalida la query para redibujar el árbol. Incluye
 * el selector de SUPERIOR (organigrama), que excluye a la propia persona y a sus
 * descendientes para no ofrecer un cambio que cerraría un ciclo (el backend también lo
 * rechaza). Abajo, una zona de acciones sensibles: resetear contraseña y eliminar.
 */
export function DialogoMiembro({
  usuario,
  usuarios,
  porId,
  hijos,
  idActual,
  catalogoMarcas,
  onCerrar,
}: {
  usuario: UsuarioAdmin | null;
  usuarios: UsuarioAdmin[];
  porId: IndiceUsuarios;
  hijos: Map<string, UsuarioAdmin[]>;
  idActual: string | null;
  catalogoMarcas: MarcaDisponible[];
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: CLAVE_USUARIOS });

  // Estado local del nombre (edición libre, se guarda al salir del campo).
  const [nombre, setNombre] = React.useState("");
  React.useEffect(() => {
    setNombre((usuario?.nombre ?? "").trim());
  }, [usuario]);

  // Estado local del nombre de cuenta (login). Igual que el nombre, se guarda al salir del
  // campo; si el backend rechaza (vacío/duplicado), revertimos al valor real.
  const [login, setLogin] = React.useState("");
  React.useEffect(() => {
    setLogin(usuario?.usuario ?? "");
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

  // Cambio del login: mutación propia para poder REVERTIR el campo si falla (409 duplicado,
  // 400 vacío). Reusar `guardar` no permitiría devolver el input a su valor anterior.
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
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const resetear = useMutation({
    mutationFn: (password: string) => api.actualizarUsuario(usuario!.id, { password }),
    onSuccess: () => toast.success("Contraseña restablecida"),
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Reset de la verificación en dos pasos: borra todas las passkeys y códigos de
  // recuperación del usuario (rescate cuando pierde sus dispositivos y queda fuera).
  const resetearMfa = useMutation({
    mutationFn: () => api.actualizarUsuario(usuario!.id, { mfa_reset: true }),
    onSuccess: () => {
      invalidar();
      toast.success("Verificación en dos pasos restablecida");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const pedirResetMfa = async () => {
    if (
      await confirmar({
        titulo: "Resetear verificación en dos pasos",
        mensaje: `Se eliminarán todas las llaves de acceso y los códigos de recuperación de ${nombreVisible(usuario!)}. Úsalo cuando la persona pierde sus dispositivos y queda fuera de su cuenta. Tendrá que registrar una llave nueva.`,
        destructivo: true,
        textoConfirmar: "Resetear",
      })
    )
      resetearMfa.mutate();
  };

  const [password, setPassword] = React.useState("");
  const [confirmarBorrado, setConfirmarBorrado] = React.useState(false);
  React.useEffect(() => {
    setPassword("");
    setConfirmarBorrado(false);
  }, [usuario]);

  if (usuario === null) {
    return <Dialog open={false} onOpenChange={() => onCerrar()} />;
  }

  const esYoMismo = usuario.id === idActual;
  const cargoActual = (usuario.cargo ?? "") as CargoUsuario;
  const marcasUsuario = new Set(usuario.marcas ?? []);
  const superiorActual = (usuario.manager_id ?? "") || SIN_SUPERIOR;

  // Candidatos a superior: todos menos uno mismo y sus descendientes (evita ciclos).
  const prohibidos = descendientes(usuario.id, hijos);
  const candidatos = usuarios
    .filter((u) => u.id !== usuario.id && !prohibidos.has(u.id))
    .sort((a, b) => nombreVisible(a).localeCompare(nombreVisible(b), "es"));

  const zona = zonaDe(usuario, porId);
  const meta = metaZona(zona);

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
    <Dialog open onOpenChange={(v) => (!v ? onCerrar() : undefined)}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{nombreVisible(usuario)}</DialogTitle>
          <DialogDescription>
            @{usuario.usuario} · {meta.etiqueta}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-1">
          {/* Nombre */}
          <div className="space-y-1.5">
            <Label htmlFor="m-nombre">Nombre</Label>
            <Input
              id="m-nombre"
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

          {/* Nombre de cuenta (login con el que inicia sesión) */}
          <div className="space-y-1.5">
            <Label htmlFor="m-usuario">Usuario</Label>
            <Input
              id="m-usuario"
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

          <div className="grid grid-cols-2 gap-3">
            {/* Cargo */}
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

            {/* Rol de permisos */}
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
          </div>

          {/* Superior (organigrama) */}
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

          {/* Marcas */}
          <div className="space-y-1.5">
            <Label>Marcas</Label>
            <div className="grid grid-cols-2 gap-x-3 gap-y-2 rounded-md border p-3">
              {catalogoMarcas.length === 0 ? (
                <p className="col-span-2 text-sm text-muted-foreground">
                  No hay catálogo de marcas.
                </p>
              ) : (
                catalogoMarcas.map((m) => {
                  const id = `m-marca-${m.id}`;
                  return (
                    <div key={m.id} className="flex items-center gap-2">
                      <Checkbox
                        id={id}
                        checked={marcasUsuario.has(m.id)}
                        onCheckedChange={(v) => {
                          const nuevas = new Set(marcasUsuario);
                          if (v) nuevas.add(m.id);
                          else nuevas.delete(m.id);
                          guardar.mutate({ marcas: [...nuevas] });
                        }}
                      />
                      <Label htmlFor={id} className="cursor-pointer text-sm font-normal">
                        {m.nombre}
                      </Label>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Flags */}
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

          <p className="text-xs text-muted-foreground">
            Alta: {formatearFecha(usuario.creado)} · Último acceso:{" "}
            {formatearFecha(usuario.ultimo_acceso)}
          </p>

          {/* Zona sensible */}
          <div className="space-y-3 rounded-md border border-destructive/30 bg-destructive/5 p-3">
            <p className="text-sm font-medium">Acciones sensibles</p>
            <div className="flex flex-wrap items-end gap-2">
              <div className="flex-1 space-y-1">
                <Label htmlFor="m-pass" className="text-xs">
                  Nueva contraseña
                </Label>
                <Input
                  id="m-pass"
                  type="password"
                  value={password}
                  autoComplete="new-password"
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={`Mín. ${MIN_PASSWORD} caracteres`}
                />
                <MedidorPassword password={password} />
              </div>
              <Button
                variant="outline"
                disabled={password.length < MIN_PASSWORD || resetear.isPending}
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

            {confirmarBorrado ? (
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm">¿Eliminar a {nombreVisible(usuario)}?</span>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setConfirmarBorrado(false)}
                    disabled={eliminar.isPending}
                  >
                    Cancelar
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => eliminar.mutate()}
                    disabled={eliminar.isPending}
                  >
                    {eliminar.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                    Eliminar
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                disabled={esYoMismo}
                onClick={() => setConfirmarBorrado(true)}
              >
                <Trash2 className="h-4 w-4" />
                {esYoMismo ? "No puedes eliminar tu propia cuenta" : "Eliminar persona"}
              </Button>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar}>
            Cerrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
