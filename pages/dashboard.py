import streamlit as st
import calendar
from data_loaders import cargar_datos_integrales, cargar_ventas
from inventario import obtener_ultimo_inventario, fecha_max_segura
from utils import limpiar_valor, ahora_hermosillo
from auth import tiene_permiso

def show_dashboard():
    if not tiene_permiso("Dashboard"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    df_raw, df_historial = cargar_datos_integrales()
    st.title("📊 Dashboard Operativo")
    ahora = ahora_hermosillo()
    dias_faltantes = calendar.monthrange(ahora.year, ahora.month)[1] - ahora.day
    if dias_faltantes <= 4:
        st.info(f"⏳ A {dias_faltantes} días del fin de mes. Recuerda ejecutar el **Corte de Mes**.")
    st.subheader("💰 Venta acumulada del mes")
    df_v_dash = cargar_ventas()
    if not df_v_dash.empty:
        df_v_mes_dash = df_v_dash[
            (df_v_dash["Mes"].apply(limpiar_valor) == ahora.month) &
            (df_v_dash["Año"].apply(limpiar_valor) == ahora.year)
        ]
        venta_acum_dash = df_v_mes_dash["Venta_Diaria"].sum() if not df_v_mes_dash.empty else 0.0
        meta_mes_dash = 145000.0
        if not df_v_mes_dash.empty and "Meta_Mensual" in df_v_mes_dash.columns:
            meta_mes_dash = limpiar_valor(df_v_mes_dash["Meta_Mensual"].iloc[-1]) or meta_mes_dash
        avance_dash = (venta_acum_dash / meta_mes_dash * 100) if meta_mes_dash > 0 else 0.0
        dias_con_venta_dash = int((df_v_mes_dash["Venta_Diaria"] > 0).sum()) if not df_v_mes_dash.empty else 0
        prom_diario_dash = venta_acum_dash / dias_con_venta_dash if dias_con_venta_dash > 0 else 0.0
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Venta acumulada", f"${venta_acum_dash:,.2f}")
        c2.metric("Meta mensual", f"${meta_mes_dash:,.2f}")
        c3.metric("Avance", f"{avance_dash:.1f}%")
        c4.metric("Promedio diario", f"${prom_diario_dash:,.2f}")
    else:
        st.info("Aún no hay ventas registradas este mes.")
    df_actual = obtener_ultimo_inventario(df_historial)
    if not df_actual.empty:
        st.divider()
        st.subheader("🛒 Lista de compras (todas las unidades)")
        com_global = df_actual[df_actual["Necesita Compra"] == True].copy()
        if not com_global.empty:
            cols_compra = ["Unidad de Negocio","Nombre del Insumo","Marca","Proveedor","Grupo",
                           "Presentación de Compra","Unidad de Medida","Stock Neto Calculado",
                           "Stock Mínimo","Necesita Compra","Responsable","Fecha de Inventario","Observaciones"]
            cols_compra_ok = [c for c in cols_compra if c in com_global.columns]
            st.dataframe(com_global[cols_compra_ok].sort_values(["Unidad de Negocio","Grupo"]),
                         use_container_width=True, hide_index=True)
        else:
            st.success("✅ No hay insumos que necesiten compra.")
        st.divider()
        st.subheader("🕒 Actividad Reciente")
        df_log = df_historial.copy()
        df_log["Fecha de Inventario"] = df_log["Fecha de Inventario"].combine_first(df_log["Fecha de Entrada"])
        cols_log = ["Fecha de Inventario","Responsable","Unidad de Negocio","Nombre del Insumo","Stock Neto","¿Comprar?","Observaciones"]
        cols_log_ok = [c for c in cols_log if c in df_log.columns]
        st.dataframe(
            df_log.dropna(subset=["Fecha de Inventario"])
                  .sort_values("Fecha de Inventario", ascending=False)[cols_log_ok]
                  .head(15),
            use_container_width=True
        )
    else:
        st.info("Sin datos históricos. Ejecuta el primer conteo de inventario.")
