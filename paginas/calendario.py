import streamlit as st
import calendar
from datetime import datetime
from auth import tiene_permiso

def show_calendario():
    st.title("📅 Calendario Noble")

    # Navegación de mes
    hoy = datetime.now()
    if "cal_mes" not in st.session_state:
        st.session_state.cal_mes = hoy.month
    if "cal_año" not in st.session_state:
        st.session_state.cal_año = hoy.year

    col1, col2, col3, col4 = st.columns([1,2,2,1])
    with col1:
        if st.button("◀ Mes anterior"):
            if st.session_state.cal_mes == 1:
                st.session_state.cal_mes = 12
                st.session_state.cal_año -= 1
            else:
                st.session_state.cal_mes -= 1
            st.rerun()
    with col2:
        st.subheader(f"{calendar.month_name[st.session_state.cal_mes]} {st.session_state.cal_año}")
    with col3:
        if st.button("Mes siguiente ▶"):
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

    # Calendario simple
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
            else:
                cols[i].markdown(f"**{dia.day}**")
