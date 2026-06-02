import streamlit as st
import pandas as pd
import calendar
from data_loaders import cargar_todas_ventas
from utils import limpiar_valor, ahora_hermosillo
from auth import tiene_permiso
from config import CANALES_VENTA

def show_dashboard_ventas():
    if not tiene_permiso("DashboardVentas"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    st.title("📊 Dashboard de Ventas — Todos los canales")
    
    df = cargar_todas_ventas()
    if df.empty:
        st.info("Sin registros de venta en ningún canal.")
        # Mostrar diagnóstico si existe
        if "debug_carga_ventas" in st.session_state:
            with st.expander("🔍 Diagnóstico de carga"):
                st.write(st.session_state["debug_carga_ventas"])
        st.stop()
    
    # Bloque de diagnóstico general (siempre visible al inicio)
    if "debug_carga_ventas" in st.session_state:
        with st.expander("🔍 Diagnóstico de carga de hojas"):
            st.write(st.session_state["debug_carga_ventas"])
    
    # Selector de canal
    canal_opciones = ["Todos"] + CANALES_VENTA
    canal_sel = st.radio("Mostrar canal:", canal_opciones, horizontal=True)
    
    if canal_sel != "Todos":
        df = df[df["Canal"] == canal_sel].copy()
    
    if df.empty:
        st.warning(f"No hay datos para {canal_sel}.")
        # Mostrar diagnóstico específico del canal seleccionado
        if canal_sel in ["Coffee Station", "Noble To Go"]:
            st.info("ℹ️ Si acabas de cargar datos, verifica que el mes seleccionado coincida con las fechas de los eventos.")
        st.stop()
    
    # Selección de mes
    df["Mes_num"] = df["Mes"].apply(limpiar_valor).astype(int)
    df["Año_num"] = df["Año"].apply(limpiar_valor).astype(int)
    meses_disp = sorted(
        df[["Mes_num","Año_num"]].drop_duplicates().apply(
            lambda r: (int(r["Mes_num"]), int(r["Año_num"])), axis=1
        ).tolist(), reverse=True
    )
    meses_disp = [(m,a) for m,a in meses_disp if m > 0 and a > 0]
    if not meses_disp:
        st.info("No hay meses completos disponibles. Verifica que los eventos tengan Mes y Año correctos.")
        st.stop()
    opciones_mes = [f"{calendar.month_name[m].capitalize()} {a}" for m,a in meses_disp]
    mes_sel_str = st.selectbox("📅 Mes:", opciones_mes)
    mes_idx = opciones_mes.index(mes_sel_str)
    mes_num, año_num = meses_disp[mes_idx]
    
    df_mes = df[
        (df["Mes_num"] == mes_num) & (df["Año_num"] == año_num)
    ].copy()
    if df_mes.empty:
        st.warning(f"Sin registros para {mes_sel_str}.")
        st.stop()
    
    # ──── RESUMEN GLOBAL (solo si se eligió "Todos") ────
    if canal_sel == "Todos":
        st.subheader("💰 Venta total por canal")
        cols_canal = st.columns(3)
        for i, canal in enumerate(CANALES_VENTA):
            df_canal = df_mes[df_mes["Canal"] == canal]
            total = df_canal["Venta_Diaria"].sum() if not df_canal.empty else 0.0
            cols_canal[i].metric(f"🏢 {canal}", f"${total:,.2f}")
        st.divider()
    
    # ──── DETALLE POR CANAL ────
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
            ), hide_index=True, use_container_width=True)
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
            c1.metric("Venta total", f"${total_cs:,.2f}")
            c2.metric("Adeudo total", f"${adeudo_cs:,.2f}")
            c3.metric("Anticipo total", f"${anticipo_cs:,.2f}")
            c4.metric("Eventos registrados", num_eventos)
            cols_mostrar = ["Fecha", "Cliente", "Total_Cotizado", "Adeudo", "Anticipo", "Metodo_Pago", "Notas"]
            cols_ok = [c for c in cols_mostrar if c in df_cs.columns]
            st.dataframe(df_cs[cols_ok].sort_values("Fecha"), hide_index=True, use_container_width=True)
        else:
            st.info("Sin registros de Coffee Station para este mes.")
            # Diagnóstico específico
            if "debug_carga_ventas" in st.session_state:
                st.caption("Diagnóstico de carga:")
                st.caption(st.session_state["debug_carga_ventas"])
    
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
            c1.metric("Venta total", f"${total_ntg:,.2f}")
            c2.metric("Adeudo total", f"${adeudo_ntg:,.2f}")
            c3.metric("Anticipo total", f"${anticipo_ntg:,.2f}")
            c4.metric("Eventos registrados", num_eventos)
            cols_mostrar = ["Fecha", "Cliente", "Total_Cotizado", "Adeudo", "Anticipo", "Metodo_Pago", "Notas"]
            cols_ok = [c for c in cols_mostrar if c in df_ntg.columns]
            st.dataframe(df_ntg[cols_ok].sort_values("Fecha"), hide_index=True, use_container_width=True)
        else:
            st.info("Sin registros de Noble To Go para este mes.")
            if "debug_carga_ventas" in st.session_state:
                st.caption("Diagnóstico de carga:")
                st.caption(st.session_state["debug_carga_ventas"])
    
    st.divider()
    csv = df_mes.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Descargar CSV del mes", data=csv,
                       file_name=f"ventas_{mes_sel_str.replace(' ','_')}.csv",
                       mime="text/csv", use_container_width=True)
