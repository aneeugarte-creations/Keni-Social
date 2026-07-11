/**
 * Panel de AUDIO del Estudio de video: separa el audio del clip BASE (volumen/silenciar
 * independientes) y permite añadir MÚSICA (una pista de audio que el render mezcla con `amix`).
 * Los mismos controles viven en el carril de audio del timeline; ambos editan el MISMO documento.
 */
import { Music, Trash2, Volume2, VolumeX } from "lucide-react";

import { EditorVideo } from "@/components/media/EditorVideo";
import { Label } from "@/components/ui/label";
import { Tooltip } from "@/components/ui/tooltip";
import { pistaAudio, segmentosBase, type ComposicionVideo } from "@/lib/video";

export interface PanelAudioProps {
  doc: ComposicionVideo;
  /** URL servible de la música (para el uploader). */
  musicaUrl: string;
  /** Volumen/silenciar del audio del clip base. */
  onAudioBase: (cambios: { volumen?: number; silenciar?: boolean }) => void;
  /** Subida/cambio del clip de música (clave + url). */
  onCambioMusica: (clave: string, url: string) => void;
  /** Volumen/silenciar de la música. */
  onVolumenMusica: (cambios: { volumen?: number; silenciar?: boolean }) => void;
  /** Quita la música. */
  onQuitarMusica: () => void;
  disabled?: boolean;
}

export function PanelAudio({
  doc,
  musicaUrl,
  onAudioBase,
  onCambioMusica,
  onVolumenMusica,
  onQuitarMusica,
  disabled,
}: PanelAudioProps) {
  const base = segmentosBase(doc)[0];
  const musica = pistaAudio(doc)?.clips[0];
  const volBase = base?.volumen ?? 1;
  const baseSilenciado = !!base?.silenciar;
  const volMusica = musica?.volumen ?? 1;
  const musicaSilenciada = !!musica?.silenciar;

  return (
    <div className="space-y-5">
      <div className="space-y-3">
        <Label className="flex items-center gap-1.5 text-sm font-semibold">
          <Volume2 className="h-4 w-4 text-muted-foreground" />
          Audio del vídeo
        </Label>
        {base ? (
          <ControlVolumen
            nombre="audio base"
            volumen={volBase}
            silenciado={baseSilenciado}
            disabled={disabled}
            onVolumen={(v) => onAudioBase({ volumen: v })}
            onSilenciar={(s) => onAudioBase({ silenciar: s })}
          />
        ) : (
          <p className="text-xs text-muted-foreground">Sube un clip base para separar su audio.</p>
        )}
      </div>

      <div className="space-y-3 border-t border-border pt-4">
        <Label className="flex items-center gap-1.5 text-sm font-semibold">
          <Music className="h-4 w-4 text-muted-foreground" />
          Música
        </Label>
        {musica ? (
          <div className="space-y-3">
            <ControlVolumen
              nombre="música"
              volumen={volMusica}
              silenciado={musicaSilenciada}
              disabled={disabled}
              onVolumen={(v) => onVolumenMusica({ volumen: v })}
              onSilenciar={(s) => onVolumenMusica({ silenciar: s })}
            />
            <button
              type="button"
              onClick={onQuitarMusica}
              disabled={disabled}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10 disabled:opacity-40"
            >
              <Trash2 className="h-3.5 w-3.5" /> Quitar música
            </button>
          </div>
        ) : (
          <EditorVideo
            video=""
            videoUrl={musicaUrl}
            onCambio={onCambioMusica}
            disabled={disabled}
            idPrefijo="musica"
            etiqueta="Música"
            compacto
          />
        )}
      </div>
    </div>
  );
}

/** Slider de volumen 0..100 % + botón de silenciar reutilizable (audio base / música). */
function ControlVolumen({
  nombre,
  volumen,
  silenciado,
  disabled,
  onVolumen,
  onSilenciar,
}: {
  /** Contexto para las etiquetas accesibles, p. ej. «audio base» o «música». */
  nombre: string;
  volumen: number;
  silenciado: boolean;
  disabled?: boolean;
  onVolumen: (v: number) => void;
  onSilenciar: (s: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Tooltip label={silenciado ? "Activar sonido" : "Silenciar"}>
        <button
          type="button"
          onClick={() => onSilenciar(!silenciado)}
          disabled={disabled}
          aria-pressed={silenciado}
          aria-label={silenciado ? `Activar sonido de ${nombre}` : `Silenciar ${nombre}`}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-accent disabled:opacity-40"
        >
          {silenciado ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
        </button>
      </Tooltip>
      <input
        type="range"
        min={0}
        max={1}
        step={0.01}
        value={silenciado ? 0 : volumen}
        disabled={disabled || silenciado}
        onChange={(e) => onVolumen(Number(e.target.value))}
        className="flex-1 disabled:opacity-40"
        aria-label={`Volumen del ${nombre}`}
      />
      <span className="w-10 text-right text-xs tabular-nums text-muted-foreground">
        {Math.round((silenciado ? 0 : volumen) * 100)}%
      </span>
    </div>
  );
}
