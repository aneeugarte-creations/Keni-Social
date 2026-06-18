import { startRegistration } from "@simplewebauthn/browser";
import { Fingerprint, Loader2, ShieldCheck } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";

/**
 * Pantalla de inscripción de passkey FORZADA. Se muestra a pantalla completa (sin el shell)
 * cuando el usuario tiene `debe_inscribir_mfa = true`: el admin le exige segundo factor y aún
 * no tiene ninguna llave. Hasta registrar una passkey no puede usar la app.
 *
 * Flujo: pide opciones de registro -> ceremonia WebAuthn (Face ID / huella / llave) -> el
 * backend verifica y guarda la credencial; al ser la PRIMERA, devuelve los códigos de
 * recuperación, que se muestran una sola vez. Cuando el usuario confirma que los guardó,
 * refresca el `me` para que `debe_inscribir_mfa` pase a `false` y la app continúe.
 */
export function PantallaInscribirMfa() {
  const { refrescar } = useSesion();
  const [nombre, setNombre] = React.useState("");
  const [recovery, setRecovery] = React.useState<string[] | null>(null);
  const [registrada, setRegistrada] = React.useState(false);
  const [enviando, setEnviando] = React.useState(false);

  async function registrar(e: React.FormEvent) {
    e.preventDefault();
    if (enviando) return;
    setEnviando(true);
    try {
      const optionsJSON = await api.mfaRegistroOpciones();
      const credential = await startRegistration({
        optionsJSON: optionsJSON as unknown as Parameters<typeof startRegistration>[0]["optionsJSON"],
      });
      const r = await api.mfaRegistroVerificar(credential, nombre.trim());
      setRegistrada(true);
      toast.success("Llave de acceso registrada.");
      if (r.recovery_codes && r.recovery_codes.length > 0) {
        // Hay códigos que mostrar una sola vez: el usuario los confirma antes de entrar.
        setRecovery(r.recovery_codes);
      } else {
        await refrescar();
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "NotAllowedError") {
        toast.error("Registro cancelado.");
      } else {
        toast.error(mensajeError(err));
      }
      setEnviando(false);
    }
  }

  return (
    <div className="flex min-h-dvh w-full items-center justify-center bg-background px-4 py-8">
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1.5 text-center">
          <div className="flex justify-center">
            <ShieldCheck className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
          </div>
          <CardTitle className="text-xl">Registra una llave de acceso</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {recovery ? (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Guarda estos códigos de recuperación en un lugar seguro.{" "}
                <span className="font-medium">No volverán a mostrarse</span>. Te permiten entrar si
                pierdes el dispositivo.
              </p>
              <ul className="grid grid-cols-2 gap-1 rounded-lg border border-border p-3 font-mono text-sm">
                {recovery.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
              <Button
                className="w-full"
                disabled={enviando}
                onClick={() => {
                  // La passkey ya está registrada: una recarga limpia relee `me` (sin caché,
                  // `debe_inscribir_mfa=false`) y entra a la consola. Es a prueba de balas (no
                  // depende de que la puerta de React transicione) para no atrapar al usuario.
                  setEnviando(true);
                  window.location.reload();
                }}
              >
                {enviando ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Ya los guardé, continuar
              </Button>
            </div>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                Tu cuenta necesita verificación en dos pasos. Registra una llave de acceso (Face
                ID, huella o llave de seguridad) para proteger tu cuenta y poder entrar.
              </p>
              <form className="space-y-3" onSubmit={registrar} noValidate>
                <div className="space-y-1.5">
                  <Label htmlFor="inscribir-nombre-llave">Nombre de la llave</Label>
                  <Input
                    id="inscribir-nombre-llave"
                    placeholder="Opcional: iPhone, laptop…"
                    value={nombre}
                    onChange={(e) => setNombre(e.target.value)}
                    disabled={enviando || registrada}
                  />
                </div>
                <Button type="submit" className="w-full" disabled={enviando || registrada}>
                  {enviando ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Fingerprint className="h-4 w-4" />
                  )}
                  Registrar llave de acceso
                </Button>
              </form>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
