import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
from io import StringIO
from data_loaders import cargar_costos_insumos, cargar_datos_integrales
from sheets import _asegurar_hoja_costos_insumos, append_rows_con_retry
from utils import limpiar_valor, ts_hermosillo
from config import UNIDADES_MED
from auth import tiene_permiso

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
    try:
        root = ET.fromstring(contenido_xml)
        ns = {"cfdi": "http://www.sat.gob.mx/cfd/4"}

        proveedor = ""
        emisor = root.find(".//cfdi:Emisor", ns)
        if emisor is not None:
            proveedor = emisor.get("Nombre", "")

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

            # Total neto real pagado (incluye IVA si aplica)
            total_neto_real = importe - descuento + iva_importe

            conceptos.append({
                "Descripcion": descripcion,
                "Cantidad_Comprada": cantidad,
                "ClaveUnidad": clave_unidad,
                "Unidad_XML": unidad_xml,
                "ValorUnitario": valor_unitario,
                "Importe_Total": importe,
                "Descuento": descuento,
                "Total_Neto_Real": total_neto_real,
                "IVA_Tasa": iva_tasa,
                "IVA_Importe": iva_importe,
                "Proveedor": proveedor,
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
    Puedes **subir archivos XML** o **pegar el contenido XML**.  
    El sistema calculará el **costo real pagado (con IVA cuando aplique)**.  
    Podrás revisar y corregir todos los campos antes de guardar.
    """)

    df_cat = cargar_datos_integrales()[0]
    if df_cat.empty:
        st.warning("No hay insumos activos en el catálogo. Agrega insumos antes de cargar facturas.")
        st.stop()

    if "xml_df_edit" not in st.session_state:
        st.session_state.xml_df_edit = None

    metodo = st.radio("Elige cómo cargar el XML:", ["📁 Subir archivo(s)", "📋 Pegar contenido XML"], horizontal=True)

    if metodo == "📁 Subir archivo(s)":
        archivos = st.file_uploader("Selecciona archivos XML", type=["xml"], accept_multiple_files=True)
        if archivos:
            conceptos_totales = []
            for archivo in archivos:
                contenido = archivo.getvalue().decode("utf-8")
                conceptos, error = parsear_contenido_xml(contenido)
                if error:
                    st.error(f"Error al leer {archivo.name}: {error}")
                    continue
                conceptos_totales.extend(conceptos)

            if conceptos_totales:
                df_conceptos = pd.DataFrame(conceptos_totales)
                insumos_disponibles = sorted(df_cat["Nombre del Insumo"].dropna().unique())

                df_edit = df_conceptos.copy()
                df_edit["Insumo"] = ""
                df_edit["Marca"] = ""
                df_edit["Unidad_Medida"] = df_edit["ClaveUnidad"].map(MAPA_UNIDADES_SAT).fillna("pieza")
                df_edit["Presentacion"] = df_edit["Cantidad_Comprada"]
                df_edit["Costo_Presentacion"] = df_edit["Total_Neto_Real"] / df_edit["Cantidad_Comprada"]
                df_edit["Costo_Unitario"] = df_edit["Costo_Presentacion"] / df_edit["Presentacion"]
                df_edit["Unidad_Base"] = df_edit["Unidad_Medida"]
                df_edit["Contenido_Base_por_Unidad"] = 1.0
                df_edit["Costo_Base_Unitario"] = df_edit["Costo_Unitario"] / df_edit["Contenido_Base_por_Unidad"]

                st.session_state.xml_df_edit = df_edit
                st.success(f"Se cargaron {len(df_edit)} conceptos.")
        else:
            st.info("Sube al menos un archivo XML para continuar.")

    else:
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
                    df_conceptos = pd.DataFrame(conceptos)
                    insumos_disponibles = sorted(df_cat["Nombre del Insumo"].dropna().unique())

                    df_edit = df_conceptos.copy()
                    df_edit["Insumo"] = ""
                    df_edit["Marca"] = ""
                    df_edit["Unidad_Medida"] = df_edit["ClaveUnidad"].map(MAPA_UNIDADES_SAT).fillna("pieza")
                    df_edit["Presentacion"] = df_edit["Cantidad_Comprada"]
                    df_edit["Costo_Presentacion"] = df_edit["Total_Neto_Real"] / df_edit["Cantidad_Comprada"]
                    df_edit["Costo_Unitario"] = df_edit["Costo_Presentacion"] / df_edit["Presentacion"]
                    df_edit["Unidad_Base"] = df_edit["Unidad_Medida"]
                    df_edit["Contenido_Base_por_Unidad"] = 1.0
                    df_edit["Costo_Base_Unitario"] = df_edit["Costo_Unitario"] / df_edit["Contenido_Base_por_Unidad"]

                    st.session_state.xml_df_edit = df_edit
                    st.success(f"Se leyeron {len(df_edit)} conceptos del XML pegado.")
                    st.rerun()
            else:
                st.warning("Pega el contenido XML antes de procesar.")

    if st.session_state.xml_df_edit is not None:
        df_edit = st.session_state.xml_df_edit
        insumos_disponibles = sorted(df_cat["Nombre del Insumo"].dropna().unique())

        # Columnas en orden lógico para pantallas pequeñas
        columnas_visibles = [
            "Descripcion", "Insumo", "Marca", "Proveedor",
            "Cantidad_Comprada", "Total_Neto_Real", "IVA_Importe",
            "Unidad_Medida", "Presentacion", "Costo_Presentacion",
            "Costo_Unitario", "Unidad_Base", "Contenido_Base_por_Unidad",
            "Costo_Base_Unitario"
        ]
        df_edit = df_edit[columnas_visibles]

        st.subheader("Asignación y ajuste de conceptos")
        st.caption("Desplázate horizontalmente si es necesario.")

        edited_df = st.data_editor(
            df_edit,
            column_config={
                "Descripcion": st.column_config.TextColumn("Descripción", disabled=True),
                "Insumo": st.column_config.SelectboxColumn(
                    "Insumo",
                    options=[""] + insumos_disponibles,
                    required=True
                ),
                "Marca": st.column_config.TextColumn("Marca"),
                "Proveedor": st.column_config.TextColumn("Proveedor"),
                "Cantidad_Comprada": st.column_config.NumberColumn("Cantidad", disabled=True, format="%.2f"),
                "Total_Neto_Real": st.column_config.NumberColumn("Total Pagado", disabled=True, format="%.2f"),
                "IVA_Importe": st.column_config.NumberColumn("IVA", disabled=True, format="%.2f"),
                "Unidad_Medida": st.column_config.SelectboxColumn(
                    "Unidad Inv.",
                    options=UNIDADES_MED,
                    help="Unidad de inventario"
                ),
                "Presentacion": st.column_config.NumberColumn(
                    "Presentación",
                    min_value=0.0,
                    step=1.0,
                    format="%.2f"
                ),
                "Costo_Presentacion": st.column_config.NumberColumn(
                    "Costo Pres. ($)",
                    min_value=0.0,
                    step=0.5,
                    format="%.2f"
                ),
                "Costo_Unitario": st.column_config.NumberColumn(
                    "Costo Unit. ($)",
                    min_value=0.0,
                    step=0.001,
                    format="%.4f"
                ),
                "Unidad_Base": st.column_config.SelectboxColumn(
                    "Unidad Base",
                    options=UNIDADES_MED,
                    help="Unidad para recetas"
                ),
                "Contenido_Base_por_Unidad": st.column_config.NumberColumn(
                    "Cont. Base",
                    min_value=0.0,
                    step=1.0,
                    format="%.2f"
                ),
                "Costo_Base_Unitario": st.column_config.NumberColumn(
                    "Costo Base ($)",
                    min_value=0.0,
                    step=0.0001,
                    format="%.6f"
                ),
            },
            hide_index=True,
            width="stretch",
            key="xml_editor"
        )

        st.session_state.xml_df_edit = edited_df

        if st.button("🔄 Recalcular derivados"):
            for idx in edited_df.index:
                pres = edited_df.at[idx, "Presentacion"]
                costo_pres = edited_df.at[idx, "Costo_Presentacion"]
                contenido = edited_df.at[idx, "Contenido_Base_por_Unidad"]
                if pres > 0:
                    edited_df.at[idx, "Costo_Unitario"] = round(costo_pres / pres, 4)
                else:
                    edited_df.at[idx, "Costo_Unitario"] = 0.0
                if contenido > 0 and edited_df.at[idx, "Costo_Unitario"] > 0:
                    edited_df.at[idx, "Costo_Base_Unitario"] = round(edited_df.at[idx, "Costo_Unitario"] / contenido, 6)
                else:
                    edited_df.at[idx, "Costo_Base_Unitario"] = 0.0
            st.session_state.xml_df_edit = edited_df
            st.success("Costos derivados recalculados.")
            st.rerun()

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
                            row.get("Marca", ""),
                            row.get("Proveedor", ""),
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
                        st.session_state.xml_df_edit = None
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(msg)
