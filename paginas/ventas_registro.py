import streamlit as st
import time
from data_loaders import cargar_ventas
from sheets import (
    _asegurar_hoja_ventas, append_rows_con_retry, _asegurar_hoja_canal_ventas
)
from utils import limpiar_valor, ahora_hermosillo
from components.avisos import mostrar_avisos
from auth import tiene_permiso
from config import CANALES_VENTA, PALETA_CANALES
from components.calendario_utils import agregar_evento
import uuid
from datetime import datetime

def _construir_fila_venta(
    fecha, efectivo, transferencias, tarjeta, uber, rappi,
    tickets_pos, tickets_uber, tickets_rappi,
    meta_mensual, dias_habiles, responsable, notas, canal="Noble",
):
    total_pos    = efectivo + transferencias + tarjeta
    venta_diaria = total_pos + uber + rappi
    total_tix    = tickets_pos + tickets_uber + tickets_rappi
    tix_prom     = round(venta_diaria / total_tix, 2) if total_tix > 0 else 0.0
    meta_diaria  = round(meta_mensual / dias_habiles, 2) if dias_habiles > 0 else 0.0
    return [
        canal,
        fecha.strftime("%Y-%m-%d"),
        fecha.day, fecha.month, fecha.year,
        efectivo, transferencias, tarjeta, total_pos,
        uber, rappi, venta_diaria,
        tickets_pos, tickets_uber, tickets_rappi, total_tix,
        tix_prom, meta_mensual, dias_habiles, meta_diaria,
        responsable, notas, canal,
        0.0,  # Adeudo
        0.0,  # Anticipo
    ]

def _parsear_linea_masiva(linea: str) -> dict | None:
    partes = [p.strip() for p in linea.split("\t")]
    if len(partes) < 2:
        return None
    fecha_str = partes[0]
    try:
        fecha_venta = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        return None
    monto_str = partes[1].replace(",", "").replace(" ", "")
    try:
        monto = float(monto_str)
    except ValueError:
        return None
    if monto <= 0:
        return None

    cliente = partes[2] if len(partes) > 2 else ""
    fecha_evento_str = partes[3] if len(partes) > 3 else fecha_str
    metodo_pago = partes[4] if len(partes) > 4 else ""

    try:
        fecha_evento = datetime.strptime(fecha_evento_str, "%Y-%m-%d").date()
    except ValueError:
        fecha_evento = fecha_venta

    return {
        "fecha_venta": fecha_venta.strftime("%Y-%m-%d"),
        "total_cotizado": monto,
        "cliente": cliente,
        "fecha_evento": fecha_evento.strftime("%Y-%m-%d"),
        "metodo_pago": metodo_pago,
    }

def show_ventas():
    if not tiene_permiso("Ventas"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    st.title("Registrar Venta")
    mostrar_avisos("Ventas")
    if not st.session_state.auth_status:
        st.error("Autenticación requerida.")
        st.stop()

    canal_sel = st.selectbox("Canal", CANALES_VENTA)

    df_ventas = cargar_ventas()
    hoy = ahora_hermosillo().date()

    ya_registrado = False
    if not df_ventas.empty and "Fecha" in df_ventas.columns:
        ya_registrado = any(f.date() == hoy for f in df_ventas["Fecha"].dropna())
    if ya_registrado and canal_sel == "Noble":
        st.info(f"Ya existe un registro para hoy ({hoy.strftime('%d/%m/%Y')}). Puedes guardar una corrección si es necesario.")

    responsables = st.session_state.responsables or ["Raúl"]
    resp_idx = responsables.index(st.session_state.current_user) if st.session_state.current_user in responsables else 0

    col_f, col_r = st.columns([1, 1])
    with col_f:
        fecha_venta = st.date_input("Fecha del registro", value=hoy, max_value=hoy)
    with col_r:
        responsable_v = st.selectbox("Responsable", responsables, index=resp_idx,
                                     disabled=(st.session_state.user_role != "admin"))

    st.divider()

    # ──────── POS (Noble) ────────
    if canal_sel == "Noble":
        meta_default = 145000.0
        dias_default = 26
        if not df_ventas.empty:
            df_mes_actual = df_ventas[
                (df_ventas["Mes"].apply(limpiar_valor) == fecha_venta.month) &
                (df_ventas["Año"].apply(limpiar_valor) == fecha_venta.year)
            ]
            if not df_mes_actual.empty:
                meta_default = limpiar_valor(df_mes_actual["Meta_Mensual"].iloc[-1]) or meta_default
                dias_default = int(limpiar_valor(df_mes_actual["Dias_Habiles"].iloc[-1])) or dias_default

        with st.expander("Configuración de meta (mes actual)", expanded=False):
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                meta_mensual = st.number_input("Meta mensual ($)", min_value=0.0, step=1000.0, value=meta_default)
            with col_m2:
                dias_habiles = st.number_input("Días hábiles del mes", min_value=1, max_value=31, value=dias_default)
            meta_diaria_calc = meta_mensual / dias_habiles if dias_habiles > 0 else 0
            st.caption(f"Meta diaria resultante: **${meta_diaria_calc:,.2f}**")

        with st.form("f_noble"):
            st.subheader("Venta del día")
            col_ef, col_tr, col_ta = st.columns(3)
            with col_ef: efectivo       = st.number_input("Efectivo ($)", min_value=0.0, step=10.0, value=0.0)
            with col_tr: transferencias = st.number_input("Transferencias ($)", min_value=0.0, step=10.0, value=0.0)
            with col_ta: tarjeta        = st.number_input("Tarjeta ($)", min_value=0.0, step=10.0, value=0.0)

            total_pos = efectivo + transferencias + tarjeta

            col_ub, col_rp = st.columns(2)
            with col_ub: uber  = st.number_input("Uber Eats ($)", min_value=0.0, step=10.0, value=0.0)
            with col_rp: rappi = st.number_input("Rappi ($)", min_value=0.0, step=10.0, value=0.0)

            venta_total = total_pos + uber + rappi

            st.divider()
            st.subheader("Tickets")
            col_tp, col_tu, col_tr2 = st.columns(3)
            with col_tp:  tickets_pos   = st.number_input("POS", min_value=0, step=1, value=0)
            with col_tu:  tickets_uber  = st.number_input("Uber", min_value=0, step=1, value=0)
            with col_tr2: tickets_rappi = st.number_input("Rappi", min_value=0, step=1, value=0)

            total_tix = tickets_pos + tickets_uber + tickets_rappi
            tix_prom  = round(venta_total / total_tix, 2) if total_tix > 0 else 0.0

            t1, t2 = st.columns(2)
            t1.metric("Total tickets", total_tix)
            t2.metric("Ticket promedio", f"${tix_prom:,.2f}" if tix_prom > 0 else "—")

            notas_v = st.text_input("Notas (opcional)")
            dia_sin_venta = st.toggle("Día sin venta", value=False)
            if dia_sin_venta and venta_total == 0:
                st.warning("Se registrará día con $0.")

            if st.form_submit_button("Guardar", width="stretch"):
                if venta_total == 0 and total_tix == 0 and not dia_sin_venta:
                    st.warning("Ingresa al menos un valor de venta o tickets, o activa 'Día sin venta'.")
                else:
                    ws_v, err = _asegurar_hoja_ventas()
                    if err:
                        st.error(err)
                    else:
                        notas_final = notas_v if notas_v.strip() else ("DÍA SIN VENTA" if dia_sin_venta else "")
                        fila = _construir_fila_venta(
                            fecha=fecha_venta, efectivo=efectivo, transferencias=transferencias,
                            tarjeta=tarjeta, uber=uber, rappi=rappi,
                            tickets_pos=tickets_pos, tickets_uber=tickets_uber,
                            tickets_rappi=tickets_rappi, meta_mensual=meta_mensual,
                            dias_habiles=int(dias_habiles), responsable=responsable_v,
                            notas=notas_final, canal=canal_sel,
                        )
                        ok, msg = append_rows_con_retry(ws_v, [fila])
                        if ok:
                            cargar_ventas.clear()
                            st.success(f"Venta del {fecha_venta.strftime('%d/%m/%Y')} registrada. Total: ${venta_total:,.2f}")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(msg)

    # ──────── Coffee Station / Noble To Go ────────
    else:
        prefijo = "☕ Evento" if canal_sel == "Coffee Station" else "🥤 Entrega"
        st.subheader(f"Datos del {prefijo} — {canal_sel}")
        with st.form("f_evento_canal", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                cliente_ev = st.text_input("Cliente")
                contacto_ev = st.text_input("Contacto")
                ubicacion_ev = st.text_input("Ubicación")
                descripcion_ev = st.text_area("Descripción")
                metodo_pago = st.text_input("Método de pago")
            with col2:
                monto_ev = st.number_input("Total cotizado ($)", min_value=0.0, step=10.0, value=0.0)
                adeudo_ev = st.number_input("Adeudo ($)", min_value=0.0, step=10.0, value=0.0)
                anticipo_ev = st.number_input("Anticipo ($)", min_value=0.0, step=10.0, value=0.0)
                fecha_contr_ev = st.date_input("Fecha contratación", value=hoy)
                fecha_entr_ev = st.date_input("Fecha del evento/entrega", value=hoy,
                                              help="Esta fecha se usará en el calendario")
                abonos_ev = st.text_area("Abonos (historial)")
                notas_ev = st.text_area("Notas")
            if st.form_submit_button("Guardar venta", width="stretch"):
                if monto_ev <= 0:
                    st.error("El monto debe ser mayor a cero.")
                else:
                    id_unico = str(uuid.uuid4())[:8]
                    cliente_final = cliente_ev.strip() if cliente_ev.strip() else "Evento sin cliente"
                    titulo = f"{prefijo} - {cliente_final}"
                    datos_evento = {
                        "fecha": fecha_entr_ev.strftime("%Y-%m-%d"),
                        "tipo": prefijo,
                        "titulo": titulo,
                        "cliente": cliente_ev,
                        "contacto": contacto_ev,
                        "ubicacion": ubicacion_ev,
                        "descripcion": descripcion_ev,
                        "total_cotizado": monto_ev,
                        "adeudo": adeudo_ev,
                        "metodo_pago": metodo_pago,
                        "fecha_contratacion": fecha_contr_ev.strftime("%Y-%m-%d"),
                        "fecha_entrega": fecha_entr_ev.strftime("%Y-%m-%d"),
                        "abonos": abonos_ev,
                        "notas": notas_ev,
                        "color": PALETA_CANALES.get(canal_sel, "#4A90D9"),
                        "responsable": st.session_state.current_user,
                        "anticipo": anticipo_ev,
                        "fecha_fin": "",
                        "origen": canal_sel,
                    }
                    ok_cal, msg_cal = agregar_evento(datos_evento, id_unico)
                    if not ok_cal:
                        st.error(f"Error al guardar en Calendario: {msg_cal}")
                        st.stop()

                    from data_loaders import cargar_todas_ventas
                    cargar_todas_ventas.clear()

                    st.success(f"Venta registrada en {canal_sel}: ${monto_ev:,.2f}")
                    time.sleep(0.5)
                    st.rerun()

        # ──────── CARGA MASIVA HISTÓRICA ────────
        with st.expander("Carga masiva histórica", expanded=False):
            st.markdown(
                "Formato esperado (una línea por evento, columnas separadas por **tabulaciones**):  \n"
                "`Fecha_venta  Total  Cliente  Fecha_evento  Método`  \n"
                "- **Fecha_venta**: fecha en que se contrató  \n"
                "- **Fecha_evento**: fecha en que ocurre el evento/entrega (aparecerá en el calendario)  \n"
                "Ejemplo: `2026-01-17	5500	Fernanda Federico	2026-01-17	Transferencia`"
            )
            texto_masivo = st.text_area("Pega aquí tus líneas:", height=200, key="texto_masivo")
            canal_masivo = st.selectbox("Canal:", ["Coffee Station", "Noble To Go"], key="canal_masivo")
            if st.button("Procesar y guardar todo", width="stretch"):
                if not texto_masivo.strip():
                    st.error("Pega al menos una línea.")
                else:
                    lineas = [l for l in texto_masivo.splitlines() if l.strip()]
                    procesadas = 0
                    fallas = []
                    prefijo = "☕ Evento" if canal_masivo == "Coffee Station" else "🥤 Entrega"
                    for linea in lineas:
                        parsed = _parsear_linea_masiva(linea)
                        if parsed is None:
                            fallas.append(f"Formato inválido: {linea[:50]}...")
                            continue
                        id_unico = str(uuid.uuid4())[:8]
                        cliente_final = parsed["cliente"].strip() if parsed["cliente"].strip() else "Evento sin cliente"
                        titulo = f"{prefijo} - {cliente_final}"
                        datos_evento = {
                            "fecha": parsed["fecha_evento"],
                            "tipo": prefijo,
                            "titulo": titulo,
                            "cliente": parsed["cliente"],
                            "contacto": "",
                            "ubicacion": "",
                            "descripcion": "",
                            "total_cotizado": parsed["total_cotizado"],
                            "adeudo": 0.0,
                            "metodo_pago": parsed["metodo_pago"],
                            "fecha_contratacion": parsed["fecha_venta"],
                            "fecha_entrega": parsed["fecha_evento"],
                            "abonos": "",
                            "notas": "",
                            "color": PALETA_CANALES.get(canal_masivo, "#4A90D9"),
                            "responsable": st.session_state.current_user,
                            "anticipo": 0.0,
                            "fecha_fin": "",
                            "origen": canal_masivo,
                        }
                        ok, msg = agregar_evento(datos_evento, id_unico)
                        if not ok:
                            fallas.append(f"Error ID {id_unico}: {msg}")
                            continue
                        procesadas += 1
                    from data_loaders import cargar_todas_ventas
                    cargar_todas_ventas.clear()
                    if procesadas:
                        st.success(f"{procesadas} líneas procesadas correctamente.")
                    if fallas:
                        st.warning(f"{len(fallas)} errores:")
                        for f in fallas:
                            st.caption(f)
                    time.sleep(0.5)
                    st.rerun()
