import streamlit as st
from sheets import safe_worksheet, sh
from config import COLS_ACCESOS
import pandas as pd

@st.cache_data(ttl=60)
def obtener_usuarios():
    if sh is None:
        return {}, [], pd.DataFrame()
    ws, err = safe_worksheet(sh, "Accesos")
    if err:
        try:
            ws = sh.add_worksheet(title="Accesos", rows="100", cols="3")
            ws.append_row(COLS_ACCESOS)
            ws.append_rows([
                ["13070518","Raúl","admin"],
                ["987654","Jenny","barista"],
                ["ilecara","Araceli","barista"],
            ])
        except Exception as e:
            st.warning(f"No se pudo crear hoja Accesos: {e}")
            return {}, [], pd.DataFrame()
    try:
        data = ws.get_all_values()
        if len(data) < 2:
            return {}, [], pd.DataFrame()
        df_usr = pd.DataFrame(data[1:], columns=data[0])
        for col in COLS_ACCESOS:
            if col not in df_usr.columns:
                df_usr[col] = ""
        usuarios_dict = {
            str(r["Clave"]): {"nombre": str(r["Nombre"]), "rol": str(r["Rol"])}
            for _, r in df_usr.iterrows()
            if str(r.get("Clave","")).strip()
        }
        return usuarios_dict, df_usr["Nombre"].dropna().tolist(), df_usr
    except Exception as e:
        st.warning(f"Error cargando usuarios: {e}")
        return {}, [], pd.DataFrame()

USUARIOS_PIN, LISTA_RESPONSABLES, DF_USUARIOS = obtener_usuarios()

def cargar_permisos():
    if sh is None:
        return {"admin": ["*"], "barista": ["Dashboard","Inventario","Ingresos","Consulta","Impresion","ListaCompra","ReporteStock"]}
    ws, err = safe_worksheet(sh, "Permisos")
    if err:
        return {"admin": ["*"], "barista": ["Dashboard","Inventario","Ingresos","Consulta","Impresion","ListaCompra","ReporteStock"]}
    try:
        data = ws.get_all_values()
        if len(data) < 2:
            return {"admin": ["*"], "barista": ["Dashboard","Inventario","Ingresos","Consulta","Impresion","ListaCompra","ReporteStock"]}
        df = pd.DataFrame(data[1:], columns=data[0])
        permisos = {}
        for _, row in df.iterrows():
            rol = str(row.get("Rol","")).strip()
            pagina = str(row.get("Pagina","")).strip()
            if rol not in permisos:
                permisos[rol] = []
            if pagina:
                permisos[rol].append(pagina)
        return permisos
    except Exception:
        return {"admin": ["*"], "barista": ["Dashboard","Inventario","Ingresos","Consulta","Impresion","ListaCompra","ReporteStock"]}

PERMISOS = cargar_permisos()

def tiene_permiso(pagina: str) -> bool:
    if not st.session_state.auth_status:
        return False
    rol = st.session_state.user_role
    if rol == "admin":
        return True
    if rol in PERMISOS:
        if "*" in PERMISOS[rol]:
            return True
        return pagina in PERMISOS[rol]
    return True

def validar_usuario(clave: str):
    """
    Consulta Google Sheets en vivo y valida la clave.
    Retorna (nombre, rol) si existe; de lo contrario (None, None).
    """
    obtener_usuarios.clear()
    usuarios, _, _ = obtener_usuarios()
    if clave in usuarios:
        return usuarios[clave]["nombre"], usuarios[clave]["rol"]
    return None, None
