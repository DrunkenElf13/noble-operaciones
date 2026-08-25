import streamlit as st
import pandas as pd
import time
from data_loaders import cargar_costos_insumos, cargar_recetas, cargar_datos_integrales
from sheets import _asegurar_hoja_costos_insumos, _asegurar_hoja_recetas, append_rows_con_retry
from utils import limpiar_valor, ts_hermosillo, normalizar_nombre
from config import UNIDADES_MED, COLS_RECETAS
from components.avisos import mostrar_avisos
from auth import tiene_permiso

def procesar_importacion_recetas(archivo, mapeo_ingredientes, precio_default=0.0,
                                 linea_default="", presentacion_default="", fecha_revision_default=""):
    try:
        df_raw = pd.read_excel(archivo)
        df_raw.columns = [str(c).strip().lower() for c in df_raw.columns]
        col_map = {
            'receta': 'Receta',
            'ingrediente': 'Ingrediente',
            'cantidad': 'Cantidad',
            'unidad': 'Unidad',
            'precio_venta': 'Precio_Venta',
            'precio': 'Precio_Venta',
        }
        for orig, dest in col_map.items():
            if orig in df_raw.columns and dest not in df_raw.columns:
                df_raw.rename(columns={orig: dest}, inplace=True)
        requeridas = ["Receta", "Ingrediente", "Cantidad"]
        for col in requeridas:
            if col not in df_raw.columns:
                st.error(f"La columna '{col}' es obligatoria en el Excel.")
                return None
        if "Unidad" not in df_raw.columns:
            df_raw["Unidad"] = "pz"
        if "Precio_Venta" not in df_raw.columns:
            df_raw["Precio_Venta"] = precio_default
        df_raw["Ingrediente_Real"] = df_raw["Ingrediente"].map(mapeo_ingredientes)
        sin_mapeo = df_raw[df_raw["Ingrediente_Real"].isna()]
        if not sin_mapeo.empty:
            st.warning(f"Hay {len(sin_mapeo)} filas con ingredientes no mapeados. Serán omitidas.")
        df_raw = df_raw.dropna(subset=["Ingrediente_Real"])
        df_costos = cargar_costos_insumos()
        if df_costos.empty:
            st.error("No hay costos de insumos registrados. Registra al menos un costo antes de importar.")
            return None
        ultimos_costos = df_costos.sort_values("Fecha_Captura").drop_duplicates(subset=["Nombre_Insumo"], keep="last")
        if "Costo_Base_Unitario" in ultimos_costos.columns:
            costo_dict = dict(zip(ultimos_costos["Nombre_Insumo"], ultimos_costos["Costo_Base_Unitario"]))
        else:
            costo_dict = dict(zip(ultimos_costos["Nombre_Insumo"], ultimos_costos["Costo_Unitario"]))
        df_cat = cargar_datos_integrales()[0]
        unidad_dict = {}
        if not df_cat.empty:
            unidad_dict = dict(zip(df_cat["Nombre del Insumo"], df_cat.get("Unidad de Medida", "pz")))
        filas = []
        for _, row in df_raw.iterrows():
            ing_real = row["Ingrediente_Real"]
            costo_unit = limpiar_valor(costo_dict.get(ing_real, 0))
            cantidad = limpiar_valor(row["Cantidad"])
            costo_ing = round(cantidad * costo_unit, 4)
            unidad = row.get("Unidad", unidad_dict.get(ing_real, "pz"))
            precio_vta = limpiar_valor(row.get("Precio_Venta", precio_default))
            if precio_vta <= 0:
                precio_vta = precio_default
            food_cost_ing = round((costo_ing / precio_vta * 100) if precio_vta > 0 else 0.0, 2)
            filas.append([
                str(row["Receta"]).strip(),
                ing_real,
                cantidad,
                unidad,
                costo_ing,
                precio_vta,
                food_cost_ing,
                ts_hermosillo(),
                st.session_state.current_user,
                linea_default,
                presentacion_default,
                fecha_revision_default,
                costo_unit,
                0.0
            ])
        df_resultado = pd.DataFrame(filas, columns=COLS_RECETAS)
        for receta in df_resultado["Receta"].unique():
            mask = df_resultado["Receta"] == receta
            costo_neto = df_resultado.loc[mask, "Costo_Ingrediente"].sum()
            df_resultado.loc[mask, "Costo_Neto_Receta"] = costo_neto
        return df_resultado
    except Exception as e:
        st.error(f"Error al procesar el archivo: {e}")
        return None

def show_base_costos():
    if not tiene_permiso("BaseCostos"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    st.title("🧾 Base de Costos y Recetas")
    mostrar_avisos("BaseCostos")
    if not st.session_state.auth_status:
        st.error("🔒 Autenticación requerida.")
        st.stop()

    tab_costos, tab_recetas = st.tabs(["💰 Costos de Insumos", "🍽️ Recetas"])
    with tab_costos:
        st.subheader("Registro de Costo de Insumos (desde catálogo)")
        df_ci = cargar_costos_insumos()
        df_cat = cargar_datos_integrales()[0]
        if df_cat.empty:
            st.warning("No hay insumos activos en el catálogo.")
        else:
            with st.form("f_costo_insumo", clear_on_submit=True):
                insumo_opts = sorted(df_cat["Nombre del Insumo"].dropna().unique())
                insumo_sel = st.selectbox("Selecciona el Insumo:", insumo_opts)
                mask_cat = df_cat["Nombre del Insumo"] == insumo_sel
                info_cat = {}
                if mask_cat.any():
                    info_cat = df_cat[mask_cat].iloc[0].to_dict()

                col_a, col_b = st.columns(2)
                with col_a:
                    marca_ci = st.text_input("Marca:", value=str(info_cat.get("Marca","")))
                with col_b:
                    prov_ci  = st.text_input("Proveedor:", value=str(info_cat.get("Proveedor","")))

                col_c, col_d = st.columns(2)
                with col_c:
                    um_ci    = st.selectbox(
                        "Unidad de Medida (Inventario):",
                        UNIDADES_MED,
                        index=UNIDADES_MED.index(str(info_cat.get("Unidad de Medida","pz")).lower())
                              if str(info_cat.get("Unidad de Medida","pz")).lower() in UNIDADES_MED else 0,
                        help="Unidad en la que controlas el inventario de este insumo (ej. pz, paquete, gr, lt)."
                    )
                with col_d:
                    pres_ci  = st.text_input(
                        "Presentación:",
                        value="",
                        placeholder="Ej: 1, 12, 100",
                        help="Cantidad de unidades de inventario que contiene la presentación que compras (ej. 1 paquete, 12 pz por caja)."
                    )

                col_e, col_f = st.columns(2)
                with col_e:
                    costo_pres = st.number_input(
                        "Costo de la Presentación ($):",
                        min_value=0.0, step=0.5, value=0.0,
                        help="Costo total pagado por la presentación (caja, bolsa, paquete, etc.)."
                    )
                with col_f:
                    costo_unit = st.number_input(
                        "Costo por Unidad ($) (opcional):",
                        min_value=0.0, step=0.001, value=0.0,
                        help="Si dejas 0, se calculará automáticamente: Costo Presentación ÷ Presentación."
                    )

                st.markdown("---")
                st.write("**Conversión para recetas / food cost**")

                if um_ci in ["pz", "paquete"]:
                    default_base = "pieza"
                elif um_ci == "kg":
                    default_base = "gr"
                elif um_ci == "lt":
                    default_base = "ml"
                else:
                    default_base = um_ci

                col_g, col_h = st.columns(2)
                with col_g:
                    unidad_base_ci = st.selectbox(
                        "Unidad base para recetas:",
                        UNIDADES_MED,
                        index=UNIDADES_MED.index(default_base) if default_base in UNIDADES_MED else 0,
                        help="Unidad en la que usarás el insumo en recetas (ml, gr, pieza, paquete, etc.)."
                    )
                with col_h:
                    contenido_base_ci = st.number_input(
                        f"Contenido en {unidad_base_ci} por unidad de inventario:",
                        min_value=0.0, step=1.0, value=0.0,
                        help=f"Cuántas unidades de {unidad_base_ci} hay en 1 {um_ci}. Ej: 1 paquete = 100 piezas → 100."
                    )
                col_i, col_j = st.columns(2)
                with col_i:
                    costo_base_ci = st.number_input(
                        f"Costo base unitario ($/{unidad_base_ci}) (opcional):",
                        min_value=0.0, step=0.0001, value=0.0,
                        format="%.6f",
                        help=f"Si dejas 0, se calculará automáticamente: Costo Unitario ÷ Contenido Base."
                    )
                with col_j:
                    resp_ci = st.selectbox(
                        "Responsable:",
                        st.session_state.responsables,
                        index=st.session_state.responsables.index(st.session_state.current_user)
                              if st.session_state.current_user in st.session_state.responsables else 0
                    )

                if st.form_submit_button("💾 Guardar Costo"):
                    if costo_pres <= 0:
                        st.error("El costo de la presentación debe ser mayor a cero.")
                    else:
                        if costo_unit <= 0:
                            try:
                                pres_num = float(pres_ci) if pres_ci.strip() else 0.0
                                if pres_num > 0:
                                    costo_unit = round(costo_pres / pres_num, 4)
                                else:
                                    st.error("La presentación debe ser un número mayor que cero para calcular el costo unitario.")
                                    st.stop()
                            except ValueError:
                                st.error("La presentación debe ser un número válido.")
                                st.stop()

                        if unidad_base_ci != um_ci:
                            if contenido_base_ci <= 0:
                                st.error(
                                    f"Debes indicar cuántas unidades de {unidad_base_ci} contiene 1 {um_ci}."
                                )
                                st.stop()
                            if costo_base_ci <= 0:
                                costo_base_ci = round(costo_unit / contenido_base_ci, 6)
                        else:
                            contenido_base_ci = 1.0
                            if costo_base_ci <= 0:
                                costo_base_ci = costo_unit

                        unidad_costo = f"$/{um_ci}"

                        ws_ci, err = _asegurar_hoja_costos_insumos()
                        if err:
                            st.error(err)
                        else:
                            fila_ci = [
                                insumo_sel, marca_ci, prov_ci, um_ci, pres_ci,
                                costo_pres, costo_unit, unidad_costo,
                                unidad_base_ci, contenido_base_ci, costo_base_ci,
                                ts_hermosillo(), resp_ci
                            ]
                            ok, msg = append_rows_con_retry(ws_ci, [fila_ci])
                            if ok:
                                cargar_costos_insumos.clear()
                                cargar_recetas.clear()
                                st.success(f"Costo de {insumo_sel} registrado.")
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error(msg)

        st.subheader("📋 Costos registrados")
        if not df_ci.empty:
            df_ci_latest = df_ci.sort_values("Fecha_Captura").drop_duplicates(subset=["Nombre_Insumo"], keep="last")
            st.dataframe(df_ci_latest, hide_index=True, width="stretch")
        else:
            st.info("Sin costos registrados aún.")
        # ⚡ EDICIÓN MASIVA DE COSTOS DE INSUMOS
        st.divider()
        with st.expander("⚡ Edición masiva de costos de insumos", expanded=False):
            st.markdown("""
            Edita los **costos actuales** de cada insumo.  
            Al guardar, se agregará **una fila nueva con fecha actual** para cada insumo modificado.  
            El sistema usará el costo más reciente para recetas y food cost.
            """)
            if df_ci.empty:
                st.info("No hay costos registrados todavía.")
            else:
                df_ci_latest = df_ci.sort_values("Fecha_Captura").drop_duplicates(subset=["Nombre_Insumo"], keep="last")
                df_ci_edit = df_ci_latest[[
                    "Nombre_Insumo", "Marca", "Proveedor", "Unidad_Medida",
                    "Presentacion", "Costo_Presentacion", "Costo_Unitario",
                    "Unidad_Base", "Contenido_Base_por_Unidad", "Costo_Base_Unitario"
                ]].copy()

                for col in ["Costo_Presentacion", "Costo_Unitario", "Contenido_Base_por_Unidad", "Costo_Base_Unitario"]:
                    df_ci_edit[col] = df_ci_edit[col].apply(limpiar_valor)

                edited_costos = st.data_editor(
                    df_ci_edit,
                    column_config={
                        "Nombre_Insumo": st.column_config.TextColumn(disabled=True),
                        "Marca": st.column_config.TextColumn(disabled=True),
                        "Proveedor": st.column_config.TextColumn(disabled=True),
                        "Unidad_Medida": st.column_config.SelectboxColumn(options=UNIDADES_MED),
                        "Presentacion": st.column_config.NumberColumn(min_value=0.0, step=1.0),
                        "Costo_Presentacion": st.column_config.NumberColumn(min_value=0.0, step=0.5),
                        "Costo_Unitario": st.column_config.NumberColumn(min_value=0.0, step=0.001, format="%.4f"),
                        "Unidad_Base": st.column_config.SelectboxColumn(options=UNIDADES_MED),
                        "Contenido_Base_por_Unidad": st.column_config.NumberColumn(min_value=0.0, step=1.0),
                        "Costo_Base_Unitario": st.column_config.NumberColumn(min_value=0.0, step=0.0001, format="%.6f"),
                    },
                    hide_index=True,
                    width="stretch",
                    key="bulk_edit_costos"
                )

                if st.button("💾 Guardar cambios de costos", type="primary", width="stretch"):
                    ws_costos_bulk, err_bulk = _asegurar_hoja_costos_insumos()
                    if err_bulk:
                        st.error(err_bulk)
                    else:
                        filas_nuevas = []
                        for _, row in edited_costos.iterrows():
                            if row["Unidad_Base"] != row["Unidad_Medida"] and row["Contenido_Base_por_Unidad"] <= 0:
                                st.error(
                                    f"Para {row['Nombre_Insumo']}, debes indicar cuántas unidades de {row['Unidad_Base']} contiene 1 {row['Unidad_Medida']}."
                                )
                                st.stop()
                            if row["Costo_Unitario"] <= 0 and row["Costo_Presentacion"] > 0 and row["Presentacion"] > 0:
                                row["Costo_Unitario"] = round(row["Costo_Presentacion"] / row["Presentacion"], 4)
                            if row["Costo_Base_Unitario"] <= 0 and row["Costo_Unitario"] > 0 and row["Contenido_Base_por_Unidad"] > 0:
                                row["Costo_Base_Unitario"] = round(row["Costo_Unitario"] / row["Contenido_Base_por_Unidad"], 6)

                            filas_nuevas.append([
                                row["Nombre_Insumo"],
                                row["Marca"],
                                row["Proveedor"],
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

                        if filas_nuevas:
                            ok_bulk, msg_bulk = append_rows_con_retry(ws_costos_bulk, filas_nuevas)
                            if ok_bulk:
                                cargar_costos_insumos.clear()
                                cargar_recetas.clear()
                                st.success(f"✅ {len(filas_nuevas)} costos actualizados con historial.")
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error(msg_bulk)
    with tab_recetas:
        st.subheader("🍽️ Editor de Recetas")
        df_rec = cargar_recetas()
        df_ci2 = cargar_costos_insumos()
        df_cat2 = cargar_datos_integrales()[0]

        insumos_con_costo = []
        if not df_ci2.empty:
            latest_costs = df_ci2.sort_values("Fecha_Captura").drop_duplicates(subset=["Nombre_Insumo"], keep="last")
            insumos_con_costo = latest_costs["Nombre_Insumo"].dropna().unique().tolist()
        else:
            insumos_con_costo = sorted(df_cat2["Nombre del Insumo"].dropna().unique()) if not df_cat2.empty else []

        # Inicialización de estado
        if "ingredientes_receta" not in st.session_state:
            st.session_state.ingredientes_receta = []
        if "receta_nombre" not in st.session_state:
            st.session_state.receta_nombre = ""
        if "receta_linea" not in st.session_state:
            st.session_state.receta_linea = ""
        if "receta_presentacion" not in st.session_state:
            st.session_state.receta_presentacion = ""
        if "receta_fecha_revision" not in st.session_state:
            st.session_state.receta_fecha_revision = ts_hermosillo().split(" ")[0]
        if "receta_precio" not in st.session_state:
            st.session_state.receta_precio = 0.0
        if "receta_factor_manual" not in st.session_state:
            st.session_state.receta_factor_manual = 2.5
        if "receta_modo" not in st.session_state:
            st.session_state.receta_modo = "Nueva receta"
        if "receta_original" not in st.session_state:
            st.session_state.receta_original = ""

        # ── IMPORTACIÓN DESDE EXCEL ──
        with st.expander("📥 Importar recetas desde Excel", expanded=False):
            st.markdown("""
            **Formato simple de 5 columnas:**  
            `Receta | Ingrediente | Cantidad | Unidad | Precio_Venta`  
            Puedes agregar columnas opcionales: `Linea`, `Presentacion`, `Fecha_Revision`.
            """)
            precio_default_imp = st.number_input("Precio de venta por defecto ($):", min_value=0.0, step=1.0, value=0.0)
            archivo_imp = st.file_uploader("Selecciona el archivo Excel", type=["xlsx"], key="import_recetas_new")
            if archivo_imp is not None:
                try:
                    df_import = pd.read_excel(archivo_imp)
                    df_import.columns = [str(c).strip().lower() for c in df_import.columns]
                    col_ing = next((c for c in df_import.columns if 'ingrediente' in c), None)
                    if col_ing is None:
                        st.error("No se encontró una columna de 'Ingrediente' en el archivo.")
                    else:
                        ingredientes_unicos = sorted(df_import[col_ing].dropna().unique())
                        st.info(f"Se encontraron {len(ingredientes_unicos)} ingredientes distintos en el archivo.")
                        st.write("**Asigna cada ingrediente del archivo a un insumo del catálogo:**")
                        mapeo = {}
                        for ing in ingredientes_unicos:
                            opciones = ["(Omitir)"] + insumos_con_costo
                            default_idx = 0
                            ing_norm = normalizar_nombre(ing)
                            for i, cat_ing in enumerate(insumos_con_costo):
                                if normalizar_nombre(cat_ing) == ing_norm:
                                    default_idx = i + 1
                                    break
                            seleccion = st.selectbox(
                                f"'{ing}' →",
                                opciones,
                                index=default_idx,
                                key=f"map_{ing}"
                            )
                            if seleccion != "(Omitir)":
                                mapeo[ing] = seleccion

                        linea_imp = st.text_input("Línea (opcional):", value="")
                        presentacion_imp = st.text_input("Presentación (opcional):", value="")
                        fecha_rev_imp = st.date_input("Fecha Revisión (opcional):", value=pd.to_datetime("today"))

                        if st.button("🔍 Previsualizar recetas importadas"):
                            if not mapeo:
                                st.warning("Asigna al menos un ingrediente.")
                            else:
                                df_resultado = procesar_importacion_recetas(
                                    archivo_imp, mapeo, precio_default_imp,
                                    linea_imp, presentacion_imp,
                                    fecha_rev_imp.strftime("%Y-%m-%d")
                                )
                                if df_resultado is not None and not df_resultado.empty:
                                    st.session_state["import_preview"] = df_resultado
                                    st.success(f"Se generaron {len(df_resultado)} filas de recetas.")
                                    st.dataframe(df_resultado, width="stretch")
                except Exception as e:
                    st.error(f"Error al leer el archivo: {e}")

            if "import_preview" in st.session_state and st.session_state["import_preview"] is not None:
                if st.button("💾 GUARDAR TODAS LAS RECETAS IMPORTADAS", type="primary"):
                    ws_rec, err = _asegurar_hoja_recetas()
                    if err:
                        st.error(err)
                    else:
                        df_to_save = st.session_state["import_preview"]
                        filas_guardar = df_to_save.values.tolist()
                        ok, msg = append_rows_con_retry(ws_rec, filas_guardar)
                        if ok:
                            cargar_recetas.clear()
                            cargar_costos_insumos.clear()
                            st.success(f"Importación exitosa: {len(filas_guardar)} registros guardados.")
                            del st.session_state["import_preview"]
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(msg)
        st.divider()

        # ── ENCABEZADO DE RECETA (fuera del formulario para poder cargar) ──
        col_r1, col_r2, col_r3 = st.columns(3)
        with col_r1:
            nombre_receta = st.text_input("Nombre de la receta:", value=st.session_state.receta_nombre, key="receta_nombre_input")
        with col_r2:
            linea_final = st.text_input("Línea / Categoría:", value=st.session_state.receta_linea, placeholder="Ej: Bebidas, Alimentos, Repostería...")
        with col_r3:
            presentacion = st.text_input("Presentación / Tamaño:", value=st.session_state.receta_presentacion, placeholder="12oz, 16oz, rebanada...")
            fecha_revision = st.date_input("Fecha Revisión:", value=pd.to_datetime(st.session_state.receta_fecha_revision))

        st.session_state.receta_nombre = nombre_receta
        st.session_state.receta_linea = linea_final
        st.session_state.receta_presentacion = presentacion
        st.session_state.receta_fecha_revision = fecha_revision.strftime("%Y-%m-%d")

        # Botones de acción
        col_acc1, col_acc2, col_acc3 = st.columns(3)
        with col_acc1:
            if st.button("🧹 Nueva receta (limpiar)", width="stretch"):
                st.session_state.ingredientes_receta = []
                st.session_state.receta_nombre = ""
                st.session_state.receta_linea = ""
                st.session_state.receta_presentacion = ""
                st.session_state.receta_precio = 0.0
                st.session_state.receta_factor_manual = 2.5
                st.session_state.receta_modo = "Nueva receta"
                st.session_state.receta_original = ""
                st.rerun()
        with col_acc2:
            if st.button("➕ Agregar ingrediente", width="stretch"):
                st.session_state.ingredientes_receta.append({
                    "insumo": "",
                    "cantidad": 0.0,
                    "unidad": "pz",
                    "costo_unit": 0.0,
                    "total": 0.0
                })
                st.rerun()
        with col_acc3:
            if st.session_state.ingredientes_receta and st.button("🗑️ Quitar último", width="stretch"):
                st.session_state.ingredientes_receta.pop()
                st.rerun()

        # Selector de receta existente
        recetas_existentes = sorted(df_rec["Receta"].unique()) if not df_rec.empty else []
        if recetas_existentes:
            col_rec1, col_rec2 = st.columns(2)
            with col_rec1:
                receta_seleccionada = st.selectbox(
                    "Seleccionar receta existente:",
                    recetas_existentes,
                    key="receta_seleccionada"
                )
            with col_rec2:
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("📂 Cargar", width="stretch"):
                        df_edit = df_rec[df_rec["Receta"] == receta_seleccionada]
                        if not df_edit.empty:
                            nuevos_ingredientes = []
                            for _, row in df_edit.iterrows():
                                nuevos_ingredientes.append({
                                    "insumo": row["Ingrediente"],
                                    "cantidad": limpiar_valor(row["Cantidad"]),
                                    "unidad": row["Unidad_Medida"],
                                    "costo_unit": limpiar_valor(row.get("Precio_Insumo", 0)),
                                    "total": limpiar_valor(row["Costo_Ingrediente"])
                                })
                            st.session_state.ingredientes_receta = nuevos_ingredientes
                            st.session_state.receta_nombre = receta_seleccionada
                            st.session_state.receta_linea = str(df_edit.iloc[0].get("Linea", ""))
                            st.session_state.receta_presentacion = str(df_edit.iloc[0].get("Presentacion", ""))
                            st.session_state.receta_fecha_revision = str(df_edit.iloc[0].get("Fecha_Revision", ""))
                            st.session_state.receta_precio = limpiar_valor(df_edit.iloc[0].get("Precio_Venta", 0))
                            st.session_state.receta_original = receta_seleccionada
                            st.session_state.receta_modo = "Editar receta existente"
                            st.rerun()
                with col_btn2:
                    if st.button("📋 Duplicar", width="stretch"):
                        df_dup = df_rec[df_rec["Receta"] == receta_seleccionada]
                        if not df_dup.empty:
                            nuevos_ingredientes = []
                            for _, row in df_dup.iterrows():
                                nuevos_ingredientes.append({
                                    "insumo": row["Ingrediente"],
                                    "cantidad": limpiar_valor(row["Cantidad"]),
                                    "unidad": row["Unidad_Medida"],
                                    "costo_unit": limpiar_valor(row.get("Precio_Insumo", 0)),
                                    "total": limpiar_valor(row["Costo_Ingrediente"])
                                })
                            st.session_state.ingredientes_receta = nuevos_ingredientes
                            st.session_state.receta_nombre = receta_seleccionada + " (copia)"
                            st.session_state.receta_linea = str(df_dup.iloc[0].get("Linea", ""))
                            st.session_state.receta_presentacion = str(df_dup.iloc[0].get("Presentacion", ""))
                            st.session_state.receta_fecha_revision = ts_hermosillo().split(" ")[0]
                            st.session_state.receta_precio = limpiar_valor(df_dup.iloc[0].get("Precio_Venta", 0))
                            st.session_state.receta_original = ""
                            st.session_state.receta_modo = "Nueva receta"
                            st.rerun()
        else:
            st.info("No hay recetas guardadas todavía.")
        st.divider()

        # Lista de ingredientes con widgets ligeros
        st.subheader("📋 Ingredientes de la receta")
        if not st.session_state.ingredientes_receta:
            st.info("Presiona '➕ Agregar ingrediente' para comenzar la captura.")
        else:
            # Mostrar encabezados
            col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([2.5, 1.0, 1.0, 1.0, 1.0])
            col_h1.write("**Ingrediente**")
            col_h2.write("**Cantidad**")
            col_h3.write("**Unidad**")
            col_h4.write("**Precio Insumo**")
            col_h5.write("**Total**")

            # Iterar sobre cada fila
            for i, ing in enumerate(st.session_state.ingredientes_receta):
                cols = st.columns([2.5, 1.0, 1.0, 1.0, 1.0])
                with cols[0]:
                    insumo_actual = ing.get("insumo", "")
                    if insumo_actual not in insumos_con_costo:
                        insumo_actual = ""
                    insumo_seleccionado = st.selectbox(
                        "Ingrediente",
                        options=[""] + insumos_con_costo,
                        index=0 if not insumo_actual else ([""] + insumos_con_costo).index(insumo_actual),
                        key=f"ing_insumo_{i}",
                        label_visibility="collapsed"
                    )
                with cols[1]:
                    cantidad = st.number_input(
                        "Cantidad",
                        min_value=0.0,
                        step=0.1,
                        value=float(ing.get("cantidad", 0.0)),
                        key=f"ing_cantidad_{i}",
                        label_visibility="collapsed"
                    )
                with cols[2]:
                    if insumo_seleccionado:
                        mask = df_ci2["Nombre_Insumo"] == insumo_seleccionado
                        if mask.any():
                            ultimo = df_ci2[mask].sort_values("Fecha_Captura").iloc[-1]
                            if "Costo_Base_Unitario" in ultimo and limpiar_valor(ultimo.get("Costo_Base_Unitario", 0)) > 0:
                                unidad_auto = str(ultimo.get("Unidad_Base", "pz"))
                                costo_auto = limpiar_valor(ultimo["Costo_Base_Unitario"])
                            else:
                                unidad_auto = str(ultimo.get("Unidad_Medida", "pz"))
                                costo_auto = limpiar_valor(ultimo["Costo_Unitario"])
                        else:
                            unidad_auto = ing.get("unidad", "pz")
                            costo_auto = ing.get("costo_unit", 0.0)
                    else:
                        unidad_auto = ing.get("unidad", "pz")
                        costo_auto = ing.get("costo_unit", 0.0)

                    unidad = st.selectbox(
                        "Unidad",
                        options=UNIDADES_MED,
                        index=UNIDADES_MED.index(unidad_auto) if unidad_auto in UNIDADES_MED else 0,
                        key=f"ing_unidad_{i}",
                        label_visibility="collapsed"
                    )
                with cols[3]:
                    st.write(f"${costo_auto:.4f}")
                with cols[4]:
                    total = round(cantidad * costo_auto, 4)
                    st.write(f"**${total:.2f}**")

                # Actualizar el diccionario de la fila
                st.session_state.ingredientes_receta[i] = {
                    "insumo": insumo_seleccionado,
                    "cantidad": cantidad,
                    "unidad": unidad,
                    "costo_unit": costo_auto,
                    "total": total
                }

        # Métricas y guardado (siempre visibles si hay ingredientes)
        if st.session_state.ingredientes_receta:
            # Calcular costo neto en tiempo real
            costo_neto = sum(limpiar_valor(ing.get("total", 0)) for ing in st.session_state.ingredientes_receta)

            # Comparador de factores
            st.markdown("### 💰 Comparador de precio por factor")
            factores = [2.0, 2.5, 3.0]
            col_factor = st.columns(len(factores))
            for i, f in enumerate(factores):
                precio_sug = round(costo_neto * f, 2)
                food_cost = (costo_neto / precio_sug * 100) if precio_sug > 0 else 0.0
                margen = precio_sug - costo_neto
                margen_pct = (margen / precio_sug * 100) if precio_sug > 0 else 0.0
                with col_factor[i]:
                    st.markdown(f"**x{f}**")
                    st.metric("Precio", f"${precio_sug:,.2f}")
                    st.caption(f"Food Cost: {food_cost:.1f}%")
                    st.caption(f"Margen: ${margen:,.2f} ({margen_pct:.0f}%)")

            # Factor personalizado y precio final
            st.markdown("### ⚙️ Factor personalizado")
            if st.session_state.receta_precio > 0:
                precio_real_guardado = st.session_state.receta_precio
                factor_real_guardado = precio_real_guardado / costo_neto if costo_neto > 0 else 0.0
                col_real1, col_real2 = st.columns(2)
                with col_real1:
                    st.metric("Precio de Venta Actual", f"${precio_real_guardado:,.2f}")
                with col_real2:
                    st.metric("Factor Actual", f"x{factor_real_guardado:.2f}")

            col_factor_custom, col_precio_custom = st.columns(2)
            with col_factor_custom:
                factor_manual = st.number_input(
                    "Factor multiplicador personalizado:",
                    min_value=0.1,
                    step=0.1,
                    value=st.session_state.get("receta_factor_manual", 2.5),
                    key="factor_manual_input"
                )
                precio_sugerido_manual = round(costo_neto * factor_manual, 2)
                st.caption(f"Precio sugerido: **${precio_sugerido_manual:,.2f}**")
            with col_precio_custom:
                if st.session_state.receta_precio > 0:
                    valor_inicial_precio = st.session_state.receta_precio
                else:
                    valor_inicial_precio = precio_sugerido_manual

                precio_venta = st.number_input(
                    "Precio de Venta ($):",
                    min_value=0.0,
                    step=0.5,
                    value=valor_inicial_precio,
                    key="precio_venta_input"
                )
                if precio_venta > 0 and costo_neto > 0:
                    factor_real = precio_venta / costo_neto
                    st.caption(f"Factor real: **x{factor_real:.2f}**")
                else:
                    st.caption("Factor real: —")

            st.session_state.receta_factor_manual = factor_manual
            st.session_state.receta_precio = precio_venta

            fc_final = (costo_neto / precio_venta * 100) if precio_venta > 0 else 0.0
            margen_final = precio_venta - costo_neto
            margen_pct_final = (margen_final / precio_venta * 100) if precio_venta > 0 else 0.0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Costo Neto Receta", f"${costo_neto:,.2f}")
            c2.metric("Precio de Venta", f"${precio_venta:,.2f}")
            c3.metric("Food Cost %", f"{fc_final:.1f}%")
            c4.metric("Margen Bruto", f"${margen_final:,.2f} ({margen_pct_final:.0f}%)")

            # Guardar receta (botón único)
            if st.button("💾 GUARDAR RECETA COMPLETA", type="primary", width="stretch"):
                nombre_final = st.session_state.receta_nombre.strip()
                if not nombre_final:
                    st.error("Escribe el nombre de la receta.")
                elif not st.session_state.ingredientes_receta:
                    st.error("Agrega al menos un ingrediente.")
                elif precio_venta <= 0:
                    st.error("El precio de venta debe ser mayor que cero.")
                else:
                    for ing in st.session_state.ingredientes_receta:
                        if not ing.get("insumo"):
                            st.error("Hay un ingrediente sin seleccionar.")
                            st.stop()
                        if limpiar_valor(ing.get("cantidad", 0)) <= 0:
                            st.error(f"La cantidad de {ing['insumo']} debe ser mayor a cero.")
                            st.stop()

                    ws_rec, err = _asegurar_hoja_recetas()
                    if err:
                        st.error(err)
                    else:
                        try:
                            if st.session_state.receta_modo == "Editar receta existente" and st.session_state.receta_original:
                                all_data = ws_rec.get_all_values()
                                if len(all_data) > 1:
                                    df_all = pd.DataFrame(all_data[1:], columns=all_data[0])
                                    df_all = df_all[df_all["Receta"] != st.session_state.receta_original]
                                    ws_rec.clear()
                                    ws_rec.append_row(COLS_RECETAS)
                                    if not df_all.empty:
                                        ws_rec.append_rows(df_all.values.tolist())

                            filas_guardar = []
                            for ing in st.session_state.ingredientes_receta:
                                costo_ing = limpiar_valor(ing.get("total", 0))
                                filas_guardar.append([
                                    nombre_final,
                                    ing["insumo"],
                                    limpiar_valor(ing.get("cantidad", 0)),
                                    ing.get("unidad", "pz"),
                                    costo_ing,
                                    precio_venta,
                                    round((costo_ing / precio_venta * 100) if precio_venta > 0 else 0.0, 2),
                                    ts_hermosillo(),
                                    st.session_state.current_user,
                                    st.session_state.receta_linea,
                                    st.session_state.receta_presentacion,
                                    st.session_state.receta_fecha_revision,
                                    limpiar_valor(ing.get("costo_unit", 0)),
                                    costo_neto
                                ])
                            ok, msg = append_rows_con_retry(ws_rec, filas_guardar)
                            if ok:
                                cargar_recetas.clear()
                                cargar_costos_insumos.clear()
                                st.success(f"Receta '{nombre_final}' guardada ({len(filas_guardar)} ingredientes).")
                                for key in ["ingredientes_receta","receta_nombre","receta_precio",
                                            "receta_modo","receta_original"]:
                                    if key in st.session_state:
                                        st.session_state[key] = [] if key == "ingredientes_receta" else ""
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error(msg)
                        except Exception as e:
                            st.error(f"Error al guardar: {e}")

        # ⚡ EDICIÓN MASIVA DE PRECIOS DE RECETAS
        if not df_rec.empty:
            st.divider()
            with st.expander("⚡ Edición masiva de precios de recetas", expanded=False):
                st.markdown("""
                Edita **Línea**, **Presentación** y **Precio de Venta** de todas las recetas.  
                Al guardar, se actualizarán **todas las filas** de cada receta en la hoja `Recetas`.
                """)
                df_rec_uniq = df_rec.drop_duplicates(subset=["Receta"]).copy()
                df_rec_uniq = df_rec_uniq[[
                    "Receta", "Linea", "Presentacion", "Precio_Venta", "Costo_Neto_Receta", "Food_Cost_Pct"
                ]].copy()
                for col in ["Precio_Venta", "Costo_Neto_Receta", "Food_Cost_Pct"]:
                    df_rec_uniq[col] = df_rec_uniq[col].apply(limpiar_valor)

                edited_recetas = st.data_editor(
                    df_rec_uniq,
                    column_config={
                        "Receta": st.column_config.TextColumn(disabled=True),
                        "Linea": st.column_config.TextColumn(),
                        "Presentacion": st.column_config.TextColumn(),
                        "Precio_Venta": st.column_config.NumberColumn(min_value=0.0, step=1.0),
                        "Costo_Neto_Receta": st.column_config.NumberColumn(disabled=True, format="%.2f"),
                        "Food_Cost_Pct": st.column_config.NumberColumn(disabled=True, format="%.2f"),
                    },
                    hide_index=True,
                    width="stretch",
                    key="bulk_edit_recetas"
                )

                if st.button("💾 Guardar cambios de recetas", type="primary", width="stretch"):
                    ws_rec_bulk, err_rec_bulk = _asegurar_hoja_recetas()
                    if err_rec_bulk:
                        st.error(err_rec_bulk)
                    else:
                        all_data = ws_rec_bulk.get_all_values()
                        if len(all_data) <= 1:
                            st.error("No hay recetas para editar.")
                            st.stop()

                        df_all = pd.DataFrame(all_data[1:], columns=all_data[0])
                        for col in COLS_RECETAS:
                            if col not in df_all.columns:
                                df_all[col] = ""

                        for _, row in edited_recetas.iterrows():
                            nombre_receta_bulk = row["Receta"]
                            mask = df_all["Receta"] == nombre_receta_bulk
                            if mask.any():
                                df_all.loc[mask, "Linea"] = row["Linea"]
                                df_all.loc[mask, "Presentacion"] = row["Presentacion"]
                                df_all.loc[mask, "Precio_Venta"] = row["Precio_Venta"]
                                df_all.loc[mask, "Food_Cost_Pct"] = df_all.loc[mask, "Costo_Ingrediente"].apply(
                                    lambda c: round((float(c) / row["Precio_Venta"] * 100) if row["Precio_Venta"] > 0 else 0.0, 2)
                                )

                        ws_rec_bulk.clear()
                        ws_rec_bulk.append_row(COLS_RECETAS)
                        ws_rec_bulk.append_rows(df_all[COLS_RECETAS].values.tolist(), value_input_option="USER_ENTERED")
                        cargar_recetas.clear()
                        cargar_costos_insumos.clear()
                        st.success("✅ Precios y datos de recetas actualizados.")
                        time.sleep(0.5)
                        st.rerun()

        # Analítica por Línea
        if not df_rec.empty and "Linea" in df_rec.columns:
            st.divider()
            st.subheader("📊 Analítica por Línea")
            df_rec_linea = df_rec.copy()
            df_rec_linea["Costo_Neto_Receta"] = df_rec_linea["Costo_Neto_Receta"].apply(limpiar_valor)
            df_rec_linea["Precio_Venta"] = df_rec_linea["Precio_Venta"].apply(limpiar_valor)
            df_rec_linea["Food_Cost_Pct"] = df_rec_linea["Food_Cost_Pct"].apply(limpiar_valor)

            df_por_receta = df_rec_linea.drop_duplicates(subset=["Receta", "Linea"]).copy()
            if not df_por_receta.empty:
                df_agrup_linea = df_por_receta.groupby("Linea").agg(
                    Num_Recetas=("Receta", "nunique"),
                    Precio_Promedio=("Precio_Venta", "mean"),
                    Food_Cost_Promedio=("Food_Cost_Pct", "mean"),
                    Margen_Promedio=("Precio_Venta", lambda x: (x - df_por_receta.loc[x.index, "Costo_Neto_Receta"]).mean())
                ).reset_index()
                st.dataframe(df_agrup_linea, hide_index=True, width="stretch")
