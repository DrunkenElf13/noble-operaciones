import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from sheets import safe_worksheet, sh, _asegurar_hoja_calendario, append_rows_con_retry
from data_loaders import cargar_config_canales, cargar_ventas, cargar_avisos
from utils import limpiar_valor
from config import COLS_CALENDARIO, COLS_EVENTO_CANAL
import uuid

# ---------------------------------------------------------------------
# Función auxiliar para convertir fecha a objeto datetime
# ---------------------------------------------------------------------
def _parse_fecha(fecha_str):
    try:
        return pd.to_datetime(fecha_str).to_pydatetime()
    except:
        return None

# ---------------------------------------------------------------------
# Cargar todos los eventos del mes (calendario + canales + ventas)
# ---------------------------------------------------------------------
def cargar_eventos_mes(mes, año):
    eventos = []

    # 1. Eventos de la hoja Calendario
    ws_cal, err = _asegurar_hoja_calendario()
    if ws_cal:
        datos = ws_cal.get_all_values()
        if len(datos) > 1:
            df = pd.DataFrame(datos[1:], columns=datos[0])
            for _, row in df.iterrows():
                fecha = _parse_fecha(row.get("Fecha", ""))
                if fecha and fecha.month == mes and fecha.year == año:
                    eventos.append({
                        "id": row.get("ID", ""),
                        "fecha": fecha,
                        "tipo_evento": row.get("Tipo", "Otro"),
                        "titulo": row.get("Título", ""),
                        "cliente": row.get("Cliente", ""),
                        "contacto": row.get("Contacto", ""),
                        "ubicacion": row.get("Ubicacion", ""),
                        "descripcion": row.get("Descripcion", ""),
                        "total_cotizado": limpiar_valor(row.get("Total_Cotizado", 0)),
                        "adeudo": limpiar_valor(row.get("Adeudo", 0)),
                        "metodo_pago": row.get("Metodo_Pago", ""),
                        "fecha_contratacion": row.get("Fecha_Contratacion", ""),
                        "fecha_entrega": row.get("Fecha_Entrega", ""),
                        "abonos": row.get("Abonos", ""),
                        "notas": row.get("Notas", ""),
                        "color": row.get("Color", "#4A90D9"),
                        "responsable": row.get("Responsable", ""),
                        "origen": "calendario"
                    })

    # 2. Eventos de hojas de canales adicionales
    df_canales = cargar_config_canales()
    if not df_canales.empty:
        for _, canal in df_canales.iterrows():
            nombre_canal = canal["Canal"]
            ws_canal, _ = safe_worksheet(sh, nombre_canal)
            if ws_canal:
                datos_canal = ws_canal.get_all_values()
                if len(datos_canal) > 1:
                    df_canal = pd.DataFrame(datos_canal[1:], columns=datos_canal[0])
                    for _, row in df_canal.iterrows():
                        fecha = _parse_fecha(row.get("Fecha", ""))
                        if fecha and fecha.month == mes and fecha.year == año:
                            eventos.append({
                                "id": f"{nombre_canal}_{row.get('Fecha','')}",
                                "fecha": fecha,
                                "tipo_evento": f"Canal: {nombre_canal}",
                                "titulo": f"Venta {nombre_canal}",
                                "cliente": row.get("Descripcion", ""),
                                "contacto": "",
                                "ubicacion": "",
                                "descripcion": row.get("Descripcion", ""),
                                "total_cotizado": limpiar_valor(row.get("Monto", 0)),
                                "adeudo": limpiar_valor(row.get("Adeudo_Saldo_Pendiente", 0)),
                                "metodo_pago": row.get("Metodo_Pago", ""),
                                "fecha_contratacion": "",
                                "fecha_entrega": row.get("Fecha_Servicio_Entrega", ""),
                                "abonos": "",
                                "notas": "",
                                "color": "#EF9F27",  # naranja para canales
                                "responsable": row.get("Responsable", ""),
                                "origen": "canal"
                            })

    # 3. Ventas diarias
    df_ventas = cargar_ventas()
    if not df_ventas.empty:
        for _, row in df_ventas.iterrows():
            fecha = row.get("Fecha")
            if fecha and fecha.month == mes and fecha.year == año:
                canal_venta = row.get("Canal", "Noble")
                monto = limpiar_valor(row.get("Venta_Diaria", 0))
                eventos.append({
                    "id": f"venta_{fecha.strftime('%Y-%m-%d')}_{canal_venta}",
                    "fecha": fecha.to_pydatetime() if hasattr(fecha, 'to_pydatetime') else fecha,
                    "tipo_evento": f"Venta {canal_venta}",
                    "titulo": f"Venta {canal_venta}",
                    "cliente": "",
                    "contacto": "",
                    "ubicacion": "",
                    "descripcion": f"Venta del día: ${monto:,.2f}",
                    "total_cotizado": monto,
                    "adeudo": 0,
                    "metodo_pago": "",
                    "fecha_contratacion": "",
                    "fecha_entrega": "",
                    "abonos": "",
                    "notas": "",
                    "color": "#48B065" if canal_venta == "Noble" else "#4A90D9",
                    "responsable": row.get("Responsable", ""),
                    "origen": "venta"
                })

    return eventos

# ---------------------------------------------------------------------
# Agregar un nuevo evento a la hoja Calendario
# ---------------------------------------------------------------------
def agregar_evento(datos: dict):
    ws, err = _asegurar_hoja_calendario()
    if err:
        return False, err
    try:
        nueva_fila = [
            str(uuid.uuid4())[:8],           # ID
            datos.get("fecha", ""),          # Fecha
            datos.get("tipo", "Otro"),       # Tipo
            datos.get("titulo", ""),         # Título
            datos.get("cliente", ""),        # Cliente
            datos.get("contacto", ""),       # Contacto
            datos.get("ubicacion", ""),      # Ubicacion
            datos.get("descripcion", ""),    # Descripcion
            datos.get("total_cotizado", 0),  # Total_Cotizado
            datos.get("adeudo", 0),          # Adeudo
            datos.get("metodo_pago", ""),    # Metodo_Pago
            datos.get("fecha_contratacion", ""),  # Fecha_Contratacion
            datos.get("fecha_entrega", ""),  # Fecha_Entrega
            datos.get("abonos", ""),         # Abonos
            datos.get("notas", ""),          # Notas
            datos.get("color", "#4A90D9"),   # Color
            datos.get("responsable", st.session_state.current_user)  # Responsable
        ]
        ok, msg = append_rows_con_retry(ws, [nueva_fila])
        return ok, msg
    except Exception as e:
        return False, str(e)

# ---------------------------------------------------------------------
# Actualizar un evento existente en la hoja Calendario
# ---------------------------------------------------------------------
def actualizar_evento(id_evento: str, datos: dict):
    ws, err = _asegurar_hoja_calendario()
    if err:
        return False, err
    try:
        todos = ws.get_all_values()
        if len(todos) <= 1:
            return False, "Calendario vacío"
        encabezados = todos[0]
        # Buscar fila por ID (columna 0)
        for i, fila in enumerate(todos[1:], start=2):  # empezamos en fila 2
            if fila[0] == id_evento:
                # Construir nueva fila con los datos actualizados
                nueva_fila = [
                    id_evento,
                    datos.get("fecha", fila[1]),
                    datos.get("tipo", fila[2]),
                    datos.get("titulo", fila[3]),
                    datos.get("cliente", fila[4]),
                    datos.get("contacto", fila[5]),
                    datos.get("ubicacion", fila[6]),
                    datos.get("descripcion", fila[7]),
                    datos.get("total_cotizado", fila[8]),
                    datos.get("adeudo", fila[9]),
                    datos.get("metodo_pago", fila[10]),
                    datos.get("fecha_contratacion", fila[11]),
                    datos.get("fecha_entrega", fila[12]),
                    datos.get("abonos", fila[13]),
                    datos.get("notas", fila[14]),
                    datos.get("color", fila[15]),
                    datos.get("responsable", fila[16])
                ]
                # Actualizar la fila completa
                ws.update(range_name=f"A{i}:Q{i}", values=[nueva_fila])
                return True, "Evento actualizado"
        return False, "Evento no encontrado"
    except Exception as e:
        return False, str(e)

# ---------------------------------------------------------------------
# Eliminar un evento de la hoja Calendario
# ---------------------------------------------------------------------
def eliminar_evento(id_evento: str):
    ws, err = _asegurar_hoja_calendario()
    if err:
        return False, err
    try:
        todos = ws.get_all_values()
        if len(todos) <= 1:
            return False, "Calendario vacío"
        for i, fila in enumerate(todos[1:], start=2):
            if fila[0] == id_evento:
                ws.delete_rows(i)
                return True, "Evento eliminado"
        return False, "Evento no encontrado"
    except Exception as e:
        return False, str(e)

# ---------------------------------------------------------------------
# Registrar un abono a un evento de Calendario
# ---------------------------------------------------------------------
def registrar_abono(id_evento: str, monto: float):
    ws, err = _asegurar_hoja_calendario()
    if err:
        return False, err
    try:
        todos = ws.get_all_values()
        if len(todos) <= 1:
            return False, "Calendario vacío"
        for i, fila in enumerate(todos[1:], start=2):
            if fila[0] == id_evento:
                adeudo_actual = limpiar_valor(fila[9]) if len(fila) > 9 else 0
                nuevo_adeudo = max(0, adeudo_actual - monto)
                # Actualizar celda de Adeudo (columna J = índice 9)
                ws.update(range_name=f"J{i}", values=[[nuevo_adeudo]])
                # Agregar registro en Abonos (columna N = índice 13)
                abonos_previos = fila[13] if len(fila) > 13 else ""
                fecha_hoy = datetime.now().strftime("%Y-%m-%d")
                nuevo_abono = f"{abonos_previos}; {fecha_hoy}: ${monto:,.2f}" if abonos_previos else f"{fecha_hoy}: ${monto:,.2f}"
                ws.update(range_name=f"N{i}", values=[[nuevo_abono]])
                return True, f"Abono de ${monto:,.2f} registrado. Nuevo adeudo: ${nuevo_adeudo:,.2f}"
        return False, "Evento no encontrado"
    except Exception as e:
        return False, str(e)
