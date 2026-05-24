// Feature Carpetas — JS vanilla. Solo fetch al endpoint local de crear carpeta.
// Reutiliza los helpers GLOBALES de consola.js (postJSON, fijarEstado,
// marcarCargando): no se redefinen aquí. Sin librerías ni red externa.
"use strict";

async function crearCarpeta(form) {
  const estado = form.querySelector(".estado");
  const exito = form.querySelector(".carpetas-exito");
  const boton = form.querySelector("button[type=submit]");
  const nombre = form.querySelector("input[name=nombre]").value;
  const plantilla = form.querySelector("select[name=plantilla]").value;
  marcarCargando(boton, true);
  if (exito) exito.hidden = true;
  fijarEstado(estado, "Creando carpeta...", "");
  try {
    const { ok, datos } = await postJSON("/api/carpetas/crear", {
      nombre: nombre,
      plantilla: plantilla,
    });
    if (ok) {
      fijarEstado(estado, "", "");
      if (exito) {
        exito.innerHTML =
          (datos.mensaje || "Carpeta creada.") +
          ' Ve a <a href="/proyectos">Proyectos</a> para editar su contexto.';
        exito.hidden = false;
      }
      form.querySelector("input[name=nombre]").value = "";
    } else {
      fijarEstado(estado, datos.error || "No se pudo crear la carpeta.", "error");
    }
  } finally {
    marcarCargando(boton, false);
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
