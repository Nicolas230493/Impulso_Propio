import { supabase } from './supabaseClient.js';

// Todas las consultas filtran por user_id además del RLS.
async function conUsuario(consulta) {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { data: null, error: { message: 'No autorizado' } };
    return await consulta(user.id);
}

const listar = (tabla, orden, ascendente = true) => conUsuario(uid => {
    let q = supabase.from(tabla).select('*').eq('user_id', uid);
    if (orden) q = q.order(orden, { ascending: ascendente });
    return q;
});
const insertar = (tabla, filas) => conUsuario(uid =>
    supabase.from(tabla).insert(filas.map(f => ({ ...f, user_id: uid }))).select());
const actualizar = (tabla, id, cambios) => conUsuario(uid =>
    supabase.from(tabla).update(cambios).eq('id', id).eq('user_id', uid));
const eliminar = (tabla, id) => conUsuario(uid =>
    supabase.from(tabla).delete().eq('id', id).eq('user_id', uid));

// --- Módulo de Transacciones ---

export const cargarTransacciones = () => listar('transacciones', 'fecha', false);
export const guardarTransacciones = filas => insertar('transacciones', filas);
export const eliminarTransaccion = id => eliminar('transacciones', id);
export const eliminarGrupoCuotas = grupoId => conUsuario(uid =>
    supabase.from('transacciones').delete().eq('grupo_id', grupoId).eq('user_id', uid));

// --- Módulo de Categorías ---

export const cargarCategorias = () => listar('categorias', 'nombre');
export const crearCategorias = filas => insertar('categorias', filas);
export const actualizarCategoria = (id, cambios) => actualizar('categorias', id, cambios);
export const eliminarCategoria = id => eliminar('categorias', id);

// Las transacciones guardan el nombre de la categoría, así que se renombran también.
export const renombrarCategoria = (viejo, nuevo) => conUsuario(async uid => {
    for (const tabla of ['transacciones', 'recurrentes']) {
        const { error } = await supabase.from(tabla).update({ categoria: nuevo }).eq('user_id', uid).eq('categoria', viejo);
        if (error) return { error };
    }
    return { error: null };
});

// --- Módulo de Cuentas ---

export const cargarCuentas = () => listar('cuentas', 'creado');
export const crearCuentas = filas => insertar('cuentas', filas);
export const actualizarCuenta = (id, cambios) => actualizar('cuentas', id, cambios);
export const eliminarCuenta = id => eliminar('cuentas', id);

// --- Módulo de Recurrentes ---

export const cargarRecurrentes = () => listar('recurrentes', 'creado');
export const crearRecurrente = fila => insertar('recurrentes', [fila]);
export const actualizarRecurrente = (id, cambios) => actualizar('recurrentes', id, cambios);
export const eliminarRecurrente = id => eliminar('recurrentes', id);

// --- Módulo de Metas ---

export const cargarMetas = () => listar('metas');

export async function guardarMeta(titulo, monto_objetivo, monto_actual, por_que, fecha_limite) {
    return insertar('metas', [{ titulo, monto_objetivo, monto_actual, por_que, fecha_limite }]);
}

export const actualizarProgresoMeta = (id, nuevoMonto) => actualizar('metas', id, { monto_actual: nuevoMonto });
