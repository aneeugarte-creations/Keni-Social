"""Modelos del flujo de publicacion. Aislados aqui (NO se tocan en `schema.py`).

`Borrador` es el contrato entre "copy aprobado por un humano" y "peticion que se
enviaria a Meta". Reutiliza `Plataforma` del esquema compartido (solo lectura),
pero todos los modelos NUEVOS de publicacion viven en este archivo.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from ..schema import Plataforma

# Solo estas dos plataformas publican via Meta Graph API en este adaptador.
PLATAFORMAS_META: frozenset[Plataforma] = frozenset(
    {Plataforma.facebook, Plataforma.instagram}
)


class TipoMedia(StrEnum):
    """Tipo de un asset referenciado por el borrador."""

    imagen = "imagen"
    video = "video"


class MediaRef(BaseModel):
    """REFERENCIA a un asset de media — nunca el binario.

    Meta publica media por URL publica (`image_url` / `video_url`), no subiendo
    bytes en esta ruta. Por eso el borrador solo lleva la URL del asset (mas un
    texto alternativo opcional). En dry-run la URL ni se abre.
    """

    tipo: TipoMedia
    url: str
    descripcion: str | None = None

    @field_validator("url")
    @classmethod
    def _url_no_vacia(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("MediaRef.url no puede estar vacia")
        return v


class Borrador(BaseModel):
    """Borrador de una publicacion para UNA plataforma de Meta.

    Es lo que un humano aprueba. No publica nada por si mismo; lo consume
    `AdaptadorPublicacionMeta` (dry-run por defecto) o `ColaPublicacion`.

    - `plataforma`: facebook | instagram (otras se rechazan en validacion).
    - `cuenta`: id/handle del destino (Page ID de FB o IG User ID).
    - `texto`: el cuerpo del post (sin los hashtags, que van aparte).
    - `media`: refs a imagenes/video (solo URL + descripcion).
    - `hashtags`: lista normalizada (sin el `#`); se anaden al texto final.
    """

    plataforma: Plataforma
    cuenta: str
    texto: str = ""
    media: list[MediaRef] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)

    @field_validator("plataforma")
    @classmethod
    def _plataforma_es_meta(cls, v: Plataforma) -> Plataforma:
        if v not in PLATAFORMAS_META:
            permitidas = ", ".join(sorted(p.value for p in PLATAFORMAS_META))
            raise ValueError(
                f"Borrador para Meta solo admite {permitidas}; recibido {v.value!r}"
            )
        return v

    @field_validator("cuenta")
    @classmethod
    def _cuenta_no_vacia(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Borrador.cuenta (Page ID / IG User ID) es obligatorio")
        return v

    @field_validator("hashtags", mode="before")
    @classmethod
    def _normaliza_hashtags(cls, v: object) -> object:
        """Quita el `#` inicial, espacios y duplicados; preserva el orden."""
        if not isinstance(v, list):
            return v
        vistos: list[str] = []
        for h in v:
            h = str(h).strip().lstrip("#").strip()
            if h and h not in vistos:
                vistos.append(h)
        return vistos

    def texto_final(self) -> str:
        """Texto + hashtags como saldria publicado (lo que se previsualiza)."""
        cuerpo = self.texto.strip()
        if not self.hashtags:
            return cuerpo
        etiquetas = " ".join(f"#{h}" for h in self.hashtags)
        return f"{cuerpo}\n\n{etiquetas}" if cuerpo else etiquetas
