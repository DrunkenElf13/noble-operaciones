import streamlit as st
from data_loaders import cargar_datos_integrales
from inventario import obtener_ultimo_inventario
from utils import ahora_hermosillo
from config import UNIDADES
from auth import tiene_permiso

def show_lista_compra():
    if not tiene_permiso("ListaCompra"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    _, df_historial = cargar_datos_integrales()
    st.title("🛒 Lista de Compra")
    u_opcion = st.selectbox("Filtrar por unidad:", ["Todas"] + UNIDADES)
    if u_opcion == "Todas":
        df_actual = obtener_ultimo_inventario(df_historial)
    else:
        df_actual = obtener_ultimo_inventario(df_historial, u_opcion)
    if df_actual.empty:
        st.info("Sin registros para armar la lista de compra.")
        st.stop()
    com = df_actual[df_actual["Necesita Compra"] == True].copy()
    if not com.empty:
        st.subheader("📋 Insumos con necesidad de compra")
        cols_compra = ["Unidad de Negocio","Nombre del Insumo","Marca","Proveedor","Grupo",
                       "Presentación de Compra","Unidad de Medida","Stock Neto Calculado",
                       "Stock Mínimo","Necesita Compra","Responsable","Fecha de Inventario","Observaciones"]
        cols_compra_ok = [c for c in cols_compra if c in com.columns]
        st.dataframe(com[cols_compra_ok].sort_values(["Unidad de Negocio","Grupo"]),
                     width="stretch", hide_index=True)
        with st.expander("🖨️ Descargar PDF (58mm)"):
            lineas_pdf = [
                (f"* COMPRAS {u_opcion.upper() if u_opcion!='Todas' else 'GLOBAL'} *", "title"),
                (f"Fecha: {ahora_hermosillo().strftime('%d/%m/%Y')}", "small"),
                ("", "divider"),
            ]
            for _, r in com.iterrows():
                lineas_pdf.append((f"* {str(r['Nombre del Insumo'])[:22]}", "bold"))
                lineas_pdf.append((f"  Stock:{r['Stock Neto Calculado']} Min:{r['Stock Mínimo']}", "small"))
                lineas_pdf.append(("", "divider"))
            prev_txt = f"{'='*28}\n* COMPRAS {u_opcion.upper() if u_opcion!='Todas' else 'GLOBAL'} *\nFecha: {ahora_hermosillo().strftime('%d/%m/%Y')}\n{'-'*28}\n"
            for _, r in com.iterrows():
                prev_txt += f"• {str(r['Nombre del Insumo'])[:22]}\n  Stock: {r['Stock Neto Calculado']} / Min: {r['Stock Mínimo']}\n{'-'*28}\n"
            st.code(prev_txt, language=None)
            from paginas.impresion import generar_pdf_58mm
            pdf_bytes = generar_pdf_58mm(f"Compras {u_opcion}", lineas_pdf)
            st.download_button(
                label="📄 Descargar PDF 58mm", data=pdf_bytes,
                file_name=f"compras_{u_opcion.replace(' ','_')}_{ahora_hermosillo().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf", width="stretch", type="primary"
            )
    else:
        st.success("No hay alertas de reabastecimiento activas.")
