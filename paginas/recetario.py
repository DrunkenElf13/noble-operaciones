import streamlit as st
import pandas as pd
import time
from io import BytesIO
from data_loaders import cargar_recetas, cargar_costos_insumos, cargar_costos_actuales_recetas
from sheets import _asegurar_hoja_recetas_instrucciones, append_rows_con_retry, safe_worksheet, sh
from utils import limpiar_valor, ts_hermosillo
from config import COLS_RECETAS_INSTRUCCIONES
from components.avisos import mostrar_avisos
from auth import tiene_permiso


@st.cache_data(ttl=120)
def cargar_instrucciones():
    """Lee la hoja Recetas_Instrucciones y devuelve un diccionario receta -> instrucciones."""
    ws, err = _asegurar_hoja_recetas_instrucciones()
    if ws is None:
        return {}
    try:
        datos = ws.get_all_values()
        if len(datos) <= 1:
            return {}
        dicc = {}
        for fila in datos[1:]:
            if len(fila) >= 2:
                dicc[str(fila[0]).strip()] = str(fila[1])
        return dicc
    except Exception:
        return {}


def guardar_instruccion(nombre_receta, instrucciones):
    """Guarda o actualiza las instrucciones de una receta."""
    ws, err = _asegurar_hoja_recetas_instrucciones()
    if err:
        return False, err
    try:
        datos = ws.get_all_values()
        # Buscar si ya existe la receta
        for i, fila in enumerate(datos[1:], start=2):
            if len(fila) >= 1 and str(fila[0]).strip() == str(nombre_receta).strip():
                ws.update(range_name=f"B{i}", values=[[instrucciones]])
                return True, "Instrucciones actualizadas."
        # Si no existe, agregar
        ws.append_row([nombre_receta, instrucciones], value_input_option="USER_ENTERED")
        return True, "Instrucciones guardadas."
    except Exception as e:
        return False, str(e)


def generar_pdf_recetario(df_recetas, instrucciones):
    """Genera un PDF tamaño carta con el recetario."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from reportlab.lib.enums import TA_LEFT, TA_CENTER

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=2*cm,
        rightMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
    )
    styles = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle('Titulo', parent=styles['Heading1'], alignment=TA_CENTER, fontSize=18, spaceAfter=12)
    estilo_linea = ParagraphStyle('Linea', parent=styles['Heading2'], fontSize=14, spaceBefore=12, spaceAfter=8)
    estilo_receta = ParagraphStyle('Receta', parent=styles['Heading3'], fontSize=12, spaceBefore=8, spaceAfter=6)
    estilo_texto = ParagraphStyle('Texto', parent=styles['Normal'], fontSize=9, leading=12)
    estilo_sub = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=9, leading=12, textColor='#555555')

    flow = []
    flow.append(Paragraph("Recetario Noble", estilo_titulo))
    flow.append(Paragraph(f"Generado: {ts_hermosillo()}", estilo_sub))
    flow.append(Spacer(1, 0.5*cm))

    lineas = sorted(df_recetas["Linea"].dropna().unique().tolist())
    for linea in lineas:
        flow.append(Paragraph(f"▸ {linea}", estilo_linea))
        df_linea = df_recetas[df_recetas["Linea"] == linea]
        for _, receta_row in df_linea.iterrows():
            nombre = receta_row["Receta"]
            presentacion = str(receta_row.get("Presentacion", ""))
            rinde = receta_row.get("Rinde", 1)
            precio = limpiar_valor(receta_row.get("Precio_Venta", 0))
            costo_porcion = limpiar_valor(receta_row.get("Costo_Actual", 0))
            fc = limpiar_valor(receta_row.get("Food_Cost_Actual", 0))
            encabezado = f"• {nombre}"
            if presentacion:
                encabezado += f" ({presentacion})"
            flow.append(Paragraph(encabezado, estilo_receta))
            flow.append(Paragraph(
                f"Rinde: {rinde} porciones | Costo por porción: ${costo_porcion:,.2f} | Precio: ${precio:,.2f} | Food Cost: {fc:.1f}%",
                estilo_sub
            ))
            # Ingredientes
            df_rec = cargar_recetas()
            df_ing = df_rec[df_rec["Receta"] == nombre]
            if not df_ing.empty:
                flow.append(Paragraph("<b>Ingredientes:</b>", estilo_texto))
                for _, ing in df_ing.iterrows():
                    cant = limpiar_valor(ing.get("Cantidad", 0))
                    um = ing.get("Unidad_Medida", "")
                    comp = ing.get("Ingrediente", "")
                    flow.append(Paragraph(f"&nbsp;&nbsp;&nbsp;— {comp}: {cant} {um}", estilo_texto))
            # Instrucciones
            instru = instrucciones.get(nombre, "")
            if instru:
                flow.append(Paragraph("<b>Preparación:</b>", estilo_texto))
                for linea_txt in str(instru).split("\n"):
                    if linea_txt.strip():
                        flow.append(Paragraph(f"&nbsp;&nbsp;&nbsp;{linea_txt}", estilo_texto))
            flow.append(Spacer(1, 0.3*cm))

    doc.build(flow)
    buffer.seek(0)
    return buffer.read()


def show_recetario():
    if not tiene_permiso("Recetario"):
        st.error("No tienes permiso para esta página.")
        st.stop()

    st.title("📖 Recetario")
    mostrar_avisos("Recetario")

    if not st.session_state.auth_status:
        st.error("🔒 Autenticación requerida.")
        st.stop()

    df_costos_recetas = cargar_costos_actuales_recetas()
    df_rec = cargar_recetas()

    if df_costos_recetas.empty or df_rec.empty:
        st.warning("No hay recetas capturadas todavía. Ve a 'Base de Costos' → 'Recetas' para crear algunas.")
        st.stop()

    instrucciones = cargar_instrucciones()

    # -------------------- Filtros --------------------
    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        buscar = st.text_input("🔍 Buscar receta:", placeholder="Escribe el nombre...")
    with col_f2:
        lineas_disp = sorted(df_costos_recetas["Linea"].dropna().unique().tolist())
        filtro_linea = st.selectbox("Filtrar por línea:", ["Todas"] + lineas_disp)

    df_vista = df_costos_recetas.copy()
    if filtro_linea != "Todas":
        df_vista = df_vista[df_vista["Linea"] == filtro_linea]
    if buscar:
        df_vista = df_vista[df_vista["Receta"].astype(str).str.contains(buscar, case=False, na=False)]

    # -------------------- Métricas generales --------------------
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Recetas mostradas", len(df_vista))
    if not df_vista.empty:
        m2.metric("Precio promedio", f"${df_vista['Precio_Venta'].mean():,.2f}")
        m3.metric("Food Cost promedio", f"{df_vista['Food_Cost_Actual'].mean():.1f}%")
        m4.metric("Margen promedio", f"${df_vista['Margen_Actual'].mean():,.2f}")
    else:
        m2.metric("Precio promedio", "$0.00")
        m3.metric("Food Cost promedio", "0.0%")
        m4.metric("Margen promedio", "$0.00")

    st.divider()

    # -------------------- Vista por línea --------------------
    if df_vista.empty:
        st.info("No hay recetas que coincidan con los filtros.")
    else:
        lineas_mostrar = sorted(df_vista["Linea"].dropna().unique().tolist()) if filtro_linea == "Todas" else [filtro_linea]
        for linea in lineas_mostrar:
            df_linea = df_vista[df_vista["Linea"] == linea]
            if df_linea.empty:
                continue
            st.subheader(f"▸ {linea}")
            for _, receta_row in df_linea.iterrows():
                nombre = receta_row["Receta"]
                presentacion = str(receta_row.get("Presentacion", ""))
                rinde = receta_row.get("Rinde", 1)
                precio = limpiar_valor(receta_row.get("Precio_Venta", 0))
                costo_porcion = limpiar_valor(receta_row.get("Costo_Actual", 0))
                fc = limpiar_valor(receta_row.get("Food_Cost_Actual", 0))
                margen = limpiar_valor(receta_row.get("Margen_Actual", 0))
                factor = limpiar_valor(receta_row.get("Factor_Actual", 0))

                with st.container():
                    titulo = f"**{nombre}**"
                    if presentacion:
                        titulo += f" — {presentacion}"
                    st.markdown(titulo)

                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("Rinde", f"{rinde} porc.")
                    c2.metric("Costo/porción", f"${costo_porcion:,.2f}")
                    c3.metric("Precio", f"${precio:,.2f}")
                    c4.metric("Food Cost", f"{fc:.1f}%")
                    c5.metric("Margen", f"${margen:,.2f}")

                    with st.expander("Ver ingredientes e instrucciones", expanded=False):
                        df_ing = df_rec[df_rec["Receta"] == nombre]
                        if not df_ing.empty:
                            st.write("**Ingredientes:**")
                            filas_ing = []
                            for _, ing in df_ing.iterrows():
                                filas_ing.append({
                                    "Componente": ing.get("Ingrediente", ""),
                                    "Tipo": ing.get("Tipo_Componente", "Insumo"),
                                    "Cantidad": limpiar_valor(ing.get("Cantidad", 0)),
                                    "Unidad": ing.get("Unidad_Medida", ""),
                                })
                            st.dataframe(pd.DataFrame(filas_ing), hide_index=True, width="stretch")

                        st.write("**Instrucciones de preparación:**")
                        instruccion_actual = instrucciones.get(nombre, "")
                        texto_instruccion = st.text_area(
                            f"Editar instrucciones para '{nombre}':",
                            value=instruccion_actual,
                            height=120,
                            key=f"instru_{nombre}"
                        )
                        if st.button("💾 Guardar instrucciones", key=f"btn_instru_{nombre}"):
                            ok, msg = guardar_instruccion(nombre, texto_instruccion)
                            if ok:
                                st.success(msg)
                                cargar_instrucciones.clear()
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error(msg)
                st.divider()

    # -------------------- Descargar PDF --------------------
    st.divider()
    st.subheader("📥 Descargar recetario en PDF")
    if st.button("Generar PDF del recetario filtrado", type="primary", width="stretch"):
        try:
            pdf_bytes = generar_pdf_recetario(df_vista, instrucciones)
            st.download_button(
                label="📄 Descargar PDF",
                data=pdf_bytes,
                file_name=f"recetario_noble_{ts_hermosillo().replace(' ', '_').replace(':', '')}.pdf",
                mime="application/pdf",
                width="stretch"
            )
        except Exception as e:
            st.error(f"Error al generar PDF: {e}")
