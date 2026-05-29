"""Adaptador de PUBLICACION / PROGRAMACION via **Metricool** (scheduler API).

╔══════════════════════════════════════════════════════════════════════════╗
║  SEGURIDAD — ESTO PUBLICA. LEER ANTES DE TOCAR.                            ║
║                                                                            ║
║  `programar(borrador, dry_run=True)` corre en DRY-RUN POR DEFECTO.         ║
║   - En dry-run NO se hace NINGUNA peticion de red: se devuelve la peticion ║
║     EXACTA que se enviaria (`PeticionProgramada`), con el cuerpo completo  ║
║     pero SIN el token (que va en la cabecera `X-Mc-Auth`, nunca en el body).║
║   - Una peticion REAL (POST) ocurre SOLO si `dry_run=False` Y la marca     ║
║     tiene credenciales completas (`user_token` + `user_id` + `blog_id`).   ║
║     Si faltan, se lanza `ProgramacionNoConfigurada` ANTES de tocar la red. ║
║                                                                            ║
║  Postura del producto: el humano aprueba; nada se publica solo.            ║
╚══════════════════════════════════════════════════════════════════════════╝

Por que Metricool y no Graph API directo
=========================================
AMX ya esta en plan **Advanced** de Metricool (que habilita el API token). En vez
de pasar el App Review de Meta + auditoria de TikTok + tier de pago de X para
PUBLICAR directo en cada red (todo gated externamente), entregamos el post al
**scheduler de Metricool** con su fecha de publicacion y Metricool lo dispara. Asi:

- una sola integracion cubre Facebook, Instagram, X (twitter), TikTok y YouTube;
- la PROGRAMACION es nativa de Metricool (`publicationDate` + `autoPublish`), no
  necesitamos cola/agendador propio (a diferencia de `cola.ColaPublicacion`, que
  existe para el camino Meta-directo donde IG no agenda por API);
- reutiliza EXACTAMENTE el mismo token por marca que ya usa la LECTURA de metricas
  (`fuentes.metricol.FuenteMetricol`): cabecera `X-Mc-Auth` + query `userId`/`blogId`.

Contrato de la API (swagger oficial https://app.metricool.com/api/swagger.json):

    POST /v2/scheduler/posts?userId=<uid>&blogId=<bid>
    Headers: X-Mc-Auth: <user_token>
    Body (modelo `ScheduledPost`, campos REQUERIDOS: text, publicationDate, providers):
      {
        "text": "...",
        "publicationDate": {"dateTime": "2026-05-30T18:00:00", "timezone": "America/Mexico_City"},
        "providers": [{"network": "facebook"}, {"network": "instagram"}],
        "media": ["https://.../a.jpg"],          # array de URLs
        "mediaAltText": ["texto alternativo"],
        "autoPublish": true,                       # true => Metricool publica solo al vencer
        "draft": false,
        "saveExternalMediaFiles": true             # que Metricool ingiera las URLs externas
      }
    Respuesta: JsonOkResponseScheduledPost -> {"data": {"id", "providers": [{"network","status"}], ...}}
    `providers[].status` ∈ {PUBLISHED, PUBLISHING, PENDING, ERROR, DRAFT}.

SUPUESTOS SIN CONFIRMAR (no hay token real para validar contra la API en vivo;
mismo criterio que `fuentes.metricol`). Se AISLAN aqui para corregirlos en un solo
sitio contra la API real sin tocar el resto:
- **Media por URL externa.** Asumimos que `media` admite URLs publicas externas con
  `saveExternalMediaFiles=true`. Si Metricool exige subir el binario antes (a su
  media-library), ese paso se anade en `cuerpo_para` / un metodo `_subir_media`.
- **`autoPublish` semantica.** Asumimos `true` => Metricool publica automaticamente
  en `publicationDate`; `false` => queda como programado que requiere accion manual
  (o `draft=true` para guardarlo como borrador sin programar).
- **Datos por red obligatorios.** YouTube/TikTok pueden exigir `youtubeData`/
  `tiktokData` (p.ej. titulo/privacidad). v1 envia lo minimo; los `...Data` por red
  se anaden en `cuerpo_para` cuando se validen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

# NO se modifica `_http.py`: se importa de solo lectura.
from ..fuentes._http import cliente_http, log, post_json
from ..schema import Plataforma
from .modelos import MediaRef  # reutiliza la ref de media (solo URL), no el Borrador (Meta-only)

BASE = "https://app.metricool.com/api"
ENDPOINT_PROGRAMAR = "/v2/scheduler/posts"
# AMX/UnoTV operan en horario de Ciudad de Mexico; configurable por borrador.
TIMEZONE_DEF = "America/Mexico_City"

# Plataforma (keni) -> network (Metricool). Metricool usa "twitter" para X.
# (Mismo mapeo que `fuentes.metricol._RED_METRICOOL`; se duplica a proposito para
# NO acoplarse a un nombre privado de un modulo bajo trabajo paralelo.)
_RED_METRICOOL: dict[Plataforma, str] = {
    Plataforma.facebook: "facebook",
    Plataforma.instagram: "instagram",
    Plataforma.x: "twitter",
    Plataforma.tiktok: "tiktok",
    Plataforma.youtube: "youtube",
}

# Redes que NO admiten publicacion de solo-texto: exigen al menos un asset.
_EXIGEN_MEDIA: frozenset[Plataforma] = frozenset(
    {Plataforma.instagram, Plataforma.tiktok, Plataforma.youtube}
)


class BorradorMetricool(BaseModel):
    """Borrador multi-red listo para programar en Metricool. Lo aprueba un humano.

    A diferencia de `modelos.Borrador` (Meta-only: facebook|instagram), aqui un solo
    borrador puede ir a VARIAS redes a la vez (es lo que hace el scheduler de
    Metricool). No publica por si mismo; lo consume `AdaptadorPublicacionMetricool`.

    - `redes`: 1+ plataformas destino (facebook|instagram|x|tiktok|youtube).
    - `texto`: cuerpo del post (sin hashtags, que van aparte).
    - `media`: refs a imagenes/video (solo URL + descripcion); nunca binarios.
    - `hashtags`: lista normalizada (sin '#'); se anaden al texto final.
    - `publicar_en`: hora de publicacion (ISO). None => ahora (al ejecutar).
    - `timezone`: zona del `publicar_en` (defecto America/Mexico_City).
    - `auto_publish`: True => Metricool publica solo al vencer; False => requiere
      accion manual en Metricool.
    - `borrador`: True => se guarda como DRAFT en Metricool (no se programa).
    """

    redes: list[Plataforma]
    texto: str = ""
    media: list[MediaRef] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    publicar_en: datetime | None = None
    timezone: str = TIMEZONE_DEF
    auto_publish: bool = True
    borrador: bool = False

    @field_validator("redes")
    @classmethod
    def _redes_validas(cls, v: list[Plataforma]) -> list[Plataforma]:
        if not v:
            raise ValueError("BorradorMetricool.redes: indica al menos una red destino")
        no_soportadas = [r for r in v if r not in _RED_METRICOOL]
        if no_soportadas:
            soportadas = ", ".join(sorted(p.value for p in _RED_METRICOOL))
            malas = ", ".join(p.value for p in no_soportadas)
            raise ValueError(f"Redes no publicables via Metricool: {malas}. Soportadas: {soportadas}.")
        # Dedup preservando orden.
        vistas: list[Plataforma] = []
        for r in v:
            if r not in vistas:
                vistas.append(r)
        return vistas

    @field_validator("hashtags", mode="before")
    @classmethod
    def _normaliza_hashtags(cls, v: object) -> object:
        """Quita el '#' inicial, espacios y duplicados; preserva el orden."""
        if not isinstance(v, list):
            return v
        vistos: list[str] = []
        for h in v:
            h = str(h).strip().lstrip("#").strip()
            if h and h not in vistos:
                vistos.append(h)
        return vistos

    @model_validator(mode="after")
    def _coherencia(self) -> BorradorMetricool:
        # Debe haber algo que publicar.
        if not self.texto.strip() and not self.media:
            raise ValueError("BorradorMetricool vacio: necesita texto o al menos un asset de media")
        # Redes que exigen media no pueden ir solo-texto.
        exigen = [r for r in self.redes if r in _EXIGEN_MEDIA]
        if exigen and not self.media:
            redes = ", ".join(r.value for r in exigen)
            raise ValueError(f"{redes}: exige(n) media; el borrador no referencia ningun asset")
        return self

    def texto_final(self) -> str:
        """Texto + hashtags como saldria publicado (lo que se previsualiza)."""
        cuerpo = self.texto.strip()
        if not self.hashtags:
            return cuerpo
        etiquetas = " ".join(f"#{h}" for h in self.hashtags)
        return f"{cuerpo}\n\n{etiquetas}" if cuerpo else etiquetas

    def redes_metricool(self) -> list[str]:
        """Nombres de red en la nomenclatura de Metricool (x -> 'twitter')."""
        return [_RED_METRICOOL[r] for r in self.redes]


@dataclass
class PeticionProgramada:
    """La unica peticion HTTP que se enviaria al scheduler de Metricool.

    Es lo que devuelve el dry-run: `metodo`, `url`, `params` (userId/blogId, SIN
    token) y `body` (el `ScheduledPost`). El token NUNCA va en `body` ni en
    `params`: viaja en la cabecera `X-Mc-Auth`, que se inyecta justo antes del POST.
    """

    metodo: str
    url: str
    params: dict = field(default_factory=dict)
    body: dict = field(default_factory=dict)

    def como_dict(self) -> dict:
        return {"metodo": self.metodo, "url": self.url, "params": dict(self.params), "body": dict(self.body)}


@dataclass
class ResultadoProgramacion:
    """Resultado de `programar(...)`: si fue dry-run, que peticion se armo y, si fue
    real, la respuesta de Metricool (id del post + estado por red)."""

    dry_run: bool
    redes: list[str]
    peticion: PeticionProgramada
    respuesta: dict | None = None
    id_post: str | None = None
    estados: dict[str, str] = field(default_factory=dict)

    def como_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "redes": list(self.redes),
            "peticion": self.peticion.como_dict(),
            "respuesta": self.respuesta,
            "id_post": self.id_post,
            "estados": dict(self.estados),
        }


class ProgramacionNoConfigurada(RuntimeError):
    """Se pidio una programacion REAL (dry_run=False) sin credenciales de Metricool."""


class AdaptadorPublicacionMetricool:
    """Construye y (opcionalmente) ejecuta la programacion de un borrador en Metricool.

    Credenciales POR MARCA: cada marca de AMX es una cuenta Metricool distinta, con
    su propio `user_token` (cabecera `X-Mc-Auth`), `user_id` y `blog_id` (query
    params). Son las MISMAS que resuelve `config.MetricoolConfig.marcas_configuradas()`
    para la lectura de metricas; aqui se reciben ya resueltas para una marca.

    `programar(borrador, dry_run=True)` -> `ResultadoProgramacion`.
    Por defecto NO toca la red. Ver el banner de SEGURIDAD del modulo.
    """

    def __init__(self, creds: dict | None = None, cliente: httpx.Client | None = None):
        creds = creds or {}
        self._token = str(creds.get("user_token") or "")
        self._user_id = str(creds.get("user_id") or "")
        self._blog_id = str(creds.get("blog_id") or "")
        # El cliente solo se crea/usa en el camino real. En dry-run no se toca.
        self._cli_externo = cliente
        self._cli = cliente

    # --- disponibilidad -----------------------------------------------------
    def disponible(self) -> bool:
        """Hay credenciales completas => se PODRIA programar de verdad. Dry-run no lo necesita."""
        return bool(self._token and self._user_id and self._blog_id)

    # --- construccion del cuerpo (sin red) ----------------------------------
    def _params(self) -> dict:
        return {"userId": self._user_id, "blogId": self._blog_id}

    def cuerpo_para(self, b: BorradorMetricool, ahora: datetime | None = None) -> dict:
        """Construye el `ScheduledPost` EXACTO para el borrador. SIN red.

        Es el corazon del dry-run y tambien lo que el camino real ejecuta.
        """
        cuando = b.publicar_en or ahora or datetime.now()
        cuerpo: dict = {
            "text": b.texto_final(),
            "publicationDate": {
                "dateTime": cuando.replace(microsecond=0).isoformat(),
                "timezone": b.timezone,
            },
            "providers": [{"network": red} for red in b.redes_metricool()],
            "autoPublish": b.auto_publish,
            "draft": b.borrador,
        }
        if b.media:
            cuerpo["media"] = [m.url for m in b.media]
            alt = [(m.descripcion or "") for m in b.media]
            if any(alt):
                cuerpo["mediaAltText"] = alt
            # SUPUESTO (ver docstring): que Metricool ingiera las URLs externas.
            cuerpo["saveExternalMediaFiles"] = True
        return cuerpo

    def peticion_para(self, b: BorradorMetricool, ahora: datetime | None = None) -> PeticionProgramada:
        return PeticionProgramada(
            metodo="POST",
            url=f"{BASE}{ENDPOINT_PROGRAMAR}",
            params=self._params(),
            body=self.cuerpo_para(b, ahora),
        )

    # --- programacion -------------------------------------------------------
    def programar(
        self, b: BorradorMetricool, dry_run: bool = True, ahora: datetime | None = None
    ) -> ResultadoProgramacion:
        """Programa/publica un borrador via Metricool. DRY-RUN POR DEFECTO (no toca red).

        - dry_run=True (defecto): devuelve la peticion que se enviaria. CERO red.
        - dry_run=False: ejecuta el POST real. Requiere credenciales; si faltan, lanza
          `ProgramacionNoConfigurada` ANTES de cualquier llamada de red.
        """
        peticion = self.peticion_para(b, ahora)
        redes = b.redes_metricool()

        if dry_run:
            log.info(
                "DRY-RUN programacion Metricool [%s]: 1 peticion, sin red",
                ", ".join(redes),
            )
            return ResultadoProgramacion(dry_run=True, redes=redes, peticion=peticion)

        # --- camino REAL: solo aqui se toca la red ---------------------------
        if not self.disponible():
            raise ProgramacionNoConfigurada(
                "Programacion real pedida (dry_run=False) pero faltan credenciales de "
                "Metricool (user_token + user_id + blog_id). Configura la marca o usa dry_run=True."
            )
        cli = self._cliente()
        resp = post_json(
            cli,
            peticion.url,
            params=peticion.params,
            json=peticion.body,
            headers={"X-Mc-Auth": self._token},
        )
        datos = resp.get("data") if isinstance(resp, dict) else None
        if not isinstance(datos, dict):
            # Algunas respuestas devuelven el post en la raiz; parseo defensivo.
            datos = resp if isinstance(resp, dict) else {}
        id_post = datos.get("id")
        estados = {
            p["network"]: p.get("status", "")
            for p in (datos.get("providers") or [])
            if isinstance(p, dict) and p.get("network")
        }
        return ResultadoProgramacion(
            dry_run=False,
            redes=redes,
            peticion=peticion,
            respuesta=resp,
            id_post=str(id_post) if id_post is not None else None,
            estados=estados,
        )

    def _cliente(self) -> httpx.Client:
        if self._cli is None:
            self._cli = self._cli_externo or cliente_http()
        return self._cli
