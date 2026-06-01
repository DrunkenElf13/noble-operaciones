import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, timedelta

def show_calendario():
    st.title("📅 Calendario Noble (prueba)")

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

    # Eventos falsos para prueba
    eventos = [
        {"fecha": hoy, "tipo_evento": "Evento Coffee Station", "titulo": "Cata de café", "color": "#FF5733"},
        {"fecha": hoy + timedelta(days=2), "tipo_evento": "Vacaciones", "titulo": "Jenny", "color": "#33FF57"},
    ]

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
            if eventos_dia:
                with cols[i].expander("📋", expanded=False):
                    for ev in eventos_dia:
                        st.markdown(
                            f"<span style='color:{ev['color']}; font-size:12px;'>{ev['tipo_evento']}</span><br>"
                            f"<small>{ev['titulo']}</small>",
                            unsafe_allow_html=True
                        )
