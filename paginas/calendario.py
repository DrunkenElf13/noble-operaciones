import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, timedelta
from components.calendario_utils import (
    cargar_eventos_mes, agregar_evento, actualizar_evento,
    eliminar_evento, registrar_abono
)
from utils import ts_hermosillo
from config import CANALES_VENTA
from auth import tiene_permiso

# Colores por tipo de evento (para la lista)
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

def show_calendario():
    st.title("📅 Calendario Noble")

    # Navegación de mes
    hoy = datetime.now()
    if "cal_mes" not in st.session_state:
        st.session_state.cal_mes = hoy.month
    if "cal_año" not in st.session_state:
        st.session_state.cal_año = hoy.year

    col_nav1, col_nav2, col_nav3, col_nav4 = st.columns([1, 2, 2, 1])
    with col_nav1:
        if st.button("◀ Mes anterior"):
            if st.session_state.cal_mes == 1:
                st.session_state.cal_mes = 12
                st.session_state.cal_año -= 1
            else:
                st.session_state.cal_mes -= 1
            st.rerun()
    with col_nav2:
        st.subheader(f"{calendar.month_name[st.session_state.cal_mes]} {st.session_state.cal_año}")
    with col_nav3:
        if st.button("Mes siguiente ▶"):
            if st.session_state.cal_mes == 12:
                st.session_state.cal_mes = 1
                st.session_state.cal_año += 1
            else:
                st.session_state.cal_mes += 1
            st.rerun()
    with col_nav4:
        if st.button("Hoy"):
            st.session_state.cal_mes = hoy.month
            st.session_state.cal_año = hoy.year
            st.rerun()

    # Cargar eventos del mes
    eventos = cargar_eventos_mes(st.session_state.cal_mes, st.session_state.cal_año)

    # Calendario en cuadrícula
    cal = calendar.Calendar()
    dias_mes = cal.monthdatescalendar(st.session_state.cal_año, st.session_state.cal_mes)

    # Mostrar cabecera de días
    dias_semana = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    cols = st.columns(7)
    for i, dia in enumerate(dias_semana):
        cols[i].markdown(f"**{dia}**")

    # Mostrar las semanas
    for semana in dias_mes:
        cols = st.columns(7)
        for i, dia in enumerate(semana):
            if dia.month != st.session_state.cal_mes:
                cols[i].markdown("")
                continue
            # Número de día
            cols[i].markdown(f"**{dia.day}**")
            # Eventos de este día
            eventos_dia = [e for e in eventos if e["fecha"].date() == dia]
            if eventos_dia:
                with cols[i].expander("📋", expanded=False):
                    for ev in eventos_dia:
                        color = ev.get("color", "#AAAAAA")
                        tipo = ev.get("tipo_evento", "")
                        st.markdown(
                            f"<span style='color:{color}; font-size:12px;'>{tipo}</span><br>"
                            f"<small>{ev['titulo'][:25]}</small>",
                            unsafe_allow_html=True
                        )
            else:
                cols[i].markdown("")

    st.divider()
    st.subheader("📋 Eventos del mes")

    # Tabla de eventos
    if eventos:
        df_eventos = pd.DataFrame(eventos)
        df_eventos["fecha_str"] = df_eventos["fecha"].dt.strftime("%d/%m/%Y")
        # Seleccionar columnas para mostrar
        cols_show = ["fecha_str", "tipo_evento", "titulo", "cliente", "total_cotizado", "adeudo", "ubicacion"]
        df_display = df_eventos[cols_show].sort_values("fecha_str")
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.info("No hay eventos este mes.")

    st.divider()
    st.subheader("➕ Agregar / Editar evento")

    # Formulario para agregar o editar
    with st.expander("➕ Nuevo evento", expanded=False):
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
                color_ev = st.color_picker("Color del evento", value="#4A90D9")
            enviar = st.form_submit_button("💾 Guardar evento")

        if enviar:
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
                    st.success("Evento agregado correctamente.")
                    st.rerun()
                else:
                    st.error(f"Error: {msg}")

    # Editar / Eliminar eventos existentes
    if eventos:
        st.subheader("✏️ Editar o eliminar eventos existentes")
        # Filtrar solo eventos de calendario (origen='calendario')
        eventos_cal = [e for e in eventos if e["origen"] == "calendario"]
        if eventos_cal:
            # Selector de evento
            opciones = {f"{e['fecha'].strftime('%d/%m/%Y')} - {e['titulo']} (ID:{e['id']})": e for e in eventos_cal}
            sel_key = st.selectbox("Selecciona un evento para modificar", list(opciones.keys()))
            if sel_key:
                ev = opciones[sel_key]
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("🗑️ Eliminar evento", key=f"del_{ev['id']}"):
                        ok, msg = eliminar_evento(ev["id"])
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                with col_b:
                    if st.button("✏️ Cargar datos para editar", key=f"edit_{ev['id']}"):
                        # Guardamos en session_state para precargar el formulario
                        st.session_state["editando_evento"] = ev
                        st.rerun()

        # Formulario de edición (aparece si hay un evento en session_state)
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
                    abonos_ev = st.text_area("Abonos (historial)", value=ev.get("abonos", ""))
                    notas_ev = st.text_area("Notas", value=ev.get("notas", ""))
                    color_ev = st.color_picker("Color del evento", value=ev.get("color", "#4A90D9"))
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.form_submit_button("💾 Actualizar evento"):
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
                    if st.form_submit_button("❌ Cancelar edición"):
                        del st.session_state["editando_evento"]
                        st.rerun()

        # Registrar abono
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
