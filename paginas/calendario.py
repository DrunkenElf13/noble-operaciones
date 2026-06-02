import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, timedelta
from components.calendario_utils import (
    cargar_eventos_mes, agregar_evento, actualizar_evento,
    eliminar_evento, registrar_abono, _asegurar_hoja_calendario
)
from config import COLS_CALENDARIO, PALETA_EVENTOS, COLOR_TARJETA, COLOR_SUBTEXTO
from sheets import safe_worksheet, sh
from utils import limpiar_valor

TIPOS_MANUALES = ["Vacaciones", "Fecha importante", "Adeudo", "Otro"]

def show_calendario():
    st.title("Calendario Noble")

    hoy = datetime.now()
    if "cal_mes" not in st.session_state:
        st.session_state.cal_mes = hoy.month
    if "cal_año" not in st.session_state:
        st.session_state.cal_año = hoy.year
    if "dia_seleccionado" not in st.session_state:
        st.session_state.dia_seleccionado = hoy.date()

    # ---------- Controles de mes ----------
    col_anio, col_mes, col_btn1, col_btn2 = st.columns([1, 1, 1, 1])
    with col_anio:
        años_opts = list(range(2024, 2031))
        año_sel = st.selectbox("Año", años_opts,
                               index=años_opts.index(st.session_state.cal_año)
                               if st.session_state.cal_año in años_opts else 0)
    with col_mes:
        mes_sel = st.selectbox("Mes", list(range(1, 13)),
                               index=st.session_state.cal_mes - 1,
                               format_func=lambda m: calendar.month_name[m])
    with col_btn1:
        st.write("")
        st.write("")
        if st.button("◀"):
            if st.session_state.cal_mes == 1:
                st.session_state.cal_mes = 12
                st.session_state.cal_año -= 1
            else:
                st.session_state.cal_mes -= 1
            st.cache_data.clear()
            st.rerun()
    with col_btn2:
        st.write("")
        st.write("")
        if st.button("▶"):
            if st.session_state.cal_mes == 12:
                st.session_state.cal_mes = 1
                st.session_state.cal_año += 1
            else:
                st.session_state.cal_mes += 1
            st.cache_data.clear()
            st.rerun()

    if st.button("Hoy", width="stretch"):
        st.session_state.cal_mes = hoy.month
        st.session_state.cal_año = hoy.year
        st.cache_data.clear()
        st.rerun()

    eventos = cargar_eventos_mes(mes_sel, año_sel)

    # Alerta de eventos con rango sospechoso
    anomalos = st.session_state.get("eventos_anomalos", [])
    if anomalos:
        with st.expander("⚠️ Eventos con posible error de rango (Fecha_Fin inesperada)", expanded=True):
            for a in anomalos:
                st.write(f"- {a}")
            st.info("Estos eventos aparecerán en cada día del rango. Si no deberían ser multi‑día, edítalos y deja 'Fecha fin' vacía.")

    # ---------- Calendario ----------
    cal = calendar.Calendar()
    dias_mes = cal.monthdatescalendar(año_sel, mes_sel)

    st.subheader(f"{calendar.month_name[mes_sel]} {año_sel}")
    dias_semana = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    cols_header = st.columns(7)
    for i, d in enumerate(dias_semana):
        cols_header[i].markdown(f"**{d}**")

    for semana in dias_mes:
        cols = st.columns(7)
        for i, dia in enumerate(semana):
            if dia.month != mes_sel:
                cols[i].markdown("")
                continue

            # Botón para seleccionar el día
            if cols[i].button(str(dia.day), key=f"dia_{dia.day}_{dia.month}", help="Ver detalles"):
                st.session_state.dia_seleccionado = dia
                st.rerun()

            eventos_dia = [e for e in eventos if e["fecha"].date() == dia]
            ventas_noble = [e for e in eventos_dia if e["tipo_evento"] == "Venta Noble"]
            otros = [e for e in eventos_dia if e["tipo_evento"] != "Venta Noble"]
            total_noble = sum(e["total_cotizado"] for e in ventas_noble)

            if total_noble > 0:
                meta = ventas_noble[0].get("meta_diaria", 145000 / 26) if ventas_noble else 145000 / 26
                pct = min(total_noble / meta * 100, 100) if meta > 0 else 0
                color_bar = "#48B065" if pct >= 100 else ("#EF9F27" if pct >= 50 else "#E24B4A")
                cols[i].markdown(
                    f"<div style='background:#ddd; border-radius:4px; height:4px; width:100%; margin-top:2px;'>"
                    f"<div style='width:{pct}%; height:4px; border-radius:4px; background:{color_bar};'></div></div>",
                    unsafe_allow_html=True
                )

            # Etiquetas de eventos con tooltip
            for ev in otros[:2]:
                color = ev.get("color", "#aaa")
                titulo = ev["titulo"][:22]
                tooltip = (
                    f"{ev['tipo_evento']}: {ev['titulo']}\n"
                    f"Cliente: {ev.get('cliente', '')}\n"
                    f"Total: ${ev['total_cotizado']:,.2f}\n"
                    f"Adeudo: ${ev.get('adeudo', 0):,.2f}\n"
                    f"Anticipo: ${ev.get('anticipo', 0):,.2f}"
                )
                cols[i].markdown(
                    f"<div title='{tooltip}' style='border-left:3px solid {color}; padding:0 4px; margin:1px 0; font-size:10px; color:{COLOR_SUBTEXTO};'>{titulo}</div>",
                    unsafe_allow_html=True
                )
            if len(otros) > 2:
                cols[i].markdown(f"<small style='color:{COLOR_SUBTEXTO}'>+{len(otros) - 2}</small>", unsafe_allow_html=True)

    # ---------- Día seleccionado ----------
    st.divider()
    st.subheader(f"📌 {st.session_state.dia_seleccionado.strftime('%d/%m/%Y')}")
    eventos_dia_sel = [e for e in eventos if e["fecha"].date() == st.session_state.dia_seleccionado]
    if eventos_dia_sel:
        for ev in eventos_dia_sel:
            with st.container(border=True):
                st.caption(f"{ev['tipo_evento']} — {ev['titulo']}")
                if ev.get("cliente"):
                    st.caption(f"Cliente: {ev['cliente']}")
                st.caption(f"Total: ${ev['total_cotizado']:,.2f} | Adeudo: ${ev.get('adeudo', 0):,.2f}")
                if ev.get("notas"):
                    st.caption(f"Notas: {ev['notas']}")
    else:
        st.info("Sin eventos para este día.")

    # ---------- Lista de eventos del mes ----------
    with st.expander("Lista de eventos del mes", expanded=False):
        eventos_filtrados = [e for e in eventos if e["tipo_evento"] != "Venta Noble"]
        if eventos_filtrados:
            eventos_unicos = {}
            for ev in eventos_filtrados:
                id_base = ev["id"].split("_dia_")[0].split("_entrega")[0]
                if id_base not in eventos_unicos:
                    eventos_unicos[id_base] = ev
            df = pd.DataFrame(eventos_unicos.values())[["fecha", "tipo_evento", "titulo", "total_cotizado", "adeudo", "anticipo"]]
            df["fecha"] = df["fecha"].dt.strftime("%d/%m/%Y")
            st.dataframe(df.sort_values("fecha"), hide_index=True, width="stretch")
        else:
            st.caption("Solo ventas regulares este mes.")

    # ---------- FORMULARIO MANUAL ----------
    with st.expander("Nuevo evento manual", expanded=False):
        with st.form("f_evento_manual"):
            tipo_ev = st.selectbox("Tipo de evento", TIPOS_MANUALES)
            fecha_ev = st.date_input("Fecha inicio", value=hoy.date())
            titulo_ev = st.text_input("Título")
            es_rango = st.toggle("Evento de varios días", value=False)
            fecha_fin = fecha_ev
            if es_rango:
                fecha_fin = st.date_input("Fecha fin", value=fecha_ev, min_value=fecha_ev)
            color_nombre = st.selectbox("Color", list(PALETA_EVENTOS.keys()), format_func=lambda x: f"● {x}")
            notas_ev = st.text_area("Notas")
            if st.form_submit_button("Guardar evento", width="stretch"):
                if not titulo_ev.strip():
                    st.error("El título es obligatorio.")
                else:
                    datos = {
                        "fecha": fecha_ev.strftime("%Y-%m-%d"),
                        "tipo": tipo_ev,
                        "titulo": titulo_ev.strip(),
                        "color": PALETA_EVENTOS[color_nombre],
                        "origen": "manual",
                        "total_cotizado": 0, "adeudo": 0, "anticipo": 0,
                        "fecha_fin": fecha_fin.strftime("%Y-%m-%d") if es_rango and fecha_fin != fecha_ev else "",
                        "notas": notas_ev,
                        "responsable": st.session_state.current_user,
                        "cliente": "", "contacto": "", "ubicacion": "", "descripcion": "",
                        "metodo_pago": "", "fecha_contratacion": "", "fecha_entrega": "", "abonos": ""
                    }
                    ok, msg = agregar_evento(datos)
                    if ok:
                        st.cache_data.clear()
                        st.success("Evento agregado.")
                        st.rerun()
                    else:
                        st.error(msg)

    # ---------- EDICIÓN DE EVENTO ----------
    if "editando_evento" in st.session_state and st.session_state["editando_evento"] is not None:
        ev = st.session_state["editando_evento"]
        with st.expander(f"Editando: {ev['titulo']}", expanded=True):
            with st.form("f_edit_evento"):
                tipo_ev = st.selectbox("Tipo", list(PALETA_EVENTOS.keys()),
                                       index=list(PALETA_EVENTOS.keys()).index(ev["tipo_evento"])
                                       if ev["tipo_evento"] in PALETA_EVENTOS else 0)
                fecha_ev = st.date_input("Fecha inicio", value=ev["fecha"].date() if hasattr(ev["fecha"], 'date') else ev["fecha"])
                fecha_fin_val = ev.get("fecha_fin", "")
                fecha_fin = fecha_ev
                if fecha_fin_val:
                    fecha_fin = st.date_input("Fecha fin", value=pd.to_datetime(fecha_fin_val).date())
                titulo_ev = st.text_input("Título", value=ev["titulo"])
                total_ev = st.number_input("Total cotizado", value=ev.get("total_cotizado", 0.0))
                adeudo_ev = st.number_input("Adeudo", value=ev.get("adeudo", 0.0))
                anticipo_ev = st.number_input("Anticipo", value=ev.get("anticipo", 0.0))
                notas_ev = st.text_area("Notas", value=ev.get("notas", ""))
                color_nombre_actual = [k for k, v in PALETA_EVENTOS.items() if v == ev.get("color", "#4A90D9")]
                color_nombre = st.selectbox("Color", list(PALETA_EVENTOS.keys()),
                                            index=list(PALETA_EVENTOS.keys()).index(color_nombre_actual[0])
                                            if color_nombre_actual else 0,
                                            format_func=lambda x: f"● {x}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("Actualizar", width="stretch"):
                        datos = {
                            "fecha": fecha_ev.strftime("%Y-%m-%d"),
                            "tipo": tipo_ev,
                            "titulo": titulo_ev.strip(),
                            "total_cotizado": total_ev,
                            "adeudo": adeudo_ev,
                            "anticipo": anticipo_ev,
                            "fecha_fin": fecha_fin.strftime("%Y-%m-%d") if fecha_fin != fecha_ev else "",
                            "notas": notas_ev,
                            "color": PALETA_EVENTOS[color_nombre],
                            "origen": ev.get("origen", "manual"),
                            "responsable": st.session_state.current_user,
                            "cliente": ev.get("cliente", ""),
                            "contacto": ev.get("contacto", ""),
                            "ubicacion": ev.get("ubicacion", ""),
                            "descripcion": ev.get("descripcion", ""),
                            "metodo_pago": ev.get("metodo_pago", ""),
                            "fecha_contratacion": ev.get("fecha_contratacion", ""),
                            "fecha_entrega": ev.get("fecha_entrega", ""),
                            "abonos": ev.get("abonos", "")
                        }
                        ok, msg = actualizar_evento(ev["id"], datos)
                        if ok:
                            st.cache_data.clear()
                            del st.session_state["editando_evento"]
                            st.success("Evento actualizado.")
                            st.rerun()
                        else:
                            st.error(msg)
                with col2:
                    if st.form_submit_button("Cancelar", width="stretch"):
                        del st.session_state["editando_evento"]
                        st.rerun()

    # ---------- ABONOS ----------
    st.divider()
    with st.expander("Registrar abono"):
        ws_cal, _ = _asegurar_hoja_calendario()
        eventos_adeudo = []
        if ws_cal:
            datos = ws_cal.get_all_values()
            if len(datos) > 1:
                df = pd.DataFrame(datos[1:], columns=datos[0])
                if "Adeudo" in df.columns:
                    df["Adeudo_num"] = df["Adeudo"].apply(limpiar_valor)
                    df = df[df["Adeudo_num"] > 0]
                    for _, row in df.iterrows():
                        if row.get("Origen", "") != "Venta Noble":
                            eventos_adeudo.append({
                                "id": row["ID"],
                                "fecha": row["Fecha"],
                                "titulo": row.get("Título", ""),
                                "cliente": row.get("Cliente", ""),
                                "adeudo": limpiar_valor(row["Adeudo"])
                            })
        if eventos_adeudo:
            cliente_busqueda = st.text_input("Filtrar por cliente")
            if cliente_busqueda:
                eventos_adeudo = [e for e in eventos_adeudo if cliente_busqueda.lower() in e["cliente"].lower()]
            if eventos_adeudo:
                opciones = {f"{e['fecha']} - {e['titulo']} (${e['adeudo']:,.2f})": e for e in eventos_adeudo}
                sel = st.selectbox("Evento", list(opciones.keys()))
                if sel:
                    ev_abono = opciones[sel]
                    monto = st.number_input("Monto del abono ($)", min_value=0.0, step=10.0)
                    if st.button("Registrar abono", width="stretch"):
                        if monto <= 0:
                            st.error("Monto mayor a cero.")
                        else:
                            ok, msg = registrar_abono(ev_abono["id"], monto)
                            if ok:
                                st.cache_data.clear()
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
            else:
                st.caption("Sin resultados.")
        else:
            st.caption("No hay eventos con adeudo pendiente.")

    # ── Panel de detalle de Coffee Station y Noble To Go ──
    st.divider()
    with st.expander("📋 Detalle de Coffee Station y Noble To Go", expanded=False):
        tab_cs, tab_ntg = st.tabs(["☕ Coffee Station", "🥤 Noble To Go"])

        @st.cache_data(ttl=120)
        def cargar_detalle(hoja):
            ws, _ = safe_worksheet(sh, hoja)
            if ws:
                datos = ws.get_all_values()
                if len(datos) > 1:
                    df = pd.DataFrame(datos[1:], columns=datos[0])
                    for col in COLS_CALENDARIO:
                        if col not in df.columns:
                            df[col] = ""
                    df["_fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
                    return df
            return pd.DataFrame()

        for hoja, tab, prefijo in [("Coffee Station", tab_cs, "☕ Evento"), ("Noble To Go", tab_ntg, "🥤 Entrega")]:
            with tab:
                df = cargar_detalle(hoja)
                if df.empty:
                    st.info("Sin datos.")
                    continue
                if "ID" in df.columns:
                    df = df[~df["ID"].astype(str).str.contains("_entrega", na=False)]

                # Filtros
                col_a, col_m, col_c, col_ad = st.columns(4)
                with col_a:
                    años_d = sorted(df["_fecha"].dt.year.dropna().unique().astype(int), reverse=True)
                    año_f = st.selectbox("Año", ["Todos"] + [str(a) for a in años_d], key=f"año_{hoja}")
                with col_m:
                    mes_f = st.selectbox("Mes", ["Todos"] + [calendar.month_name[m] for m in range(1, 13)], key=f"mes_{hoja}")
                with col_c:
                    cliente_f = st.text_input("Cliente", key=f"cliente_{hoja}")
                with col_ad:
                    adeudo_f = st.selectbox("Adeudo", ["Todos", "Con adeudo", "Sin adeudo"], key=f"adeudo_{hoja}")

                if año_f != "Todos":
                    df = df[df["_fecha"].dt.year == int(año_f)]
                if mes_f != "Todos":
                    mes_num = list(calendar.month_name).index(mes_f)
                    df = df[df["_fecha"].dt.month == mes_num]
                if cliente_f.strip():
                    df = df[df["Cliente"].astype(str).str.contains(cliente_f.strip(), case=False, na=False)]
                if adeudo_f == "Con adeudo":
                    df = df[df["Adeudo"].apply(limpiar_valor) > 0]
                elif adeudo_f == "Sin adeudo":
                    df = df[df["Adeudo"].apply(limpiar_valor) == 0]

                st.caption(f"{len(df)} resultados")
                ver_tabla = st.toggle("Vista tabla", key=f"tabla_{hoja}")
                if ver_tabla:
                    st.dataframe(df.drop(columns=["_fecha"], errors="ignore"), hide_index=True, width="stretch")
                else:
                    if df.empty:
                        st.info("Sin resultados.")
                    else:
                        df = df.sort_values("Fecha", ascending=False)
                        for i in range(0, len(df), 2):
                            cols = st.columns(2)
                            for j in range(2):
                                idx = i + j
                                if idx >= len(df):
                                    break
                                row = df.iloc[idx]
                                with cols[j]:
                                    color = row.get("Color", "#4A90D9") or "#4A90D9"
                                    st.markdown(
                                        f"""
                                        <div style="border-left:4px solid {color}; padding:8px 12px; margin:4px 0; background:{COLOR_TARJETA}; border-radius:4px;">
                                            <b>{prefijo} - {row.get('Cliente', 'Sin cliente')}</b><br>
                                            <small style='color:{COLOR_SUBTEXTO}'>{row.get('Fecha', '')}</small>
                                            <hr style='margin:4px 0;'>
                                            <small>Total: ${limpiar_valor(row.get('Total_Cotizado', 0)):,.2f}</small><br>
                                            <small>Adeudo: ${limpiar_valor(row.get('Adeudo', 0)):,.2f} | Anticipo: ${limpiar_valor(row.get('Anticipo', 0)):,.2f}</small><br>
                                            <small>Método: {row.get('Metodo_Pago', '')} | Contacto: {row.get('Contacto', '')}</small><br>
                                            <small>Notas: {row.get('Notas', '')}</small>
                                        </div>
                                        """,
                                        unsafe_allow_html=True
                                    )
