/**
 * Cliente SPA para Libro Matriz FP · DETP Jujuy
 * Migrado desde Cliente.html con soporte para el circuito oficial de emisión de certificados
 * y bandeja de entrada centralizada del rol 'titulos'.
 */

var estado = {
  sesion: null,
  cursos: [],
  curso: null,
  datos: null,
  pestania: 'notas',
  emailActual: localStorage.getItem('lm_email') || 'sge.detp.areapedagogica@jujuy.edu.ar',
  filtroBandeja: 'Pendiente'
};

var $ = function (id) { return document.getElementById(id); };

// Helper para llamadas a la API REST del backend
async function llamar(url, metodo, cuerpo) {
  metodo = metodo || 'GET';
  var headers = { 'Accept': 'application/json' };
  if (cuerpo) {
    headers['Content-Type'] = 'application/json';
  }
  if (estado.emailActual) {
    headers['X-User-Email'] = estado.emailActual;
  }

  var opt = { method: metodo, headers: headers };
  if (cuerpo && metodo !== 'GET') {
    opt.body = JSON.stringify(cuerpo);
  }

  var resp;
  try {
    resp = await fetch(url, opt);
  } catch (err) {
    throw new Error('No se pudo conectar con el servidor local. Verifica que el backend esté activo.');
  }

  var json;
  try {
    json = await resp.json();
  } catch (err) {
    throw new Error('Respuesta no válida del servidor.');
  }

  if (!resp.ok || json.ok === false) {
    throw new Error(json.error || ('Error en la solicitud HTTP ' + resp.status));
  }
  return json;
}

function esc(t) {
  return String(t == null ? '' : t)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

var tiempoAviso;
function avisar(texto, tipo) {
  var a = $('aviso');
  a.textContent = texto;
  a.className = 'aviso ' + (tipo || '');
  a.hidden = false;
  clearTimeout(tiempoAviso);
  tiempoAviso = setTimeout(function () { a.hidden = true; }, tipo === 'error' ? 9000 : 3500);
}

function problema(e) {
  avisar((e && e.message) ? e.message : String(e), 'error');
}

// ---------- INICIALIZACIÓN ----------
window.addEventListener('load', async function () {
  if ($('btnTopImportar')) {
    $('btnTopImportar').addEventListener('click', mostrarModalImportarExcel);
  }
  if ($('btnTopUsuarios')) {
    $('btnTopUsuarios').addEventListener('click', async function () {
      if (!estado.sesion || !estado.sesion.puedeAdministrarUsuarios) {
        estado.emailActual = 'sge.detp.areapedagogica@jujuy.edu.ar';
        localStorage.setItem('lm_email', estado.emailActual);
        await cargarUsuariosPrueba();
        await iniciarSesion();
      }
      verAdminUsuarios();
    });
  }
  await cargarUsuariosPrueba();
  await iniciarSesion();
});

async function cargarUsuariosPrueba() {
  try {
    var res = await llamar('/api/usuarios');
    var listaU = res.usuarios || [];
    var existe = listaU.some(function (u) {
      return u.Email.toLowerCase() === (estado.emailActual || '').toLowerCase();
    });
    if (!existe && listaU.length > 0) {
      estado.emailActual = listaU[0].Email;
      localStorage.setItem('lm_email', estado.emailActual);
    }
    var select = $('selectorUsuario');
    select.innerHTML = '<option value="">-- Cambiar Usuario / Rol (Pruebas) --</option>';
    listaU.forEach(function (u) {
      var opt = document.createElement('option');
      opt.value = u.Email;
      opt.textContent = (u.Nombre || u.Email) + ' [' + u.Rol + ']';
      if (u.Email.toLowerCase() === (estado.emailActual || '').toLowerCase()) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });

    select.onchange = function () {
      if (select.value) {
        estado.emailActual = select.value;
        localStorage.setItem('lm_email', select.value);
        iniciarSesion();
      }
    };
  } catch (err) {
    console.warn('No se pudo cargar la lista de usuarios para prueba:', err);
  }
}

async function iniciarSesion() {
  $('main').innerHTML = '<div class="cargando">Iniciando sesión…</div>';
  try {
    var r = await llamar('/api/inicio');
    estado.sesion = r.sesion;
    estado.cursos = r.cursos;
    estado.emailActual = r.sesion.email;

    $('usuario').innerHTML = '<b>' + esc(r.sesion.nombre) + '</b>' +
      '<span class="rol">' + esc(r.sesion.rol) + '</span>';

    // Si entra con rol 'titulos', llevarlo directamente a su bandeja de trabajo
    if (r.sesion.esTitulos) {
      verBandejaTitulos();
    } else {
      verCursos();
    }
  } catch (e) {
    $('main').innerHTML = '<div class="vacio">' + esc(e.message || e) +
      '<div style="margin-top:12px"><small>Configura tu <code>service_account.json</code> en <code>credentials/</code> y tu <code>PANEL_ID</code> en el archivo .env.</small></div></div>';
  }
}

$('volver').addEventListener('click', function () {
  if (estado.sesion && estado.sesion.esTitulos) {
    verBandejaTitulos();
  } else {
    verCursos();
  }
});

// ---------- LISTA DE CURSOS (ESCUELAS Y DIRECCIÓN) ----------
function verCursos() {
  estado.curso = null;
  $('migas').hidden = true;
  var m = $('main');
  var subtitulo = (estado.sesion && estado.sesion.verTodo)
    ? 'Acceso a todas las instituciones · ' + estado.cursos.length + ' curso(s).'
    : 'Acceso a tu institución · ' + estado.cursos.length + ' curso(s).';

  m.innerHTML =
    '<h1>Cursos</h1>' +
    '<p style="color:var(--suave);margin:0 0 12px">' + subtitulo + '</p>' +
    '<div class="acciones">' +
      '<button class="boton" id="btnNuevoCurso">+ Nuevo curso</button>' +
      '<button class="boton" id="btnImportarExcel" style="background:#137333">📥 Importar Viejo Excel</button>' +
      (estado.sesion.verTodo ? '<button class="boton suave" id="btnResumen">Resumen por institución</button>' : '') +
      '<button class="boton suave" id="btnTitulos">Certificados de Títulos</button>' +
      (estado.sesion.puedeAdministrarUsuarios ? '<button class="boton suave" id="btnUsuarios">👤 Administrar Usuarios</button>' : '') +
    '</div>' +
    '<input class="buscar" id="buscar" placeholder="Buscar por institución, oferta o CUE…">' +
    '<div class="tarjetas" id="lista"></div>';

  if ($('btnNuevoCurso')) $('btnNuevoCurso').addEventListener('click', mostrarModalNuevoCurso);
  if ($('btnImportarExcel')) $('btnImportarExcel').addEventListener('click', mostrarModalImportarExcel);
  if ($('btnResumen')) $('btnResumen').addEventListener('click', verResumen);
  if ($('btnTitulos')) $('btnTitulos').addEventListener('click', verBandejaTitulos);
  if ($('btnUsuarios')) $('btnUsuarios').addEventListener('click', verAdminUsuarios);
  $('buscar').addEventListener('input', pintarLista);
  pintarLista();
}

function pintarLista() {
  var q = ($('buscar').value || '').toLowerCase().trim();
  var cs = estado.cursos.filter(function (c) {
    return !q || (c.institucion + ' ' + c.oferta + ' ' + c.cue + ' ' + c.ciclo).toLowerCase().indexOf(q) >= 0;
  });
  $('lista').innerHTML = cs.length ? cs.map(function (c) {
    var cerrado = String(c.estado).toLowerCase() === 'cerrado';
    var claseEstado = cerrado ? 'cerrado' : 'abierto';
    return '<button class="tarjeta" data-id="' + esc(c.id) + '">' +
      '<span class="of">' + esc(c.oferta) + '</span>' +
      '<span class="inst">' + esc(c.institucion) + '</span>' +
      '<span class="meta">' + esc(c.ciclo) + ' · ' + esc(c.turno) + ' · ' + esc(c.division) + '</span>' +
      '<div><span class="etiqueta ' + claseEstado + '">' + esc(c.estado) + '</span></div></button>';
  }).join('') : '<div class="vacio">Ningún curso coincide con la búsqueda.</div>';

  Array.prototype.forEach.call(document.querySelectorAll('.tarjeta'), function (b) {
    b.addEventListener('click', function () { abrirCurso(b.dataset.id); });
  });
}

// ---------- DETALLE DE UN CURSO ----------
async function abrirCurso(id, pestaniaInicial) {
  $('main').innerHTML = '<div class="cargando">Abriendo el curso desde Google Drive…</div>';
  try {
    var r = await llamar('/api/curso/' + encodeURIComponent(id));
    var d = r.datos;
    estado.curso = d.curso;
    estado.datos = d;
    estado.pestania = pestaniaInicial || 'notas';
    $('migas').hidden = false;
    pintarCurso();
  } catch (e) {
    problema(e);
    verCursos();
  }
}

function pintarCurso() {
  var d = estado.datos, e = d.encabezado;
  $('main').innerHTML =
    '<h1>' + esc(e.oferta || estado.curso.oferta) + '</h1>' +
    '<dl class="ficha">' +
      '<dt>Establecimiento</dt><dd>' + esc(e.establecimiento) + (e.cue ? ' · CUE ' + esc(e.cue) : '') + '</dd>' +
      '<dt>Curso</dt><dd>' + esc(e.ciclo) + ' · ' + esc(e.turno) + ' · ' + esc(e.division) +
        ' · ' + d.estudiantes.length + ' estudiantes</dd>' +
      '<dt>Diseño curricular</dt><dd>' + esc(e.disenio) + '</dd>' +
    '</dl>' +
    '<div class="pestanias" role="tablist">' +
      '<button role="tab" data-p="notas">Registro Anual de Calificaciones</button>' +
      '<button role="tab" data-p="acta">Acta de Examen</button>' +
      '<button role="tab" data-p="analitico">Certificado</button>' +
      '<button role="tab" data-p="solicitudes">Circuito de Certificados</button>' +
    '</div><div class="panel" id="panel"></div>';

  Array.prototype.forEach.call(document.querySelectorAll('[role=tab]'), function (b) {
    b.addEventListener('click', function () {
      estado.pestania = b.dataset.p;
      pintarPestania();
    });
  });
  pintarPestania();
}

function pintarPestania() {
  Array.prototype.forEach.call(document.querySelectorAll('[role=tab]'), function (b) {
    b.setAttribute('aria-selected', b.dataset.p === estado.pestania);
  });
  if (estado.pestania === 'notas') pintarNotas();
  else if (estado.pestania === 'acta') pintarActa();
  else if (estado.pestania === 'analitico') pintarAnalitico();
  else if (estado.pestania === 'solicitudes') pintarSolicitudesCurso();
}

// ---------- PESTAÑA: REGISTRO ANUAL DE CALIFICACIONES (CON CONGELAMIENTO) ----------
// Regla: nota >= 7 → Aprobado | nota < 7 → Desaprobado | AUS → Ausente
function notaCondicion(val) {
  if (!val || val === '') return '';
  var v = String(val).trim().toUpperCase();
  if (v === 'AUS' || v === 'AUSENTE') return 'Ausente';
  var n = parseFloat(v);
  if (isNaN(n)) return '';
  return n >= 7 ? 'Aprobado' : 'Desaprobado';
}

function _etiquetaCuatrimestre(m) {
  var p = String(m.periodo || '').toLowerCase();
  if (m.cuatrimestre === 2 || p.indexOf('2') !== -1) return '2° Cuatrimestre';
  if (m.cuatrimestre === 3 || p.indexOf('3') !== -1) return '3° Cuatrimestre';
  if (p.indexOf('unico') !== -1 || p.indexOf('único') !== -1) return 'Cuatrimestre único';
  return '1° Cuatrimestre';
}

function _etiquetaCortaCuat(m) {
  var c = _etiquetaCuatrimestre(m);
  if (c.indexOf('2°') === 0) return '2°C';
  if (c.indexOf('3°') === 0) return '3°C';
  return '1°C';
}

function pintarNotas() {
  var d = estado.datos, editable = d.puedeCargar;
  if (!d.estudiantes.length) {
    $('panel').innerHTML =
      '<div class="vacio">' +
        '<p>El curso todavía no tiene estudiantes cargados en la pestaña RAC.</p>' +
        (editable
          ? '<button class="boton" style="margin-top:10px;background:#137333" onclick="mostrarModalNuevoEstudiante()">+ Agregar Alumno</button>'
          : '') +
      '</div>';
    return;
  }

  var filtroCuat = estado.filtroCuatrimestre || 'Todos';
  var cuatrimestresDisponibles = [];
  d.modulos.forEach(function (m) {
    var et = _etiquetaCuatrimestre(m);
    if (cuatrimestresDisponibles.indexOf(et) === -1) cuatrimestresDisponibles.push(et);
  });

  var modulosVisibles = d.modulos.filter(function (m) {
    if (filtroCuat === 'Todos') return true;
    return _etiquetaCuatrimestre(m) === filtroCuat;
  });
  if (!modulosVisibles.length) {
    modulosVisibles = d.modulos;
    filtroCuat = 'Todos';
  }

  // Agrupar módulos visibles por cuatrimestre para la fila superior del encabezado
  var gruposCuat = [];
  modulosVisibles.forEach(function (m) {
    var et = _etiquetaCuatrimestre(m);
    if (!gruposCuat.length || gruposCuat[gruposCuat.length - 1].nombre !== et) {
      gruposCuat.push({ nombre: et, cantidad: 1 });
    } else {
      gruposCuat[gruposCuat.length - 1].cantidad++;
    }
  });

  var thGrupos = gruposCuat.map(function (g) {
    var bg = g.nombre.indexOf('2°') === 0 ? '#d9ead3' : (g.nombre.indexOf('3°') === 0 ? '#fce5cd' : '#cfe2f3');
    var colorTxt = g.nombre.indexOf('2°') === 0 ? '#135c2d' : '#1F4E78';
    return '<th colspan="' + g.cantidad + '" style="text-align:center;background:' + bg + ';color:' + colorTxt + ';font-size:12px;letter-spacing:0.4px;text-transform:uppercase;border-bottom:2px solid ' + colorTxt + '">' +
           '📌 ' + esc(g.nombre) + ' (' + g.cantidad + ' mód.)</th>';
  }).join('');

  var th = modulosVisibles.map(function (m) {
    var corto = _etiquetaCortaCuat(m);
    return '<th class="mod" title="' + esc(m.nombre) + ' (' + esc(_etiquetaCuatrimestre(m)) + ')">' +
           '<b style="color:var(--azul)">[' + esc(corto) + ']</b> ' + esc(m.nombre) + '</th>';
  }).join('');

  var tieneDosCuat = cuatrimestresDisponibles.indexOf('1° Cuatrimestre') !== -1 &&
                     cuatrimestresDisponibles.indexOf('2° Cuatrimestre') !== -1;

  var hayCongelados = false;
  var filas = d.estudiantes.map(function (es) {
    if (es.notasCongeladas) hayCongelados = true;
    var bloqueado = !editable || es.notasCongeladas;

    // Calcular promedios de 1°C y 2°C si corresponde
    var suma1 = 0, cnt1 = 0, suma2 = 0, cnt2 = 0;
    d.modulos.forEach(function (m, idxAll) {
      var valStr = es.notas[idxAll];
      var num = parseFloat(valStr);
      if (!isNaN(num)) {
        var et = _etiquetaCuatrimestre(m);
        if (et.indexOf('2°') === 0) { suma2 += num; cnt2++; }
        else { suma1 += num; cnt1++; }
      }
    });
    var prom1C = cnt1 ? Math.round(suma1 / cnt1) : '—';
    var prom2C = cnt2 ? Math.round(suma2 / cnt2) : '—';

    var celdas = modulosVisibles.map(function (m) {
      var idxReal = m.i;
      var n = (es.notas && idxReal < es.notas.length) ? es.notas[idxReal] : '';
      var cond = notaCondicion(n);
      var color = cond === 'Aprobado' ? '#137333' : cond === 'Desaprobado' ? '#b3261e' : '';
      var estilo = color ? 'style="text-align:center;color:' + color + ';font-weight:bold"' : 'style="text-align:center"';
      if (bloqueado) {
        return '<td class="nota" ' + estilo + '><input value="' + esc(n) + '" disabled ' +
               'title="' + (es.notasCongeladas ? '🔒 Calificaciones congeladas por certificado oficial aprobado' : '') + '"></td>';
      }
      return '<td class="nota" ' + estilo + '><input value="' + esc(n) + '" maxlength="3" ' +
             'data-fila="' + es.fila + '" data-mod="' + idxReal + '"></td>';
    }).join('');

    var candado = es.notasCongeladas ? ' <span title="Certificado Aprobado - Notas Congeladas">🔒</span>' : '';
    var celdasPromCuat = '';
    if (tieneDosCuat && filtroCuat === 'Todos') {
      celdasPromCuat =
        '<td style="text-align:center;background:#f4f8fc;font-weight:600;color:#1F4E78">' + esc(prom1C) + '</td>' +
        '<td style="text-align:center;background:#f3faf5;font-weight:600;color:#135c2d">' + esc(prom2C) + '</td>';
    }

    return '<tr><td style="text-align:center">' + esc(es.orden) + '</td>' +
      '<td>' + esc(es.apellido) + ', ' + esc(es.nombres) + candado + '</td>' +
      '<td style="text-align:center">' + esc(es.documento) + '</td>' +
      '<td style="text-align:center">' + esc(es.fechaNac || '—') + '</td>' +
      '<td style="text-align:center">' + esc(es.provincia || 'Jujuy') + '</td>' +
      '<td style="text-align:center">' + esc(es.pais || 'Argentina') + '</td>' +
      celdas +
      celdasPromCuat +
    '</tr>';
  }).join('');

  var barraFiltroCuat = '';
  if (cuatrimestresDisponibles.length > 1) {
    barraFiltroCuat =
      '<div class="no-imprimir" style="display:flex;gap:8px;align-items:center;margin:8px 0 12px;flex-wrap:wrap">' +
        '<span style="font-size:12px;font-weight:600;color:var(--suave)">Ver período:</span>' +
        '<button type="button" class="boton ' + (filtroCuat === 'Todos' ? '' : 'suave') + '" style="padding:4px 12px;font-size:12px" data-cuat="Todos">Todos (' + d.modulos.length + ' módulos)</button>' +
        cuatrimestresDisponibles.map(function (c) {
          var activo = filtroCuat === c;
          return '<button type="button" class="boton ' + (activo ? '' : 'suave') + '" style="padding:4px 12px;font-size:12px" data-cuat="' + esc(c) + '">' + esc(c) + '</button>';
        }).join('') +
      '</div>';
  }

  var thGrupoProm = (tieneDosCuat && filtroCuat === 'Todos')
    ? '<th colspan="2" style="text-align:center;background:#e9eef4">PROMEDIO</th>'
    : '';
  var thExtraFinal = (tieneDosCuat && filtroCuat === 'Todos')
    ? '<th class="mod" style="background:#e8f1fa">Prom. 1° Cuat.</th>' +
      '<th class="mod" style="background:#e6f4ea">Prom. 2° Cuat.</th>'
    : '';

  var enc = d.encabezado || {};
  var encabezadoImpresionRac =
    '<div class="solo-impresion" style="margin-bottom:12px;border-bottom:2px solid #222;padding-bottom:8px;font-family:\'Times New Roman\',serif">' +
      '<div style="text-align:center;margin-bottom:8px">' +
        '<div style="font-size:11px;font-weight:bold;letter-spacing:0.5px">PROVINCIA DE JUJUY · SECRETARÍA DE GESTIÓN EDUCATIVA</div>' +
        '<div style="font-size:11px;font-weight:bold;letter-spacing:0.5px">DIRECCIÓN DE EDUCACIÓN TÉCNICO PROFESIONAL - DIRECCIÓN DE TÍTULOS</div>' +
        '<h2 style="margin:6px 0 2px;font-size:16px;text-transform:uppercase;letter-spacing:1px">REGISTRO ANUAL DE CALIFICACIONES</h2>' +
      '</div>' +
      '<table style="width:100%;border-collapse:collapse;font-size:11px;border:none">' +
        '<tr>' +
          '<td style="border:none;padding:2px 4px"><b>Establecimiento:</b> ' + esc(enc.establecimiento || estado.curso.institucion || '—') + '</td>' +
          '<td style="border:none;padding:2px 4px"><b>CUE:</b> ' + esc(enc.cue || estado.curso.cue || '—') + '</td>' +
          '<td style="border:none;padding:2px 4px"><b>Libro Matriz N°:</b> ' + esc(enc.libro || '1') + '</td>' +
        '</tr>' +
        '<tr>' +
          '<td style="border:none;padding:2px 4px"><b>Oferta Formativa:</b> ' + esc(enc.oferta || estado.curso.oferta || '—') + '</td>' +
          '<td style="border:none;padding:2px 4px"><b>Ciclo Lectivo:</b> ' + esc(enc.ciclo || estado.curso.ciclo || '—') + '</td>' +
          '<td style="border:none;padding:2px 4px"><b>Turno / División:</b> ' + esc(enc.turno || estado.curso.turno || '—') + ' · ' + esc(enc.division || estado.curso.division || '—') + '</td>' +
        '</tr>' +
        '<tr>' +
          '<td colspan="3" style="border:none;padding:2px 4px"><b>Diseño Curricular / Norma Aprobatoria:</b> ' + esc(enc.disenio || '—') + '</td>' +
        '</tr>' +
      '</table>' +
    '</div>';

  var pieImpresionRac =
    '<div class="solo-impresion" style="margin-top:42px;font-family:\'Times New Roman\',serif;font-size:12px">' +
      '<div style="display:flex;justify-content:space-around;text-align:center">' +
        '<div style="width:220px;border-top:1px solid #000;padding-top:4px"><b>Secretario/a / Administrativo/a</b><br><small>Firma y Sello</small></div>' +
        '<div style="width:220px;border-top:1px solid #000;padding-top:4px"><b>Director/a del Establecimiento</b><br><small>Firma y Sello</small></div>' +
      '</div>' +
    '</div>';

  $('panel').innerHTML =
    '<h2 style="font-size:16px;margin:0 0 10px">Registro Anual de Calificaciones</h2>' +
    encabezadoImpresionRac +
    barraFiltroCuat +
    (hayCongelados
      ? '<div class="alerta-congelado">🔒 <b>Atención:</b> Los estudiantes con certificado oficial aprobado tienen sus calificaciones <b>congeladas e inmutables</b>.</div>'
      : '') +
    (editable
      ? '<div class="acciones">' +
          '<button class="boton" id="guardar" disabled>Guardar cambios</button>' +
          '<button type="button" class="boton" style="background:#137333" onclick="mostrarModalNuevoEstudiante()">+ Agregar Alumno</button>' +
          '<button type="button" class="boton" style="background:#1F4E78" id="imprimirRac">🖨️ Imprimir Registro Anual</button>' +
          '<span style="color:var(--suave);font-size:12px">Nota de 1 a 10, o AUS si estuvo ausente. ≥7 Aprobado · <7 Desaprobado</span>' +
        '</div>'
      : '<div class="acciones">' +
          '<button type="button" class="boton" style="background:#1F4E78" id="imprimirRac">🖨️ Imprimir Registro Anual</button>' +
          '<span style="color:var(--suave);font-size:12px">Tu rol es de consulta: puedes visualizar e imprimir, no modificar.</span>' +
        '</div>') +
    '<div class="tabla-ancha"><table><thead>' +
      '<tr>' +
        '<th colspan="4" style="text-align:center;background:#e9eef4">DATOS DEL ESTUDIANTE</th>' +
        '<th colspan="2" style="text-align:center;background:#dce6f1">LUGAR DE NACIMIENTO</th>' +
        thGrupos +
        thGrupoProm +
      '</tr>' +
      '<tr>' +
        '<th style="width:36px">N°</th><th>Apellido y nombres</th><th style="width:92px">Documento</th>' +
        '<th style="width:96px;text-align:center">Fecha de nacimiento</th>' +
        '<th style="width:92px;text-align:center">Provincia</th>' +
        '<th style="width:88px;text-align:center">País</th>' +
        th + thExtraFinal +
      '</tr>' +
    '</thead><tbody>' + filas + '</tbody></table></div>' +
    pieImpresionRac;

  if ($('imprimirRac')) {
    $('imprimirRac').addEventListener('click', function () { window.print(); });
  }

  Array.prototype.forEach.call(document.querySelectorAll('[data-cuat]'), function (btn) {
    btn.addEventListener('click', function () {
      estado.filtroCuatrimestre = btn.dataset.cuat;
      pintarNotas();
    });
  });

  if (!editable) return;
  var pendientes = {};
  Array.prototype.forEach.call(document.querySelectorAll('td.nota input:not([disabled])'), function (inp) {
    var original = inp.value;
    inp.addEventListener('input', function () {
      inp.value = inp.value.toUpperCase();
      var k = inp.dataset.fila + '-' + inp.dataset.mod;
      if (inp.value === original) delete pendientes[k];
      else pendientes[k] = { fila: +inp.dataset.fila, modulo: +inp.dataset.mod, valor: inp.value };
      $('guardar').disabled = !Object.keys(pendientes).length;
    });
  });

  $('guardar').addEventListener('click', async function () {
    var cambios = Object.keys(pendientes).map(function (k) { return pendientes[k]; });
    $('guardar').disabled = true;
    avisar('Guardando notas en Google Sheets…');
    try {
      var r = await llamar('/api/curso/' + encodeURIComponent(estado.curso.id) + '/notas', 'POST', { cambios: cambios });
      avisar(r.guardados + ' nota(s) guardadas con éxito', 'ok');
      abrirCurso(estado.curso.id);
    } catch (e) {
      problema(e);
      $('guardar').disabled = false;
    }
  });
}

// ---------- PESTAÑA: ACTA DE EXAMEN ----------
async function pintarActa() {
  $('panel').innerHTML = '<div class="cargando">Cargando el acta desde Google Sheets…</div>';
  try {
    var r = await llamar('/api/curso/' + encodeURIComponent(estado.curso.id) + '/acta');
    var a = r.acta;
    var ed = a.puedeCargar;
    var enc = estado.datos.encabezado || {};

    // Conversión de nota numérica a letras mayúsculas para el Acta
    var mapaNotaLetras = {
      '1': 'UNO', '2': 'DOS', '3': 'TRES', '4': 'CUATRO', '5': 'CINCO',
      '6': 'SEIS', '7': 'SIETE', '8': 'OCHO', '9': 'NUEVE', '10': 'DIEZ',
      'AUS': 'AUSENTE', 'AUSENTE': 'AUSENTE'
    };
    function notaALetras(val) {
      var v = String(val == null ? '' : val).trim().toUpperCase();
      return mapaNotaLetras[v] || '';
    }

    // Contadores Aprobados / Desaprobados / Ausentes
    var nApr = 0, nDes = 0, nAus = 0;
    var filas = a.estudiantes.map(function (es) {
      var campo = function (c, v) {
        return ed ? '<td class="nota"><input value="' + esc(v) + '" maxlength="3" ' +
                    'data-fila="' + es.filaActa + '" data-campo="' + c + '"></td>'
                  : '<td style="text-align:center">' + esc(v) + '</td>';
      };
      // Calcular condición en cliente
      var def = parseFloat(es.definitiva);
      var condStr = '';
      if (es.definitiva === 'AUS' || es.definitiva === 'AUSENTE') { condStr = 'Ausente'; nAus++; }
      else if (!isNaN(def)) { if (def >= 7) { condStr = 'Aprobado'; nApr++; } else { condStr = 'Desaprobado'; nDes++; } }

      var teoLetras = es.teoricoLetras || notaALetras(es.teorico);
      var pracLetras = es.practicoLetras || notaALetras(es.practico);
      var defLetras = es.definitivaLetras || notaALetras(es.definitiva);

      var badgeCond = '—';
      if (condStr === 'Aprobado') {
        badgeCond = '<span class="badge-estado badge-aprobado">Aprobado</span>';
      } else if (condStr === 'Desaprobado') {
        badgeCond = '<span class="badge-estado badge-observado">Desaprobado</span>';
      } else if (condStr === 'Ausente') {
        badgeCond = '<span class="badge-estado badge-no-solicitado">Ausente</span>';
      }

      return '<tr>' +
        '<td style="text-align:center">' + esc(es.orden) + '</td>' +
        '<td style="text-align:center">' + esc(es.permiso || '') + '</td>' +
        '<td style="text-align:center">' + esc(es.documento) + '</td>' +
        '<td>' + esc(es.nombre) + '</td>' +
        campo('teorico', es.teorico) +
        '<td style="text-align:center">' + esc(teoLetras) + '</td>' +
        campo('practico', es.practico) +
        '<td style="text-align:center">' + esc(pracLetras) + '</td>' +
        '<td style="text-align:center;font-weight:bold">' + esc(es.definitiva) + '</td>' +
        '<td style="text-align:center">' + esc(defLetras) + '</td>' +
        '<td style="text-align:center">' + badgeCond + '</td>' +
      '</tr>';
    }).join('');

    var totalEst = a.estudiantes.length;
    // Texto en letras del total
    var letrasMap = {0:'cero',1:'uno',2:'dos',3:'tres',4:'cuatro',5:'cinco',6:'seis',7:'siete',8:'ocho',9:'nueve',10:'diez',
      11:'once',12:'doce',13:'trece',14:'catorce',15:'quince',16:'dieciséis',17:'diecisiete',18:'dieciocho',19:'diecinueve',20:'veinte'};
    function enLetras(n) { return letrasMap[n] || String(n); }

    var libroNro = enc.libro || '____';
    var folioNro = enc.folio || '____';

    $('panel').innerHTML =
      // ── Encabezado con Libro y Folio ──
      '<div class="acta-encabezado">' +
        '<div style="text-align:center;font-family:\'Times New Roman\',serif;font-size:11px;font-weight:bold;letter-spacing:0.5px;margin-bottom:4px">' +
          'PROVINCIA DE JUJUY · SECRETARÍA DE GESTIÓN EDUCATIVA<br>' +
          'DIRECCIÓN DE EDUCACIÓN TÉCNICO PROFESIONAL - DIRECCIÓN DE TÍTULOS' +
        '</div>' +
        '<div class="acta-libro-folio">' +
          '<span>Libro de Actas N°: <b>' + esc(libroNro) + '</b></span>' +
          '<span style="margin-left:32px">Folio N°: <b>' + esc(folioNro) + '</b></span>' +
        '</div>' +
        '<h2 class="acta-titulo">ACTA DE EXAMEN DE ALUMNOS REGULARES</h2>' +
        '<table class="acta-ficha">' +
          '<tr><td><b>Establecimiento:</b></td><td>' + esc(enc.establecimiento || '—') + ' · CUE ' + esc(enc.cue || '') + '</td></tr>' +
          '<tr><td><b>De:</b></td><td>' + esc(enc.oferta || '—') + '</td></tr>' +
          '<tr><td><b>Correspondiente al:</b></td><td>' + esc(enc.turno || '') + ' · ' + esc(enc.division || '') + ' · Ciclo lectivo: ' + esc(enc.ciclo || '') + '</td></tr>' +
          '<tr><td><b>Fecha del examen:</b></td><td>' + esc(a.mesa.fecha || '—') + '</td></tr>' +
        '</table>' +
        '<p class="acta-texto-intro">A los ' + esc(a.mesa.fecha || '___') + ', reunida la comisión examinadora del Trayecto Formativo con asistencia de sus tres miembros señores:</p>' +
        '<table class="acta-ficha">' +
          '<tr><td><b>Presidente/a:</b></td><td>' + esc(a.mesa.presidente || '—') + '</td><td><b>Vocal 1°:</b></td><td>' + esc(a.mesa.vocal1 || '—') + '</td></tr>' +
          '<tr><td><b>Vocal 2°:</b></td><td>' + esc(a.mesa.vocal2 || '—') + '</td><td></td><td></td></tr>' +
        '</table>' +
        '<p class="acta-texto-intro">procedió a cumplir su cometido con el resultado que se consigna a continuación:</p>' +
        '<p style="font-size:11px;font-style:italic;margin:4px 0 10px">NOTA: Será considerada como fraudulenta toda enmienda o raspadura que no haya sido salvada expresamente con la firma de todos los miembros de la mesa. El número de alumnos examinados se anotará con letras y números.</p>' +
      '</div>' +

      // ── Acciones guardar e imprimir ──
      '<div class="acciones">' +
        (ed ? '<button class="boton" id="guardarActa" disabled>Guardar cambios</button>' : '') +
        '<button type="button" class="boton" style="background:#1F4E78" id="imprimirActa">🖨️ Imprimir Acta de Examen</button>' +
        '<span style="color:var(--suave);font-size:12px">La nota definitiva y en letras se calculan automáticamente. ≥7 Aprobado · <7 Desaprobado</span>' +
      '</div>' +

      // ── Tabla de alumnos ──
      '<div class="tabla-ancha"><table><thead><tr>' +
        '<th style="width:36px">N° de orden</th>' +
        '<th style="width:70px">Permiso de examen N°</th>' +
        '<th style="width:92px">N° doc. de identidad</th>' +
        '<th>Apellido y nombre</th>' +
        '<th style="width:60px">Teórico N°</th><th style="width:70px">Teórico Letras</th>' +
        '<th style="width:60px">Práctico N°</th><th style="width:70px">Práctico Letras</th>' +
        '<th style="width:60px">Definitiva N°</th><th style="width:90px">Definitiva Letras</th>' +
        '<th style="width:105px">Condición</th>' +
      '</tr></thead><tbody>' + (filas || '') + '</tbody></table></div>' +

      // ── Resumen ──
      '<div class="acta-resumen">' +
        '<table class="acta-resumen-tabla">' +
          '<tr><td>Aprobados</td><td><b>' + nApr + '</b></td></tr>' +
          '<tr><td>Desaprobados</td><td><b>' + nDes + '</b></td></tr>' +
          '<tr><td>Ausentes</td><td><b>' + nAus + '</b></td></tr>' +
          '<tr style="border-top:2px solid #333"><td><b>Total</b></td><td><b>' + totalEst + '</b></td></tr>' +
        '</table>' +
        '<p class="acta-texto-intro" style="margin-top:14px">Se hace constar que sobre un total de ' + enLetras(totalEst) + ' (' + totalEst + ') alumnos/as, ' +
          'resultaron ' + enLetras(nApr) + ' (' + nApr + ') aprobados/as, ' +
          enLetras(nDes) + ' (' + nDes + ') desaprobados/as y ' +
          enLetras(nAus) + ' (' + nAus + ') ausentes.</p>' +
      '</div>' +

      // ── Firmas ──
      '<div class="acta-firmas">' +
        '<div class="acta-firma"><div class="acta-firma-linea"></div><b>Vocal 2°</b><br><small>Firma y aclaración</small></div>' +
        '<div class="acta-firma"><div class="acta-firma-linea"></div><b>Presidente/a de mesa</b><br><small>Firma y aclaración</small></div>' +
        '<div class="acta-firma"><div class="acta-firma-linea"></div><b>Vocal 1°</b><br><small>Firma y aclaración</small></div>' +
      '</div>';

    if ($('imprimirActa')) {
      $('imprimirActa').addEventListener('click', function () { window.print(); });
    }

    if (!ed) return;
    var pend = {};
    Array.prototype.forEach.call(document.querySelectorAll('#panel input'), function (inp) {
      var orig = inp.value;
      inp.addEventListener('input', function () {
        inp.value = inp.value.toUpperCase();
        var k = inp.dataset.fila + '-' + inp.dataset.campo;
        if (inp.value === orig) delete pend[k];
        else pend[k] = { filaActa: +inp.dataset.fila, campo: inp.dataset.campo, valor: inp.value };
        $('guardarActa').disabled = !Object.keys(pend).length;
      });
    });

    $('guardarActa').addEventListener('click', async function () {
      var cambios = Object.keys(pend).map(function (k) { return pend[k]; });
      $('guardarActa').disabled = true;
      avisar('Guardando acta…');
      try {
        var res = await llamar('/api/curso/' + encodeURIComponent(estado.curso.id) + '/acta', 'POST', { cambios: cambios });
        avisar(res.guardados + ' nota(s) guardadas en el acta', 'ok');
        pintarActa();
      } catch (e) {
        problema(e);
        $('guardarActa').disabled = false;
      }
    });
  } catch (err) {
    problema(err);
  }
}

// ---------- PESTAÑA: CIRCUITO DE CERTIFICADOS (VISTA ESCUELA) ----------
function pintarSolicitudesCurso() {
  var d = estado.datos;
  var filas = d.estudiantes.map(function (es) {
    var aprobo = String(es.situacion || '').startsWith('Aprobó');
    var sol = es.solicitudCertificado || {};
    var st = sol.estado || 'No solicitado';

    var badgeClass = 'badge-no-solicitado';
    if (st === 'Pendiente') badgeClass = 'badge-pendiente';
    else if (st === 'Observado') badgeClass = 'badge-observado';
    else if (st === 'Aprobado') badgeClass = 'badge-aprobado';

    var accionHtml = '';
    if (!aprobo) {
      accionHtml = '<button class="boton" disabled style="opacity:0.4;background:var(--suave)" title="Solo habilitado para estudiantes con situación Aprobó">No elegible (No aprobó)</button>';
    } else {
      if (st === 'No solicitado') {
        accionHtml = '<button class="boton" onclick="solicitarCertificadoEstudiante(\'' + esc(es.documento) + '\')">Solicitar Certificado</button>';
      } else if (st === 'Pendiente') {
        accionHtml = '<span style="color:#b06000;font-weight:600">⏳ En revisión por Títulos</span>';
      } else if (st === 'Observado') {
        accionHtml = '<button class="boton" style="background:#e37400" onclick="solicitarCertificadoEstudiante(\'' + esc(es.documento) + '\')">Reenviar a Títulos</button>';
      } else if (st === 'Aprobado') {
        accionHtml = '<span style="color:#137333;font-weight:600">🔒 Aprobado (' + esc(sol.numeroCertificado) + ')</span>';
      }
    }

    var alertaObs = '';
    if (st === 'Observado' && sol.motivoObservacion) {
      alertaObs = '<div class="alerta-observacion">⚠️ <b>Observación de Títulos:</b> ' + esc(sol.motivoObservacion) + '</div>';
    }

    return '<tr>' +
      '<td style="text-align:center">' + esc(es.orden) + '</td>' +
      '<td><b>' + esc(es.apellido) + ', ' + esc(es.nombres) + '</b>' + alertaObs + '</td>' +
      '<td style="text-align:center">' + esc(es.documento) + '</td>' +
      '<td>' + esc(es.situacion || '—') + '</td>' +
      '<td style="text-align:center"><span class="badge-estado ' + badgeClass + '">' + esc(st) + '</span></td>' +
      '<td style="text-align:center;font-weight:bold">' + esc(sol.numeroCertificado || '—') + '</td>' +
      '<td style="text-align:center">' +
        accionHtml +
        ' <button class="boton suave" style="margin-left:4px" onclick="verAnaliticoEstudiante(\'' + esc(es.documento) + '\')">Ver Analítico</button>' +
      '</td>' +
    '</tr>';
  }).join('');

  $('panel').innerHTML =
    '<div class="ficha">' +
      '<dt>Regla de solicitud:</dt>' +
      '<dd>La escuela solo puede solicitar la emisión del certificado oficial para alumnos en estado <b>"Aprobó"</b>. Quienes no aprobaron no tienen la opción habilitada.</dd>' +
    '</div>' +
    '<div class="tabla-ancha"><table><thead><tr>' +
      '<th style="width:36px">N°</th><th>Estudiante</th><th style="width:90px">DNI</th>' +
      '<th style="width:130px">Situación</th><th style="width:110px">Estado Pedido</th>' +
      '<th style="width:140px">N° Certificado</th><th style="width:230px">Acción</th>' +
    '</tr></thead><tbody>' + filas + '</tbody></table></div>';
}

async function solicitarCertificadoEstudiante(doc) {
  avisar('Enviando pedido a la Dirección de Títulos…');
  try {
    var r = await llamar('/api/solicitudes', 'POST', {
      idCurso: estado.curso.id,
      documento: doc
    });
    avisar('¡Solicitud enviada a la bandeja de Títulos con éxito!', 'ok');
    abrirCurso(estado.curso.id, 'solicitudes');
  } catch (e) {
    problema(e);
  }
}

function verAnaliticoEstudiante(doc) {
  estado.pestania = 'analitico';
  pintarPestania();
  setTimeout(function () {
    if ($('selEst')) { $('selEst').value = doc; $('generar').click(); }
  }, 100);
}

// ---------- PESTAÑA: CERTIFICADO (CON CONTROL DE BORRADOR VS OFICIAL) ----------
function pintarAnalitico() {
  var opciones = estado.datos.estudiantes.map(function (e) {
    return '<option value="' + esc(e.documento) + '">' + esc(e.apellido) + ', ' +
           esc(e.nombres) + '</option>';
  }).join('');

  $('panel').innerHTML =
    '<h2 style="font-size:16px;margin:0 0 10px">Certificado</h2>' +
    '<div class="acciones" style="background:#fff;padding:10px 14px;border:1px solid var(--borde);border-radius:6px;align-items:center">' +
      '<label style="display:flex;align-items:center;gap:6px">Estudiante: <select id="selEst" style="min-width:220px">' + opciones + '</select></label>' +
      '<label style="display:flex;align-items:center;gap:6px">Emisión: <input type="date" id="fecha"></label>' +
      '<button class="boton" id="generar" style="background:#1F4E78">Ver el certificado</button>' +
      '<button class="boton suave" id="imprimir" disabled style="opacity:0.5;cursor:not-allowed">Imprimir</button>' +
    '</div>' +
    '<div id="bannerEstadoAnalitico"></div>' +
    '<div id="salida"></div>';

  $('fecha').valueAsDate = new Date();

  $('generar').addEventListener('click', async function () {
    var doc = $('selEst').value;
    if (!doc) { avisar('Ese estudiante no tiene documento registrado.', 'error'); return; }
    $('salida').innerHTML = '<div class="cargando">Generando certificado oficial…</div>';
    var f = $('fecha').value || '';
    try {
      var url = '/api/curso/' + encodeURIComponent(estado.curso.id) + '/analitico?documento=' + encodeURIComponent(doc) +
                '&fecha=' + encodeURIComponent(f);
      var r = await llamar(url);
      var an = r.analitico;
      var docOf = an.documentoOficial || {};
      var bannerBox = $('bannerEstadoAnalitico');
      var btnImp = $('imprimir');

      var rolActual = (estado.sesion && estado.sesion.rol) ? String(estado.sesion.rol).toLowerCase() : '';
      var puedeImprimirRol = (rolActual === 'administrativo' || rolActual === 'directivo');

      if (an.esBorrador) {
        var msg = docOf.mensajeEstado || 'Documento en estado BORRADOR – no válido: requiere aprobación de la Dirección de Títulos para que el Administrativo o Directivo pueda imprimirlo.';
        bannerBox.innerHTML = '<div class="banner-aviso-analitico">' + esc(msg) + '</div>';
        btnImp.disabled = true; btnImp.style.opacity = '0.5'; btnImp.style.cursor = 'not-allowed';
        btnImp.title = 'Impresión bloqueada: requiere aprobación de la Dirección de Títulos';
      } else if (!puedeImprimirRol) {
        bannerBox.innerHTML =
          '<div class="banner-aviso-analitico" style="background:#e6f4ea;border-color:#34a853;color:#137333">' +
            '✅ <b>Certificado Oficial APROBADO:</b> N° <b>' + esc(an.numeroCertificado) + '</b>. ' +
            '(Solo el rol <b>Administrativo</b> o <b>Directivo</b> de la institución tiene habilitado el botón de impresión).' +
          '</div>';
        btnImp.disabled = true; btnImp.style.opacity = '0.5'; btnImp.style.cursor = 'not-allowed';
        btnImp.title = 'Solo el Administrativo o el Directivo de la escuela puede imprimir el certificado';
      } else {
        bannerBox.innerHTML =
          '<div class="banner-aviso-analitico" style="background:#e6f4ea;border-color:#34a853;color:#137333">' +
            '✅ <b>Certificado Oficial APROBADO:</b> N° <b>' + esc(an.numeroCertificado) + '</b>. Calificaciones congeladas – habilitado para impresión por Administrativo / Directivo.' +
          '</div>';
        btnImp.disabled = false; btnImp.style.opacity = '1'; btnImp.style.cursor = 'pointer';
        btnImp.style.background = 'var(--azul)'; btnImp.style.color = '#fff';
        btnImp.title = 'Imprimir certificado oficial';
      }

      $('salida').innerHTML = armarAnalitico(an);
    } catch (e) { problema(e); $('salida').innerHTML = ''; }
  });

  $('imprimir').addEventListener('click', function () { if (!$('imprimir').disabled) window.print(); });
  setTimeout(function () { if ($('generar')) $('generar').click(); }, 50);
}

function armarAnalitico(r) {
  var d = r.documentoOficial;
  if (!d) { return armarAnaliticoCeldas(r); }

  var certNroFormateado = d.certNro || '__________________';
  var watermark = d.esBorrador
    ? '<div class="marca-agua-borrador-oficial">BORRADOR<br>NO VÁLIDO</div>' : '';
  var escudoFondo = '<img src="/img/escudo_nacional.png?v=20261105b" class="hoja-fondo-escudo" alt="" aria-hidden="true">';

  var filasModulos = (d.trayecto || []).map(function (m) {
    return '<tr>' +
      '<td style="text-align:center">'                  + esc(m.nro)        + '</td>' +
      '<td>'                                             + esc(m.modulo)     + '</td>' +
      '<td style="text-align:center">'                  + esc(m.tipo)       + '</td>' +
      '<td style="text-align:center">'                  + esc(m.periodo)    + '</td>' +
      '<td style="text-align:center">'                  + esc(m.hsReloj)    + '</td>' +
      '<td style="text-align:center">'                  + esc(m.hsCat)      + '</td>' +
      '<td style="text-align:center;font-weight:bold">' + esc(m.nota || '') + '</td>' +
      '<td style="text-align:center">'                  + esc(m.enLetras || '') + '</td>' +
    '</tr>';
  }).join('');

  return _hojaOficialHTML(d, certNroFormateado, watermark, escudoFondo, filasModulos);
}

// ── Función interna compartida ──────────────────────────────────────────────
function _hojaOficialHTML(d, certNroFormateado, watermark, escudoFondo, filasModulos) {
  var idCursoQr = (estado.curso && estado.curso.id) ? estado.curso.id : '';
  var validarPath = '/validar?nro=' + encodeURIComponent(d.esBorrador ? '' : certNroFormateado) +
                    '&dni=' + encodeURIComponent(String(d.dniFormateado || '').replace(/\./g, '')) +
                    '&curso=' + encodeURIComponent(idCursoQr);
  var validarFullUrl = window.location.origin + validarPath;
  var qrImgSrc = 'https://api.qrserver.com/v1/create-qr-code/?size=120x120&data=' + encodeURIComponent(validarFullUrl);
  var qrHtml = '<a href="' + esc(validarPath) + '" target="_blank" title="Verificar validez del título">' +
    '<img src="' + esc(qrImgSrc) + '" alt="QR Validación" style="width:82px;height:82px;border:1px solid #222;padding:2px;background:#fff" ' +
    'onerror="this.outerHTML=\'<div class=hoja-qr-placeholder style=border-color:#000;font-weight:bold>VERIFICAR<br>VALIDEZ<br>QR</div>\'">' +
    '</a>';

  // Formatear fecha de otorgamiento ("el día X del mes de MES del año YYYY")
  var mesesNombres = [
    'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
    'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE'
  ];
  var hoy = new Date();
  var diaOtorgado = String(hoy.getDate()).padStart(2, '0');
  var mesOtorgado = mesesNombres[hoy.getMonth()];
  var anioOtorgado = String(hoy.getFullYear());
  if (d.fechaEmision && /^\d{4}-\d{2}-\d{2}$/.test(d.fechaEmision)) {
    var partesF = d.fechaEmision.split('-');
    anioOtorgado = partesF[0];
    mesOtorgado = mesesNombres[parseInt(partesF[1], 10) - 1] || mesOtorgado;
    diaOtorgado = partesF[2];
  }

  var cohorteStr = d.cohorte || anioOtorgado;
  var ofertaStr = d.oferta || (estado.curso && estado.curso.oferta) || 'FORMACIÓN PROFESIONAL';
  var normaStr = d.normaJurisdiccional || 'Res. Ministerial';
  var firmaDigitalTexto = !d.esBorrador
    ? '<div style="font-size:10px;line-height:1.35;color:#222;margin-bottom:6px">' +
        'Firmado digitalmente por Dirección de Títulos<br>' +
        'Fecha: ' + esc(d.fechaAprobacion || (anioOtorgado + '-' + String(hoy.getMonth() + 1).padStart(2, '0') + '-' + diaOtorgado)) + '<br>' +
        'Ubicación: Jujuy' +
      '</div>'
    : '<div style="font-size:10px;line-height:1.35;color:#777;margin-bottom:6px">' +
        'Pendiente de firma digital (Documento en Borrador)<br>' +
        'Ubicación: Jujuy' +
      '</div>';

  return '<div class="hoja-oficial">' +
    escudoFondo + watermark +
    '<div class="hoja-cabecera">' +
      '<div class="hoja-qr">' + qrHtml + '</div>' +
      '<div class="hoja-escudo-bloque">' +
        '<div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:4px">' +
          '<span class="hoja-republica" style="margin:0">República</span>' +
          '<img src="/img/escudo_nacional.png?v=20261105f" alt="Escudo Nacional" style="height:68px;display:block;margin:0;mix-blend-mode:multiply;filter:contrast(1.06) brightness(1.04)">' +
          '<span class="hoja-republica" style="margin:0">Argentina</span>' +
        '</div>' +
        '<p class="hoja-ley-nac">LEY DE EDUCACIÓN NACIONAL N° 26.206</p>' +
        '<p class="hoja-provincia">PROVINCIA DE JUJUY</p>' +
        '<p class="hoja-ley-nac" style="margin-top:6px">LEY PROVINCIAL N° 5807</p>' +
        '<p class="hoja-ley-nac">SECRETARÍA DE GESTIÓN EDUCATIVA</p>' +
        '<p class="hoja-ley-nac">DIRECCIÓN DE EDUCACIÓN TÉCNICO PROFESIONAL - DIRECCIÓN DE TÍTULOS</p>' +
      '</div>' +
      '<div class="hoja-cert-nro">' + esc(certNroFormateado) + '</div>' +
    '</div>' +
    '<div class="hoja-titulo-doc">CERTIFICADO</div>' +
    '<p class="hoja-parrafo">' +
      'La autoridad del establecimiento educativo, <b>' + esc(d.establecimiento) + '</b> CUE ' +
      esc(d.cue) + ', ubicado en <b>' + esc(d.domicilio) + '</b>, de <b>' + esc(d.localidad) +
      '</b>, provincia de JUJUY, certifica que <b>' + esc(d.estudianteNombre) + '</b>, con lugar ' +
      'de nacimiento en ' + esc(d.lugarNac) + ', el ' + esc(d.fechaNac) +
      ', Tipo de Documento ' + esc(d.tipoDoc) + ' N° <b>' + esc(d.dniFormateado) + '</b>' +
      ', aprobó los espacios curriculares que con sus respectivas calificaciones a continuación se expresan:' +
    '</p>' +
    '<div class="hoja-seccion">TRAYECTO CURRICULAR</div>' +
    '<table class="tabla-trayecto">' +
      '<thead><tr>' +
        '<th style="width:28px">N°</th>' +
        '<th>Módulo / Espacio Curricular</th>' +
        '<th style="width:70px">Tipo</th>' +
        '<th style="width:120px">Período</th>' +
        '<th style="width:52px">Hs reloj</th>' +
        '<th style="width:52px">Hs cát.</th>' +
        '<th style="width:38px">Nota</th>' +
        '<th style="width:80px">En letras</th>' +
      '</tr></thead>' +
      '<tbody>' +
        filasModulos +
        '<tr style="font-weight:bold">' +
          '<td colspan="4" style="text-align:left">Carga horaria total</td>' +
          '<td style="text-align:center">' + esc(d.cargaHorariaTotal.reloj) + '</td>' +
          '<td style="text-align:center">' + esc(d.cargaHorariaTotal.cat)  + '</td>' +
          '<td colspan="2"></td>' +
        '</tr>' +
      '</tbody>' +
    '</table>' +

    // ── Parte inferior oficial del Certificado / Título (según modelo provincial) ──
    '<div class="hoja-pie-legal" style="margin-top:16px;font-size:11.5px;line-height:1.5;position:relative;z-index:2">' +
      '<p style="margin:2px 0"><b>Cohorte:</b> ' + esc(cohorteStr) + '</p>' +
      '<p style="margin:2px 0 10px"><b>Observaciones:</b> ' + esc(d.observaciones || '—') + '</p>' +
      '<p style="margin:8px 0;text-align:justify">' +
        '<b>' + esc(d.estudianteNombre) + '</b>, con tipo de documento ' + esc(d.tipoDoc) + ' N° <b>' + esc(d.dniFormateado) + '</b>, ' +
        'aprobó los espacios curriculares expresados anteriormente de los estudios conducentes al certificado de ' +
        '<b>' + esc(ofertaStr) + '</b> que se corresponde con <b>FORMACIÓN PROFESIONAL</b>.' +
      '</p>' +
      '<p style="margin:3px 0"><b>NORMA JURISD. DE APROB. PLAN DE ESTUDIOS / DISEÑO CURRICULAR:</b> ' + esc(normaStr) + '</p>' +
      '<p style="margin:3px 0"><b>Libro Matriz N°</b> ' + esc(d.libro) + ' &nbsp; <b>Folio N°</b> ' + esc(d.folio) + '</p>' +
      '<p style="margin:6px 0 18px"><b>Otorgado en la localidad de ' + esc(d.localidad) + ', provincia de JUJUY, República Argentina, el día ' + esc(diaOtorgado) + ' del mes de ' + esc(mesOtorgado) + ' del año ' + esc(anioOtorgado) + '</b></p>' +

      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:32px;margin-top:26px;align-items:start">' +
        '<div style="font-size:11px;line-height:1.35">' +
          '<div style="border-top:1px solid #333;width:220px;margin-bottom:4px"></div>' +
          '<b>Director/a</b><br>' +
          '<span>' + esc(d.establecimiento) + '</span>' +
        '</div>' +
        '<div style="font-size:11px;line-height:1.35">' +
          firmaDigitalTexto +
          '<b>Responsable</b><br>' +
          '<span>Dirección de Títulos</span>' +
        '</div>' +
      '</div>' +
    '</div>' +
  '</div>';
}

function armarAnaliticoCeldas(r) {
  var ocultas = {};
  (r.combinadas || []).forEach(function (m) {
    for (var f = m.f; f < m.f + m.nf; f++)
      for (var c = m.c; c < m.c + m.nc; c++)
        if (!(f === m.f && c === m.c)) ocultas[f + ',' + c] = true;
  });
  var span = {};
  (r.combinadas || []).forEach(function (m) { span[m.f + ',' + m.c] = m; });

  var watermark = r.esBorrador
    ? '<div class="marca-agua-borrador-oficial">BORRADOR<br>NO VÁLIDO</div>'
    : '';

  var html = '<div class="hoja-oficial">' + watermark + '<table class="analitico">';
  for (var f = 1; f <= r.celdas.length; f++) {
    var fila = r.celdas[f - 1];
    if (fila.join('').trim() === '') continue;
    html += '<tr>';
    for (var c = 1; c <= fila.length; c++) {
      if (ocultas[f + ',' + c]) continue;
      var m = span[f + ',' + c];
      html += '<td' + (m && m.nc > 1 ? ' colspan="' + m.nc + '"' : '') +
                     (m && m.nf > 1 ? ' rowspan="' + m.nf + '"' : '') + '>' +
              esc(fila[c - 1]) + '</td>';
    }
    html += '</tr>';
  }
  return html + '</table></div>';
}

// =========================================================================
// BANDEJA DE ENTRADA CENTRALIZADA · DIRECCIÓN DE TÍTULOS (ROL 'titulos')
// =========================================================================

async function verBandejaTitulos() {
  $('migas').hidden = false;
  $('main').innerHTML = '<div class="cargando">Cargando bandeja de pedidos de títulos…</div>';

  try {
    var r = await llamar('/api/solicitudes');
    var solicitudes = r.solicitudes || [];

    var nPendientes = solicitudes.filter(function (s) { return s.estado === 'Pendiente'; }).length;
    var nAprobados = solicitudes.filter(function (s) { return s.estado === 'Aprobado'; }).length;
    var nObservados = solicitudes.filter(function (s) { return s.estado === 'Observado'; }).length;

    var filtradas = solicitudes.filter(function (s) {
      if (estado.filtroBandeja === 'Todos') return true;
      return s.estado === estado.filtroBandeja;
    });

    var filasHtml = filtradas.map(function (s) {
      var badgeClass = 'badge-pendiente';
      if (s.estado === 'Aprobado') badgeClass = 'badge-aprobado';
      else if (s.estado === 'Observado') badgeClass = 'badge-observado';

      var checkHtml = (s.estado !== 'Aprobado')
        ? '<input type="checkbox" class="chk-sol" value="' + esc(s.id) + '">'
        : '<span style="color:#137333">✓</span>';

      var detalleEstado = '';
      if (s.estado === 'Aprobado') {
        detalleEstado = '<div style="color:#137333;font-size:12px;font-weight:bold">Cert. ' + esc(s.numeroCertificado) + ' (' + esc(s.fechaAprobacion) + ')</div>';
      } else if (s.estado === 'Observado') {
        detalleEstado = '<div class="alerta-observacion"><b>Motivo:</b> ' + esc(s.motivoObservacion) + '</div>';
      }

      var accionesHtml = '';
      if (s.estado !== 'Aprobado') {
        accionesHtml =
          '<button class="boton" style="padding:4px 10px;font-size:12px" onclick="abrirModalAprobar(\'' + esc(s.id) + '\', \'' + esc(s.estudiante) + '\')">Aprobar</button> ' +
          '<button class="boton suave" style="padding:4px 10px;font-size:12px;color:var(--mal);border-color:var(--mal)" onclick="abrirModalObservar(\'' + esc(s.id) + '\', \'' + esc(s.estudiante) + '\')">Observar</button>';
      } else {
        accionesHtml = '<span style="color:var(--suave);font-size:12px">Calificaciones congeladas</span>';
      }

      return '<tr>' +
        '<td style="text-align:center">' + checkHtml + '</td>' +
        '<td><b>' + esc(s.institucion) + '</b><br><small style="color:var(--suave)">CUE ' + esc(s.cue) + '</small></td>' +
        '<td>' + esc(s.oferta) + '<br><small style="color:var(--suave)">' + esc(s.ciclo) + '</small></td>' +
        '<td><b>' + esc(s.estudiante) + '</b><br><small>DNI ' + esc(s.documento) + '</small></td>' +
        '<td style="text-align:center;font-size:12px">' + esc(s.fechaSolicitud) + '</td>' +
        '<td style="text-align:center"><span class="badge-estado ' + badgeClass + '">' + esc(s.estado) + '</span>' + detalleEstado + '</td>' +
        '<td style="text-align:center">' +
          accionesHtml +
          ' <button class="boton suave" style="padding:4px 8px;font-size:12px" onclick="inspeccionarAnaliticoModal(\'' + esc(s.idCurso) + '\', \'' + esc(s.documento) + '\')">Ver Analítico</button>' +
        '</td>' +
      '</tr>';
    }).join('');

    $('main').innerHTML =
      '<h1>Bandeja de Entrada · Dirección de Títulos</h1>' +
      '<p style="color:var(--suave)">Gestión, revisión centralizada y emisión de certificados de Formación Profesional.</p>' +

      '<div style="display:flex;gap:12px;margin:16px 0;flex-wrap:wrap">' +
        '<button class="boton ' + (estado.filtroBandeja === 'Pendiente' ? '' : 'suave') + '" id="f_pen">Pendientes (' + nPendientes + ')</button>' +
        '<button class="boton ' + (estado.filtroBandeja === 'Observado' ? '' : 'suave') + '" id="f_obs">Observados (' + nObservados + ')</button>' +
        '<button class="boton ' + (estado.filtroBandeja === 'Aprobado' ? '' : 'suave') + '" id="f_apr">Aprobados (' + nAprobados + ')</button>' +
        '<button class="boton ' + (estado.filtroBandeja === 'Todos' ? '' : 'suave') + '" id="f_tod">Todos (' + solicitudes.length + ')</button>' +
      '</div>' +

      '<div class="acciones" style="background:#fff;padding:10px 14px;border:1px solid var(--borde);border-radius:6px">' +
        '<label style="display:flex;align-items:center;gap:6px;font-weight:600">' +
          '<input type="checkbox" id="chkTodos"> Seleccionar todos' +
        '</label>' +
        '<button class="boton" id="btnAprobarLote" disabled>Aprobar seleccionados en lote</button>' +
      '</div>' +

      '<div class="tabla-ancha"><table><thead><tr>' +
        '<th style="width:36px;text-align:center">✓</th>' +
        '<th>Institución</th><th>Curso</th><th>Estudiante</th>' +
        '<th style="width:130px;text-align:center">Fecha Pedido</th>' +
        '<th style="width:130px;text-align:center">Estado</th>' +
        '<th style="width:230px;text-align:center">Acciones</th>' +
      '</tr></thead><tbody>' + (filasHtml || '<tr><td colspan="7" class="vacio">No hay pedidos en esta sección.</td></tr>') + '</tbody></table></div>';

    $('f_pen').addEventListener('click', function () { estado.filtroBandeja = 'Pendiente'; verBandejaTitulos(); });
    $('f_obs').addEventListener('click', function () { estado.filtroBandeja = 'Observado'; verBandejaTitulos(); });
    $('f_apr').addEventListener('click', function () { estado.filtroBandeja = 'Aprobado'; verBandejaTitulos(); });
    $('f_tod').addEventListener('click', function () { estado.filtroBandeja = 'Todos'; verBandejaTitulos(); });

    var chkTodos = $('chkTodos');
    var chks = document.querySelectorAll('.chk-sol');
    chkTodos.addEventListener('change', function () {
      chks.forEach(function (c) { c.checked = chkTodos.checked; });
      actualizarBotonLote();
    });

    chks.forEach(function (c) {
      c.addEventListener('change', actualizarBotonLote);
    });

    function actualizarBotonLote() {
      var seleccionados = Array.from(document.querySelectorAll('.chk-sol:checked'));
      var btn = $('btnAprobarLote');
      btn.disabled = seleccionados.length === 0;
      btn.textContent = 'Aprobar seleccionados en lote (' + seleccionados.length + ')';
    }

    $('btnAprobarLote').addEventListener('click', async function () {
      var ids = Array.from(document.querySelectorAll('.chk-sol:checked')).map(function (c) { return c.value; });
      if (!ids.length) return;
      if (!confirm('¿Confirma la aprobación en lote de ' + ids.length + ' certificado(s)? Se generarán números correlativos oficiales y las notas quedarán congeladas.')) {
        return;
      }
      avisar('Aprobando en lote…');
      try {
        var res = await llamar('/api/solicitudes/aprobar-lote', 'POST', { ids: ids });
        avisar('¡Se aprobaron ' + res.cantidad + ' certificados con éxito!', 'ok');
        verBandejaTitulos();
      } catch (err) {
        problema(err);
      }
    });

  } catch (e) {
    problema(e);
  }
}

// Modales para Aprobar y Observar
function abrirModalAprobar(idSol, nombre) {
  var modal = document.createElement('div');
  modal.className = 'modal-backdrop';
  modal.id = 'modalActivo';
  modal.innerHTML =
    '<div class="modal-caja">' +
      '<h2>Aprobar Certificado Oficial</h2>' +
      '<p>Estudiante: <b>' + esc(nombre) + '</b></p>' +
      '<p style="font-size:12px;color:var(--suave)">Al aprobar, se genera el número oficial y las notas del estudiante quedan bloqueadas permanentemente.</p>' +
      '<label style="display:block;margin:12px 0">' +
        'Número de Certificado (dejar vacío para correlativo automático AÑO-00000001-CUE):' +
        '<input id="m_numCert" style="width:100%;margin-top:6px" placeholder="Ej: 2026-00000001-3800006">' +
      '</label>' +
      '<div class="acciones" style="justify-content:flex-end">' +
        '<button class="boton suave" onclick="cerrarModal()">Cancelar</button>' +
        '<button class="boton" id="btnConfirmarAprobar">Aprobar y Congelar Notas</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(modal);

  $('btnConfirmarAprobar').addEventListener('click', async function () {
    var num = $('m_numCert').value.trim();
    cerrarModal();
    avisar('Aprobando certificado…');
    try {
      await llamar('/api/solicitudes/' + encodeURIComponent(idSol) + '/aprobar', 'POST', { numeroCertificado: num });
      avisar('¡Certificado aprobado exitosamente!', 'ok');
      verBandejaTitulos();
    } catch (e) {
      problema(e);
    }
  });
}

function abrirModalObservar(idSol, nombre) {
  var modal = document.createElement('div');
  modal.className = 'modal-backdrop';
  modal.id = 'modalActivo';
  modal.innerHTML =
    '<div class="modal-caja">' +
      '<h2>Observar Solicitud de Certificado</h2>' +
      '<p>Estudiante: <b>' + esc(nombre) + '</b></p>' +
      '<p style="font-size:12px;color:var(--mal)">El motivo de observación es obligatorio. La escuela verá este texto para realizar las correcciones necesarias.</p>' +
      '<label style="display:block;margin:12px 0">' +
        '<b>Motivo de observación (Obligatorio):</b>' +
        '<textarea id="m_motivo" rows="4" style="width:100%;margin-top:6px;border:1px solid var(--borde);padding:8px" placeholder="Escriba detalladamente el motivo del rechazo u observación…"></textarea>' +
      '</label>' +
      '<div class="acciones" style="justify-content:flex-end">' +
        '<button class="boton suave" onclick="cerrarModal()">Cancelar</button>' +
        '<button class="boton" style="background:var(--mal)" id="btnConfirmarObservar">Confirmar Observación</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(modal);

  $('btnConfirmarObservar').addEventListener('click', async function () {
    var motivo = $('m_motivo').value.trim();
    if (!motivo) {
      alert('Debes ingresar un motivo de observación obligatorio.');
      return;
    }
    cerrarModal();
    avisar('Registrando observación…');
    try {
      await llamar('/api/solicitudes/' + encodeURIComponent(idSol) + '/observar', 'POST', { motivo: motivo });
      avisar('Solicitud observada y devuelta a la escuela.', 'ok');
      verBandejaTitulos();
    } catch (e) {
      problema(e);
    }
  });
}

function cerrarModal() {
  var m = $('modalActivo');
  if (m) m.remove();
}

async function inspeccionarAnaliticoModal(idCurso, doc) {
  avisar('Generando analítico de inspección…');
  try {
    var r = await llamar('/api/curso/' + encodeURIComponent(idCurso) + '/analitico?documento=' + encodeURIComponent(doc));
    var modal = document.createElement('div');
    modal.className = 'modal-backdrop';
    modal.id = 'modalActivo';
    modal.innerHTML =
      '<div class="modal-caja" style="max-width:850px;max-height:85vh;overflow:auto">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">' +
          '<h2>Inspección de Analítico</h2>' +
          '<button class="boton suave" onclick="cerrarModal()">Cerrar</button>' +
        '</div>' +
        armarAnalitico(r.analitico) +
      '</div>';
    document.body.appendChild(modal);
  } catch (e) {
    problema(e);
  }
}

// Modal para cargar un nuevo alumno en el curso actual (Rol Administrativo / Dirección)
function mostrarModalNuevoEstudiante() {
  var modal = document.createElement('div');
  modal.className = 'modal-backdrop';
  modal.id = 'modalActivo';
  modal.innerHTML =
    '<div class="modal-caja" style="max-width:520px">' +
      '<h2>+ Cargar Alumno en el Curso</h2>' +
      '<p style="font-size:12px;color:var(--suave);margin-top:2px">Completá los datos personales del estudiante para incorporarlo al Registro Anual de Calificaciones y al Acta de Examen.</p>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px">' +
        '<label style="display:block;font-size:12px;font-weight:600">Apellido(s) *' +
          '<input id="ne_apellido" style="width:100%;margin-top:4px" placeholder="Ej: GÓMEZ">' +
        '</label>' +
        '<label style="display:block;font-size:12px;font-weight:600">Nombre(s) *' +
          '<input id="ne_nombres" style="width:100%;margin-top:4px" placeholder="Ej: Juan Carlos">' +
        '</label>' +
        '<label style="display:block;font-size:12px;font-weight:600">Tipo Doc.' +
          '<select id="ne_tipodoc" style="width:100%;margin-top:4px"><option value="DNI">DNI</option><option value="CI">CI</option><option value="Pasaporte">Pasaporte</option></select>' +
        '</label>' +
        '<label style="display:block;font-size:12px;font-weight:600">N° de Documento (DNI) *' +
          '<input id="ne_documento" style="width:100%;margin-top:4px" placeholder="Ej: 42123456">' +
        '</label>' +
        '<label style="display:block;font-size:12px;font-weight:600">Fecha de Nacimiento' +
          '<input id="ne_fechanac" style="width:100%;margin-top:4px" placeholder="dd/mm/aaaa">' +
        '</label>' +
        '<label style="display:block;font-size:12px;font-weight:600">Folio N° (opcional)' +
          '<input id="ne_folio" style="width:100%;margin-top:4px" placeholder="Autocompletar">' +
        '</label>' +
        '<label style="display:block;font-size:12px;font-weight:600">Lugar de Nac. · Provincia' +
          '<input id="ne_provincia" style="width:100%;margin-top:4px" value="Jujuy">' +
        '</label>' +
        '<label style="display:block;font-size:12px;font-weight:600">Lugar de Nac. · País' +
          '<input id="ne_pais" style="width:100%;margin-top:4px" value="Argentina">' +
        '</label>' +
      '</div>' +
      '<div class="acciones" style="justify-content:flex-end;margin-top:16px">' +
        '<button type="button" class="boton suave" onclick="cerrarModal()">Cancelar</button>' +
        '<button type="button" class="boton" style="background:#137333" id="btnGuardarEstudiante">Guardar Alumno</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(modal);
  if ($('ne_apellido')) $('ne_apellido').focus();

  $('btnGuardarEstudiante').addEventListener('click', async function () {
    var ape = $('ne_apellido').value.trim();
    var nom = $('ne_nombres').value.trim();
    var doc = $('ne_documento').value.trim();
    if (!ape || !nom || !doc) {
      avisar('Completá Apellido, Nombres y N° de Documento (DNI).', 'error');
      return;
    }
    $('btnGuardarEstudiante').disabled = true;
    try {
      await llamar('/api/curso/' + encodeURIComponent(estado.curso.id) + '/estudiante', 'POST', {
        apellido: ape,
        nombres: nom,
        tipoDoc: $('ne_tipodoc').value,
        documento: doc,
        fechaNac: $('ne_fechanac').value.trim(),
        provincia: $('ne_provincia').value.trim(),
        pais: $('ne_pais').value.trim(),
        folio: $('ne_folio').value.trim()
      });
      cerrarModal();
      avisar('¡Alumno ' + ape.toUpperCase() + ', ' + nom + ' cargado con éxito!', 'ok');
      abrirCurso(estado.curso.id, 'notas');
    } catch (e) {
      problema(e);
      $('btnGuardarEstudiante').disabled = false;
    }
  });
}

// Modal para crear curso
function mostrarModalNuevoCurso() {
  var modal = document.createElement('div');
  modal.className = 'panel';
  modal.style.maxWidth = '550px';
  modal.style.margin = '20px auto';
  modal.style.border = '1px solid var(--borde)';
  modal.style.borderRadius = '8px';
  modal.style.boxShadow = '0 4px 16px rgba(0,0,0,0.15)';

  modal.innerHTML =
    '<h2>+ Registrar Nuevo Curso</h2>' +
    '<div style="display:flex;flex-direction:column;gap:10px;margin-top:12px">' +
      '<label>Institución <input id="nc_inst" placeholder="Ej: Escuela Profesional Nº 6" value="Escuela Profesional Nº 6"></label>' +
      '<label>CUE <input id="nc_cue" placeholder="Ej: 3800006" value="3800006"></label>' +
      '<label>Oferta Formativa <input id="nc_oferta" placeholder="Ej: Peluquero" value="Peluquero"></label>' +
      '<label>Ciclo <input id="nc_ciclo" placeholder="2026" value="2026"></label>' +
      '<label>Turno <select id="nc_turno"><option value="Mañana">Mañana</option><option value="Tarde">Tarde</option><option value="Vespertino" selected>Vespertino</option></select></label>' +
      '<label>Curso / División <input id="nc_division" placeholder=\'1º "U"\' value=\'1º "U"\'></label>' +
      '<label>ID del archivo de Google Drive <input id="nc_id" placeholder="Opcional (se genera automático si queda vacío)"></label>' +
      '<div class="acciones" style="justify-content:flex-end;margin-top:14px">' +
        '<button class="boton suave" id="nc_cancelar">Cancelar</button>' +
        '<button class="boton" id="nc_guardar">Guardar curso</button>' +
      '</div>' +
    '</div>';

  $('main').innerHTML = '';
  $('main').appendChild(modal);

  $('nc_cancelar').addEventListener('click', verCursos);
  $('nc_guardar').addEventListener('click', async function () {
    var payload = {
      cue: $('nc_cue').value.trim(),
      institucion: $('nc_inst').value.trim(),
      oferta: $('nc_oferta').value.trim(),
      ciclo: $('nc_ciclo').value.trim(),
      turno: $('nc_turno').value,
      division: $('nc_division').value.trim(),
      id: $('nc_id').value.trim() || ('curso-' + Date.now()),
      estado: 'Abierto'
    };
    try {
      var r = await llamar('/api/cursos', 'POST', payload);
      estado.cursos.push(r.curso);
      avisar('Curso registrado con éxito. Ahora podés cargar sus alumnos.', 'ok');
      abrirCurso(r.curso.id);
    } catch (e) {
      problema(e);
    }
  });
}

// ---------- MODAL IMPORTAR VIEJO EXCEL (.XLSM / .XLSX) ----------
function mostrarModalImportarExcel() {
  $('migas').hidden = false;
  var modal = document.createElement('div');
  modal.style.background = '#fff';
  modal.style.padding = '24px';
  modal.style.maxWidth = '540px';
  modal.style.margin = '20px auto';
  modal.style.border = '1px solid var(--borde)';
  modal.style.borderRadius = '8px';
  modal.style.boxShadow = '0 4px 16px rgba(0,0,0,0.15)';

  modal.innerHTML =
    '<h2>📥 Importar Viejo Excel (.xlsm / .xlsx)</h2>' +
    '<p style="color:var(--suave);font-size:13px;line-height:1.5;margin-top:4px">' +
      'Seleccioná el archivo histórico de Excel con macros (<b>.xlsm</b>) o planilla (<b>.xlsx</b>) de la escuela. ' +
      'El conversor automático migrará la nómina de estudiantes, los módulos, las calificaciones y el Acta de Examen sin necesidad de volver a tipear.' +
    '</p>' +
    '<div style="border:2px dashed var(--azul);background:var(--celeste);padding:20px;border-radius:8px;text-align:center;margin:16px 0">' +
      '<input type="file" id="inp_excel_file" accept=".xlsm,.xlsx" style="font-size:13px;width:100%">' +
    '</div>' +
    '<div id="estado_importacion" style="font-size:13px;color:var(--azul);margin:8px 0"></div>' +
    '<div class="acciones" style="justify-content:flex-end;margin-top:14px">' +
      '<button class="boton suave" id="imp_cancelar">Cancelar</button>' +
      '<button class="boton" id="imp_procesar" style="background:#137333">Convertir e Importar Curso</button>' +
    '</div>';

  $('main').innerHTML = '';
  $('main').appendChild(modal);

  $('imp_cancelar').addEventListener('click', verCursos);
  $('imp_procesar').addEventListener('click', function () {
    var input = $('inp_excel_file');
    if (!input.files || !input.files.length) {
      avisar('Seleccioná primero un archivo Excel (.xlsm o .xlsx)', 'error');
      return;
    }
    var archivo = input.files[0];
    $('imp_procesar').disabled = true;
    $('estado_importacion').textContent = '⏳ Leyendo y convirtiendo ' + archivo.name + '…';

    var reader = new FileReader();
    reader.onload = async function (ev) {
      try {
        var b64 = ev.target.result;
        var res = await llamar('/api/importar-excel', 'POST', {
          nombreArchivo: archivo.name,
          contenidoBase64: b64
        });
        estado.cursos.push(res.curso);
        avisar('¡Excel importado con éxito! (' + res.cantidadEstudiantes + ' estudiantes y ' + res.cantidadModulos + ' módulos)', 'ok');
        abrirCurso(res.curso.id);
      } catch (e) {
        problema(e);
        $('imp_procesar').disabled = false;
        $('estado_importacion').textContent = '';
      }
    };
    reader.readAsDataURL(archivo);
  });
}

// ---------- RESUMEN DIRECCIÓN DETP ----------
async function verResumen() {
  $('main').innerHTML = '<div class="cargando">Calculando el resumen por institución…</div>';
  $('migas').hidden = false;
  try {
    var r = await llamar('/api/resumen');
    var lista = r.resumen || [];
    var tot = lista.reduce(function (a, i) {
      return {
        cursos: a.cursos + i.cursos,
        estudiantes: a.estudiantes + i.estudiantes,
        aprobados: a.aprobados + i.aprobados
      };
    }, { cursos: 0, estudiantes: 0, aprobados: 0 });

    $('main').innerHTML = '<h1>Resumen por institución</h1>' +
      '<p style="color:var(--suave)">' + tot.cursos + ' cursos · ' + tot.estudiantes +
      ' estudiantes · ' + tot.aprobados + ' con todos los módulos aprobados.</p>' +
      '<table><thead><tr><th>CUE</th><th>Institución</th><th>Cursos</th>' +
      '<th>Estudiantes</th><th>Aprobaron todo</th></tr></thead><tbody>' +
      lista.map(function (i) {
        return '<tr><td>' + esc(i.cue) + '</td><td>' + esc(i.institucion) + '</td>' +
          '<td style="text-align:center">' + i.cursos + '</td>' +
          '<td style="text-align:center">' + i.estudiantes + '</td>' +
          '<td style="text-align:center">' + i.aprobados + '</td></tr>';
      }).join('') + '</tbody></table>';
  } catch (err) {
    problema(err);
  }
}

// ---------- ADMINISTRACIÓN DE USUARIOS (EXCLUSIVO ROL DIRECCIÓN DETP) ----------
async function verAdminUsuarios() {
  $('migas').hidden = false;
  $('main').innerHTML = '<div class="cargando">Cargando padrón de usuarios autorizados…</div>';
  try {
    var r = await llamar('/api/usuarios');
    var usuarios = r.usuarios || [];

    var filas = usuarios.map(function (u) {
      var esOficial = String(u.Email || '').toLowerCase().endsWith('@jujuy.edu.ar');
      var badgeCorreo = esOficial
        ? '<span class="badge-estado badge-aprobado" style="margin-left:6px">@jujuy.edu.ar</span>'
        : '<span class="badge-estado badge-pendiente" style="margin-left:6px">Autorizado</span>';
      var esPrincipal = String(u.Email || '').toLowerCase() === 'sge.detp.areapedagogica@jujuy.edu.ar';

      return '<tr>' +
        '<td><b>' + esc(u.Email) + '</b>' + badgeCorreo + '</td>' +
        '<td>' + esc(u.Nombre) + '</td>' +
        '<td><b>' + esc(u.Rol) + '</b></td>' +
        '<td style="text-align:center">' + esc(u.CUE || 'Todas (Global)') + '</td>' +
        '<td style="text-align:center">' +
          '<span class="badge-estado ' + (u.Activo === 'Sí' ? 'badge-aprobado' : 'badge-observado') + '">' + esc(u.Activo) + '</span>' +
        '</td>' +
        '<td style="text-align:center">' +
          '<button class="boton suave" style="padding:4px 8px;font-size:12px;margin-right:4px" onclick="cargarUsuarioEnFormulario(\'' + esc(u.Email) + '\', \'' + esc(u.Nombre) + '\', \'' + esc(u.Rol) + '\', \'' + esc(u.CUE || '') + '\')">Editar Rol</button>' +
          (esPrincipal
            ? '<span style="color:var(--suave);font-size:11px">Principal</span>'
            : '<button class="boton suave" style="padding:4px 8px;font-size:12px;color:var(--mal);border-color:var(--mal)" onclick="borrarUsuarioSistema(\'' + esc(u.Email) + '\')">Borrar</button>') +
        '</td>' +
      '</tr>';
    }).join('');

    $('main').innerHTML =
      '<h1>Administración de Usuarios · Dirección DETP</h1>' +
      '<p style="color:var(--suave)">Pueden ingresar usuarios con <b>cualquier correo electrónico</b> (<code>@jujuy.edu.ar</code>, <code>@gmail.com</code>, etc.), siempre que un usuario con rol <b>Dirección DETP</b> los dé de alta aquí y les asigne su rol.</p>' +
      '<div style="background:#fff;border:1px solid var(--borde);border-radius:8px;padding:16px;margin:14px 0">' +
        '<h3 style="margin:0 0 12px;font-size:14px">+ Crear Usuario o Modificar Rol</h3>' +
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;align-items:end">' +
          '<div><label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px">Correo electrónico (cualquier dominio)</label>' +
            '<input id="usr_email" class="buscar" style="margin:0;width:100%" placeholder="ejemplo@gmail.com o @jujuy.edu.ar"></div>' +
          '<div><label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px">Nombre y Apellido / Área</label>' +
            '<input id="usr_nombre" class="buscar" style="margin:0;width:100%" placeholder="Ej: Dir. Escuela Prof. N° 6"></div>' +
          '<div><label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px">Rol asignado por Dirección</label>' +
            '<select id="usr_rol" class="buscar" style="margin:0;width:100%">' +
              '<option value="Administrativo">Administrativo (Carga escuela)</option>' +
              '<option value="Directivo">Directivo (Consulta escuela)</option>' +
              '<option value="titulos">titulos (Dirección de Títulos)</option>' +
              '<option value="Dirección DETP">Dirección DETP (Crea/Borra usuarios)</option>' +
            '</select></div>' +
          '<div><label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px">CUE (solo para escuelas)</label>' +
            '<input id="usr_cue" class="buscar" style="margin:0;width:100%" placeholder="Ej: 3800006"></div>' +
          '<div><button class="boton" id="btnGuardarUsr" style="width:100%">Guardar Usuario y Rol</button></div>' +
        '</div>' +
      '</div>' +
      '<div class="tabla-ancha"><table><thead><tr>' +
        '<th>Correo Electrónico</th><th>Nombre / Cargo</th><th>Rol Asignado</th>' +
        '<th style="width:120px;text-align:center">CUE Asignado</th>' +
        '<th style="width:80px;text-align:center">Activo</th>' +
        '<th style="width:170px;text-align:center">Acciones</th>' +
      '</tr></thead><tbody>' + filas + '</tbody></table></div>';

    $('btnGuardarUsr').addEventListener('click', async function () {
      var payload = {
        Email: $('usr_email').value.trim(),
        Nombre: $('usr_nombre').value.trim(),
        Rol: $('usr_rol').value,
        CUE: $('usr_cue').value.trim(),
        Activo: 'Sí'
      };
      try {
        await llamar('/api/usuarios', 'POST', payload);
        avisar('Usuario guardado correctamente', 'ok');
        await cargarUsuariosPrueba();
        verAdminUsuarios();
      } catch (e) {
        problema(e);
      }
    });
  } catch (e) {
    problema(e);
  }
}

function cargarUsuarioEnFormulario(email, nombre, rol, cue) {
  if ($('usr_email')) $('usr_email').value = email;
  if ($('usr_nombre')) $('usr_nombre').value = nombre;
  if ($('usr_rol')) $('usr_rol').value = rol;
  if ($('usr_cue')) $('usr_cue').value = cue;
  if ($('usr_email')) $('usr_email').focus();
  avisar('Editando rol de ' + email + '. Modificá los datos arriba y tocá Guardar.');
}

async function borrarUsuarioSistema(emailObj) {
  if (!confirm('¿Seguro que deseas borrar al usuario ' + emailObj + '?')) return;
  try {
    await llamar('/api/usuarios', 'DELETE', { Email: emailObj });
    avisar('Usuario eliminado: ' + emailObj, 'ok');
    await cargarUsuariosPrueba();
    verAdminUsuarios();
  } catch (e) {
    problema(e);
  }
}
