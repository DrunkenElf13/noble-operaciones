import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
from io import StringIO
from data_loaders import cargar_costos_insumos, cargar_datos_integrales
from sheets import _asegurar_hoja_costos_insumos, _asegurar_hoja_mapeo_xml, append_rows_con_retry
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
    "XUN": "unidad",
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
            no_identificacion = concepto.get("NoIdentificacion", "")

            iva_tasa = 0.0
            iva_importe = 0.0
            for traslado in concepto.findall(".//cfdi:Traslado", ns):
                impuesto = traslado.get("Impuesto", "")
                if impuesto == "002":
                    tasa = float(traslado.get("TasaOCuota", "0"))
                    iva_tasa = max(iva_tasa, tasa)
                    iva_importe += float(traslado.get("Importe", "0"))

            total_neto_real = importe - descuento + iva_importe

            conceptos.append({
                "Descripcion": descripcion,
                "NoIdentificacion": no_identificacion,
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

def preparar_dataframe_con_mapeo(df_conceptos, df_mapeo, df_cat):
    """Prepara el DataFrame editable, autocompletando con MapeoXML."""
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
    df_edit["Costo_Base_Unitario"] = df_edit["Costo_Unitario"]
    df_edit["Guardar_Regla"] = True

    # Autocompletar desde MapeoXML
    if not df_mapeo.empty:
        for idx, row in df_edit.iterrows():
            desc = row["Descripcion"].upper()
            proveedor_factura = row["Proveedor"].strip().upper()
            no_id = row["NoIdentificacion"].strip().upper()

            # 1) Intento por NoIdentificacion + Proveedor
            coincidencia = None
            if no_id:
                mascara = (
                    (df_mapeo["NoIdentificacion"].str.upper() == no_id) &
                    (df_mapeo["Proveedor"].str.upper() == proveedor_factura)
                )
                if mascara.any():
                    coincidencia = df_mapeo[mascara].iloc[0]

            # 2) Intento por texto buscado
            if coincidencia is None:
                mascara_texto = df_mapeo["Texto_Buscado"].apply(lambda x: x.upper() in desc)
                if mascara_texto.any():
                    coincidencia = df_mapeo[mascara_texto].iloc[0]

            if coincidencia is not None:
                df_edit.at[idx, "Insumo"] = coincidencia["Insumo"]
                df_edit.at[idx, "Marca"] = coincidencia.get("Marca", "")
                df_edit.at[idx, "Unidad_Medida"] = coincidencia.get("Unidad_Medida", row["Unidad_Medida"])
                df_edit.at[idx, "Presentacion"] = float(coincidencia.get("Presentacion", row["Presentacion"]))
                df_edit.at[idx, "Unidad_Base"] = coincidencia.get("Unidad_Base", row["Unidad_Base"])
                df_edit.at[idx, "Contenido_Base_por_Unidad"] = float(coincidencia.get("Contenido_Base_por_Unidad", 1.0))
                df_edit.at[idx, "Costo_Unitario"] = df_edit.at[idx, "Costo_Presentacion"] / df_edit.at[idx, "Presentacion"]
                df_edit.at[idx, "Costo_Base_Unitario"] = df_edit.at[idx, "Costo_Unitario"] / df_edit.at[idx, "Contenido_Base_por_Unidad"]
                df_edit.at[idx, "Guardar_Regla"] = False  # ya existe regla

    # Reordenar columnas para visualización
    columnas_orden = [
        "Descripcion", "NoIdentificacion", "Insumo", "Marca", "Proveedor",
        "Cantidad_Comprada", "Total_Neto_Real", "IVA_Importe",
        "Unidad_Medida", "Presentacion", "Costo_Presentacion",
        "Costo_Unitario", "Unidad_Base", "Contenido_Base_por_Unidad",
        "Costo_Base_Unitario", "Guardar_Regla"
    ]
    return df_edit[columnas_orden]

def show_carga_xml():
    if not tiene_permiso("BaseCostos"):
        st.error("No tienes permiso para esta página.")
        st.stop()

    st.title("📄 Carga de Facturas XML")
    st.markdown("""
    Puedes **subir archivos XML** o **pegar el contenido XML**.  
    El sistema **recordará** las asignaciones previas para autocompletar futuras cargas.
    """)

    df_cat = cargar_datos_integrales()[0]
    if df_cat.empty:
        st.warning("No hay insumos activos en el catálogo. Agrega insumos antes de cargar facturas.")
        st.stop()

    # Cargar hoja MapeoXML
    ws_mapeo, err_mapeo = _asegurar_hoja_mapeo_xml()
    if err_mapeo:
        st.error(err_mapeo)
        st.stop()
    datos_mapeo = ws_mapeo.get_all_values()
    if len(datos_mapeo) > 1:
        df_mapeo = pd.DataFrame(datos_mapeo[1:], columns=datos_mapeo[0])
    else:
        df_mapeo = pd.DataFrame(columns=[
            "Texto_Buscado", "NoIdentificacion", "Insumo", "Marca", "Proveedor",
            "Unidad_Medida", "Presentacion", "Unidad_Base", "Contenido_Base_por_Unidad"
        ])

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
                df_edit = preparar_dataframe_con_mapeo(df_conceptos, df_mapeo, df_cat)
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
                    df_edit = preparar_dataframe_con_mapeo(df_conceptos, df_mapeo, df_cat)
                    st.session_state.xml_df_edit = df_edit
                    st.success(f"Se leyeron {len(df_edit)} conceptos del XML pegado.")
                    st.rerun()
            else:
                st.warning("Pega el contenido XML antes de procesar.")

    if st.session_state.xml_df_edit is not None:
        df_edit = st.session_state.xml_df_edit
        insumos_disponibles = sorted(df_cat["Nombre del Insumo"].dropna().unique())

        st.subheader("Asignación y ajuste de conceptos")
        st.caption("Desplázate horizontalmente si es necesario.")

        edited_df = st.data_editor(
            df_edit,
            column_config={
                "Descripcion": st.column_config.TextColumn("Descripción", disabled=True),
                "NoIdentificacion": st.column_config.TextColumn("NoID", disabled=True),
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
                "Guardar_Regla": st.column_config.CheckboxColumn(
                    "Guardar regla",
                    help="Marcar para recordar esta equivalencia en futuras cargas."
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
                    filas_mapeo_nuevas = []
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

                        if row.get("Guardar_Regla", False):
                            filas_mapeo_nuevas.append({
                                "Texto_Buscado": row["Descripcion"].upper(),
                                "NoIdentificacion": row["NoIdentificacion"],
                                "Insumo": row["Insumo"],
                                "Marca": row.get("Marca", ""),
                                "Proveedor": row.get("Proveedor", ""),
                                "Unidad_Medida": row["Unidad_Medida"],
                                "Presentacion": row["Presentacion"],
                                "Unidad_Base": row["Unidad_Base"],
                                "Contenido_Base_por_Unidad": row["Contenido_Base_por_Unidad"],
                            })

                    ok_costos, msg_costos = append_rows_con_retry(ws_costos, filas_guardar)
                    if not ok_costos:
                        st.error(msg_costos)
                        st.stop()

                    if filas_mapeo_nuevas:
                        # Evitar duplicados
                        datos_actuales = ws_mapeo.get_all_values()
                        if len(datos_actuales) > 1:
                            df_existentes = pd.DataFrame(datos_actuales[1:], columns=datos_actuales[0])
                            existentes_ids = set(
                                (str(r["NoIdentificacion"]).upper(), str(r["Proveedor"]).upper())
                                for _, r in df_existentes.iterrows()
                            )
                            existentes_textos = set(df_existentes["Texto_Buscado"].str.upper())
                        else:
                            existentes_ids = set()
                            existentes_textos = set()

                        nuevas_filas = []
                        for regla in filas_mapeo_nuevas:
                            clave_id = (regla["NoIdentificacion"].upper(), regla["Proveedor"].upper())
                            clave_texto = regla["Texto_Buscado"].upper()
                            if clave_id not in existentes_ids and clave_texto not in existentes_textos:
                                nuevas_filas.append([
                                    regla["Texto_Buscado"],
                                    regla["NoIdentificacion"],
                                    regla["Insumo"],
                                    regla.get("Marca", ""),
                                    regla.get("Proveedor", ""),
                                    regla["Unidad_Medida"],
                                    regla["Presentacion"],
                                    regla["Unidad_Base"],
                                    regla["Contenido_Base_por_Unidad"],
                                ])
                                existentes_ids.add(clave_id)
                                existentes_textos.add(clave_texto)
                        if nuevas_filas:
                            append_rows_con_retry(ws_mapeo, nuevas_filas)

                    cargar_costos_insumos.clear()
                    st.success(f"✅ {len(filas_guardar)} costos guardados con historial.")
                    st.session_state.xml_df_edit = None
                    st.cache_data.clear()
                    st.rerun()
