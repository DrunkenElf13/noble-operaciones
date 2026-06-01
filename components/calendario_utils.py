import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from sheets import safe_worksheet, sh, _asegurar_hoja_calendario, append_rows_con_retry
from data_loaders import cargar_todas_ventas
from utils import limpiar_valor
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

def cargar_eventos_mes(mes, año):
    eventos = []
    ids_vistos = set()

    # 1. Calendario
    ws_cal, err = _asegurar_hoja_calendario()
    if ws_cal:
        try:
            datos = ws_cal.get_all_values()
            if len(datos) > 1:
                df = pd.DataFrame(datos[1:], columns=datos[0])
                for _, row in df.iterrows():
                    fecha_inicio = _parse_fecha(row.get("Fecha", ""))
                    fecha_fin_str = row.get("Fecha_Fin", "")
                    fecha_fin = _parse_fecha(fecha_fin_str) if fecha_fin_str else None
                    id_base = row.get("ID", "")
                    if fecha_inicio:
                        if fecha_fin and fecha_fin > fecha_inicio:
                            fechas_rango = [fecha_inicio + timedelta(days=i) for i in range((fecha_fin - fecha_inicio).days + 1)]
                        else:
                            fechas_rango = [fecha_inicio]
                        for f in fechas_rango:
                            if f.month == mes and f.year == año:
                                ev = {
                                    "id": id_base if f == fecha_inicio else f"{id_base}_dia_{f.day}",
                                    "fecha": f,
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
                                    "origen": "calendario",
                                    "anticipo": limpiar_valor(row.get("Anticipo", 0)),
                                    "fecha_fin": fecha_fin_str
                                }
                                if ev["id"] not in ids_vistos:
                                    eventos.append(ev)
                                    ids_vistos.add(ev["id"])
        except Exception as e:
            st.warning(f"Error al leer Calendario: {e}")

    # 2. Hojas de CoffeeStation y NobleToGo
    for hoja in ["CoffeeStation", "NobleToGo"]:
        ws, _ = safe_worksheet(sh, hoja)
        if ws:
            try:
                datos = ws.get_all_values()
                if len(datos) > 1:
                    df = pd.DataFrame(datos[1:], columns=datos[0])
                    for _, row in df.iterrows():
                        id_base = row.get("ID", str(uuid.uuid4())[:8])
                        fecha_venta = _parse_fecha(row.get("Fecha", ""))
                        if fecha_venta and fecha_venta.month == mes and fecha_venta.year == año:
                            ev = {
                                "id": id_base,
                                "fecha": fecha_venta,
                                "tipo_evento": row.get("Tipo", f"💰 Venta {hoja}"),
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
                                "origen": "calendario",
                                "anticipo": limpiar_valor(row.get("Anticipo", 0)),
                                "fecha_fin": row.get("Fecha_Fin", "")
                            }
                            if ev["id"] not in ids_vistos:
                                eventos.append(ev)
                                ids_vistos.add(ev["id"])
                        fecha_entrega = _parse_fecha(row.get("Fecha_Entrega", ""))
                        if fecha_entrega and fecha_entrega != fecha_venta and fecha_entrega.month == mes and fecha_entrega.year == año:
                            cliente = row.get("Cliente", "")
                            ev2 = {
                                "id": id_base + "_entrega",
                                "fecha": fecha_entrega,
                                "tipo_evento": f"📦 Entrega {hoja}",
                                "titulo": f"Entrega {hoja}: {cliente}" if cliente else f"Entrega {hoja}",
                                "cliente": cliente,
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
                                "origen": "calendario",
                                "anticipo": limpiar_valor(row.get("Anticipo", 0)),
                                "fecha_fin": row.get("Fecha_Fin", "")
                            }
                            if ev2["id"] not in ids_vistos:
                                eventos.append(ev2)
                                ids_vistos.add(ev2["id"])
            except Exception as e:
                st.warning(f"Error al leer {hoja}: {e}")

    # 3. Ventas diarias de todos los canales (para acumulado POS con meta)
    try:
        df_ventas = cargar_todas_ventas()
        if not df_ventas.empty:
            # Obtener meta mensual de Noble (suponemos 145000 y 26 días hábiles)
            # Podríamos obtenerla de la hoja Presupuesto o de los datos de ventas del mes actual
            # Para simplificar, usamos el promedio de Meta_Mensual del mes actual si existe, sino 145000
            now = datetime.now()
            if now.month == mes and now.year == año:
                df_mes_actual = df_ventas[
                    (df_ventas["Mes"].apply(limpiar_valor) == mes) &
                    (df_ventas["Año"].apply(limpiar_valor) == año)
                ]
                if not df_mes_actual.empty and "Meta_Mensual" in df_mes_actual.columns:
                    meta_mensual = limpiar_valor(df_mes_actual["Meta_Mensual"].iloc[-1]) or 145000.0
                else:
                    meta_mensual = 145000.0
                # Días hábiles: suponer 26 o tomar el valor más reciente
                dias_habiles = 26
                if "Dias_Habiles" in df_mes_actual.columns and not df_mes_actual.empty:
                    dias_habiles = int(limpiar_valor(df_mes_actual["Dias_Habiles"].iloc[-1]) or 26)
            else:
                meta_mensual = 145000.0
                dias_habiles = 26
            meta_diaria = meta_mensual / dias_habiles if dias_habiles > 0 else 0

            for _, row in df_ventas.iterrows():
                fecha = _parse_fecha(row.get("Fecha"))
                if fecha and fecha.month == mes and fecha.year == año:
                    canal_venta = row.get("Canal", "Noble") or "Noble"
                    monto = limpiar_valor(row.get("Venta_Diaria", 0))
                    if canal_venta == "Noble":
                        ev = {
                            "id": f"venta_{fecha.strftime('%Y-%m-%d')}_Noble",
                            "fecha": fecha,
                            "tipo_evento": "Venta Noble",
                            "titulo": "Venta Noble",
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
                            "color": "#48B065",
                            "responsable": row.get("Responsable", ""),
                            "origen": "venta",
                            "anticipo": 0,
                            "fecha_fin": "",
                            "meta_diaria": meta_diaria,
                            # Datos adicionales para el desglose
                            "efectivo": limpiar_valor(row.get("Efectivo", 0)),
                            "transferencias": limpiar_valor(row.get("Transferencias", 0)),
                            "tarjeta": limpiar_valor(row.get("Tarjeta", 0)),
                            "uber_eats": limpiar_valor(row.get("Uber_Eats", 0)),
                            "rappi": limpiar_valor(row.get("Rappi", 0)),
                            "tickets_pos": int(limpiar_valor(row.get("Tickets_POS", 0))),
                            "tickets_uber": int(limpiar_valor(row.get("Tickets_Uber", 0))),
                            "tickets_rappi": int(limpiar_valor(row.get("Tickets_Rappi", 0))),
                            "notas_venta": row.get("Notas", ""),
                        }
                        if ev["id"] not in ids_vistos:
                            eventos.append(ev)
                            ids_vistos.add(ev["id"])
    except Exception as e:
        st.warning(f"Error al leer ventas: {e}")

    return eventos

def agregar_evento(datos: dict):
    ws, err = _asegurar_hoja_calendario()
    if err:
        return False, err
    try:
        nueva_fila = [
            str(uuid.uuid4())[:8],
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
            datos.get("responsable", st.session_state.current_user),
            datos.get("anticipo", 0),
            datos.get("fecha_fin", ""),
        ]
        ok, msg = append_rows_con_retry(ws, [nueva_fila])
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
                ]
                ws.update(range_name=f"A{i}:S{i}", values=[nueva_fila])
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
        for i, fila in enumerate(todos[1:], start=2):
            if fila[0] == id_evento:
                ws.delete_rows(i)
                return True, "Evento eliminado"
        return False, "Evento no encontrado"
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
                return True, f"Abono de ${monto:,.2f} registrado. Nuevo adeudo: ${nuevo_adeudo:,.2f}"
        return False, "Evento no encontrado"
    except Exception as e:
        return False, str(e)
