import streamlit as st
import io
import base64
from data_loaders import cargar_datos_integrales
from utils import ahora_hermosillo
from config import UNIDADES
from auth import tiene_permiso

# La función generar_pdf_58mm es demasiado larga para duplicar; la colocamos en utils o en un módulo aparte.
# Para simplificar, la definimos aquí (es un helper estático).
def generar_pdf_58mm(titulo: str, lineas: list) -> bytes:
    from reportlab.lib.pagesizes import landscape
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.units import mm
    ANCHO_MM   = 58
    MARGEN_MM  = 3
    LINEA_H_MM = 4.2
    FUENTE_NORMAL = 7.5
    FUENTE_BOLD   = 8
    FUENTE_SMALL  = 6.5
    alto_mm  = max(20 + len(lineas) * LINEA_H_MM + 10, 40)
    ancho_pts = ANCHO_MM * mm
    alto_pts  = alto_mm  * mm
    margen_pts = MARGEN_MM * mm
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(ancho_pts, alto_pts))
    y = alto_pts - (5 * mm)
    for linea in lineas:
        texto, estilo = linea if isinstance(linea, tuple) else (linea, 'normal')
        if estilo == 'divider':
            c.setFont("Courier", FUENTE_SMALL)
            c.drawString(margen_pts, y, "-" * 30)
        elif estilo == 'bold':
            c.setFont("Courier-Bold", FUENTE_BOLD)
            c.drawString(margen_pts, y, str(texto)[:int((ANCHO_MM - MARGEN_MM*2)/(FUENTE_NORMAL*0.6))])
        elif estilo == 'small':
            c.setFont("Courier", FUENTE_SMALL)
            c.drawString(margen_pts, y, str(texto)[:int((ANCHO_MM - MARGEN_MM*2)/(FUENTE_NORMAL*0.6))])
        elif estilo == 'title':
            c.setFont("Courier-Bold", FUENTE_BOLD + 1)
            c.drawString(margen_pts, y, str(texto)[:int((ANCHO_MM - MARGEN_MM*2)/(FUENTE_NORMAL*0.6))])
        else:
            c.setFont("Courier", FUENTE_NORMAL)
            c.drawString(margen_pts, y, str(texto)[:int((ANCHO_MM - MARGEN_MM*2)/(FUENTE_NORMAL*0.6))])
        y -= LINEA_H_MM * mm
        if y < (5 * mm):
            c.showPage()
            y = alto_pts - (5 * mm)
    c.save()
    buf.seek(0)
    return buf.read()

def show_impresion():
    if not tiene_permiso("Impresion"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    df_raw, _ = cargar_datos_integrales()
    st.title("🖨️ Ticket de Conteo (58mm)")
    u_sel = st.selectbox("Sucursal:", UNIDADES)
    df_u  = df_raw[df_raw["Unidad de Negocio"] == u_sel] if not df_raw.empty else pd.DataFrame()
    grps  = sorted(df_u["Grupo"].dropna().unique().tolist()) if not df_u.empty and "Grupo" in df_u.columns else []
    g_sel = st.multiselect("Filtrar por Grupos:", grps)
    if g_sel and not df_u.empty:
        df_p = df_u[df_u["Grupo"].isin(g_sel)].sort_values(["Grupo","Nombre del Insumo"])
        lineas_pdf = [
            (f"* CONTEO {u_sel.upper()} *", "title"),
            (f"Fecha: {ahora_hermosillo().strftime('%d/%m/%Y')}", "small"),
            ("", "divider"),
        ]
        gr_actual = ""
        for _, r in df_p.iterrows():
            grupo = str(r.get("Grupo",""))
            if grupo != gr_actual:
                lineas_pdf.append((f">> GRUPO {grupo} <<", "bold"))
                gr_actual = grupo
            lineas_pdf.append((f"{str(r['Nombre del Insumo'])[:22]}  ________", "normal"))
        with st.expander("👁️ Vista previa del contenido", expanded=True):
            prev_txt = f"{'='*28}\n* CONTEO {u_sel.upper()} *\nFecha: {ahora_hermosillo().strftime('%d/%m/%Y')}\n{'-'*28}\n"
            gr_actual_p = ""
            for _, r in df_p.iterrows():
                grupo = str(r.get("Grupo",""))
                if grupo != gr_actual_p:
                    prev_txt += f"\n>> GRUPO {grupo} <<\n"
                    gr_actual_p = grupo
                prev_txt += f" {str(r['Nombre del Insumo'])[:22]}  ________\n"
            st.code(prev_txt, language=None)
        pdf_bytes = generar_pdf_58mm(f"Conteo {u_sel}", lineas_pdf)
        # Botón para abrir en nueva pestaña (sin descargar)
        b64_pdf = base64.b64encode(pdf_bytes).decode()
        st.markdown(
            f'<a href="data:application/pdf;base64,{b64_pdf}" target="_blank">'
            f'<button style="width:100%;padding:8px;border-radius:4px;border:1px solid #ccc;background:#f0f0f0;cursor:pointer;">'
            f'🖨️ Abrir para imprimir</button></a>',
            unsafe_allow_html=True
        )
        st.download_button(
            label="📄 Descargar PDF 58mm", data=pdf_bytes,
            file_name=f"conteo_{u_sel.replace(' ','_')}_{ahora_hermosillo().strftime('%Y%m%d_%H%M')}.pdf",
            mime="application/pdf", width="stretch", type="primary"
        )
    else:
        st.info("Selecciona grupos para generar la lista.")
