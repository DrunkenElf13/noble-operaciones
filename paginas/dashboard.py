import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, timedelta

from data_loaders import cargar_datos_integrales, cargar_todas_ventas
from inventario import obtener_ultimo_inventario, fecha_max_segura
from utils import limpiar_valor, ahora_hermosillo
from auth import tiene_permiso
from components.calendario_utils import cargar_eventos_mes
from config import CANALES_VENTA, PALETA_CANALES, COLOR_TARJETA, COLOR_EXITO, COLOR_ERROR, COLOR_SUBTEXTO

def _tarjeta(titulo, valor, delta=None, color=COLOR_TARJETA):
    delta_html = ""
    if delta:
        color_delta = COLOR_EXITO if delta.startswith("+") else COLOR_ERROR
        delta_html = f"<br><small style='color:{color_delta}'>{delta}</small>"
    st.markdown(
        f"""
        <div style="border-left:4px solid {color}; padding:8px 12px; margin:4px 0; background:{COLOR_TARJETA}; border-radius:4px;">
            <div style="color:{COLOR_SUBTEXTO}; font-size:0.75rem;">{titulo}</div>
            <div style="font-size:1.25rem; font-weight:600;">{valor}{delta_html}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

def show_dashboard():
    if not tiene_permiso("Dashboard"):
        st.error("No tienes permiso para esta página.")
        st.stop()

    df_raw, df_historial = cargar_datos_integrales()
    st.title("Dashboard Noble")

    ahora = ahora_hermosillo()
    dias_faltantes = calendar.monthrange(ahora.year, ahora.month)[1] - ahora.day
    if dias_faltantes <= 4:
        st.info(f"⏳ {dias_faltantes} días para fin de mes. Considera ejecutar el Corte de Mes.")

    # ── Ventas del mes ──
    with st.container(border=True):
        st.subheader("💰 Ventas del mes")
        df_v_dash = cargar_todas_ventas()
        if not df_v_dash.empty:
            años_disp = sorted(df_v_dash["Año"].apply(limpiar_valor).astype(int).unique(), reverse=True)
            col_a, col_m = st.columns(2)
            with col_a:
                año_sel = st.selectbox("Año", años_disp, index=0, key="dash_año")
            with col_m:
                mes_sel = st.selectbox("Mes", list(range(1,13)),
                                       index=ahora.month-1,
                                       format_func=lambda m: calendar.month_name[m], key="dash_mes")

            df_mes = df_v_dash[(df_v_dash["Mes"].apply(limpiar_valor)==mes_sel) &
                               (df_v_dash["Año"].apply(limpiar_valor)==año_sel)]
            cobrado = df_mes["Venta_Diaria"].sum()
            total   = df_mes["Venta_Total"].sum()
            dias_con_v = int((df_mes["Venta_Diaria"] > 0).sum())
            ticket_prom = cobrado / max(1, dias_con_v)

            c1, c2, c3, c4 = st.columns(4)
            with c1: _tarjeta("Cobrado", f"${cobrado:,.0f}")
            with c2: _tarjeta("Total facturado", f"${total:,.0f}")
            with c3: _tarjeta("Ticket promedio", f"${ticket_prom:,.0f}")
            with c4: _tarjeta("Días con venta", str(dias_con_v))

            # Canales
            st.caption("Por canal")
            ventas_canal = df_mes.groupby("Canal")["Venta_Diaria"].sum()
            cols_c = st.columns(len(CANALES_VENTA))
            for i, canal in enumerate(CANALES_VENTA):
                monto = ventas_canal.get(canal, 0)
                with cols_c[i]:
                    _tarjeta(canal, f"${monto:,.0f}", color=PALETA_CANALES.get(canal, COLOR_TARJETA))

    # ── Adeudos vencidos ──
    with st.container(border=True):
        st.subheader("⚠️ Adeudos vencidos")
        eventos = []
        for offset in [0, -1, -2]:
            mes = ahora.month + offset
            año = ahora.year
            if mes <= 0:
                mes += 12
                año -= 1
            eventos.extend(cargar_eventos_mes(mes, año))
        hoy = ahora.date()
        adeudos = []
        for e in eventos:
            adeudo = e.get("adeudo", 0)
            if adeudo <= 0:
                continue
            fecha_limite_str = e.get("fecha_entrega") or e.get("fecha")
            if isinstance(fecha_limite_str, str):
                try:
                    fecha_limite = pd.to_datetime(fecha_limite_str).date()
                except:
                    continue
            else:
                try:
                    fecha_limite = fecha_limite_str.date()
                except:
                    continue
            if fecha_limite < hoy:
                adeudos.append({
                    "Evento": e.get("titulo", ""),
                    "Cliente": e.get("cliente", ""),
                    "Adeudo": f"${adeudo:,.2f}",
                    "Fecha límite": fecha_limite.strftime("%d/%m/%Y"),
                })
        if adeudos:
            df_adeudos = pd.DataFrame(adeudos)
            st.dataframe(df_adeudos, hide_index=True, width="stretch")
        else:
            st.caption("Sin adeudos vencidos")

    # ── Compras sugeridas ──
    df_actual = obtener_ultimo_inventario(df_historial)
    with st.container(border=True):
        st.subheader("🛒 Compras sugeridas")
        if not df_actual.empty:
            com = df_actual[df_actual["Necesita Compra"] == True]
            if not com.empty:
                st.caption(f"{len(com)} insumos bajo mínimo")
                cols_compra = ["Unidad de Negocio","Nombre del Insumo","Marca","Proveedor","Grupo",
                               "Presentación de Compra","Unidad de Medida","Stock Neto Calculado",
                               "Stock Mínimo"]
                cols_ok = [c for c in cols_compra if c in com.columns]
                st.dataframe(com[cols_ok].sort_values(["Unidad de Negocio","Grupo"]),
                             hide_index=True, width="stretch")
            else:
                st.caption("Todo en orden")
        else:
            st.info("Sin datos de inventario.")

    # ── Actividad reciente ──
    with st.container(border=True):
        st.subheader("🕒 Actividad reciente")
        df_log = df_historial.copy()
        df_log["Fecha de Inventario"] = df_log["Fecha de Inventario"].combine_first(df_log["Fecha de Entrada"])
        cols_log = ["Fecha de Inventario","Responsable","Unidad de Negocio","Nombre del Insumo","Stock Neto","¿Comprar?","Observaciones"]
        cols_log_ok = [c for c in cols_log if c in df_log.columns]
        st.dataframe(
            df_log.dropna(subset=["Fecha de Inventario"])
                  .sort_values("Fecha de Inventario", ascending=False)[cols_log_ok]
                  .head(15),
            hide_index=True, width="stretch"
        )
