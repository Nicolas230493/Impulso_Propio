import { supabase } from './supabaseClient.js';

export async function registrarUsuario(email, password) {
    try {
        const { data, error } = await supabase.auth.signUp({ email, password });
        if (error) return { success: false, error: error.message };
        return { success: true, data };
    } catch (err) {
        console.error('Error inesperado en registro:', err);
        return { success: false, error: err.message };
    }
}

export async function iniciarSesion(email, password) {
    try {
        const { data, error } = await supabase.auth.signInWithPassword({
            email: email,
            password: password
        });

        if (error) {
            console.error('Error de autenticación:', error.message);
            return { success: false, error: error.message };
        }

        return { success: true, user: data.user };
    } catch (err) {
        console.error('Error inesperado:', err);
        return { success: false, error: err.message };
    }
}

export async function cerrarSesion() {
    await supabase.auth.signOut();
}

export async function obtenerUsuarioActual() {
    const { data: { user }, error } = await supabase.auth.getUser();
    return { user, error };
}
