import streamlit as st
import gspread
import time
import json
from google.oauth2.service_account import Credentials
from config import (
    SPREADSHEET_ID, COLS_VENTAS, COLS_GASTOS, COLS_PRESUPUESTO,
    COLS_COSTOS_INSUMOS, COLS_RECETAS, COLS_COMBOS, COLS_MERMA, COLS_CALENDARIO,
    COLS_MENUS, COLS_MENUS_HISTORIAL
)
from utils import ts_hermosillo

@st.cache_resource
def conectar_google_sheets():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        creds_info = st.secrets["gcp_service_account"]
        if isinstance(creds_info, str):
            creds_info = json.loads(creds_info)
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(creds)
        return client.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        st.error(f"Error crítico de conexión con Google Sheets: {e}")
        return None

sh = conectar_google_sheets()

def safe_worksheet(sh, nombre: str):
    if sh is None:
        return None, "Sin conexión activa a Google Sheets."
    try:
        return sh.worksheet(nombre), None
    except gspread.exceptions.WorksheetNotFound:
        return None, f"Pestaña '{nombre}' no encontrada en el Spreadsheet."
    except Exception as e:
        return None, f"Error accediendo a '{nombre}': {e}"

def append_rows_con_retry(worksheet, filas: list, max_intentos: int = 3) -> tuple:
    if not filas:
        return False, "No hay filas para escribir."
    for intento in range(1, max_intentos + 1):
        try:
            worksheet.append_rows(filas, value_input_option="USER_ENTERED")
            return True, f"{len(filas)} fila(s) registrada(s)."
        except gspread.exceptions.APIError as e:
            codigo = getattr(e.response, 'status_code', 0)
            if codigo == 429 and intento < max_intentos:
                time.sleep(2 ** intento)
                continue
            return False, f"Error de API Sheets (intento {intento}/{max_intentos}): {e}"
        except Exception as e:
            return False, f"Error inesperado al escribir en Sheets: {e}"
    return False, "Se agotaron los reintentos de escritura."

def _asegurar_hoja_ventas():
    ws, err = safe_worksheet(sh, "Ventas")
    if err:
        try:
            ws = sh.add_worksheet(title="Ventas", rows="2000", cols=str(len(COLS_VENTAS)))
            ws.append_row(COLS_VENTAS)
            return ws, None
        except Exception as e:
            return None, f"No se pudo crear hoja Ventas: {e}"
    return ws, None

def _asegurar_hoja_gastos():
    ws, err = safe_worksheet(sh, "Gastos")
    if err:
        try:
            ws = sh.add_worksheet(title="Gastos", rows="5000", cols=str(len(COLS_GASTOS)))
            ws.append_row(COLS_GASTOS)
            return ws, None
        except Exception as e:
            return None, f"No se pudo crear hoja Gastos: {e}"
    return ws, None

def _asegurar_hoja_presupuesto():
    ws, err = safe_worksheet(sh, "Presupuesto")
    if err:
        try:
            ws = sh.add_worksheet(title="Presupuesto", rows="500", cols=str(len(COLS_PRESUPUESTO)))
            ws.append_row(COLS_PRESUPUESTO)
            return ws, None
        except Exception as e:
            return None, f"No se pudo crear hoja Presupuesto: {e}"
    return ws, None

def _asegurar_hoja_costos_insumos():
    ws, err = safe_worksheet(sh, "CostosInsumos")
    if err:
        try:
            ws = sh.add_worksheet(title="CostosInsumos", rows="2000", cols=str(len(COLS_COSTOS_INSUMOS)))
            ws.append_row(COLS_COSTOS_INSUMOS)
            return ws, None
        except Exception as e:
            return None, f"No se pudo crear hoja CostosInsumos: {e}"
    return ws, None

def _asegurar_hoja_recetas():
    try:
        ws = sh.worksheet("Recetas")
        encabezados_actuales = ws.row_values(1)
        if len(encabezados_actuales) < len(COLS_RECETAS):
            ws.update(range_name="A1:Q1", values=[COLS_RECETAS])
        return ws, None
    except gspread.exceptions.WorksheetNotFound:
        try:
            ws = sh.add_worksheet(title="Recetas", rows="2000", cols=str(len(COLS_RECETAS)))
            ws.append_row(COLS_RECETAS)
            return ws, None
        except Exception as e:
            return None, f"No se pudo crear hoja Recetas: {e}"
    except Exception as e:
        return None, f"Error accediendo a Recetas: {e}"

def _asegurar_hoja_combos():
    ws, err = safe_worksheet(sh, "Combos")
    if err:
        try:
            ws = sh.add_worksheet(title="Combos", rows="2000", cols=str(len(COLS_COMBOS)))
            ws.append_row(COLS_COMBOS)
            return ws, None
        except Exception as e:
            return None, f"No se pudo crear hoja Combos: {e}"
    return ws, None
def _asegurar_hoja_menus():
    ws, err = safe_worksheet(sh, "Menus")
    if err:
        try:
            ws = sh.add_worksheet(title="Menus", rows="2000", cols=str(len(COLS_MENUS)+2))
            encabezados = COLS_MENUS + ["Notas", "Incluir_KPI"]
            ws.append_row(encabezados)
            return ws, None
        except Exception as e:
            return None, f"No se pudo crear hoja Menus: {e}"

    # Si ya existe, asegurar columnas adicionales sin borrar datos
    try:
        actuales = ws.row_values(1)
        # Agregar Menu_Nombre si falta
        if "Menu_Nombre" not in actuales:
            col_idx = len(actuales) + 1
            ws.update_cell(1, col_idx, "Menu_Nombre")
            actuales.append("Menu_Nombre")
        # Agregar Notas si falta
        if "Notas" not in actuales:
            col_idx = len(actuales) + 1
            ws.update_cell(1, col_idx, "Notas")
            actuales.append("Notas")
        # Agregar Incluir_KPI si falta
        if "Incluir_KPI" not in actuales:
            col_idx = len(actuales) + 1
            ws.update_cell(1, col_idx, "Incluir_KPI")
    except Exception:
        pass
    return ws, None

def _asegurar_hoja_historial_menus():
    ws, err = safe_worksheet(sh, "Menus_Historial")
    if err:
        try:
            ws = sh.add_worksheet(title="Menus_Historial", rows="2000", cols=str(len(COLS_MENUS_HISTORIAL)))
            ws.append_row(COLS_MENUS_HISTORIAL)
            return ws, None
        except Exception as e:
            return None, f"No se pudo crear hoja Menus_Historial: {e}"
    return ws, None

def _asegurar_hoja_merma():
    ws, err = safe_worksheet(sh, "Merma")
    if err:
        try:
            ws = sh.add_worksheet(title="Merma", rows="2000", cols=str(len(COLS_MERMA)))
            ws.append_row(COLS_MERMA)
            return ws, None
        except Exception as e:
            return None, f"No se pudo crear hoja Merma: {e}"
    return ws, None

def _asegurar_hoja_calendario():
    try:
        ws = sh.worksheet("Calendario")
        try:
            encabezados_actuales = ws.row_values(1)
            if len(encabezados_actuales) < len(COLS_CALENDARIO):
                ws.update(range_name="A1:T1", values=[COLS_CALENDARIO])
        except Exception:
            ws.update(range_name="A1:T1", values=[COLS_CALENDARIO])
        return ws, None
    except gspread.exceptions.WorksheetNotFound:
        try:
            ws = sh.add_worksheet(title="Calendario", rows="1000", cols=str(len(COLS_CALENDARIO)))
            ws.append_row(COLS_CALENDARIO)
            return ws, None
        except Exception as e:
            return None, f"No se pudo crear hoja Calendario: {e}"
    except Exception as e:
        return None, f"Error accediendo a Calendario: {e}"

def _asegurar_hoja_canal_ventas(nombre_canal: str):
    ws, err = safe_worksheet(sh, nombre_canal)
    if err:
        try:
            ws = sh.add_worksheet(title=nombre_canal, rows="1000", cols=str(len(COLS_CALENDARIO)))
            ws.append_row(COLS_CALENDARIO)
            return ws, None
        except Exception as e:
            return None, f"No se pudo crear hoja {nombre_canal}: {e}"
    try:
        valores = ws.get_all_values()
        if len(valores) < 2:
            ws.update(range_name="A1:T1", values=[COLS_CALENDARIO])
    except Exception:
        pass
    return ws, None

def _asegurar_hoja_mapeo_xml():
    encabezados_esperados = [
        "Texto_Buscado", "NoIdentificacion", "Insumo", "Marca", "Proveedor",
        "Unidad_Medida", "Factor_Conversion", "Unidad_Base", "Contenido_Base_por_Unidad"
    ]
    try:
        ws = sh.worksheet("MapeoXML")
        encabezados_actuales = ws.row_values(1)
        if len(encabezados_actuales) < len(encabezados_esperados):
            ws.update(range_name="A1:I1", values=[encabezados_esperados])
        return ws, None
    except gspread.exceptions.WorksheetNotFound:
        try:
            ws = sh.add_worksheet(title="MapeoXML", rows="1000", cols="9")
            ws.append_row(encabezados_esperados)
            return ws, None
        except Exception as e:
            return None, f"No se pudo crear hoja MapeoXML: {e}"
    except Exception as e:
        return None, f"Error accediendo a MapeoXML: {e}"
def _asegurar_hoja_borradores():
    encabezados = ["usuario", "unidad", "fecha_captura", "modo", "parte", "datos_json", "timestamp"]
    try:
        ws = sh.worksheet("Borradores_Inventario")
        actuales = ws.row_values(1)
        if actuales != encabezados:
            ws.update(range_name="A1:G1", values=[encabezados])
        return ws, None
    except gspread.exceptions.WorksheetNotFound:
        try:
            ws = sh.add_worksheet(title="Borradores_Inventario", rows="100", cols="7")
            ws.append_row(encabezados)
            return ws, None
        except Exception as e:
            return None, f"No se pudo crear hoja Borradores_Inventario: {e}"
    except Exception as e:
        return None, f"Error accediendo a Borradores_Inventario: {e}"

def _guardar_borrador_inventario(usuario, u_sel, fecha, modo, data_dict):
    ws, err = _asegurar_hoja_borradores()
    if err:
        return False
    try:
        json_completo = json.dumps(data_dict)
        max_chars = 20000
        partes = [json_completo[i:i+max_chars] for i in range(0, len(json_completo), max_chars)]

        todos = ws.get_all_values()
        filas_a_eliminar = [i for i, fila in enumerate(todos[1:], start=2) if fila[0] == usuario and fila[1] == u_sel]
        for i in sorted(filas_a_eliminar, reverse=True):
            ws.delete_rows(i)

        filas_nuevas = []
        for idx, parte in enumerate(partes, start=1):
            filas_nuevas.append([usuario, u_sel, fecha, modo, idx, parte, ts_hermosillo()])
        if filas_nuevas:
            ws.append_rows(filas_nuevas, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        st.warning(f"No se pudo autoguardar borrador: {e}")
        return False

def _cargar_borrador_inventario(usuario, u_sel):
    ws, err = _asegurar_hoja_borradores()
    if err:
        return None
    try:
        datos = ws.get_all_values()
        filas_usuario = [fila for fila in datos[1:] if fila[0] == usuario and fila[1] == u_sel]
        if not filas_usuario:
            return None
        filas_usuario.sort(key=lambda x: int(x[4]) if x[4].isdigit() else 0)
        json_completo = ''.join(fila[5] for fila in filas_usuario)
        data = json.loads(json_completo)
        return {
            "fecha_captura": filas_usuario[0][2],
            "modo": filas_usuario[0][3],
            "data": data
        }
    except Exception:
        return None

def _eliminar_borrador_inventario(usuario, u_sel):
    ws, err = _asegurar_hoja_borradores()
    if err:
        return
    try:
        todos = ws.get_all_values()
        filas_a_eliminar = [i for i, fila in enumerate(todos[1:], start=2) if fila[0] == usuario and fila[1] == u_sel]
        for i in sorted(filas_a_eliminar, reverse=True):
            ws.delete_rows(i)
    except Exception:
        pass
# Fin del archivo sheets.py
