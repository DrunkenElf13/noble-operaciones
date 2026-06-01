import streamlit as st
import time
from data_loaders import cargar_ventas
from sheets import (
    _asegurar_hoja_ventas, append_rows_con_retry, _asegurar_hoja_canal_ventas
)
from utils import limpiar_valor, ahora_hermosillo
from components.avisos import mostrar_avisos
from auth import tiene_permiso
from config import CANALES_VENTA, COLS_VENTAS, COLS_CALENDARIO
from components.calendario_utils import agregar_evento

PALETA_COLORES = {
    "🔵 Azul": "#4A90D9",
    "🟣 Morado": "#9B59B6",
    "🔴 Rojo": "#E24B4A",
    "🟢 Verde": "#48B065",
    "🟠 Naranja": "#EF9F27",
    "🟡 Amarillo": "#F1C40F",
    "🩵 Turquesa": "#1ABC9C",
    "⚫ Gris": "#34495E",
}

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
    ]

def _construir_fila_venta_canal(datos_evento: dict, canal: str):
    """Construye una fila para la hoja del canal con las columnas de Calendario."""
    import uuid
    return [
        str(uuid.uuid4())[:8],
        datos_evento.get("fecha", ""),
        datos_evento.get("tipo", ""),
        datos_evento.get("titulo", ""),
        datos_evento.get("cliente", ""),
        datos_evento.get("contacto", ""),
        datos_evento.get("ubicacion", ""),
        datos_evento.get("descripcion", ""),
        datos_evento.get("total_cotizado", 0),
        datos_evento.get("adeudo", 0),
        datos_evento.get("metodo_pago", ""),
        datos_evento.get("fecha_contratacion", ""),
        datos_evento.get("fecha_entrega", ""),
        datos_evento.get("abonos", ""),
        datos_evento.get("notas", ""),
        datos_evento.get("color", "#4A90D9"),
        datos_evento.get("responsable", ""),
        datos_evento.get("anticipo", 0),
        datos_evento.get("fecha_fin", ""),
    ]

def show_ventas():
    if not tiene_permiso("Ventas"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    st.title("📈 Registrar Ventas")
    mostrar_avisos("Ventas")
    if not st.session_state.auth_status:
        st.error("🔒 Autenticación requerida.")
        st.stop()

    canal_sel = st.selectbox("🏢 Canal de venta:", CANALES_VENTA)

    df_ventas = cargar_ventas()
    hoy = ahora_hermosillo().date()

    ya_registrado = False
    if not df_ventas.empty and "Fecha" in df_ventas.columns:
        ya_registrado = any(f.date() == hoy for f in df_ventas["Fecha"].dropna())
    if ya_registrado and canal_sel == "Noble":
        st.info(f"ℹ️ Ya existe un registro para hoy ({hoy.strftime('%d/%m/%Y')}). Puedes guardar una corrección si es necesario.")

    responsables = st.session_state.responsables or ["Raúl"]
    resp_idx = responsables.index(st.session_state.current_user) if st.session_state.current_user in responsables else 0

    col_f, col_r = st.columns([1,1])
    with col_f:
        fecha_venta = st.date_input("📅 Fecha del registro:", value=hoy, max_value=hoy)
    with col_r:
        responsable_v = st.selectbox("👤 Responsable:", responsables, index=resp_idx,
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

        with st.expander("⚙️ Configuración de Meta (mes actual)", expanded=False):
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                meta_mensual = st.number_input("Meta mensual ($):", min_value=0.0, step=1000.0, value=meta_default)
            with col_m2:
                dias_habiles = st.number_input("Días hábiles del mes:", min_value=1, max_value=31, value=dias_default)
            meta_diaria_calc = meta_mensual / dias_habiles if dias_habiles > 0 else 0
            st.caption(f"Meta diaria resultante: **${meta_diaria_calc:,.2f}**")

        st.subheader("💵 Venta del día")
        col_ef, col_tr, col_ta = st.columns(3)
        with col_ef: efectivo       = st.number_input("Efectivo ($):",       min_value=0.0, step=10.0, value=0.0)
        with col_tr: transferencias = st.number_input("Transferencias ($):", min_value=0.0, step=10.0, value=0.0)
        with col_ta: tarjeta        = st.number_input("Tarjeta ($):",        min_value=0.0, step=10.0, value=0.0)

        total_pos = efectivo + transferencias + tarjeta

        col_ub, col_rp = st.columns(2)
        with col_ub: uber  = st.number_input("Uber Eats ($):", min_value=0.0, step=10.0, value=0.0)
        with col_rp: rappi = st.number_input("Rappi ($):",     min_value=0.0, step=10.0, value=0.0)

        venta_total = total_pos + uber + rappi
        avance_pct  = (venta_total / meta_diaria_calc * 100) if meta_diaria_calc > 0 else 0

        st.divider()
        st.subheader("📊 Resumen en tiempo real")
        p1,p2,p3,p4 = st.columns(4)
        p1.metric("Total POS",   f"${total_pos:,.2f}")
        p2.metric("Plataformas", f"${uber + rappi:,.2f}")
        p3.metric("Venta Total", f"${venta_total:,.2f}")
        p4.metric("vs Meta día", f"{avance_pct:.1f}%", delta_color="normal" if avance_pct >= 100 else "inverse")

        st.divider()
        st.subheader("🎫 Tickets")
        col_tp, col_tu, col_tr2 = st.columns(3)
        with col_tp:  tickets_pos   = st.number_input("Tickets POS:",   min_value=0, step=1, value=0)
        with col_tu:  tickets_uber  = st.number_input("Tickets Uber:",  min_value=0, step=1, value=0)
        with col_tr2: tickets_rappi = st.number_input("Tickets Rappi:", min_value=0, step=1, value=0)

        total_tix = tickets_pos + tickets_uber + tickets_rappi
        tix_prom  = round(venta_total / total_tix, 2) if total_tix > 0 else 0.0

        t1, t2 = st.columns(2)
        t1.metric("Total Tickets",   total_tix)
        t2.metric("Ticket Promedio", f"${tix_prom:,.2f}" if tix_prom > 0 else "—")

        notas_v = st.text_input("📝 Notas del día (opcional):")
        dia_sin_venta = st.toggle(
            "📵 Día sin venta (cierre en cero)",
            value=False,
            help="Activa esta opción para registrar un día operativo donde no hubo ventas."
        )
        if dia_sin_venta and venta_total == 0:
            st.warning("⚠️ Se registrará este día con venta = $0.")

        st.divider()
        if st.button("💾 GUARDAR REGISTRO DE VENTA", type="primary", use_container_width=True):
            if venta_total == 0 and total_tix == 0 and not dia_sin_venta:
                st.warning("⚠️ Ingresa al menos un valor de venta o tickets, o activa 'Día sin venta'.")
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
                        st.success(f"✅ Venta del {fecha_venta.strftime('%d/%m/%Y')} registrada. Total: ${venta_total:,.2f}")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(msg)

    # ──────── Coffee Station / Noble To Go ────────
    else:
        st.subheader(f"📋 Datos del evento — {canal_sel}")
        with st.form("f_evento_canal", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                cliente_ev = st.text_input("Cliente")
                contacto_ev = st.text_input("Contacto")
                ubicacion_ev = st.text_input("Ubicación")
                descripcion_ev = st.text_area("Descripción")
                metodo_pago = st.text_input("Método de pago")
                color_nombre = st.selectbox("Color del evento", list(PALETA_COLORES.keys()))
                color_ev = PALETA_COLORES[color_nombre]
                st.markdown(f"<div style='width:30px;height:30px;background-color:{color_ev};border-radius:4px;'></div>", unsafe_allow_html=True)
            with col2:
                monto_ev = st.number_input("Total cotizado ($)", min_value=0.0, step=10.0, value=0.0)
                adeudo_ev = st.number_input("Adeudo ($)", min_value=0.0, step=10.0, value=0.0)
                anticipo_ev = st.number_input("Anticipo ($)", min_value=0.0, step=10.0, value=0.0)
                fecha_contr_ev = st.date_input("Fecha contratación", value=hoy)
                fecha_entr_ev = st.date_input("Fecha entrega/evento", value=hoy)
                fecha_fin_ev = st.date_input("Fecha fin (rango)", value=hoy, help="Si el evento dura varios días, elige la fecha final")
                abonos_ev = st.text_area("Abonos (historial)")
                notas_ev = st.text_area("Notas")
            enviar = st.form_submit_button("💾 Guardar venta")

        if enviar:
            if monto_ev <= 0:
                st.error("El monto debe ser mayor a cero.")
            else:
                import uuid
                datos_evento = {
                    "fecha": fecha_venta.strftime("%Y-%m-%d"),
                    "tipo": f"💰 Venta {canal_sel}",      # tipo diferenciado para venta
                    "titulo": f"Venta {canal_sel} - {cliente_ev}" if cliente_ev else f"Venta {canal_sel}",
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
                    "color": color_ev,
                    "responsable": st.session_state.current_user,
                    "anticipo": anticipo_ev,
                    "fecha_fin": fecha_fin_ev.strftime("%Y-%m-%d") if fecha_fin_ev != fecha_venta else "",
                }
                # 1. Guardar en la hoja del canal
                ws_canal, err_canal = _asegurar_hoja_canal_ventas(canal_sel)
                if err_canal:
                    st.error(err_canal)
                else:
                    fila = _construir_fila_venta_canal(datos_evento, canal_sel)
                    ok, msg = append_rows_con_retry(ws_canal, [fila])
                    if not ok:
                        st.error(msg)
                        st.stop()
                    from data_loaders import cargar_todas_ventas
                    cargar_todas_ventas.clear()

                # 2. Guardar en Calendario (con ambas fechas si son distintas)
                ok1, _ = agregar_evento(datos_evento)
                if fecha_entr_ev != fecha_venta:
                    datos_evento_entrega = datos_evento.copy()
                    datos_evento_entrega["fecha"] = fecha_entr_ev.strftime("%Y-%m-%d")
                    datos_evento_entrega["tipo"] = f"📦 Entrega {canal_sel}"
                    datos_evento_entrega["titulo"] = f"Entrega {canal_sel}: {cliente_ev}" if cliente_ev else f"Entrega {canal_sel}"
                    agregar_evento(datos_evento_entrega)

                if ok1:
                    st.success(f"✅ Venta registrada en {canal_sel}: ${monto_ev:,.2f}")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Error al guardar en calendario")
