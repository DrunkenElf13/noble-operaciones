import streamlit as st
import gspread
import time
from google.oauth2.service_account import Credentials
from config import (
    SPREADSHEET_ID, COLS_VENTAS, COLS_GASTOS, COLS_PRESUPUESTO,
    COLS_COSTOS_INSUMOS, COLS_RECETAS, COLS_MERMA, COLS_CALENDARIO
)

@st.cache_resource
def conectar_google_sheets():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=scope
        )
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
        return sh.worksheet("Recetas"), None
    except gspread.exceptions.WorksheetNotFound:
        try:
            ws = sh.add_worksheet(title="Recetas", rows="2000", cols=str(len(COLS_RECETAS)))
            ws.append_row(COLS_RECETAS)
            return ws, None
        except Exception as e:
            return None, f"No se pudo crear hoja Recetas: {e}"
    except Exception as e:
        return None, f"Error accediendo a Recetas: {e}"

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
        return sh.worksheet("Calendario"), None
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
    """Crea o actualiza la hoja del canal con las columnas de Calendario."""
    ws, err = safe_worksheet(sh, nombre_canal)
    if err:
        # No existe, la creamos
        try:
            ws = sh.add_worksheet(title=nombre_canal, rows="1000", cols=str(len(COLS_CALENDARIO)))
            ws.append_row(COLS_CALENDARIO)
            return ws, None
        except Exception as e:
            return None, f"No se pudo crear hoja {nombre_canal}: {e}"
    # Si existe, SOBRESCRIBIR los encabezados para asegurar que coincidan
    try:
        ws.update(range_name="A1:S1", values=[COLS_CALENDARIO])
        return ws, None
    except Exception as e:
        return None, f"Error al actualizar hoja {nombre_canal}: {e}"
