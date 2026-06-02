import streamlit as st
import pandas as pd
import calendar
from data_loaders import cargar_todas_ventas
from utils import limpiar_valor, ahora_hermosillo
from auth import tiene_permiso
from config import CANALES_VENTA, COLS_CALENDARIO
from sheets import safe_worksheet, sh

def show_dashboard_ventas():
    if not tiene_permiso("DashboardVentas"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    st.title("📊 Dashboard de Ventas — Todos los canales")
    
    df = cargar_todas_ventas()
    if df.empty:
        st.info("Sin registros de venta en ningún canal.")
        st.stop()
    
    # Selector de canal
    canal_opciones = ["Todos"] + CANALES_VENTA
    canal_sel = st.radio("Mostrar canal:", canal_opciones, horizontal=True)
    
    if canal_sel != "Todos":
        df = df[df["Canal"] == canal_sel].copy()
    
    if df.empty:
        st.warning(f"No hay datos para {canal_sel}.")
        st.stop()
    
    # Selección de mes y año por separado
    df["Mes_num"] = df["Mes"].apply(limpiar_valor).astype(int)
    df["Año_num"] = df["Año"].apply(limpiar_valor).astype(int)
    años_disp = sorted(df["Año_num"].unique(), reverse=True)
    año_actual = ahora_hermosillo().year
    año_sel = st.selectbox("Año", años_disp, index=años_disp.index(año_actual) if año_actual in años_disp else 0)
    df_año = df[df["Año_num"] == año_sel]
    meses_disp = sorted(df_año["Mes_num"].unique())
    mes_actual = ahora_hermosillo().month
    mes_sel = st.selectbox("Mes", meses_disp,
                           index=meses_disp.index(mes_actual) if mes_actual in meses_disp else 0,
                           format_func=lambda m: calendar.month_name[m])
    
    df_mes = df_año[df_año["Mes_num"] == mes_sel].copy()
    if df_mes.empty:
        st.warning(f"Sin registros para {calendar.month_name[mes_sel]} {año_sel}.")
        st.stop()
    
    # ──── RESUMEN GLOBAL (solo "Todos") ────
    if canal_sel == "Todos":
        st.subheader("💰 Venta total por canal (Total | Cobrado)")
        cols_canal = st.columns(3)
        for i, canal in enumerate(CANALES_VENTA):
            df_canal = df_mes[df_mes["Canal"] == canal]
            total = df_canal["Venta_Total"].sum() if not df_canal.empty else 0.0
            cobrado = df_canal["Venta_Diaria"].sum() if not df_canal.empty else 0.0
            cols_canal[i].metric(f"🏢 {canal}", f"${cobrado:,.2f}", delta=f"Total: ${total:,.2f}")
        st.divider()
    
    # ──── Noble ────
    if canal_sel == "Noble" or (canal_sel == "Todos" and "Noble" in df_mes["Canal"].unique()):
        st.subheader("📈 Noble — Detalle diario")
        df_noble = df_mes[df_mes["Canal"] == "Noble"].sort_values("Fecha")
        if not df_noble.empty:
            meta_m     = limpiar_valor(df_noble["Meta_Mensual"].iloc[-1]) or 145000.0
            dias_hab   = int(limpiar_valor(df_noble["Dias_Habiles"].iloc[-1]) or 26)
            venta_acum = df_noble["Venta_Diaria"].sum()
            tix_total  = int(df_noble["Total_Tickets"].sum())
            tix_prom_g = round(venta_acum / tix_total, 2) if tix_total > 0 else 0
            faltante   = meta_m - venta_acum
            avance_pct = (venta_acum / meta_m * 100) if meta_m > 0 else 0

            k1,k2,k3,k4 = st.columns(4)
            k1.metric("Venta Acumulada", f"${venta_acum:,.2f}")
            k2.metric("Meta Mensual",    f"${meta_m:,.2f}")
            k3.metric("Faltante",        f"${faltante:,.2f}", delta=f"{avance_pct:.1f}% avance",
                      delta_color="normal" if faltante <= 0 else "inverse")
            k4.metric("Ticket Promedio", f"${tix_prom_g:,.2f}")

            st.divider()
            st.subheader("🎫 Métricas de Tickets")
            tk1, tk2, tk3, tk4 = st.columns(4)
            tk1.metric("Tickets Acumulados", f"{tix_total:,}")
            dias_con_v = int((df_noble["Venta_Diaria"] > 0).sum())
            dias_sin_v = len(df_noble) - dias_con_v
            tk2.metric("Días con Venta", f"{dias_con_v}", delta=f"de {len(df_noble)} registrados", delta_color="off")
            tk3.metric("Días sin Venta", f"{dias_sin_v}", delta_color="inverse" if dias_sin_v > 0 else "off")
            tk4.metric("Ticket Promedio Real", f"${tix_prom_g:,.2f}" if tix_prom_g > 0 else "—")

            st.divider()
            df_disp = df_noble[["Día","Fecha","Efectivo","Transferencias","Tarjeta","Total_POS",
                                "Uber_Eats","Rappi","Venta_Diaria","Total_Tickets",
                                "Ticket_Promedio","Meta_Diaria","Responsable","Notas"]].copy()
            df_disp["Fecha"] = df_disp["Fecha"].apply(lambda x: x.strftime("%d/%m/%Y") if pd.notna(x) else "")
            df_disp["vs Meta"] = df_disp.apply(
                lambda r: f"{(r['Venta_Diaria']/r['Meta_Diaria']*100):.0f}%" if r['Meta_Diaria'] > 0 else "—", axis=1
            )
            st.dataframe(df_disp.style.apply(
                lambda row: ["background-color: rgba(80,200,120,0.15)" if limpiar_valor(row.get("Venta_Diaria",0)) >= limpiar_valor(row.get("Meta_Diaria",0))
                             else "background-color: rgba(239,159,39,0.15)" if limpiar_valor(row.get("Venta_Diaria",0)) >= limpiar_valor(row.get("Meta_Diaria",0))*0.7
                             else "background-color: rgba(226,75,74,0.12)"] * len(row), axis=1
            ), hide_index=True, width="stretch")
        else:
            st.info("Sin registros de Noble para este mes.")
    
    # ──── Coffee Station ────
    if canal_sel in ["Coffee Station", "Todos"]:
        st.subheader("☕ Coffee Station")
        df_cs = df_mes[df_mes["Canal"] == "Coffee Station"].copy()
        if not df_cs.empty:
            total_cs = df_cs["Venta_Diaria"].sum()
            adeudo_cs = df_cs["Adeudo"].sum() if "Adeudo" in df_cs.columns else 0.0
            anticipo_cs = df_cs["Anticipo"].sum() if "Anticipo" in df_cs.columns else 0.0
            num_eventos = len(df_cs)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Venta cobrada", f"${total_cs:,.2f}")
            c2.metric("Adeudo total", f"${adeudo_cs:,.2f}")
            c3.metric("Anticipo total", f"${anticipo_cs:,.2f}")
            c4.metric("Eventos registrados", num_eventos)
        else:
            st.info("Sin registros de Coffee Station para este mes.")
    
    # ──── Noble To Go ────
    if canal_sel in ["Noble To Go", "Todos"]:
        st.subheader("🥤 Noble To Go")
        df_ntg = df_mes[df_mes["Canal"] == "Noble To Go"].copy()
        if not df_ntg.empty:
            total_ntg = df_ntg["Venta_Diaria"].sum()
            adeudo_ntg = df_ntg["Adeudo"].sum() if "Adeudo" in df_ntg.columns else 0.0
            anticipo_ntg = df_ntg["Anticipo"].sum() if "Anticipo" in df_ntg.columns else 0.0
            num_eventos = len(df_ntg)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Venta cobrada", f"${total_ntg:,.2f}")
            c2.metric("Adeudo total", f"${adeudo_ntg:,.2f}")
            c3.metric("Anticipo total", f"${anticipo_ntg:,.2f}")
            c4.metric("Eventos registrados", num_eventos)
        else:
            st.info("Sin registros de Noble To Go para este mes.")
    
    # ──── DETALLE COMPLETO DE CANALES ADICIONALES ────
    st.divider()
    with st.expander(f"📋 Detalle completo de canales adicionales ({calendar.month_name[mes_sel]} {año_sel})", expanded=False):
        tab_cs_d, tab_ntg_d = st.tabs(["☕ Coffee Station", "🥤 Noble To Go"])

        @st.cache_data(ttl=120)
        def cargar_detalle_canal(nombre_hoja):
            ws, err = safe_worksheet(sh, nombre_hoja)
            if ws:
                datos = ws.get_all_values()
                if len(datos) > 1:
                    df = pd.DataFrame(datos[1:], columns=datos[0])
                    for col in COLS_CALENDARIO:
                        if col not in df.columns:
                            df[col] = ""
                    if "Fecha" in df.columns:
                        df["_fecha_dt"] = pd.to_datetime(df["Fecha"], errors="coerce")
                    return df
            return pd.DataFrame()

        for nombre_hoja, tab, prefijo in [
            ("Coffee Station", tab_cs_d, "☕ Evento"),
            ("Noble To Go", tab_ntg_d, "🥤 Entrega"),
        ]:
            with tab:
                df_canal = cargar_detalle_canal(nombre_hoja)
                if df_canal.empty:
                    st.info(f"No hay registros en {nombre_hoja}.")
                    continue
                # Excluir IDs de entrega antiguos
                if "ID" in df_canal.columns:
                    df_canal = df_canal[~df_canal["ID"].astype(str).str.contains("_entrega", na=False)]
                # Filtrar por mes y año seleccionados
                if "_fecha_dt" in df_canal.columns:
                    df_canal = df_canal[(df_canal["_fecha_dt"].dt.month == mes_sel) &
                                        (df_canal["_fecha_dt"].dt.year == año_sel)]
                if df_canal.empty:
                    st.info(f"Ningún registro en {calendar.month_name[mes_sel]} {año_sel}.")
                    continue
                # Ordenar por fecha descendente
                df_canal = df_canal.sort_values("Fecha", ascending=False)
                # Mostrar todas las columnas de COLS_CALENDARIO excepto las internas
                columnas_mostrar = [c for c in COLS_CALENDARIO if c in df_canal.columns and c != "_fecha_dt"]
                st.dataframe(df_canal[columnas_mostrar], hide_index=True, width="stretch")
