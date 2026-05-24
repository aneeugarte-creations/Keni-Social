// Feature Carpetas — JS vanilla. Solo fetch al endpoint local de crear carpeta.
// Sin librerias ni red externa (coherente con privacidad por diseno).
"use strict";

async function carpetasPostJSON(url, cuerpo) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cuerpo),
  });
  let datos = {};
  try {
    datos = await resp.json();
  } catch (e) {
    datos = {};
  }
  return { ok: resp.ok, datos };
}

function carpetasFijarEstado(el, texto, clase) {
  if (!el) return;
  el.textContent = texto || "";
  el.className = "estado" + (clase ? " " + clase : "");
}

async function crearCarpeta(form) {
  const estado = form.querySelector(".estado");
  const exito = form.querySelector(".carpetas-exito");
  const boton = form.querySelector("button[type=submit]");
  const nombre = form.querySelector("input[name=nombre]").value;
  const plantilla = form.querySelector("select[name=plantilla]").value;
  boton.disabled = true;
  if (exito) exito.hidden = true;
  carpetasFijarEstado(estado, "Creando carpeta...", "");
  const { ok, datos } = await carpetasPostJSON("/api/carpetas/crear", {
    nombre: nombre,
    plantilla: plantilla,
  });
  boton.disabled = false;
  if (ok) {
    carpetasFijarEstado(estado, "", "");
    if (exito) {
      exito.innerHTML =
        (datos.mensaje || "Carpeta creada.") +
        ' Ve a <a href="/proyectos">Proyectos</a> para editar su CLAUDE.md.';
      exito.hidden = false;
    }
    form.querySelector("input[name=nombre]").value = "";
  } else {
    carpetasFijarEstado(estado, datos.error || "No se pudo crear la carpeta.", "error");
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("form-carpetas");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      crearCarpeta(form);
    });
  }
});
