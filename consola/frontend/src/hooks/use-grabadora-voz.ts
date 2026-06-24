import * as React from "react";

/**
 * Grabadora de voz sobre `MediaRecorder` para capturar una nota desde el micrófono del dispositivo.
 *
 * Centraliza el ciclo de vida del stream y del recorder en refs (no estado) para no re-renderizar
 * en cada chunk: sólo `estado`, `segundos` y el blob resultante son observables por la UI. El blob
 * sale en `audio/webm` (formato por defecto del recorder), ya soportado por el backend, y se expone
 * además como `audioUrl` para previsualizar antes de transcribir. `limpiar()` libera el micrófono
 * (apaga el indicador del navegador) y revoca la URL; debe llamarse al cerrar el diálogo.
 */
export type EstadoGrabadora = "idle" | "grabando" | "listo";

export interface Grabadora {
  estado: EstadoGrabadora;
  segundos: number;
  audioBlob: Blob | null;
  audioUrl: string | null;
  soportado: boolean;
  iniciar: () => Promise<void>;
  detener: () => void;
  reset: () => void;
  limpiar: () => void;
}

export function useGrabadoraVoz(): Grabadora {
  const [estado, setEstado] = React.useState<EstadoGrabadora>("idle");
  const [segundos, setSegundos] = React.useState(0);
  const [audioBlob, setAudioBlob] = React.useState<Blob | null>(null);
  const [audioUrl, setAudioUrl] = React.useState<string | null>(null);

  const streamRef = React.useRef<MediaStream | null>(null);
  const recorderRef = React.useRef<MediaRecorder | null>(null);
  const chunksRef = React.useRef<Blob[]>([]);
  const timerRef = React.useRef<ReturnType<typeof setInterval> | null>(null);
  const urlRef = React.useRef<string | null>(null);

  const soportado =
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices &&
    typeof window !== "undefined" &&
    "MediaRecorder" in window;

  const pararTimer = React.useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const revocarUrl = React.useCallback(() => {
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
  }, []);

  const liberarStream = React.useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const iniciar = React.useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;
    chunksRef.current = [];
    const recorder = new MediaRecorder(stream);
    recorderRef.current = recorder;
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
      revocarUrl();
      const url = URL.createObjectURL(blob);
      urlRef.current = url;
      setAudioBlob(blob);
      setAudioUrl(url);
      setEstado("listo");
      liberarStream();
    };
    recorder.start();
    setSegundos(0);
    setEstado("grabando");
    pararTimer();
    timerRef.current = setInterval(() => setSegundos((s) => s + 1), 1000);
  }, [liberarStream, pararTimer, revocarUrl]);

  const detener = React.useCallback(() => {
    pararTimer();
    recorderRef.current?.stop();
  }, [pararTimer]);

  const reset = React.useCallback(() => {
    revocarUrl();
    setAudioBlob(null);
    setAudioUrl(null);
    setSegundos(0);
    setEstado("idle");
  }, [revocarUrl]);

  const limpiar = React.useCallback(() => {
    pararTimer();
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.onstop = null;
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    chunksRef.current = [];
    liberarStream();
    revocarUrl();
    setAudioBlob(null);
    setAudioUrl(null);
    setSegundos(0);
    setEstado("idle");
  }, [liberarStream, pararTimer, revocarUrl]);

  React.useEffect(() => limpiar, [limpiar]);

  return { estado, segundos, audioBlob, audioUrl, soportado, iniciar, detener, reset, limpiar };
}
