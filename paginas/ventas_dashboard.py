import streamlit as st
import pandas as pd
import calendar
from data_loaders import cargar_todas_ventas
from utils import limpiar_valor, ahora_hermosillo
from auth import tiene_permiso
from config import CANALES_VENTA, COLS_CALENDARIO, PALETA_CANALES, COLOR_TARJETA, COLOR_SUBTEXTO
from sheets import safe_worksheet, sh

def _tarjeta(titulo, valor, delta=None, color=COLOR_TARJETA):
    delta_html = ""
    if delta:
        delta_html = f"<br><small style='color:{COLOR_SUBTEXTO}'>{delta}</small>"
    st.markdown(
        f"""
        <div style="border-left:4px solid {color}; padding:8px 12px; margin:4px 0; background:{COLOR_TARJETA}; border-radius:4px;">
            <div style="color:{COLOR_SUBTEXTO}; font-size:0.75rem;">{titulo}</div>
            <div style="font-size:1.25rem; font-weight:600;">{valor}{delta_html}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

def show_dashboard_ventas():
    if not tiene_permiso("DashboardVentas"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    st.title("Dashboard de Ventas")

    df = cargar_todas_ventas()
    if df.empty:
        st.info("Sin datos aún")
        st.stop()

    # ── Selector de canal ──
    canal_sel = st.radio("Canal", ["Todos"] + CANALES_VENTA, horizontal=True)
    if canal_sel != "Todos":
        df = df[df["Canal"] == canal_sel]

    # ── Selectores de año/mes separados ──
    df["Mes_num"] = df["Mes"].apply(limpiar_valor).astype(int)
    df["Año_num"] = df["Año"].apply(limpiar_valor).astype(int)
    años_disp = sorted(df["Año_num"].unique(), reverse=True)
    año_sel = st.selectbox("Año", años_disp)
    df_año = df[df["Año_num"] == año_sel]
    meses_disp = sorted(df_año["Mes_num"].unique())
    mes_sel = st.selectbox("Mes", meses_disp, format_func=lambda m: calendar.month_name[m])
    df_mes = df_año[df_año["Mes_num"] == mes_sel]

    if df_mes.empty:
        st.warning("Sin datos para el período")
        st.stop()

    # ── Resumen por canal ──
    with st.container(border=True):
        st.subheader("Resumen")
        cols = st.columns(3)
        for i, canal in enumerate(CANALES_VENTA):
            df_c = df_mes[df_mes["Canal"] == canal]
            cobrado = df_c["Venta_Diaria"].sum() if not df_c.empty else 0
            total = df_c["Venta_Total"].sum() if not df_c.empty else 0
            with cols[i]:
                _tarjeta(canal, f"${cobrado:,.0f}", f"Total: ${total:,.0f}", PALETA_CANALES.get(canal, COLOR_TARJETA))

    # ── Noble detalle ──
    if canal_sel in ["Noble", "Todos"] and "Noble" in df_mes["Canal"].unique():
        with st.container(border=True):
            st.subheader("Noble — Detalle diario")
            df_n = df_mes[df_mes["Canal"] == "Noble"].sort_values("Día")
            venta_acum = df_n["Venta_Diaria"].sum()
            tix_total = int(df_n["Total_Tickets"].sum())
            tix_prom = round(venta_acum / tix_total, 2) if tix_total > 0 else 0
            dias_con_v = int((df_n["Venta_Diaria"] > 0).sum())
            meta_m = limpiar_valor(df_n["Meta_Mensual"].iloc[-1]) if not df_n.empty else 145000

            k1, k2, k3, k4 = st.columns(4)
            with k1: _tarjeta("Venta acumulada", f"${venta_acum:,.0f}")
            with k2: _tarjeta("Meta mensual", f"${meta_m:,.0f}")
            with k3: _tarjeta("Ticket promedio", f"${tix_prom:,.2f}")
            with k4: _tarjeta("Días con venta", str(dias_con_v))

            st.dataframe(df_n[["Día","Fecha","Efectivo","Transferencias","Tarjeta","Total_POS",
                               "Uber_Eats","Rappi","Venta_Diaria","Total_Tickets",
                               "Ticket_Promedio","Meta_Diaria","Responsable","Notas"]],
                         hide_index=True, width="stretch")

    # ── Canales adicionales con detalle completo ──
    if canal_sel in ["Coffee Station", "Noble To Go", "Todos"]:
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
                    if "Fecha" in df.columns:
                        df["_fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
                    return df
            return pd.DataFrame()

        with st.expander("📋 Detalle completo de canales adicionales", expanded=canal_sel != "Todos"):
            for nombre, prefijo in [("Coffee Station", "☕"), ("Noble To Go", "🥤")]:
                st.caption(f"{prefijo} {nombre}")
                df_c = cargar_detalle(nombre)
                if df_c.empty:
                    st.caption("Hoja sin datos")
                    continue
                # Excluir IDs de entrega antiguos
                if "ID" in df_c.columns:
                    df_c = df_c[~df_c["ID"].astype(str).str.contains("_entrega", na=False)]
                # Filtrar por período
                if "_fecha" in df_c.columns:
                    df_c = df_c[(df_c["_fecha"].dt.month == mes_sel) & (df_c["_fecha"].dt.year == año_sel)]
                if df_c.empty:
                    st.caption("Sin datos en el período")
                    continue
                cols_mostrar = [c for c in COLS_CALENDARIO if c in df_c.columns and c != "_fecha"]
                st.dataframe(df_c[cols_mostrar].sort_values("Fecha", ascending=False),
                             hide_index=True, width="stretch")
