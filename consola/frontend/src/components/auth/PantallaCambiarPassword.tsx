import { KeyRound, Loader2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import { useSesion } from "@/hooks/sesion-contexto";

/** Longitud mínima razonable para la nueva contraseña (validación de UI). */
const MIN_PASSWORD = 8;

/**
 * Pantalla de cambio de contraseña forzado. Se muestra a pantalla completa (sin
 * el shell) cuando el usuario tiene `debe_cambiar_password = true`: hasta que no
 * cambie la contraseña no puede usar la app. Al terminar, refresca el `me` para
 * que `debe_cambiar_password` pase a `false` y la app continúe.
 */
export function PantallaCambiarPassword() {
  const { usuario, refrescar } = useSesion();
  const [actual, setActual] = React.useState("");
  const [nueva, setNueva] = React.useState("");
  const [confirmar, setConfirmar] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [enviando, setEnviando] = React.useState(false);

  const coincide = nueva.length > 0 && nueva === confirmar;
  const suficiente = nueva.length >= MIN_PASSWORD;
  const puedeEnviar = actual.length > 0 && coincide && suficiente && !enviando;

  async function alEnviar(e: React.FormEvent) {
    e.preventDefault();
    if (!puedeEnviar) return;
    setEnviando(true);
    setError(null);
    try {
      await api.cambiarPassword({ password_actual: actual, password_nueva: nueva });
      toast.success("Contraseña actualizada.");
      // Refresca el usuario para que `debe_cambiar_password` se quede en false.
      await refrescar();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("No se pudo cambiar la contraseña. Vuelve a intentarlo.");
      }
      setEnviando(false);
    }
  }

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1.5 text-center">
          <div className="flex justify-center">
            <KeyRound className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
          </div>
          <CardTitle className="text-xl">Cambia tu contraseña</CardTitle>
          <p className="text-sm text-muted-foreground">
            {usuario
              ? `Por seguridad, ${usuario.usuario} debe elegir una contraseña nueva antes de continuar.`
              : "Por seguridad, elige una contraseña nueva antes de continuar."}
          </p>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={alEnviar} noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="pwd-actual">Contraseña actual</Label>
              <Input
                id="pwd-actual"
                type="password"
                autoComplete="current-password"
                autoFocus
                value={actual}
                onChange={(e) => setActual(e.target.value)}
                disabled={enviando}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pwd-nueva">Contraseña nueva</Label>
              <Input
                id="pwd-nueva"
                type="password"
                autoComplete="new-password"
                value={nueva}
                onChange={(e) => setNueva(e.target.value)}
                disabled={enviando}
              />
              <p className="text-xs text-muted-foreground">Mínimo {MIN_PASSWORD} caracteres.</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pwd-confirmar">Repite la contraseña nueva</Label>
              <Input
                id="pwd-confirmar"
                type="password"
                autoComplete="new-password"
                value={confirmar}
                onChange={(e) => setConfirmar(e.target.value)}
                disabled={enviando}
              />
              {confirmar.length > 0 && !coincide && (
                <p className="text-xs text-destructive">Las contraseñas no coinciden.</p>
              )}
            </div>

            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}

            <Button type="submit" className="w-full" disabled={!puedeEnviar}>
              {enviando ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Cambiar contraseña
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
