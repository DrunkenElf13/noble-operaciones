import streamlit as st
import pandas as pd
import time
from data_loaders import cargar_costos_insumos, cargar_recetas, cargar_datos_integrales
from sheets import _asegurar_hoja_costos_insumos, _asegurar_hoja_recetas, append_rows_con_retry
from utils import limpiar_valor, ts_hermosillo, normalizar_nombre
from config import UNIDADES_MED
from components.avisos import mostrar_avisos
from auth import tiene_permiso

def procesar_importacion_recetas(archivo, mapeo_ingredientes, precio_default=0.0):
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
                st.session_state.current_user
            ])
        from config import COLS_RECETAS
        return pd.DataFrame(filas, columns=COLS_RECETAS)
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
                marca_ci = st.text_input("Marca:", value=str(info_cat.get("Marca","")))
                prov_ci  = st.text_input("Proveedor:", value=str(info_cat.get("Proveedor","")))
                um_ci    = st.selectbox("Unidad de Medida:", UNIDADES_MED, index=UNIDADES_MED.index(str(info_cat.get("Unidad de Medida","pz")).lower()) if str(info_cat.get("Unidad de Medida","pz")).lower() in UNIDADES_MED else 0)
                pres_ci  = st.text_input("Presentación:", value=str(info_cat.get("Presentación de Compra","")))
                costo_pres = st.number_input("Costo de la Presentación ($):", min_value=0.0, step=0.5, value=0.0)
                costo_unit = st.number_input("Costo por Unidad ($):", min_value=0.0, step=0.001, value=0.0,
                                             help="Costo por gramo, mililitro, pieza, etc.")
                unidad_costo = st.text_input("Unidad de Costo:", placeholder="Ej: $/gr, $/ml, $/pz")
                resp_ci = st.selectbox("Responsable:", st.session_state.responsables, index=st.session_state.responsables.index(st.session_state.current_user) if st.session_state.current_user in st.session_state.responsables else 0)
                if st.form_submit_button("💾 Guardar Costo"):
                    if costo_pres <= 0:
                        st.error("El costo de la presentación debe ser mayor a cero.")
                    else:
                        ws_ci, err = _asegurar_hoja_costos_insumos()
                        if err:
                            st.error(err)
                        else:
                            fila_ci = [insumo_sel, marca_ci, prov_ci, um_ci, pres_ci, costo_pres, costo_unit, unidad_costo, ts_hermosillo(), resp_ci]
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

    with tab_recetas:
        st.subheader("📋 Editor de Recetas (Visual / Bulk)")
        df_rec = cargar_recetas()
        df_ci2 = cargar_costos_insumos()
        df_cat2 = cargar_datos_integrales()[0]

        insumos_con_costo = []
        if not df_ci2.empty:
            latest_costs = df_ci2.sort_values("Fecha_Captura").drop_duplicates(subset=["Nombre_Insumo"], keep="last")
            insumos_con_costo = latest_costs["Nombre_Insumo"].dropna().unique().tolist()
        else:
            insumos_con_costo = sorted(df_cat2["Nombre del Insumo"].dropna().unique()) if not df_cat2.empty else []

        # ── IMPORTACIÓN ──
        with st.expander("📥 Importar recetas desde Excel", expanded=False):
            st.markdown("""
            **Sube un archivo Excel (.xlsx) con las columnas:**  
            `Receta`, `Ingrediente`, `Cantidad`, `Unidad` (opcional) y `Precio_Venta` (opcional).  
            Si no incluyes precio de venta, se usará el valor por defecto que establezcas abajo.
            """)
            precio_default_imp = st.number_input("Precio de venta por defecto ($):", min_value=0.0, step=1.0, value=0.0)
            archivo_imp = st.file_uploader("Selecciona el archivo Excel", type=["xlsx"], key="import_recetas")
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
                        if st.button("🔍 Previsualizar recetas importadas"):
                            if not mapeo:
                                st.warning("Asigna al menos un ingrediente.")
                            else:
                                df_resultado = procesar_importacion_recetas(archivo_imp, mapeo, precio_default_imp)
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

        # ── EDITOR MANUAL ──
        st.divider()
        st.subheader("✏️ Editor manual de receta")
        recetas_existentes = sorted(df_rec["Receta"].unique()) if not df_rec.empty else []
        col1, col2 = st.columns(2)
        with col1:
            modo_receta = st.radio("Modo:", ["Nueva receta", "Editar receta existente"])
        with col2:
            if modo_receta == "Editar receta existente" and recetas_existentes:
                receta_edit_sel = st.selectbox("Receta a editar:", recetas_existentes)
                if st.button("📂 Cargar receta"):
                    df_edit = df_rec[df_rec["Receta"] == receta_edit_sel]
                    if not df_edit.empty:
                        nuevos_ingredientes = []
                        for _, row in df_edit.iterrows():
                            costo_unit = 0.0
                            if not df_ci2.empty:
                                mask = df_ci2["Nombre_Insumo"] == row["Ingrediente"]
                                if mask.any():
                                    costo_unit = limpiar_valor(df_ci2[mask].sort_values("Fecha_Captura").iloc[-1]["Costo_Unitario"])
                            nuevos_ingredientes.append({
                                "insumo": row["Ingrediente"],
                                "cantidad": limpiar_valor(row["Cantidad"]),
                                "unidad": row["Unidad_Medida"],
                                "costo_unit": costo_unit,
                                "total": round(limpiar_valor(row["Cantidad"]) * costo_unit, 4)
                            })
                        st.session_state.ingredientes_receta = nuevos_ingredientes
                        st.session_state.receta_nombre = receta_edit_sel
                        st.session_state.receta_precio = limpiar_valor(df_edit.iloc[0].get("Precio_Venta", 0))
                        st.session_state.receta_modo = "Editar receta existente"
                        st.session_state.receta_original = receta_edit_sel
                        st.rerun()
            else:
                if st.button("🧹 Nueva receta (limpiar)"):
                    st.session_state.ingredientes_receta = []
                    st.session_state.receta_nombre = ""
                    st.session_state.receta_precio = 0.0
                    st.session_state.receta_modo = "Nueva receta"
                    st.session_state.receta_original = ""
                    st.rerun()

        col_r1, col_r2, col_r3 = st.columns(3)
        with col_r1:
            nombre_receta = st.text_input("Nombre de la receta:", value=st.session_state.receta_nombre, key="receta_nombre_input")
        with col_r2:
            precio_venta = st.number_input("Precio de Venta ($):", min_value=0.0, step=1.0, value=st.session_state.receta_precio, key="receta_precio_input")
        with col_r3:
            factor = st.number_input("Factor de precio sugerido:", min_value=0.1, step=0.1, value=st.session_state.receta_factor, key="receta_factor_input")
        st.session_state.receta_nombre = nombre_receta
        st.session_state.receta_precio = precio_venta
        st.session_state.receta_factor = factor

        with st.expander("➕ Agregar ingrediente a la receta", expanded=(len(st.session_state.ingredientes_receta) == 0)):
            insumo_opt = insumos_con_costo
            if insumo_opt:
                col_i1, col_i2, col_i3 = st.columns(3)
                with col_i1:
                    insumo_add = st.selectbox("Ingrediente:", insumo_opt, key="add_ing")
                with col_i2:
                    cantidad_add = st.number_input("Cantidad:", min_value=0.0, step=0.1, key="add_cant")
                costo_uni_add = 0.0
                unidad_add = "pz"
                if not df_ci2.empty:
                    mask = df_ci2["Nombre_Insumo"] == insumo_add
                    if mask.any():
                        ultimo = df_ci2[mask].sort_values("Fecha_Captura").iloc[-1]
                        costo_uni_add = limpiar_valor(ultimo["Costo_Unitario"])
                        unidad_add = str(ultimo.get("Unidad_Medida", "pz"))
                else:
                    unidad_add = str(df_cat2[df_cat2["Nombre del Insumo"]==insumo_add].iloc[0].get("Unidad de Medida","pz")) if not df_cat2.empty else "pz"
                with col_i3:
                    st.write(f"Costo unitario: **${costo_uni_add:.4f}**")
                    st.write(f"Unidad: {unidad_add}")
                if st.button("Agregar a la receta"):
                    nuevo_ing = {
                        "insumo": insumo_add,
                        "cantidad": cantidad_add,
                        "unidad": unidad_add,
                        "costo_unit": costo_uni_add,
                        "total": round(cantidad_add * costo_uni_add, 4)
                    }
                    st.session_state.ingredientes_receta.append(nuevo_ing)
                    st.rerun()
            else:
                st.warning("No hay insumos con costo registrado. Ve a 'Costos de Insumos' primero.")

        st.subheader("📋 Ingredientes de la receta (edita directamente)")
        if st.session_state.ingredientes_receta:
            df_ingredientes = pd.DataFrame(st.session_state.ingredientes_receta)
            for col in ["insumo","cantidad","unidad","costo_unit","total"]:
                if col not in df_ingredientes.columns:
                    df_ingredientes[col] = 0.0 if col in ("cantidad","costo_unit","total") else ""
            df_ingredientes = df_ingredientes[["insumo","cantidad","unidad","costo_unit","total"]]
            edited_df = st.data_editor(
                df_ingredientes,
                column_config={
                    "insumo": st.column_config.SelectboxColumn(
                        "Ingrediente",
                        options=insumos_con_costo,
                        required=True
                    ),
                    "cantidad": st.column_config.NumberColumn("Cantidad", min_value=0.0, step=0.1),
                    "unidad": st.column_config.SelectboxColumn("Unidad", options=UNIDADES_MED),
                    "costo_unit": st.column_config.NumberColumn("Costo Unitario", min_value=0.0, step=0.001),
                    "total": st.column_config.NumberColumn("Total", min_value=0.0, disabled=True)
                },
                hide_index=True,
                width="stretch",
                num_rows="dynamic"
            )
            for idx, row in edited_df.iterrows():
                edited_df.loc[idx, "total"] = round(row["cantidad"] * row["costo_unit"], 4)
            st.session_state.ingredientes_receta = edited_df.to_dict(orient="records")
            costo_total = sum(ing["total"] for ing in st.session_state.ingredientes_receta)
            precio_sug = costo_total * st.session_state.receta_factor
            fc_pct = (costo_total / st.session_state.receta_precio * 100) if st.session_state.receta_precio > 0 else 0.0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Costo Total Receta", f"${costo_total:,.2f}")
            c2.metric("Precio Sugerido", f"${precio_sug:,.2f}")
            c3.metric("Food Cost %", f"{fc_pct:.1f}%")
            c4.metric("Margen Bruto", f"${st.session_state.receta_precio - costo_total:,.2f}" if st.session_state.receta_precio > 0 else "—")

            if st.button("💾 GUARDAR RECETA COMPLETA", type="primary", width="stretch"):
                nombre_final = st.session_state.receta_nombre.strip()
                if not nombre_final:
                    st.error("Escribe el nombre de la receta en el formulario superior.")
                elif len(st.session_state.ingredientes_receta) == 0:
                    st.error("La receta debe tener al menos un ingrediente.")
                else:
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
                                costo_ing = round(ing["cantidad"] * ing["costo_unit"], 4)
                                filas_guardar.append([
                                    nombre_final,
                                    ing["insumo"],
                                    ing["cantidad"],
                                    ing["unidad"],
                                    costo_ing,
                                    st.session_state.receta_precio,
                                    round((costo_ing / st.session_state.receta_precio * 100) if st.session_state.receta_precio > 0 else 0.0, 2),
                                    ts_hermosillo(),
                                    st.session_state.current_user
                                ])
                            ok, msg = append_rows_con_retry(ws_rec, filas_guardar)
                            if ok:
                                cargar_recetas.clear()
                                cargar_costos_insumos.clear()
                                st.success(f"Receta '{nombre_final}' guardada ({len(filas_guardar)} ingredientes).")
                                st.session_state.ingredientes_receta = []
                                st.session_state.receta_nombre = ""
                                st.session_state.receta_precio = 0.0
                                st.session_state.receta_modo = "Nueva receta"
                                st.session_state.receta_original = ""
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error(msg)
                        except Exception as e:
                            st.error(f"Error al guardar: {e}")
        else:
            st.info("No hay ingredientes. Usa el botón 'Agregar a la receta' para comenzar.")
        if not df_rec.empty:
            st.subheader("📋 Recetas registradas")
            st.dataframe(df_rec, hide_index=True, width="stretch")
