import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, timedelta
from components.calendario_utils import (
    cargar_eventos_mes, agregar_evento, actualizar_evento,
    eliminar_evento, registrar_abono
)
from config import CANALES_VENTA
from sheets import safe_worksheet, sh
from data_loaders import cargar_todas_ventas
from utils import limpiar_valor

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

COLORES_TIPO = {
    "☕ Evento": "#4A90D9",
    "🥤 Entrega": "#9B59B6",
    "Venta Noble": "#48B065",
    "Vacaciones": "#33FF57",
    "Fecha importante": "#3357FF",
    "Adeudo": "#FF3333",
    "Otro": "#AAAAAA",
}

ICONOS_TIPO = {
    "☕ Evento": "☕",
    "🥤 Entrega": "🥤",
    "Vacaciones": "🏖️",
    "Fecha importante": "📌",
    "Adeudo": "⚠️",
}

CAMPOS_POR_TIPO = {
    "Vacaciones": ["titulo", "fecha_inicio", "fecha_fin", "color", "notas"],
    "Fecha importante": ["titulo", "descripcion", "fecha_inicio", "fecha_fin", "color", "notas"],
    "Adeudo": ["titulo", "cliente", "total_cotizado", "adeudo", "metodo_pago", "fecha_inicio", "fecha_entrega", "color", "notas"],
    "Otro": ["titulo", "cliente", "contacto", "ubicacion", "descripcion", "total_cotizado", "adeudo", "anticipo", "metodo_pago", "fecha_contratacion", "fecha_inicio", "fecha_entrega", "fecha_fin", "abonos", "notas", "color"],
}

def show_calendario():
    st.title("📅 Calendario Noble")

    hoy = datetime.now()
    if "cal_mes" not in st.session_state:
        st.session_state.cal_mes = hoy.month
    if "cal_año" not in st.session_state:
        st.session_state.cal_año = hoy.year
    if "dia_seleccionado" not in st.session_state:
        st.session_state.dia_seleccionado = hoy.date()

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
            st.cache_data.clear()
            st.rerun()

    col1, col2, col3, col4 = st.columns([1,2,2,1])
    with col1:
        if st.button("◀"):
            if st.session_state.cal_mes == 1:
                st.session_state.cal_mes = 12
                st.session_state.cal_año -= 1
            else:
                st.session_state.cal_mes -= 1
            st.cache_data.clear()
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
            st.cache_data.clear()
            st.rerun()
    with col4:
        if st.button("Hoy"):
            st.session_state.cal_mes = hoy.month
            st.session_state.cal_año = hoy.year
            st.cache_data.clear()
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

            if cols[i].button(str(dia.day), key=f"dia_{dia.day}_{dia.month}", help="Ver detalles"):
                st.session_state.dia_seleccionado = dia
                st.rerun()

            eventos_dia = [e for e in eventos if e["fecha"].date() == dia]
            ventas_noble = [e for e in eventos_dia if e["tipo_evento"] == "Venta Noble"]
            otros = [e for e in eventos_dia if e["tipo_evento"] != "Venta Noble"]
            total_noble = sum(e["total_cotizado"] for e in ventas_noble)

            if total_noble > 0:
                meta = ventas_noble[0].get("meta_diaria", 145000/26) if ventas_noble else 145000/26
                pct = min(total_noble / meta * 100, 100) if meta > 0 else 0
                color_bar = "#48B065" if pct >= 100 else ("#EF9F27" if pct >= 50 else "#E24B4A")
                barra = (
                    f"<div style='background:#ddd; border-radius:4px; height:6px; width:100%; margin-top:2px;'>"
                    f"<div style='width:{pct}%; height:6px; border-radius:4px; background:{color_bar};'></div></div>"
                )
                cols[i].markdown(
                    f"<div style='background-color:rgba(72,176,101,0.15); padding:2px 4px; border-radius:4px; font-size:11px;'>"
                    f"💰 ${total_noble:,.0f}{barra}</div>",
                    unsafe_allow_html=True
                )

            for ev in otros[:2]:
                color = ev.get("color", "#AAAAAA")
                icono = ICONOS_TIPO.get(ev["tipo_evento"], "")
                titulo = ev["titulo"][:22]
                texto = f"{icono} {titulo}" if icono else titulo
                # Tooltip con información clave
                tooltip = (
                    f"{ev['tipo_evento']}: {ev['titulo']}\n"
                    f"Cliente: {ev.get('cliente','')}\n"
                    f"Total: ${ev['total_cotizado']:,.2f}\n"
                    f"Adeudo: ${ev.get('adeudo',0):,.2f}\n"
                    f"Anticipo: ${ev.get('anticipo',0):,.2f}"
                )
                cols[i].markdown(
                    f"<div title='{tooltip}' style='background-color:{color}20; border-left:3px solid {color}; padding:1px 4px; margin:2px 0; font-size:10px;'>{texto}</div>",
                    unsafe_allow_html=True
                )
            if len(otros) > 2:
                cols[i].markdown(f"<small>+{len(otros)-2} más</small>", unsafe_allow_html=True)

    st.divider()
    st.subheader(f"📌 {st.session_state.dia_seleccionado.strftime('%d/%m/%Y')}")
    eventos_dia_sel = [e for e in eventos if e["fecha"].date() == st.session_state.dia_seleccionado]
    if eventos_dia_sel:
        for ev in eventos_dia_sel:
            with st.container():
                col1, col2 = st.columns([1,4])
                with col1:
                    st.markdown(f"<div style='width:20px;height:20px;background-color:{ev.get('color','#AAAAAA')};border-radius:4px;'></div>", unsafe_allow_html=True)
                with col2:
                    st.write(f"**{ev['tipo_evento']}**: {ev['titulo']}")
                    if ev.get("cliente"):
                        st.caption(f"Cliente: {ev['cliente']}")
                    st.caption(f"Total: ${ev['total_cotizado']:,.2f}")
                    if ev.get("adeudo",0) > 0:
                        st.caption(f"Adeudo: ${ev['adeudo']:,.2f}")
                    if ev.get("notas"):
                        st.caption(f"Notas: {ev['notas']}")
    else:
        st.info("Sin eventos para este día.")

    st.divider()
    st.subheader("📋 Eventos del mes")
    if eventos:
        eventos_filtrados = [e for e in eventos if e["tipo_evento"] != "Venta Noble"]
        if eventos_filtrados:
            eventos_unicos = {}
            for ev in eventos_filtrados:
                id_base = ev["id"].split("_dia_")[0].split("_entrega")[0]
                if id_base not in eventos_unicos:
                    eventos_unicos[id_base] = ev
            df_lista = []
            for ev in eventos_unicos.values():
                fecha_str = ev["fecha"].strftime("%d/%m/%Y")
                df_lista.append({
                    "Fecha": fecha_str,
                    "Tipo": ev["tipo_evento"],
                    "Título": ev["titulo"],
                    "Cliente": ev.get("cliente", ""),
                    "Total": ev["total_cotizado"],
                    "Adeudo": ev.get("adeudo", 0),
                    "Anticipo": ev.get("anticipo", 0),
                })
            df_display = pd.DataFrame(df_lista).sort_values("Fecha")
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.info("Solo ventas regulares este mes.")
    else:
        st.info("No hay eventos este mes.")

    # ────── FORMULARIO MANUAL (con toggle de varios días) ──────
    st.divider()
    with st.expander("➕ Nuevo evento manual", expanded=False):
        with st.form("f_evento_manual", clear_on_submit=True):
            tipo_ev = st.selectbox("Tipo de evento", list(COLORES_TIPO.keys()), key="tipo_manual")
            campos = CAMPOS_POR_TIPO.get(tipo_ev, [])
            col1, col2 = st.columns(2)
            with col1:
                fecha_ev = st.date_input("Fecha inicio", value=hoy.date(), key="fecha_manual")
                permite_rango = "fecha_fin" in campos
                if permite_rango:
                    es_rango = st.toggle("Evento de varios días", value=False, key="rango_manual")
                    if es_rango:
                        fecha_fin_ev = st.date_input("Fecha fin", value=fecha_ev, min_value=fecha_ev, key="fecha_fin_manual")
                    else:
                        fecha_fin_ev = fecha_ev
                else:
                    fecha_fin_ev = fecha_ev
                titulo_ev = st.text_input("Título", key="titulo_manual")
                if "cliente" in campos:
                    cliente_ev = st.text_input("Cliente", key="cliente_manual")
                else:
                    cliente_ev = ""
                if "contacto" in campos:
                    contacto_ev = st.text_input("Contacto", key="contacto_manual")
                else:
                    contacto_ev = ""
                if "ubicacion" in campos:
                    ubicacion_ev = st.text_input("Ubicación", key="ubicacion_manual")
                else:
                    ubicacion_ev = ""
                if "descripcion" in campos:
                    descripcion_ev = st.text_area("Descripción", key="descripcion_manual")
                else:
                    descripcion_ev = ""
            with col2:
                if "total_cotizado" in campos:
                    total_ev = st.number_input("Total cotizado ($)", min_value=0.0, step=10.0, value=0.0, key="total_manual")
                else:
                    total_ev = 0.0
                if "adeudo" in campos:
                    adeudo_ev = st.number_input("Adeudo ($)", min_value=0.0, step=10.0, value=0.0, key="adeudo_manual")
                else:
                    adeudo_ev = 0.0
                if "anticipo" in campos:
                    anticipo_ev = st.number_input("Anticipo ($)", min_value=0.0, step=10.0, value=0.0, key="anticipo_manual")
                else:
                    anticipo_ev = 0.0
                if "metodo_pago" in campos:
                    metodo_ev = st.text_input("Método de pago", key="metodo_manual")
                else:
                    metodo_ev = ""
                if "fecha_contratacion" in campos:
                    fecha_contr_ev = st.date_input("Fecha contratación", value=hoy.date(), key="fecha_contr_manual")
                else:
                    fecha_contr_ev = hoy.date()
                if "fecha_entrega" in campos:
                    fecha_entr_ev = st.date_input("Fecha entrega/evento", value=hoy.date(), key="fecha_entr_manual")
                else:
                    fecha_entr_ev = hoy.date()
                if "abonos" in campos:
                    abonos_ev = st.text_area("Abonos", key="abonos_manual")
                else:
                    abonos_ev = ""
                if "notas" in campos:
                    notas_ev = st.text_area("Notas", key="notas_manual")
                else:
                    notas_ev = ""
                color_nombre = st.selectbox("Color", list(PALETA_COLORES.keys()), key="color_manual")
                color_ev = PALETA_COLORES[color_nombre]
                st.markdown(f"<div style='width:30px;height:30px;background-color:{color_ev};border-radius:4px;'></div>", unsafe_allow_html=True)
            if st.form_submit_button("💾 Guardar evento"):
                if not titulo_ev.strip():
                    st.error("El título es obligatorio.")
                else:
                    datos = {
                        "fecha": fecha_ev.strftime("%Y-%m-%d"),
                        "tipo": tipo_ev,
                        "titulo": titulo_ev.strip(),
                        "cliente": cliente_ev.strip() if isinstance(cliente_ev, str) else "",
                        "contacto": contacto_ev.strip() if isinstance(contacto_ev, str) else "",
                        "ubicacion": ubicacion_ev.strip() if isinstance(ubicacion_ev, str) else "",
                        "descripcion": descripcion_ev.strip() if isinstance(descripcion_ev, str) else "",
                        "total_cotizado": total_ev,
                        "adeudo": adeudo_ev,
                        "metodo_pago": metodo_ev.strip() if isinstance(metodo_ev, str) else "",
                        "fecha_contratacion": fecha_contr_ev.strftime("%Y-%m-%d") if hasattr(fecha_contr_ev, 'strftime') else "",
                        "fecha_entrega": fecha_entr_ev.strftime("%Y-%m-%d") if hasattr(fecha_entr_ev, 'strftime') else "",
                        "abonos": abonos_ev.strip() if isinstance(abonos_ev, str) else "",
                        "notas": notas_ev.strip() if isinstance(notas_ev, str) else "",
                        "color": color_ev,
                        "responsable": st.session_state.current_user,
                        "anticipo": anticipo_ev,
                        "fecha_fin": fecha_fin_ev.strftime("%Y-%m-%d") if permite_rango and es_rango and fecha_fin_ev != fecha_ev else "",
                        "origen": "manual",
                    }
                    ok, msg = agregar_evento(datos)
                    if ok:
                        st.cache_data.clear()
                        st.success("Evento agregado.")
                        st.rerun()
                    else:
                        st.error(msg)

    # ────── EDICIÓN (si existe) ──────
    if "editando_evento" in st.session_state and st.session_state["editando_evento"] is not None:
        ev = st.session_state["editando_evento"]
        st.subheader(f"Editando: {ev['titulo']}")
        with st.form("f_edit_evento", clear_on_submit=False):
            tipo_ev = st.selectbox("Tipo", list(COLORES_TIPO.keys()),
                                   index=list(COLORES_TIPO.keys()).index(ev["tipo_evento"]) if ev["tipo_evento"] in COLORES_TIPO else 0,
                                   key="tipo_editar")
            col1, col2 = st.columns(2)
            with col1:
                fecha_ev = st.date_input("Fecha inicio", value=ev["fecha"].date() if hasattr(ev["fecha"], 'date') else ev["fecha"], key="fecha_editar")
                fecha_fin_val = ev.get("fecha_fin", "")
                if fecha_fin_val:
                    fecha_fin_ev = st.date_input("Fecha fin", value=pd.to_datetime(fecha_fin_val).date(), key="fecha_fin_editar")
                else:
                    fecha_fin_ev = fecha_ev
                titulo_ev = st.text_input("Título", value=ev["titulo"], key="titulo_editar")
                cliente_ev = st.text_input("Cliente", value=ev.get("cliente", ""), key="cliente_editar")
                contacto_ev = st.text_input("Contacto", value=ev.get("contacto", ""), key="contacto_editar")
                ubicacion_ev = st.text_input("Ubicación", value=ev.get("ubicacion", ""), key="ubicacion_editar")
                descripcion_ev = st.text_area("Descripción", value=ev.get("descripcion", ""), key="descripcion_editar")
            with col2:
                total_ev = st.number_input("Total cotizado", min_value=0.0, step=10.0, value=ev.get("total_cotizado",0.0), key="total_editar")
                adeudo_ev = st.number_input("Adeudo", min_value=0.0, step=10.0, value=ev.get("adeudo",0.0), key="adeudo_editar")
                anticipo_ev = st.number_input("Anticipo", min_value=0.0, step=10.0, value=ev.get("anticipo",0.0), key="anticipo_editar")
                metodo_ev = st.text_input("Método de pago", value=ev.get("metodo_pago", ""), key="metodo_editar")
                fecha_contr_ev = st.date_input("Fecha contratación", value=pd.to_datetime(ev.get("fecha_contratacion")).date() if ev.get("fecha_contratacion") else hoy.date(), key="fecha_contr_editar")
                fecha_entr_ev = st.date_input("Fecha entrega", value=pd.to_datetime(ev.get("fecha_entrega")).date() if ev.get("fecha_entrega") else hoy.date(), key="fecha_entr_editar")
                abonos_ev = st.text_area("Abonos", value=ev.get("abonos", ""), key="abonos_editar")
                notas_ev = st.text_area("Notas", value=ev.get("notas", ""), key="notas_editar")
                color_nombre_actual = [k for k, v in PALETA_COLORES.items() if v == ev.get("color", "#4A90D9")]
                color_nombre = st.selectbox("Color", list(PALETA_COLORES.keys()),
                                           index=list(PALETA_COLORES.keys()).index(color_nombre_actual[0]) if color_nombre_actual else 0,
                                           key="color_editar")
                color_ev = PALETA_COLORES[color_nombre]
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
                        "responsable": st.session_state.current_user,
                        "anticipo": anticipo_ev,
                        "fecha_fin": fecha_fin_ev.strftime("%Y-%m-%d") if fecha_fin_ev != fecha_ev else "",
                        "origen": ev.get("origen", "manual"),
                    }
                    ok, msg = actualizar_evento(ev["id"], datos)
                    if ok:
                        st.cache_data.clear()
                        st.success("Evento actualizado.")
                        del st.session_state["editando_evento"]
                        st.rerun()
                    else:
                        st.error(msg)
            with col_btn2:
                if st.form_submit_button("❌ Cancelar"):
                    del st.session_state["editando_evento"]
                    st.rerun()

    # ────── ABONOS ──────
    st.subheader("💵 Registrar abono")
    with st.expander("Añadir abono a evento con adeudo"):
        eventos_con_adeudo = [e for e in eventos if e.get("adeudo",0) > 0 and e["origen"] != "Venta Noble"]
        if eventos_con_adeudo:
            opciones = {f"{e['fecha'].strftime('%d/%m/%Y')} - {e['titulo']} (${e['adeudo']:,.2f})": e for e in eventos_con_adeudo}
            sel = st.selectbox("Evento", list(opciones.keys()))
            if sel:
                ev_abono = opciones[sel]
                monto = st.number_input("Monto del abono ($)", min_value=0.0, step=10.0, value=0.0)
                if st.button("Registrar abono"):
                    if monto <= 0:
                        st.error("El monto debe ser mayor a cero.")
                    else:
                        ok, msg = registrar_abono(ev_abono["id"], monto)
                        if ok:
                            st.cache_data.clear()
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
        else:
            st.info("No hay eventos con adeudo pendiente.")

    # ──────────────────────────────────────────────
    # NUEVO: Panel de detalle de Coffee Station y Noble To Go
    # ──────────────────────────────────────────────
    st.divider()
    with st.expander("📋 Detalle de Coffee Station y Noble To Go", expanded=False):
        st.markdown("Consulta todos los registros de estos canales, sin importar la fecha.")
        tab_cs, tab_ntg = st.tabs(["☕ Coffee Station", "🥤 Noble To Go"])

        @st.cache_data(ttl=120)
        def cargar_detalle_canal(nombre_hoja):
            ws, err = safe_worksheet(sh, nombre_hoja)
            if ws:
                datos = ws.get_all_values()
                if len(datos) > 1:
                    df = pd.DataFrame(datos[1:], columns=datos[0])
                    # Asegurar que tenga al menos las columnas básicas
                    columnas_deseadas = ["ID","Fecha","Título","Cliente","Total_Cotizado","Adeudo","Anticipo","Metodo_Pago","Fecha_Contratacion","Fecha_Entrega","Notas"]
                    for col in columnas_deseadas:
                        if col not in df.columns:
                            df[col] = ""
                    return df[columnas_deseadas]
            return pd.DataFrame()

        with tab_cs:
            df_cs = cargar_detalle_canal("Coffee Station")
            if not df_cs.empty:
                st.dataframe(df_cs, hide_index=True, use_container_width=True)
            else:
                st.info("No hay registros en Coffee Station.")

        with tab_ntg:
            df_ntg = cargar_detalle_canal("Noble To Go")
            if not df_ntg.empty:
                st.dataframe(df_ntg, hide_index=True, use_container_width=True)
            else:
                st.info("No hay registros en Noble To Go.")
