import streamlit as st
from data_loaders import cargar_datos_integrales
from inventario import obtener_ultimo_inventario
from utils import limpiar_valor, ahora_hermosillo
from config import UNIDADES
from auth import tiene_permiso

def show_consulta():
    if not tiene_permiso("Consulta"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    df_raw, df_historial = cargar_datos_integrales()
    st.title("📦 Inventario actual")
    u_sel     = st.selectbox("🏢 Unidad:", UNIDADES)
    df_actual = obtener_ultimo_inventario(df_historial, u_sel)
    if df_actual.empty:
        st.warning("No hay registros en la base de datos para esta unidad.")
        st.stop()
    bajo_min = df_actual[df_actual["Necesita Compra"] == True]
    m1,m2,m3 = st.columns(3)
    m1.metric("Total Referencias", len(df_actual))
    m2.metric("Alertas de Compra", len(bajo_min), delta=-len(bajo_min), delta_color="inverse")
    m3.metric("Volumen Global",    f"{df_actual['Stock Neto Calculado'].sum():,.1f}")
    st.divider()
    col_s, col_p = st.columns([2,1])
    with col_s:
        busqueda = st.text_input("🔍 Búsqueda rápida:")
    with col_p:
        col_prov = "Proveedor" if "Proveedor" in df_actual.columns else None
        if col_prov:
            provs    = ["Todos"] + sorted(df_actual[col_prov].dropna().unique().tolist())
            prov_sel = st.selectbox("🚛 Filtro Proveedor:", provs)
        else:
            prov_sel = "Todos"
    df_display = df_actual.copy()
    if busqueda:
        df_display = df_display[df_display["Nombre del Insumo"].astype(str).str.contains(busqueda, case=False, na=False)]
    if prov_sel != "Todos" and col_prov:
        df_display = df_display[df_display[col_prov] == prov_sel]
    col_map = {
        "Grupo":"Grupo","Nombre del Insumo":"Insumo","Marca":"Marca","Proveedor":"Proveedor",
        "Alm":"Almacén","Barra":"Barra","Stock Neto Calculado":"Stock Total","Tara":"Tara",
        "Unidad de Medida":"Medida","Stock Mínimo":"Mínimo","Necesita Compra":"¿Comprar?",
        "Responsable":"Responsable","Fecha de Inventario":"Último Corte","Observaciones":"Observaciones",
    }
    cols_ok  = [c for c in col_map if c in df_display.columns]
    df_final = df_display[cols_ok].rename(columns=col_map)
    def highlight_low(row):
        total  = row.get("Stock Total",9999)
        minimo = row.get("Mínimo",0)
        color  = "background-color: rgba(255, 75, 75, 0.2)" if total < minimo else ""
        return [color] * len(row)
    st.dataframe(df_final.style.apply(highlight_low, axis=1), use_container_width=True, hide_index=True)
    st.divider()
    csv = df_final.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Descargar Reporte (CSV)", data=csv,
                       file_name=f"Inventario_{u_sel}_{ahora_hermosillo().strftime('%Y%m%d_%H%M')}.csv",
                       mime="text/csv", use_container_width=True)
