import { supabase } from './supabaseClient.js';
import {
    actualizarResumenFinanciero, renderizarMetas, inicializarGraficos, actualizarGraficos, renderizarTablaTransacciones,
    renderizarAlertaPresupuesto, renderizarReportes, renderizarCategorias, renderizarCuentas, renderizarRecurrentes,
    llenarSelects, descargarCSV
} from './dashboard.js';
import {
    guardarMeta, cargarTransacciones, guardarTransacciones, eliminarTransaccion, eliminarGrupoCuotas,
    cargarCategorias, crearCategorias, actualizarCategoria, eliminarCategoria, renombrarCategoria,
    cargarCuentas, crearCuentas, actualizarCuenta, eliminarCuenta,
    cargarRecurrentes, crearRecurrente, actualizarRecurrente, eliminarRecurrente
} from './dataService.js';
import { cerrarSesion, iniciarSesion, registrarUsuario } from './auth.js';
import { hoyISO, mesActual, delMes, filasCuotas, pendientesRecurrente } from './utils.js';

const CATEGORIAS_POR_DEFECTO = ['Alimentación', 'Transporte', 'Vivienda', 'Salario', 'Otros'];
const CUENTAS_POR_DEFECTO = [
    { nombre: 'Efectivo', tipo: 'efectivo' },
    { nombre: 'Tarjeta', tipo: 'tarjeta' },
    { nombre: 'Transferencia', tipo: 'transferencia' },
];

const estado = { transacciones: [], categorias: [], cuentas: [], recurrentes: [] };
let usuarioIniciado = null;

// Inicializar gráficos una vez al cargar la app
inicializarGraficos();

const authContainer = document.getElementById('auth-container');
const appContainer = document.getElementById('app-container');
const authForm = document.getElementById('auth-form');
const btnRegister = document.getElementById('btn-register');
const authError = document.getElementById('auth-error');
const btnLogout = document.getElementById('btn-logout');

const formMeta = document.getElementById('form-meta');
const formTransaccion = document.getElementById('form-transaccion');
const tablaTransacciones = document.getElementById('tabla-transacciones');
const btnGuardarTrans = document.getElementById('btn-guardar-trans');
const filtroMes = document.getElementById('filtro-mes');

const transCuenta = document.getElementById('trans-cuenta');
const transMoneda = document.getElementById('trans-moneda');
const transTC = document.getElementById('trans-tc');
const transCuotas = document.getElementById('trans-cuotas');
const transRecurrente = document.getElementById('trans-recurrente');

filtroMes.value = mesActual();

// --- FUNCIONES DE UI ---

async function mostrarDashboard(usuario) {
    authContainer.classList.add('hidden');
    appContainer.classList.remove('hidden');
    authError.textContent = '';
    document.getElementById('user-email').textContent = usuario.email;

    // onAuthStateChange dispara varias veces (sesión inicial, refresh de token): inicializar una sola vez.
    if (usuarioIniciado === usuario.id) return;
    usuarioIniciado = usuario.id;
    await recargarDashboard();
    await sembrarDatosIniciales();
    prepararFormulario();
}

function mostrarLogin() {
    usuarioIniciado = null;
    authContainer.classList.remove('hidden');
    appContainer.classList.add('hidden');
}

function cuentaSeleccionada() {
    return estado.cuentas.find(c => c.id === transCuenta.value);
}

// Muestra TC solo en USD y cuotas solo para gastos con tarjeta.
function actualizarCamposCondicionales() {
    const esGasto = document.querySelector('input[name="trans-tipo"]:checked').value === 'gasto';
    transTC.classList.toggle('hidden', transMoneda.value !== 'USD');
    document.getElementById('campo-cuotas').classList.toggle('hidden', !(esGasto && cuentaSeleccionada()?.tipo === 'tarjeta'));
}

// Valores por defecto para cargar rápido: hoy, última cuenta usada, último TC.
function prepararFormulario() {
    document.getElementById('trans-fecha').value = hoyISO();
    const ultimaCuenta = localStorage.getItem('ultimaCuenta');
    if (estado.cuentas.some(c => c.id === ultimaCuenta)) transCuenta.value = ultimaCuenta;
    transMoneda.value = cuentaSeleccionada()?.moneda ?? 'ARS';
    transTC.value = localStorage.getItem('ultimoTC') ?? '';
    transCuotas.value = 1;
    actualizarCamposCondicionales();
    document.getElementById('trans-monto').focus();
}

// --- LÓGICA DE DATOS ---

async function cargarDatos() {
    const [transacciones, categorias, cuentas, recurrentes] = await Promise.all([
        cargarTransacciones(), cargarCategorias(), cargarCuentas(), cargarRecurrentes()
    ]);
    const conError = [transacciones, categorias, cuentas, recurrentes].find(r => r.error);
    if (conError) {
        alert('Error al cargar datos: ' + conError.error.message);
        return false;
    }
    estado.transacciones = transacciones.data;
    estado.categorias = categorias.data;
    estado.cuentas = cuentas.data;
    estado.recurrentes = recurrentes.data;
    return true;
}

// Primera vez que entra el usuario: categorías y cuentas por defecto.
async function sembrarDatosIniciales() {
    const pendientes = [];
    if (!estado.categorias.length) pendientes.push(crearCategorias(CATEGORIAS_POR_DEFECTO.map(nombre => ({ nombre }))));
    if (!estado.cuentas.length) pendientes.push(crearCuentas(CUENTAS_POR_DEFECTO));
    if (!pendientes.length) return;
    await Promise.all(pendientes);
    await recargarDashboard();
}

// Genera los movimientos de los recurrentes que vencieron desde la última vez.
async function generarRecurrentes() {
    let generados = false;
    for (const r of estado.recurrentes) {
        const { filas, ultimoMes } = pendientesRecurrente(r);
        if (!filas.length) continue;
        const { error } = await guardarTransacciones(filas);
        if (error) {
            console.error('Error al generar recurrente:', error);
            continue;
        }
        await actualizarRecurrente(r.id, { ultimo_mes: ultimoMes });
        generados = true;
    }
    return generados;
}

async function recargarDashboard() {
    if (!(await cargarDatos())) return;
    if (await generarRecurrentes()) await cargarDatos();
    await renderizar();
}

async function renderizar() {
    const mes = filtroMes.value || mesActual();
    const filtradas = delMes(estado.transacciones, mes);

    llenarSelects(estado.categorias, estado.cuentas);
    renderizarAlertaPresupuesto(estado.transacciones, estado.categorias, mesActual());
    actualizarResumenFinanciero(filtradas);
    renderizarTablaTransacciones(filtradas, estado.cuentas);
    actualizarGraficos(filtradas);
    renderizarReportes(estado.transacciones, mes);
    renderizarCuentas(estado.cuentas, estado.transacciones);
    renderizarCategorias(estado.categorias);
    renderizarRecurrentes(estado.recurrentes, estado.cuentas);
    await renderizarMetas();
}

// Ejecuta una operación, avisa si falla y recarga.
async function ejecutar(operacion) {
    const { error } = await operacion;
    if (error) alert('Error: ' + error.message);
    await recargarDashboard();
    return !error;
}

// --- PERSISTENCIA Y EVENTOS ---

filtroMes.addEventListener('change', renderizar);

supabase.auth.onAuthStateChange((event, session) => {
    // Las llamadas a Supabase dentro de este callback pueden bloquearse: se difieren con setTimeout.
    setTimeout(() => {
        if (session) mostrarDashboard(session.user);
        else mostrarLogin();
    }, 0);
});

// Listener formulario Login
authForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('auth-email').value.trim();
    const password = document.getElementById('auth-password').value.trim();

    authError.textContent = 'Iniciando sesión...';
    authError.className = 'mt-4 text-center text-blue-500 font-semibold';

    const { success, error } = await iniciarSesion(email, password);

    if (!success) {
        authError.textContent = error;
        authError.className = 'mt-4 text-center text-red-500 font-semibold';
    } else {
        authError.textContent = '';
    }
});

// Listener botón Registrar
btnRegister.addEventListener('click', async () => {
    const email = document.getElementById('auth-email').value.trim();
    const password = document.getElementById('auth-password').value.trim();

    if (!email || !password) {
        authError.textContent = 'Por favor ingresa email y contraseña';
        return;
    }

    const { error } = await registrarUsuario(email, password);
    if (error) authError.textContent = error;
    else authError.textContent = 'Registro exitoso. Revisa tu email.';
});

// Listener formulario metas
formMeta.addEventListener('submit', async (e) => {
    e.preventDefault();
    const titulo = document.getElementById('meta-titulo').value;
    const objetivo = parseFloat(document.getElementById('meta-monto-objetivo').value);
    const actual = parseFloat(document.getElementById('meta-monto-actual').value);
    const fecha = document.getElementById('meta-fecha-limite').value;
    const porque = document.getElementById('meta-por-que').value;

    const { error } = await guardarMeta(titulo, objetivo, actual, porque, fecha);

    if (error) alert('Error: ' + error.message);
    else {
        formMeta.reset();
        await renderizarMetas();
    }
});

// Campos condicionales del formulario de movimientos
transCuenta.addEventListener('change', () => {
    transMoneda.value = cuentaSeleccionada()?.moneda ?? 'ARS';
    actualizarCamposCondicionales();
});
transMoneda.addEventListener('change', actualizarCamposCondicionales);
document.querySelectorAll('input[name="trans-tipo"]').forEach(r => r.addEventListener('change', actualizarCamposCondicionales));

// Listener formulario transacciones
formTransaccion.addEventListener('submit', async (e) => {
    e.preventDefault();

    const monto = parseFloat(document.getElementById('trans-monto').value);
    const fecha = document.getElementById('trans-fecha').value;
    const moneda = transMoneda.value;
    const tipoCambio = moneda === 'USD' ? parseFloat(transTC.value) : 1;
    const cuotas = document.getElementById('campo-cuotas').classList.contains('hidden') ? 1 : parseInt(transCuotas.value, 10) || 1;
    const repetir = transRecurrente.checked;

    if (moneda === 'USD' && !(tipoCambio > 0)) {
        alert('Cargá el tipo de cambio para un movimiento en dólares.');
        return;
    }
    if (repetir && cuotas > 1) {
        alert('Un movimiento no puede ser en cuotas y recurrente a la vez.');
        return;
    }

    const base = {
        tipo: document.querySelector('input[name="trans-tipo"]:checked').value,
        categoria: document.getElementById('trans-categoria').value,
        cuenta_id: transCuenta.value || null,
        moneda,
        tipo_cambio: tipoCambio,
        descripcion: document.getElementById('trans-descripcion').value.trim() || null,
    };

    btnGuardarTrans.textContent = 'Guardando...';
    btnGuardarTrans.disabled = true;

    let resultado;
    if (repetir) {
        resultado = await crearRecurrente({ ...base, monto, dia: Number(fecha.slice(8, 10)), ultimo_mes: fecha.slice(0, 7) });
        if (!resultado.error) {
            resultado = await guardarTransacciones([{ ...base, monto, fecha, recurrente_id: resultado.data[0].id }]);
        }
    } else {
        resultado = await guardarTransacciones(filasCuotas(base, monto, fecha, cuotas, crypto.randomUUID()));
    }

    btnGuardarTrans.textContent = 'Guardar Movimiento';
    btnGuardarTrans.disabled = false;

    if (resultado.error) {
        alert('Error: ' + resultado.error.message);
        return;
    }

    if (base.cuenta_id) localStorage.setItem('ultimaCuenta', base.cuenta_id);
    if (moneda === 'USD') localStorage.setItem('ultimoTC', tipoCambio);
    const tipoActual = base.tipo;
    formTransaccion.reset();
    document.querySelector(`input[name="trans-tipo"][value="${tipoActual}"]`).checked = true;
    await recargarDashboard();
    prepararFormulario();
});

// Event Delegation para eliminar transacciones
tablaTransacciones.addEventListener('click', async (e) => {
    if (!e.target.classList.contains('btn-eliminar-trans')) return;
    const { id, grupo, cuotas } = e.target.dataset;

    if (grupo) {
        if (confirm(`Este gasto es parte de ${cuotas} cuotas. ¿Eliminar todas?`)) await ejecutar(eliminarGrupoCuotas(grupo));
    } else if (confirm('¿Eliminar transacción?')) {
        await ejecutar(eliminarTransaccion(id));
    }
});

// Exportar CSV
document.getElementById('btn-exportar-mes').addEventListener('click', () => {
    const mes = filtroMes.value || mesActual();
    descargarCSV(delMes(estado.transacciones, mes), estado.cuentas, `movimientos-${mes}.csv`);
});
document.getElementById('btn-exportar-todo').addEventListener('click', () => {
    descargarCSV(estado.transacciones, estado.cuentas, `movimientos-backup-${hoyISO()}.csv`);
});

// Categorías
document.getElementById('form-categoria').addEventListener('submit', async (e) => {
    e.preventDefault();
    const nombre = document.getElementById('categoria-nombre').value.trim();
    const tope = parseFloat(document.getElementById('categoria-tope').value);
    if (await ejecutar(crearCategorias([{ nombre, tope_mensual: tope > 0 ? tope : null }]))) e.target.reset();
});

document.getElementById('categorias-lista').addEventListener('click', async (e) => {
    const fila = e.target.closest('.fila-categoria');
    if (!fila) return;
    const { id, nombre: nombreViejo } = fila.dataset;

    if (e.target.classList.contains('btn-guardar-cat')) {
        const nombre = fila.querySelector('.cat-nombre').value.trim();
        const tope = parseFloat(fila.querySelector('.cat-tope').value);
        if (!nombre) return alert('La categoría necesita un nombre.');
        const { error } = await actualizarCategoria(id, { nombre, tope_mensual: tope > 0 ? tope : null });
        if (error) return alert('Error: ' + error.message);
        if (nombre !== nombreViejo) await ejecutar(renombrarCategoria(nombreViejo, nombre));
        else await recargarDashboard();
    } else if (e.target.classList.contains('btn-eliminar-cat')) {
        if (confirm(`¿Eliminar la categoría "${nombreViejo}"? Los movimientos existentes la conservan.`)) {
            await ejecutar(eliminarCategoria(id));
        }
    }
});

// Cuentas
document.getElementById('form-cuenta').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fila = {
        nombre: document.getElementById('cuenta-nombre').value.trim(),
        tipo: document.getElementById('cuenta-tipo').value,
        moneda: document.getElementById('cuenta-moneda').value,
        saldo_inicial: parseFloat(document.getElementById('cuenta-saldo-inicial').value) || 0,
    };
    if (await ejecutar(crearCuentas([fila]))) e.target.reset();
});

document.getElementById('cuentas-lista').addEventListener('click', async (e) => {
    const fila = e.target.closest('.fila-cuenta');
    if (!fila) return;
    const { id } = fila.dataset;

    if (e.target.classList.contains('btn-guardar-cuenta')) {
        const nombre = fila.querySelector('.cuenta-nombre').value.trim();
        if (!nombre) return alert('La cuenta necesita un nombre.');
        await ejecutar(actualizarCuenta(id, {
            nombre,
            tipo: fila.querySelector('.cuenta-tipo').value,
            moneda: fila.querySelector('.cuenta-moneda').value,
            saldo_inicial: parseFloat(fila.querySelector('.cuenta-saldo-inicial').value) || 0,
        }));
    } else if (e.target.classList.contains('btn-eliminar-cuenta')) {
        if (confirm('¿Eliminar la cuenta? Sus movimientos quedan sin cuenta asignada.')) await ejecutar(eliminarCuenta(id));
    }
});

// Recurrentes
document.getElementById('recurrentes-lista').addEventListener('click', async (e) => {
    if (!e.target.classList.contains('btn-eliminar-recurrente')) return;
    const { id } = e.target.closest('[data-id]').dataset;
    if (confirm('¿Dejar de repetir? Los movimientos ya generados se conservan.')) await ejecutar(eliminarRecurrente(id));
});

// Función de Cierre de Sesión
btnLogout.addEventListener('click', async () => {
    await cerrarSesion();
});
