import streamlit as st
import time
from data_loaders import cargar_ventas
from sheets import _asegurar_hoja_ventas, append_rows_con_retry
from utils import limpiar_valor, ahora_hermosillo
from components.avisos import mostrar_avisos
from auth import tiene_permiso
from config import CANALES_VENTA

# ------------------------------------------------------------
# Función auxiliar para construir fila de venta (POS)
# ------------------------------------------------------------
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
        canal,  # Unidad (usamos el nombre del canal)
        fecha.strftime("%Y-%m-%d"),
        fecha.day, fecha.month, fecha.year,
        efectivo, transferencias, tarjeta, total_pos,
        uber, rappi, venta_diaria,
        tickets_pos, tickets_uber, tickets_rappi, total_tix,
        tix_prom, meta_mensual, dias_habiles, meta_diaria,
        responsable, notas, canal,  # columna Canal al final
    ]

# ------------------------------------------------------------
# Función auxiliar para construir fila de venta (canales secundarios)
# ------------------------------------------------------------
def _construir_fila_venta_canal(
    fecha, monto, metodo_pago, responsable, notas, canal,
):
    venta_diaria = monto
    return [
        canal,                     # Unidad
        fecha.strftime("%Y-%m-%d"),
        fecha.day, fecha.month, fecha.year,
        0.0, 0.0, 0.0, monto,     # Efectivo, Transferencias, Tarjeta, Total_POS
        0.0, 0.0, venta_diaria,   # Uber, Rappi, Venta_Diaria
        0, 0, 0, 0,               # Tickets
        0.0,                       # Ticket_Promedio
        0.0, 0, 0.0,              # Meta_Mensual, Dias_Habiles, Meta_Diaria
        responsable, notas, canal, # columna Canal al final
    ]

# ------------------------------------------------------------
# Página principal: Registrar Ventas
# ------------------------------------------------------------
def show_ventas():
    if not tiene_permiso("Ventas"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    st.title("📈 Registrar Ventas")
    mostrar_avisos("Ventas")
    if not st.session_state.auth_status:
        st.error("🔒 Autenticación requerida.")
        st.stop()

    # ---------- Selector de canal ----------
    canal_sel = st.selectbox("🏢 Canal de venta:", CANALES_VENTA)

    df_ventas = cargar_ventas()
    hoy = ahora_hermosillo().date()

    ya_registrado = False
    if not df_ventas.empty and "Fecha" in df_ventas.columns:
        ya_registrado = any(f.date() == hoy for f in df_ventas["Fecha"].dropna())
    if ya_registrado:
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

    # ---------- Formulario para POS (Noble) ----------
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

        notas_v = st.text_input("📝 Notas del día (opcional):", placeholder="Ej: Día festivo, falla de sistema, etc.")
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

    # ---------- Formulario para canales secundarios ----------
    else:
        st.subheader(f"💵 Venta del día — {canal_sel}")
        monto_canal = st.number_input("Monto total ($):", min_value=0.0, step=10.0, value=0.0)
        metodo_pago = st.text_input("Método de pago:", placeholder="Efectivo, transferencia, etc.")
        notas_canal = st.text_area("📝 Notas:", placeholder="Detalles del evento o cliente")

        if st.button("💾 GUARDAR REGISTRO DE VENTA", type="primary", use_container_width=True):
            if monto_canal <= 0:
                st.warning("⚠️ Ingresa un monto mayor a cero.")
            else:
                ws_v, err = _asegurar_hoja_ventas()
                if err:
                    st.error(err)
                else:
                    fila = _construir_fila_venta_canal(
                        fecha=fecha_venta,
                        monto=monto_canal,
                        metodo_pago=metodo_pago,
                        responsable=responsable_v,
                        notas=notas_canal,
                        canal=canal_sel,
                    )
                    ok, msg = append_rows_con_retry(ws_v, [fila])
                    if ok:
                        cargar_ventas.clear()
                        st.success(f"✅ Venta registrada para {canal_sel}: ${monto_canal:,.2f}")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(msg)
