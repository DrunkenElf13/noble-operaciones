import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from sheets import safe_worksheet, sh, _asegurar_hoja_calendario, _asegurar_hoja_canal_ventas, append_rows_con_retry
from data_loaders import cargar_todas_ventas
from utils import limpiar_valor
from config import COLS_CALENDARIO
import uuid

def _parse_fecha(fecha):
    if fecha is None:
        return None
    try:
        if isinstance(fecha, datetime):
            return fecha
        if isinstance(fecha, pd.Timestamp):
            return fecha.to_pydatetime()
        return pd.to_datetime(str(fecha)).to_pydatetime()
    except Exception:
        return None

@st.cache_data(ttl=120)
def cargar_eventos_mes(mes, año):
    eventos = []
    ids_vistos = set()
    eventos_anomalos = []  # para alertar al usuario
    ws_cal, err = _asegurar_hoja_calendario()
    if ws_cal:
        try:
            datos = ws_cal.get_all_values()
            if len(datos) > 1:
                cols_hoja = datos[0]
                df = pd.DataFrame(datos[1:], columns=cols_hoja)
                for col in COLS_CALENDARIO:
                    if col not in df.columns:
                        df[col] = ""
                for _, row in df.iterrows():
                    fecha_inicio = _parse_fecha(row.get("Fecha", ""))
                    fecha_fin_str = row.get("Fecha_Fin", "")
                    fecha_fin = _parse_fecha(fecha_fin_str) if fecha_fin_str else None
                    id_base = row.get("ID", "")
                    origen = str(row.get("Origen", "manual")).strip().lower() or "manual"
                    tipo = row.get("Tipo", "")
                    if fecha_inicio:
                        # Detectar eventos con rango sospechoso (no vacaciones y >1 día)
                        if fecha_fin and fecha_fin > fecha_inicio and tipo != "Vacaciones":
                            dif = (fecha_fin - fecha_inicio).days
                            if dif > 1:
                                eventos_anomalos.append(
                                    f"{tipo}: '{row.get('Título','')}' "
                                    f"({fecha_inicio.strftime('%d/%m/%Y')} → {fecha_fin.strftime('%d/%m/%Y')})"
                                )
                        # Mostrar solo en el mes correcto
                        if fecha_inicio.month == mes and fecha_inicio.year == año:
                            titulo = row.get("Título", "")
                            # Forzar prefijo para canales
                            if origen in ["coffee station", "noble to go"]:
                                prefijo = "☕ Evento" if origen == "coffee station" else "🥤 Entrega"
                                if not titulo.startswith(prefijo):
                                    titulo = f"{prefijo} - {titulo}"
                                tipo = prefijo
                            ev = {
                                "id": id_base,
                                "fecha": fecha_inicio,
                                "tipo_evento": tipo,
                                "titulo": titulo,
                                "cliente": row.get("Cliente", ""),
                                "total_cotizado": limpiar_valor(row.get("Total_Cotizado", 0)),
                                "adeudo": limpiar_valor(row.get("Adeudo", 0)),
                                "anticipo": limpiar_valor(row.get("Anticipo", 0)),
                                "color": row.get("Color", "#4A90D9"),
                                "origen": origen,
                            }
                            if ev["id"] not in ids_vistos:
                                eventos.append(ev)
                                ids_vistos.add(ev["id"])
        except Exception as e:
            st.warning(f"Error al leer Calendario: {e}")

    # Guardar anomalías en session_state para que la UI las muestre
    st.session_state["eventos_anomalos"] = eventos_anomalos

    # Ventas Noble
    try:
        df_ventas = cargar_todas_ventas()
        if not df_ventas.empty:
            meta_mensual = 145000.0
            dias_habiles = 26
            meta_diaria = meta_mensual / dias_habiles if dias_habiles > 0 else 0
            for _, row in df_ventas.iterrows():
                fecha = _parse_fecha(row.get("Fecha"))
                if fecha and fecha.month == mes and fecha.year == año and row.get("Canal", "") == "Noble":
                    monto = limpiar_valor(row.get("Venta_Diaria", 0))
                    ev = {
                        "id": f"venta_{fecha.strftime('%Y-%m-%d')}_Noble",
                        "fecha": fecha,
                        "tipo_evento": "Venta Noble",
                        "titulo": "Venta Noble",
                        "total_cotizado": monto,
                        "adeudo": 0,
                        "anticipo": 0,
                        "color": "#48B065",
                        "origen": "Venta Noble",
                    }
                    if ev["id"] not in ids_vistos:
                        eventos.append(ev)
                        ids_vistos.add(ev["id"])
    except Exception as e:
        st.warning(f"Error al leer ventas: {e}")

    return eventos

# (Las funciones _sincronizar_canal, agregar_evento, actualizar_evento, eliminar_evento, registrar_abono se mantienen idénticas a la versión anterior)
