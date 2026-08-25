import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
from io import StringIO
from data_loaders import cargar_costos_insumos, cargar_datos_integrales
from sheets import _asegurar_hoja_costos_insumos, append_rows_con_retry
from utils import limpiar_valor, ts_hermosillo
from config import UNIDADES_MED
from auth import tiene_permiso

# Mapeo de ClaveUnidad SAT a unidades del sistema
MAPA_UNIDADES_SAT = {
    "H87": "pieza",
    "XPK": "paquete",
    "KGM": "kg",
    "LTR": "lt",
    "XBX": "paquete",
    "BB": "paquete",
    "GRM": "gr",
    "MLT": "ml",
}

def parsear_contenido_xml(contenido_xml: str):
    """Parsea un string con contenido XML y extrae conceptos."""
    try:
        root = ET.fromstring(contenido_xml)
        ns = {"cfdi": "http://www.sat.gob.mx/cfd/4"}
        conceptos = []
        for concepto in root.findall(".//cfdi:Concepto", ns):
            descripcion = concepto.get("Descripcion", "")
            cantidad = float(concepto.get("Cantidad", "0"))
            clave_unidad = concepto.get("ClaveUnidad", "")
            unidad_xml = concepto.get("Unidad", "")
            valor_unitario = float(concepto.get("ValorUnitario", "0"))
            importe = float(concepto.get("Importe", "0"))
            descuento = float(concepto.get("Descuento", "0"))
            iva_tasa = 0.0
            iva_importe = 0.0
            for traslado in concepto.findall(".//cfdi:Traslado", ns):
                impuesto = traslado.get("Impuesto", "")
                if impuesto == "002":
                    tasa = float(traslado.get("TasaOCuota", "0"))
                    iva_tasa = max(iva_tasa, tasa)
                    iva_importe += float(traslado.get("Importe", "0"))
            conceptos.append({
                "Descripcion": descripcion,
                "Cantidad_Comprada": cantidad,
                "ClaveUnidad": clave_unidad,
                "Unidad_XML": unidad_xml,
                "ValorUnitario": valor_unitario,
                "Importe_Total": importe,
                "Descuento": descuento,
                "IVA_Tasa": iva_tasa,
                "IVA_Importe": iva_importe,
            })
        return conceptos, None
    except Exception as e:
        return None, str(e)

def show_carga_xml():
    if not tiene_permiso("BaseCostos"):
        st.error("No tienes permiso para esta página.")
        st.stop()

    st.title("📄 Carga de Facturas XML")
    st.markdown("""
    Puedes **subir archivos XML** o **pegar el contenido XML** directamente.  
    El sistema extraerá los conceptos y podrás revisar/modificar todos los campos antes de guardar.
    """)

    df_cat = cargar_datos_integrales()[0]
    if df_cat.empty:
        st.warning("No hay insumos activos en el catálogo. Agrega insumos antes de cargar facturas.")
        st.stop()

    # Método de entrada
    metodo = st.radio("Elige cómo cargar el XML:", ["📁 Subir archivo(s)", "📋 Pegar contenido XML"])

    conceptos_totales = []

    if metodo == "📁 Subir archivo(s)":
        archivos = st.file_uploader("Selecciona archivos XML", type=["xml"], accept_multiple_files=True)
        if archivos:
            for archivo in archivos:
                # Leer contenido del archivo y parsear
                contenido = archivo.getvalue().decode("utf-8")
                conceptos, error = parsear_contenido_xml(contenido)
                if error:
                    st.error(f"Error al leer {archivo.name}: {error}")
                    continue
                conceptos_totales.extend(conceptos)

    else:  # Pegar contenido XML
        texto_xml = st.text_area(
            "Pega aquí el contenido del XML:",
            height=300,
            placeholder="<cfdi:Comprobante ...>"
        )
        if st.button("🔍 Procesar XML pegado"):
            if texto_xml.strip():
                conceptos, error = parsear_contenido_xml(texto_xml.strip())
                if error:
                    st.error(f"Error al parsear el XML pegado: {error}")
                else:
                    conceptos_totales = conceptos
                    st.success(f"Se leyeron {len(conceptos)} conceptos del XML pegado.")
            else:
                st.warning("Pega el contenido XML antes de procesar.")

    if conceptos_totales:
        st.success(f"Se cargaron {len(conceptos_totales)} conceptos en total.")
        df_conceptos = pd.DataFrame(conceptos_totales)

        insumos_disponibles = sorted(df_cat["Nombre del Insumo"].dropna().unique())

        # Preparar DataFrame editable
        df_edit = df_conceptos.copy()
        df_edit["Insumo"] = ""
        df_edit["Unidad_Medida"] = df_edit["ClaveUnidad"].map(MAPA_UNIDADES_SAT).fillna("pieza")
        df_edit["Presentacion"] = 1.0
        df_edit["Costo_Presentacion"] = (df_edit["Importe_Total"] - df_edit["Descuento"]) / df_edit["Cantidad_Comprada"]
        df_edit["Costo_Unitario"] = df_edit["Costo_Presentacion"] / df_edit["Presentacion"]
        df_edit["Unidad_Base"] = df_edit["Unidad_Medida"]
        df_edit["Contenido_Base_por_Unidad"] = 1.0
        df_edit["Costo_Base_Unitario"] = df_edit["Costo_Unitario"] / df_edit["Contenido_Base_por_Unidad"]

        st.subheader("Asignación y ajuste de conceptos")
        edited_df = st.data_editor(
            df_edit,
            column_config={
                "Descripcion": st.column_config.TextColumn("Descripción", disabled=True),
                "Cantidad_Comprada": st.column_config.NumberColumn("Cantidad Comprada", disabled=True, format="%.2f"),
                "Unidad_XML": st.column_config.TextColumn("Unidad XML", disabled=True),
                "Importe_Total": st.column_config.NumberColumn("Importe Total", disabled=True, format="%.2f"),
                "Descuento": st.column_config.NumberColumn("Descuento", disabled=True, format="%.2f"),
                "Insumo": st.column_config.SelectboxColumn(
                    "Insumo",
                    options=[""] + insumos_disponibles,
                    required=True
                ),
                "Unidad_Medida": st.column_config.SelectboxColumn(
                    "Unidad Medida (Inventario)",
                    options=UNIDADES_MED,
                    help="Unidad en la que controlas el inventario de este insumo."
                ),
                "Presentacion": st.column_config.NumberColumn(
                    "Presentación",
                    min_value=0.0,
                    step=1.0,
                    help="Cantidad de unidades de inventario que contiene una presentación."
                ),
                "Costo_Presentacion": st.column_config.NumberColumn(
                    "Costo Presentación ($)",
                    min_value=0.0,
                    step=0.5,
                    format="%.2f"
                ),
                "Costo_Unitario": st.column_config.NumberColumn(
                    "Costo Unitario ($)",
                    min_value=0.0,
                    step=0.001,
                    format="%.4f"
                ),
                "Unidad_Base": st.column_config.SelectboxColumn(
                    "Unidad Base (Recetas)",
                    options=UNIDADES_MED,
                    help="Unidad que usarás en recetas (ml, gr, pieza, etc.)."
                ),
                "Contenido_Base_por_Unidad": st.column_config.NumberColumn(
                    "Contenido Base por Unidad",
                    min_value=0.0,
                    step=1.0,
                    help="Cuántas unidades base contiene 1 unidad de inventario."
                ),
                "Costo_Base_Unitario": st.column_config.NumberColumn(
                    "Costo Base Unitario ($)",
                    min_value=0.0,
                    step=0.0001,
                    format="%.6f"
                ),
            },
            hide_index=True,
            width="stretch",
            key="xml_editor"
        )

        if st.button("💾 Guardar costos en CostosInsumos", type="primary", width="stretch"):
            filas_validas = edited_df[edited_df["Insumo"] != ""]
            if filas_validas.empty:
                st.error("Selecciona al menos un insumo.")
            else:
                ws_costos, err = _asegurar_hoja_costos_insumos()
                if err:
                    st.error(err)
                else:
                    filas_guardar = []
                    for _, row in filas_validas.iterrows():
                        if row["Unidad_Base"] != row["Unidad_Medida"] and row["Contenido_Base_por_Unidad"] <= 0:
                            st.error(f"Contenido base inválido para {row['Insumo']}.")
                            st.stop()

                        if row["Costo_Unitario"] <= 0 and row["Costo_Presentacion"] > 0 and row["Presentacion"] > 0:
                            row["Costo_Unitario"] = round(row["Costo_Presentacion"] / row["Presentacion"], 4)
                        if row["Costo_Base_Unitario"] <= 0 and row["Costo_Unitario"] > 0 and row["Contenido_Base_por_Unidad"] > 0:
                            row["Costo_Base_Unitario"] = round(row["Costo_Unitario"] / row["Contenido_Base_por_Unidad"], 6)

                        filas_guardar.append([
                            row["Insumo"],
                            "",
                            "",
                            row["Unidad_Medida"],
                            row["Presentacion"],
                            row["Costo_Presentacion"],
                            row["Costo_Unitario"],
                            f"$/{row['Unidad_Medida']}",
                            row["Unidad_Base"],
                            row["Contenido_Base_por_Unidad"],
                            row["Costo_Base_Unitario"],
                            ts_hermosillo(),
                            st.session_state.current_user
                        ])
                    ok, msg = append_rows_con_retry(ws_costos, filas_guardar)
                    if ok:
                        cargar_costos_insumos.clear()
                        st.success(f"✅ {len(filas_guardar)} costos guardados con historial.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(msg)
