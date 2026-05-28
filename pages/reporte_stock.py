import streamlit as st
from data_loaders import cargar_datos_integrales
from inventario import obtener_ultimo_inventario
from utils import ahora_hermosillo
from config import UNIDADES
from auth import tiene_permiso

def show_reporte_stock():
    if not tiene_permiso("ReporteStock"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    _, df_historial = cargar_datos_integrales()
    st.title("📦 Reporte de Stock (58mm)")
    u_sel     = st.radio("Generar reporte para:", UNIDADES, horizontal=True)
    df_actual = obtener_ultimo_inventario(df_historial, u_sel)
    if df_actual.empty:
        st.warning("Sin registros para generar el reporte.")
        st.stop()
    df_rep = df_actual.sort_values(["Grupo","Nombre del Insumo"])
    lineas_pdf = [
        (f"* INVENTARIO {u_sel.upper()} *", "title"),
        (ahora_hermosillo().strftime('%d/%m/%Y %H:%M'), "small"),
        ("", "divider"),
    ]
    gr_actual = ""
    for _, r in df_rep.iterrows():
        grupo = str(r.get("Grupo",""))
        if grupo != gr_actual:
            lineas_pdf.append((f">> GRUPO {grupo} <<", "bold"))
            gr_actual = grupo
        lineas_pdf.append((str(r['Nombre del Insumo'])[:20], "normal"))
        lineas_pdf.append((f" Alm:{r['Alm']} Bar:{r['Barra']} Tot:{r['Stock Neto Calculado']}", "small"))
    lineas_pdf.append(("", "divider"))
    with st.expander("👁️ Vista previa del contenido", expanded=True):
        prev_txt = f"{'='*28}\n* INVENTARIO {u_sel.upper()} *\n{ahora_hermosillo().strftime('%d/%m/%Y %H:%M')}\n{'-'*28}\n"
        gr_actual_p = ""
        for _, r in df_rep.iterrows():
            grupo = str(r.get("Grupo",""))
            if grupo != gr_actual_p:
                prev_txt += f"\n>> GRUPO {grupo} <<\n"
                gr_actual_p = grupo
            prev_txt += f"{str(r['Nombre del Insumo'])[:20]}\n Alm:{r['Alm']} Bar:{r['Barra']} Total:{r['Stock Neto Calculado']}\n"
        prev_txt += "-" * 28 + "\n"
        st.code(prev_txt, language=None)
    from pages.impresion import generar_pdf_58mm
    pdf_bytes = generar_pdf_58mm(f"Stock {u_sel}", lineas_pdf)
    st.download_button(
        label="📄 Descargar PDF 58mm", data=pdf_bytes,
        file_name=f"stock_{u_sel.replace(' ','_')}_{ahora_hermosillo().strftime('%Y%m%d_%H%M')}.pdf",
        mime="application/pdf", use_container_width=True, type="primary"
    )
