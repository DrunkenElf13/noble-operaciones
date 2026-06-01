import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, timedelta
from components.calendario_utils import (
    cargar_eventos_mes, agregar_evento, actualizar_evento,
    eliminar_evento, registrar_abono
)
from config import CANALES_VENTA

COLORES_TIPO = {
    "Evento Coffee Station": "#FF5733",
    "Vacaciones": "#33FF57",
    "Adeudo": "#FF3333",
    "Fecha importante": "#3357FF",
    "Otro": "#AAAAAA",
    "Venta Noble": "#48B065",
    "Venta Coffee Station": "#4A90D9",
    "Venta Noble To Go": "#9B59B6",
}

PALETA_COLORES = [
    "#4A90D9",
    "#9B59B6",
    "#E24B4A",
    "#48B065",
    "#EF9F27",
    "#F1C40F",
    "#1ABC9C",
    "#34495E",
]

def show_calendario():
    st.title("📅 Calendario Noble")

    hoy = datetime.now()
    if "cal_mes" not in st.session_state:
        st.session_state.cal_mes = hoy.month
    if "cal_año" not in st.session_state:
        st.session_state.cal_año = hoy.year

    col_anio, col_mes, col_btn = st.columns([1,1,2])
    with col_anio:
        años_opts = list(range(2024, 2031))
        año_sel = st.selectbox("Año", años_opts, index=años_opts.index(st.session_state.cal_año) if st.session_state.cal_año in años_opts else 0)
    with col_mes:
        meses_nombres = [calendar.month_name[m] for m in range(1,13)]
        mes_sel = st.selectbox("Mes", range(1,13), index=st.session_state.cal_mes-1,
                               format_func=lambda m: calendar.month_name[m])
    with col_btn:
        st.write("")
        st.write("")
        if st.button("Ir al mes seleccionado"):
            st.session_state.cal_mes = mes_sel
            st.session_state.cal_año = año_sel
            st.rerun()

    col1, col2, col3, col4 = st.columns([1,2,2,1])
    with col1:
        if st.button("◀"):
            if st.session_state.cal_mes == 1:
                st.session_state.cal_mes = 12
                st.session_state.cal_año -= 1
            else:
                st.session_state.cal_mes -= 1
            st.rerun()
    with col2:
        st.subheader(f"{calendar.month_name[st.session_state.cal_mes]} {st.session_state.cal_año}")
    with col3:
        if st.button("▶"):
            if st.session_state.cal_mes == 12:
                st.session_state.cal_mes = 1
                st.session_state.cal_año += 1
            else:
                st.session_state.cal_mes += 1
            st.rerun()
    with col4:
        if st.button("Hoy"):
            st.session_state.cal_mes = hoy.month
            st.session_state.cal_año = hoy.year
            st.rerun()

    eventos = cargar_eventos_mes(st.session_state.cal_mes, st.session_state.cal_año)

    cal = calendar.Calendar()
    dias_mes = cal.monthdatescalendar(st.session_state.cal_año, st.session_state.cal_mes)

    dias_semana = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    cols = st.columns(7)
    for i, dia in enumerate(dias_semana):
        cols[i].markdown(f"**{dia}**")

    for semana in dias_mes:
        cols = st.columns(7)
        for i, dia in enumerate(semana):
            if dia.month != st.session_state.cal_mes:
                cols[i].markdown("")
                continue
            cols[i].markdown(f"**{dia.day}**")
            eventos_dia = [e for e in eventos if e["fecha"].date() == dia]
            ventas_noble = [e for e in eventos_dia if e["tipo_evento"] == "Venta Noble"]
            otros = [e for e in eventos_dia if e["tipo_evento"] != "Venta Noble"]
            total_noble = sum(e["total_cotizado"] for e in ventas_noble)
            if total_noble > 0:
                cols[i].markdown(
                    f"<div style='background-color:rgba(72,176,101,0.2); padding:2px 4px; border-radius:4px; font-size:11px; color:#111;'>💰 ${total_noble:,.0f}</div>",
                    unsafe_allow_html=True
                )
            for ev in otros[:2]:
                color = ev.get("color", "#AAAAAA")
                titulo = ev["titulo"][:20]
                cols[i].markdown(
                    f"<div style='background-color:{color}20; border-left:3px solid {color}; padding:1px 4px; margin:2px 0; font-size:10px; color:#111;'>{titulo}</div>",
                    unsafe_allow_html=True
                )
            if len(otros) > 2:
                cols[i].markdown(f"<small>+{len(otros)-2} más</small>", unsafe_allow_html=True)

    st.divider()
    st.subheader("📋 Eventos del mes")
    if eventos:
        # Filtrar para no mostrar ventas POS repetitivas
        eventos_filtrados = [e for e in eventos if e["tipo_evento"] != "Venta Noble"]
        if eventos_filtrados:
            df_eventos = pd.DataFrame(eventos_filtrados)
            df_eventos["fecha_str"] = df_eventos["fecha"].dt.strftime("%d/%m/%Y")
            cols_show = ["fecha_str", "tipo_evento", "titulo", "cliente", "total_cotizado", "adeudo", "ubicacion"]
            df_display = df_eventos[cols_show].sort_values("fecha_str")
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.info("No hay eventos este mes (solo ventas regulares).")
    else:
        st.info("No hay eventos este mes.")

    st.divider()
    with st.expander("➕ Nuevo evento manual (no ventas)", expanded=False):
        with st.form("f_evento", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                fecha_ev = st.date_input("Fecha", value=hoy.date())
                tipo_ev = st.selectbox("Tipo", list(COLORES_TIPO.keys()))
                titulo_ev = st.text_input("Título")
                cliente_ev = st.text_input("Cliente")
                contacto_ev = st.text_input("Contacto")
                ubicacion_ev = st.text_input("Ubicación")
                descripcion_ev = st.text_area("Descripción")
            with col2:
                total_ev = st.number_input("Total cotizado ($)", min_value=0.0, step=10.0, value=0.0)
                adeudo_ev = st.number_input("Adeudo ($)", min_value=0.0, step=10.0, value=0.0)
                metodo_ev = st.text_input("Método de pago")
                fecha_contr_ev = st.date_input("Fecha contratación", value=hoy.date())
                fecha_entr_ev = st.date_input("Fecha entrega/evento", value=hoy.date())
                abonos_ev = st.text_area("Abonos (historial)")
                notas_ev = st.text_area("Notas")
                color_ev = st.selectbox("Color del evento", options=PALETA_COLORES)
                st.markdown(
                    f"<div style='width:30px;height:30px;background-color:{color_ev};border-radius:4px;'></div>",
                    unsafe_allow_html=True
                )
            if st.form_submit_button("💾 Guardar evento"):
                if not titulo_ev.strip():
                    st.error("El título es obligatorio.")
                else:
                    datos = {
                        "fecha": fecha_ev.strftime("%Y-%m-%d"),
                        "tipo": tipo_ev,
                        "titulo": titulo_ev.strip(),
                        "cliente": cliente_ev.strip(),
                        "contacto": contacto_ev.strip(),
                        "ubicacion": ubicacion_ev.strip(),
                        "descripcion": descripcion_ev.strip(),
                        "total_cotizado": total_ev,
                        "adeudo": adeudo_ev,
                        "metodo_pago": metodo_ev.strip(),
                        "fecha_contratacion": fecha_contr_ev.strftime("%Y-%m-%d"),
                        "fecha_entrega": fecha_entr_ev.strftime("%Y-%m-%d"),
                        "abonos": abonos_ev.strip(),
                        "notas": notas_ev.strip(),
                        "color": color_ev,
                        "responsable": st.session_state.current_user
                    }
                    ok, msg = agregar_evento(datos)
                    if ok:
                        st.success("Evento agregado.")
                        st.rerun()
                    else:
                        st.error(msg)

    if eventos:
        st.subheader("✏️ Editar o eliminar eventos")
        eventos_cal = [e for e in eventos if e["origen"] == "calendario"]
        if eventos_cal:
            opciones = {f"{e['fecha'].strftime('%d/%m/%Y')} - {e['titulo']} (ID:{e['id']})": e for e in eventos_cal}
            sel_key = st.selectbox("Selecciona un evento", list(opciones.keys()))
            if sel_key:
                ev = opciones[sel_key]
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("🗑️ Eliminar", key=f"del_{ev['id']}"):
                        ok, msg = eliminar_evento(ev["id"])
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                with col_b:
                    if st.button("✏️ Cargar para editar", key=f"edit_{ev['id']}"):
                        st.session_state["editando_evento"] = ev
                        st.rerun()

        if "editando_evento" in st.session_state and st.session_state["editando_evento"] is not None:
            ev = st.session_state["editando_evento"]
            st.subheader(f"Editando: {ev['titulo']}")
            with st.form("f_edit_evento", clear_on_submit=False):
                col1, col2 = st.columns(2)
                with col1:
                    fecha_ev = st.date_input("Fecha", value=ev["fecha"].date() if hasattr(ev["fecha"], 'date') else ev["fecha"])
                    tipo_ev = st.selectbox("Tipo", list(COLORES_TIPO.keys()), index=list(COLORES_TIPO.keys()).index(ev["tipo_evento"]) if ev["tipo_evento"] in COLORES_TIPO else 0)
                    titulo_ev = st.text_input("Título", value=ev["titulo"])
                    cliente_ev = st.text_input("Cliente", value=ev.get("cliente", ""))
                    contacto_ev = st.text_input("Contacto", value=ev.get("contacto", ""))
                    ubicacion_ev = st.text_input("Ubicación", value=ev.get("ubicacion", ""))
                    descripcion_ev = st.text_area("Descripción", value=ev.get("descripcion", ""))
                with col2:
                    total_ev = st.number_input("Total cotizado ($)", min_value=0.0, step=10.0, value=ev.get("total_cotizado", 0.0))
                    adeudo_ev = st.number_input("Adeudo ($)", min_value=0.0, step=10.0, value=ev.get("adeudo", 0.0))
                    metodo_ev = st.text_input("Método de pago", value=ev.get("metodo_pago", ""))
                    fecha_contr_ev = st.date_input("Fecha contratación", value=pd.to_datetime(ev.get("fecha_contratacion")).date() if ev.get("fecha_contratacion") else hoy.date())
                    fecha_entr_ev = st.date_input("Fecha entrega/evento", value=pd.to_datetime(ev.get("fecha_entrega")).date() if ev.get("fecha_entrega") else hoy.date())
                    abonos_ev = st.text_area("Abonos", value=ev.get("abonos", ""))
                    notas_ev = st.text_area("Notas", value=ev.get("notas", ""))
                    color_ev = st.selectbox("Color", options=PALETA_COLORES, index=PALETA_COLORES.index(ev.get("color", "#4A90D9")) if ev.get("color") in PALETA_COLORES else 0)
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.form_submit_button("💾 Actualizar"):
                        datos = {
                            "fecha": fecha_ev.strftime("%Y-%m-%d"),
                            "tipo": tipo_ev,
                            "titulo": titulo_ev.strip(),
                            "cliente": cliente_ev.strip(),
                            "contacto": contacto_ev.strip(),
                            "ubicacion": ubicacion_ev.strip(),
                            "descripcion": descripcion_ev.strip(),
                            "total_cotizado": total_ev,
                            "adeudo": adeudo_ev,
                            "metodo_pago": metodo_ev.strip(),
                            "fecha_contratacion": fecha_contr_ev.strftime("%Y-%m-%d"),
                            "fecha_entrega": fecha_entr_ev.strftime("%Y-%m-%d"),
                            "abonos": abonos_ev.strip(),
                            "notas": notas_ev.strip(),
                            "color": color_ev,
                            "responsable": st.session_state.current_user
                        }
                        ok, msg = actualizar_evento(ev["id"], datos)
                        if ok:
                            st.success("Evento actualizado.")
                            del st.session_state["editando_evento"]
                            st.rerun()
                        else:
                            st.error(msg)
                with col_btn2:
                    if st.form_submit_button("❌ Cancelar"):
                        del st.session_state["editando_evento"]
                        st.rerun()

        st.subheader("💵 Registrar abono")
        with st.expander("Añadir abono a un evento con adeudo"):
            eventos_con_adeudo = [e for e in eventos if e.get("adeudo", 0) > 0 and e["origen"] == "calendario"]
            if eventos_con_adeudo:
                opciones_abono = {f"{e['fecha'].strftime('%d/%m/%Y')} - {e['titulo']} (Adeudo: ${e['adeudo']:,.2f})": e for e in eventos_con_adeudo}
                sel_abono = st.selectbox("Evento", list(opciones_abono.keys()))
                if sel_abono:
                    ev_abono = opciones_abono[sel_abono]
                    monto_abono = st.number_input("Monto del abono ($)", min_value=0.0, step=10.0, value=0.0)
                    if st.button("Registrar abono"):
                        if monto_abono <= 0:
                            st.error("El monto debe ser mayor a cero.")
                        else:
                            ok, msg = registrar_abono(ev_abono["id"], monto_abono)
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
            else:
                st.info("No hay eventos con adeudo pendiente.")
