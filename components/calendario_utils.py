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
    eventos_anomalos = []
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
                    origen = str(row.get("Origen", "manual")).strip()
                    tipo = row.get("Tipo", "")
                    if fecha_inicio:
                        if fecha_fin and fecha_fin > fecha_inicio and tipo != "Vacaciones":
                            dif = (fecha_fin - fecha_inicio).days
                            if dif > 1:
                                eventos_anomalos.append(
                                    f"{tipo}: '{row.get('Título','')}' "
                                    f"({fecha_inicio.strftime('%d/%m/%Y')} → {fecha_fin.strftime('%d/%m/%Y')})"
                                )
                        if fecha_inicio.month == mes and fecha_inicio.year == año:
                            titulo = row.get("Título", "")
                            if origen in ["Coffee Station", "Noble To Go"]:
                                prefijo = "☕ Evento" if origen == "Coffee Station" else "🥤 Entrega"
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

    st.session_state["eventos_anomalos"] = eventos_anomalos

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

def _sincronizar_canal(id_evento: str, datos: dict, accion: str = "actualizar"):
    origen = datos.get("origen", "manual")
    if origen in ["Coffee Station", "Noble To Go"]:
        ws_canal, err_canal = _asegurar_hoja_canal_ventas(origen)
        if not err_canal and ws_canal:
            if accion == "eliminar":
                try:
                    todos = ws_canal.get_all_values()
                    for i, fila in enumerate(todos[1:], start=2):
                        if fila[0] == id_evento:
                            ws_canal.delete_rows(i)
                            break
                except Exception:
                    pass
            else:
                nueva_fila = [
                    id_evento,
                    datos.get("fecha", ""),
                    datos.get("tipo", "Otro"),
                    datos.get("titulo", ""),
                    datos.get("cliente", ""),
                    datos.get("contacto", ""),
                    datos.get("ubicacion", ""),
                    datos.get("descripcion", ""),
                    datos.get("total_cotizado", 0),
                    datos.get("adeudo", 0),
                    datos.get("metodo_pago", ""),
                    datos.get("fecha_contratacion", ""),
                    datos.get("fecha_entrega", ""),
                    datos.get("abonos", ""),
                    datos.get("notas", ""),
                    datos.get("color", "#4A90D9"),
                    datos.get("responsable", ""),
                    datos.get("anticipo", 0),
                    datos.get("fecha_fin", ""),
                    origen,
                ]
                try:
                    todos = ws_canal.get_all_values()
                    encontrado = False
                    for i, fila in enumerate(todos[1:], start=2):
                        if fila[0] == id_evento:
                            ws_canal.update(range_name=f"A{i}:T{i}", values=[nueva_fila])
                            encontrado = True
                            break
                    if not encontrado:
                        append_rows_con_retry(ws_canal, [nueva_fila])
                except Exception:
                    pass

def agregar_evento(datos: dict, id_externo: str = None):
    ws, err = _asegurar_hoja_calendario()
    if err:
        return False, err
    id_final = id_externo if id_externo else str(uuid.uuid4())[:8]
    origen = datos.get("origen", "manual")
    try:
        nueva_fila = [
            id_final,
            datos.get("fecha", ""),
            datos.get("tipo", "Otro"),
            datos.get("titulo", ""),
            datos.get("cliente", ""),
            datos.get("contacto", ""),
            datos.get("ubicacion", ""),
            datos.get("descripcion", ""),
            datos.get("total_cotizado", 0),
            datos.get("adeudo", 0),
            datos.get("metodo_pago", ""),
            datos.get("fecha_contratacion", ""),
            datos.get("fecha_entrega", ""),
            datos.get("abonos", ""),
            datos.get("notas", ""),
            datos.get("color", "#4A90D9"),
            datos.get("responsable", st.session_state.get("current_user", "")),
            datos.get("anticipo", 0),
            datos.get("fecha_fin", ""),
            origen,
        ]
        ok, msg = append_rows_con_retry(ws, [nueva_fila])
        if ok and origen in ["Coffee Station", "Noble To Go"]:
            _sincronizar_canal(id_final, datos, "agregar")
        return ok, msg
    except Exception as e:
        return False, str(e)

def actualizar_evento(id_evento: str, datos: dict):
    ws, err = _asegurar_hoja_calendario()
    if err:
        return False, err
    try:
        todos = ws.get_all_values()
        if len(todos) <= 1:
            return False, "Calendario vacío"
        origen = datos.get("origen", "manual")
        for i, fila in enumerate(todos[1:], start=2):
            if fila[0] == id_evento:
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
                    datos.get("responsable", fila[16]),
                    datos.get("anticipo", fila[17] if len(fila) > 17 else 0),
                    datos.get("fecha_fin", fila[18] if len(fila) > 18 else ""),
                    origen,
                ]
                ws.update(range_name=f"A{i}:T{i}", values=[nueva_fila])
                if origen in ["Coffee Station", "Noble To Go"]:
                    _sincronizar_canal(id_evento, datos, "actualizar")
                return True, "Evento actualizado"
        return False, "Evento no encontrado"
    except Exception as e:
        return False, str(e)

def eliminar_evento(id_evento: str):
    ws, err = _asegurar_hoja_calendario()
    if err:
        return False, err
    try:
        todos = ws.get_all_values()
        if len(todos) <= 1:
            return False, "Calendario vacío"
        origen = "manual"
        ids_a_eliminar = [id_evento]
        for i, fila in enumerate(todos[1:], start=2):
            if fila[0] == id_evento:
                if len(fila) > 19:
                    origen = str(fila[19]).strip()
                id_base = id_evento.split("_entrega")[0]
                for j, f2 in enumerate(todos[1:], start=2):
                    if f2[0] == f"{id_base}_entrega" or f2[0].startswith(f"{id_base}_entrega"):
                        ids_a_eliminar.append(f2[0])
                break
        filas_a_eliminar = []
        for id_e in ids_a_eliminar:
            for i, fila in enumerate(todos[1:], start=2):
                if fila[0] == id_e:
                    filas_a_eliminar.append(i)
                    break
        for i in sorted(filas_a_eliminar, reverse=True):
            ws.delete_rows(i)
        if origen in ["Coffee Station", "Noble To Go"]:
            _sincronizar_canal(id_evento, {"origen": origen}, "eliminar")
        return True, f"{len(ids_a_eliminar)} evento(s) eliminado(s)."
    except Exception as e:
        return False, str(e)

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
                ws.update(range_name=f"J{i}", values=[[nuevo_adeudo]])
                abonos_previos = fila[13] if len(fila) > 13 else ""
                fecha_hoy = datetime.now().strftime("%Y-%m-%d")
                nuevo_abono = f"{abonos_previos}; {fecha_hoy}: ${monto:,.2f}" if abonos_previos else f"{fecha_hoy}: ${monto:,.2f}"
                ws.update(range_name=f"N{i}", values=[[nuevo_abono]])
                if len(fila) > 19:
                    origen = str(fila[19]).strip()
                    if origen in ["Coffee Station", "Noble To Go"]:
                        ws_canal, _ = _asegurar_hoja_canal_ventas(origen)
                        if ws_canal:
                            todos_canal = ws_canal.get_all_values()
                            for j, f_canal in enumerate(todos_canal[1:], start=2):
                                if f_canal[0] == id_evento:
                                    ws_canal.update(range_name=f"J{j}", values=[[nuevo_adeudo]])
                                    ws_canal.update(range_name=f"N{j}", values=[[nuevo_abono]])
                                    break
                return True, f"Abono de ${monto:,.2f} registrado. Nuevo adeudo: ${nuevo_adeudo:,.2f}"
        return False, "Evento no encontrado"
    except Exception as e:
        return False, str(e)
