import streamlit as st
import pandas as pd
import time
import uuid
from data_loaders import (
    cargar_recetas, cargar_costos_insumos, cargar_combos,
    cargar_costos_actuales_recetas
)
from sheets import _asegurar_hoja_menus, _asegurar_hoja_historial_menus, append_rows_con_retry, safe_worksheet, sh
from utils import limpiar_valor, ts_hermosillo, normalizar_nombre
from config import COLS_MENUS, COLS_MENUS_HISTORIAL
from components.avisos import mostrar_avisos
from auth import tiene_permiso


@st.cache_data(ttl=120)
def cargar_menus():
    """Lee la hoja Menus y devuelve un DataFrame con los productos del menú."""
    ws, err = safe_worksheet(sh, "Menus")
    if err:
        ws, err2 = _asegurar_hoja_menus()
        if err2:
            return pd.DataFrame(columns=COLS_MENUS + ["Notas", "Incluir_KPI"])
        return pd.DataFrame(columns=COLS_MENUS + ["Notas", "Incluir_KPI"])
    try:
        datos = ws.get_all_values()
        if len(datos) <= 1:
            return pd.DataFrame(columns=COLS_MENUS + ["Notas", "Incluir_KPI"])
        headers = datos[0]
        df = pd.DataFrame(datos[1:], columns=headers)
        # Rellenar columnas faltantes
        for col in COLS_MENUS + ["Notas", "Incluir_KPI"]:
            if col not in df.columns:
                if col == "Menu_Nombre":
                    df[col] = "Menú Actual"
                elif col == "Incluir_KPI":
                    df[col] = "TRUE"
                else:
                    df[col] = ""
        for col in ["Precio_Venta", "Costo_Neto", "Food_Cost_Pct", "Margen_Bruto"]:
            if col in df.columns:
                df[col] = df[col].apply(limpiar_valor)
        # Normalizar Incluir_KPI a booleano
        def _parse_bool(v):
            s = str(v).strip().upper()
            return s in ["TRUE", "1", "SÍ", "SI", "YES"]
        if "Incluir_KPI" in df.columns:
            df["Incluir_KPI"] = df["Incluir_KPI"].apply(_parse_bool)
        return df
    except Exception as e:
        st.warning(f"Error cargando menú: {e}")
        return pd.DataFrame(columns=COLS_MENUS + ["Notas", "Incluir_KPI"])


def _guardar_historial_menu(menu_id, nombre_menu, producto, precio_anterior, precio_nuevo, responsable):
    ws_hist, err = _asegurar_hoja_historial_menus()
    if err:
        return
    fila = [str(uuid.uuid4())[:8], nombre_menu, producto,
            precio_anterior, precio_nuevo, ts_hermosillo(), responsable]
    append_rows_con_retry(ws_hist, [fila])


def show_menu_maker():
    if not tiene_permiso("MenuMaker"):
        st.error("No tienes permiso para esta página.")
        st.stop()

    st.title("🍽️ Menú Maker")
    mostrar_avisos("MenuMaker")

    if not st.session_state.auth_status:
        st.error("🔒 Autenticación requerida.")
        st.stop()

    if st.session_state.user_role != "admin":
        st.error("🚫 Solo administradores pueden gestionar el menú.")
        st.stop()

    df_rec = cargar_recetas()
    df_combos = cargar_combos()
    df_menus = cargar_menus()

    if df_rec.empty and df_combos.empty:
        st.warning("No hay recetas ni combos capturados. Primero crea recetas o combos en 'Base de Costos'.")
        st.stop()

    # Costos actuales dinámicos
    df_costos_act = cargar_costos_actuales_recetas()
    if not df_costos_act.empty:
        costo_por_receta = dict(zip(df_costos_act["Receta"], df_costos_act["Costo_Actual"]))
    else:
        costo_por_receta = {}

    costo_por_combo = {}
    if not df_combos.empty:
        for combo, grupo in df_combos.groupby("Combo"):
            costo_por_combo[combo] = grupo["Costo_Total_Componente"].apply(limpiar_valor).sum()

    tab_crear, tab_ver, tab_comparar = st.tabs(["➕ Agregar / Editar Producto", "📋 Menú Actual", "📊 Comparar Menús"])

    # ==================== TAB AGREGAR / EDITAR ====================
    with tab_crear:
        st.subheader("Agregar o actualizar producto del menú")

        # ⚡ CARGA VISUAL MEJORADA
        with st.expander("⚡ Cargar productos al menú (selección visual)", expanded=False):
            st.markdown("Selecciona recetas/combos para agregarlos al menú. Podrás editar categoría y KPIs antes de guardar.")
            # Selector de menú destino
            menús_existentes = sorted(df_menus["Menu_Nombre"].dropna().unique().tolist()) if not df_menus.empty else ["Menú Actual"]
            if not menús_existentes:
                menús_existentes = ["Menú Actual"]
            menu_destino_carga = st.selectbox("Menú destino:", menús_existentes + ["Nuevo menú"], key="menu_destino_carga")
            if menu_destino_carga == "Nuevo menú":
                nuevo_menu_nombre = st.text_input("Nombre del nuevo menú:", value="", key="nuevo_menu_nombre")
            else:
                nuevo_menu_nombre = ""

            opciones_carga = []
            if not df_rec.empty:
                for _, r in df_rec.drop_duplicates(subset=["Receta"]).iterrows():
                    opciones_carga.append(f"🍽️ {r['Receta']} (Receta)")
            if not df_combos.empty:
                for _, c in df_combos.drop_duplicates(subset=["Combo"]).iterrows():
                    opciones_carga.append(f"🍱 {c['Combo']} (Combo)")
            opciones_carga = sorted(opciones_carga)

            seleccion = st.multiselect("Productos a agregar:", opciones_carga, key="menu_carga_multiselect")

            if seleccion:
                productos_seleccionados = []
                for s in seleccion:
                    tipo = "Receta" if "(Receta)" in s else "Combo"
                    nombre_real = s.split(" (")[0].replace("🍽️ ", "").replace("🍱 ", "")
                    if tipo == "Receta":
                        categoria = str(df_rec[df_rec["Receta"] == nombre_real].iloc[0].get("Linea", ""))
                        costo_neto = costo_por_receta.get(nombre_real, 0.0)
                    else:
                        categoria = str(df_combos[df_combos["Combo"] == nombre_real].iloc[0].get("Linea", ""))
                        costo_neto = costo_por_combo.get(nombre_real, 0.0)

                    precio_venta = limpiar_valor(
                        df_rec[df_rec["Receta"] == nombre_real].iloc[0].get("Precio_Venta", 0)
                        if tipo == "Receta"
                        else df_combos[df_combos["Combo"] == nombre_real].iloc[0].get("Precio_Venta", 0)
                    )

                    productos_seleccionados.append({
                        "Producto": nombre_real,
                        "Tipo": tipo,
                        "Categoria": categoria,
                        "Incluir_KPI": True,
                        "Precio_Venta": precio_venta,
                        "Costo_Neto": costo_neto,
                    })

                df_editor = pd.DataFrame(productos_seleccionados)

                if not df_menus.empty:
                    claves_existentes = set(
                        (str(r["Producto"]), str(r["Tipo_Producto"]), str(r.get("Menu_Nombre","")))
                        for _, r in df_menus.iterrows()
                    )
                    df_editor["_Existe"] = df_editor.apply(
                        lambda row: (row["Producto"], row["Tipo"], menu_destino_carga if menu_destino_carga != "Nuevo menú" else nuevo_menu_nombre) in claves_existentes,
                        axis=1
                    )
                else:
                    df_editor["_Existe"] = False

                st.write("**Edita los valores antes de guardar:**")
                edited_df = st.data_editor(
                    df_editor,
                    column_config={
                        "Producto": st.column_config.TextColumn(disabled=True),
                        "Tipo": st.column_config.TextColumn(disabled=True),
                        "Categoria": st.column_config.TextColumn("Categoría"),
                        "Incluir_KPI": st.column_config.CheckboxColumn("Incluir en KPIs"),
                        "Precio_Venta": st.column_config.NumberColumn("Precio ($)", min_value=0.0, step=1.0),
                        "Costo_Neto": st.column_config.NumberColumn("Costo ($)", disabled=True),
                        "_Existe": st.column_config.CheckboxColumn("Ya existe", disabled=True),
                    },
                    hide_index=True,
                    width="stretch",
                    key="editor_carga_visual"
                )

                duplicados = edited_df[edited_df["_Existe"]].shape[0]
                if duplicados > 0:
                    st.warning(f"⚠️ {duplicados} producto(s) ya existen en este menú y serán omitidos.")

                if st.button("💾 Guardar seleccionados en menú", key="btn_guardar_carga_visual", type="primary", width="stretch"):
                    ws_menu, err_menu = _asegurar_hoja_menus()
                    if err_menu:
                        st.error(err_menu)
                    else:
                        guardados = 0
                        omitidos = 0
                        menu_nombre_final = nuevo_menu_nombre.strip() if menu_destino_carga == "Nuevo menú" and nuevo_menu_nombre.strip() else menu_destino_carga
                        if not menu_nombre_final:
                            st.error("Debes escribir un nombre para el nuevo menú.")
                            st.stop()
                        for _, row in edited_df.iterrows():
                            if row["_Existe"]:
                                omitidos += 1
                                continue

                            nombre_producto = row["Producto"]
                            tipo_producto = row["Tipo"]
                            categoria = row["Categoria"] if str(row["Categoria"]).strip() else "Sin categoría"
                            incluir_kpi = bool(row["Incluir_KPI"])
                            precio_venta = float(row["Precio_Venta"])
                            costo_neto = float(row["Costo_Neto"])

                            if precio_venta <= 0:
                                continue

                            food_cost = round((costo_neto / precio_venta * 100), 2) if precio_venta > 0 else 0.0
                            margen_bruto = round(precio_venta - costo_neto, 2)

                            menu_id = str(uuid.uuid4())[:8]
                            nueva_fila = [
                                menu_id,
                                menu_nombre_final,
                                nombre_producto,
                                categoria,
                                tipo_producto,
                                nombre_producto,
                                precio_venta,
                                costo_neto,
                                food_cost,
                                margen_bruto,
                                "TRUE",
                                ts_hermosillo(),
                                st.session_state.current_user,
                                "",
                                "TRUE" if incluir_kpi else "FALSE"
                            ]
                            append_rows_con_retry(ws_menu, [nueva_fila])
                            guardados += 1

                        cargar_menus.clear()
                        st.success(f"{guardados} producto(s) guardado(s) en '{menu_nombre_final}'. {omitidos} omitido(s).")
                        time.sleep(0.5)
                        st.rerun()
            else:
                st.info("Selecciona al menos un producto.")
        st.divider()

        tipo_producto_sel = st.radio(
            "¿Qué tipo de producto quieres agregar?",
            ["Receta", "Combo", "Reventa"],
            horizontal=True,
            key="tipo_producto_menu"
        )

        if tipo_producto_sel == "Receta":
            if df_rec.empty:
                st.info("No hay recetas disponibles.")
                st.stop()
            opciones = sorted(df_rec["Receta"].unique().tolist())
            titulo_opciones = "Selecciona una receta existente:"
        elif tipo_producto_sel == "Combo":
            if df_combos.empty:
                st.info("No hay combos disponibles.")
                st.stop()
            opciones = sorted(df_combos["Combo"].unique().tolist())
            titulo_opciones = "Selecciona un combo existente:"
        else:
            opciones = []
            titulo_opciones = ""

        if tipo_producto_sel in ["Receta", "Combo"]:
            prod_sel = st.selectbox(titulo_opciones, opciones, key="menu_prod_sel")

            if tipo_producto_sel == "Receta":
                df_fila = df_rec[df_rec["Receta"] == prod_sel].iloc[0]
                costo_neto_prod = costo_por_receta.get(prod_sel, 0.0)
                precio_prod = limpiar_valor(df_fila.get("Precio_Venta", 0))
                linea_prod = str(df_fila.get("Linea", ""))
                nombre_producto = prod_sel
            else:
                df_fila = df_combos[df_combos["Combo"] == prod_sel].iloc[0]
                costo_neto_prod = costo_por_combo.get(prod_sel, 0.0)
                precio_prod = limpiar_valor(df_fila.get("Precio_Venta", 0))
                linea_prod = str(df_fila.get("Linea", ""))
                nombre_producto = prod_sel

            existe_menu = False
            menu_previo = None
            if not df_menus.empty:
                mask = (df_menus["Producto"] == nombre_producto) & (df_menus["Tipo_Producto"] == ("Receta" if tipo_producto_sel == "Receta" else "Combo"))
                if mask.any():
                    existe_menu = True
                    menu_previo = df_menus[mask].iloc[0]

            # Selector de menú destino
            menús_existentes = sorted(df_menus["Menu_Nombre"].dropna().unique().tolist()) if not df_menus.empty else ["Menú Actual"]
            if not menús_existentes:
                menús_existentes = ["Menú Actual"]
            menu_destino = st.selectbox("Menú:", menús_existentes + ["Nuevo menú"], key="menu_destino_individual")
            if menu_destino == "Nuevo menú":
                nuevo_menu_nombre_ind = st.text_input("Nombre del nuevo menú:", value="", key="nuevo_menu_nombre_individual")
            else:
                nuevo_menu_nombre_ind = ""

            with st.form("f_menu_maker", clear_on_submit=False):
                col1, col2 = st.columns(2)
                with col1:
                    categoria = st.text_input(
                        "Categoría del menú:",
                        value=str(menu_previo.get("Categoria_Menu", linea_prod)) if existe_menu else linea_prod,
                        help="Puedes usar la línea/categoría del producto o escribir una propia."
                    )
                    tipo_interno = st.selectbox(
                        "Tipo de producto:",
                        ["Bebida", "Alimento", "Postre", "Snack", "Combo", "Otro"],
                        index=["Bebida", "Alimento", "Postre", "Snack", "Combo", "Otro"].index(
                            str(menu_previo.get("Tipo_Producto", "Bebida"))
                        ) if existe_menu and str(menu_previo.get("Tipo_Producto", "Bebida")) in
                           ["Bebida", "Alimento", "Postre", "Snack", "Combo", "Otro"] else 0
                    )
                    activo = st.toggle(
                        "Producto activo en menú",
                        value=bool(str(menu_previo.get("Activo", "TRUE")).strip().upper() == "TRUE") if existe_menu else True
                    )
                    incluir_kpi = st.toggle(
                        "Incluir en KPIs",
                        value=bool(menu_previo.get("Incluir_KPI", True)) if existe_menu else True,
                        help="Si está desactivado, este producto no se contará en los promedios ni totales de KPIs del menú."
                    )
                with col2:
                    precio_venta = st.number_input(
                        "Precio de venta ($):",
                        min_value=0.0,
                        step=1.0,
                        value=float(menu_previo.get("Precio_Venta", precio_prod)) if existe_menu else float(precio_prod)
                    )
                    st.caption(f"Costo neto: **${costo_neto_prod:,.2f}**")
                    if precio_venta > 0 and costo_neto_prod > 0:
                        fc = costo_neto_prod / precio_venta * 100
                        margen = precio_venta - costo_neto_prod
                        st.caption(f"Food cost: **{fc:.1f}%** | Margen bruto: **${margen:,.2f}**")

                notas = st.text_area("Notas (opcional):", value=str(menu_previo.get("Notas", "")) if existe_menu else "")

                enviar = st.form_submit_button("💾 Guardar en Menú", type="primary", width="stretch")

            if enviar:
                if precio_venta <= 0:
                    st.error("El precio de venta debe ser mayor a cero.")
                else:
                    menu_nombre_final = nuevo_menu_nombre_ind.strip() if menu_destino == "Nuevo menú" and nuevo_menu_nombre_ind.strip() else menu_destino
                    if not menu_nombre_final:
                        st.error("Debes escribir un nombre para el nuevo menú.")
                    else:
                        costo_neto = costo_neto_prod
                        food_cost = (costo_neto / precio_venta * 100) if precio_venta > 0 else 0.0
                        margen_bruto = precio_venta - costo_neto

                        ws_menu, err_menu = _asegurar_hoja_menus()
                        if err_menu:
                            st.error(err_menu)
                        else:
                            try:
                                if existe_menu:
                                    menu_id = str(menu_previo.get("Menu_ID", ""))
                                    todos = ws_menu.get_all_values()
                                    fila_actualizar = None
                                    for i, fila in enumerate(todos[1:], start=2):
                                        if fila[0] == menu_id:
                                            fila_actualizar = i
                                            break
                                    if fila_actualizar is None:
                                        st.error("No se pudo localizar el registro en Menus.")
                                        st.stop()
                                    precio_anterior = limpiar_valor(menu_previo.get("Precio_Venta", 0))
                                    nueva_fila = [
                                        menu_id,
                                        menu_nombre_final,
                                        nombre_producto,
                                        categoria,
                                        tipo_interno,
                                        nombre_producto,
                                        precio_venta,
                                        costo_neto,
                                        round(food_cost, 2),
                                        margen_bruto,
                                        "TRUE" if activo else "FALSE",
                                        menu_previo.get("Fecha_Captura", ts_hermosillo()),
                                        st.session_state.current_user,
                                        notas,
                                        "TRUE" if incluir_kpi else "FALSE"
                                    ]
                                    ws_menu.update(range_name=f"A{fila_actualizar}:O{fila_actualizar}", values=[nueva_fila])
                                    if abs(precio_anterior - precio_venta) > 0.001:
                                        _guardar_historial_menu(menu_id, nombre_producto, nombre_producto,
                                                                precio_anterior, precio_venta,
                                                                st.session_state.current_user)
                                    st.success(f"Producto '{nombre_producto}' actualizado en '{menu_nombre_final}'.")
                                else:
                                    menu_id = str(uuid.uuid4())[:8]
                                    nueva_fila = [
                                        menu_id,
                                        menu_nombre_final,
                                        nombre_producto,
                                        categoria,
                                        tipo_interno,
                                        nombre_producto,
                                        precio_venta,
                                        costo_neto,
                                        round(food_cost, 2),
                                        margen_bruto,
                                        "TRUE" if activo else "FALSE",
                                        ts_hermosillo(),
                                        st.session_state.current_user,
                                        notas,
                                        "TRUE" if incluir_kpi else "FALSE"
                                    ]
                                    ok, msg = append_rows_con_retry(ws_menu, [nueva_fila])
                                    if not ok:
                                        st.error(msg)
                                        st.stop()
                                    _guardar_historial_menu(menu_id, nombre_producto, nombre_producto,
                                                            0.0, precio_venta,
                                                            st.session_state.current_user)
                                    st.success(f"Producto '{nombre_producto}' agregado a '{menu_nombre_final}'.")
                                cargar_menus.clear()
                                time.sleep(0.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al guardar en Menú: {e}")
        else:  # REVENTA
            st.markdown("Producto de reventa (no requiere receta ni combo).")

            df_costos_rev = cargar_costos_insumos()
            if not df_costos_rev.empty:
                ultimos_costos_rev = df_costos_rev.sort_values("Fecha_Captura").drop_duplicates(subset=["Nombre_Insumo"], keep="last")
                lista_insumos_rev = sorted(ultimos_costos_rev["Nombre_Insumo"].dropna().unique().tolist())
            else:
                ultimos_costos_rev = pd.DataFrame()
                lista_insumos_rev = []

            usar_vinculo = st.checkbox("Vincular con insumo existente (precargar costo)", key="rev_vinculo")
            costo_sugerido = 0.0
            nombre_sugerido = ""
            if usar_vinculo and lista_insumos_rev:
                insumo_vinculado = st.selectbox("Insumo:", [""] + lista_insumos_rev, key="rev_insumo_sel")
                if insumo_vinculado:
                    mask = ultimos_costos_rev["Nombre_Insumo"] == insumo_vinculado
                    if mask.any():
                        fila_costo = ultimos_costos_rev[mask].iloc[0]
                        costo_sugerido = limpiar_valor(fila_costo.get("Costo_Unitario", 0))
                        nombre_sugerido = insumo_vinculado
            elif usar_vinculo:
                st.info("No hay insumos con costo registrado para vincular.")

            producto_nombre_reventa = st.text_input("Nombre del producto:", value=nombre_sugerido, key="rev_nombre")

            # Menú destino
            menús_existentes = sorted(df_menus["Menu_Nombre"].dropna().unique().tolist()) if not df_menus.empty else ["Menú Actual"]
            if not menús_existentes:
                menús_existentes = ["Menú Actual"]
            menu_destino_rev = st.selectbox("Menú:", menús_existentes + ["Nuevo menú"], key="menu_destino_reventa")
            if menu_destino_rev == "Nuevo menú":
                nuevo_menu_rev = st.text_input("Nombre del nuevo menú:", value="", key="nuevo_menu_rev")
            else:
                nuevo_menu_rev = ""

            existe_menu = False
            menu_previo = None
            if producto_nombre_reventa.strip() and not df_menus.empty:
                mask = (df_menus["Nombre_Menu"] == producto_nombre_reventa.strip()) & (df_menus["Tipo_Producto"] == "Reventa")
                if mask.any():
                    existe_menu = True
                    menu_previo = df_menus[mask].iloc[0]

            with st.form("f_menu_reventa", clear_on_submit=False):
                col1, col2 = st.columns(2)
                with col1:
                    categoria = st.text_input(
                        "Categoría:",
                        value=str(menu_previo.get("Categoria_Menu", "Reventa")) if existe_menu else "Reventa"
                    )
                    tipo_interno = st.selectbox(
                        "Tipo de producto:",
                        ["Bebida", "Alimento", "Snack", "Otro"],
                        index=["Bebida", "Alimento", "Snack", "Otro"].index(
                            str(menu_previo.get("Tipo_Producto", "Otro"))
                        ) if existe_menu and str(menu_previo.get("Tipo_Producto", "Otro")) in
                           ["Bebida", "Alimento", "Snack", "Otro"] else 3
                    )
                    activo = st.toggle(
                        "Producto activo en menú",
                        value=bool(str(menu_previo.get("Activo", "TRUE")).strip().upper() == "TRUE") if existe_menu else True
                    )
                    incluir_kpi = st.toggle(
                        "Incluir en KPIs",
                        value=bool(menu_previo.get("Incluir_KPI", True)) if existe_menu else True,
                        help="Si está desactivado, este producto no se contará en los promedios ni totales de KPIs."
                    )
                with col2:
                    precio_venta = st.number_input(
                        "Precio de venta ($):",
                        min_value=0.0,
                        step=1.0,
                        value=float(menu_previo.get("Precio_Venta", 0.0)) if existe_menu else 0.0
                    )
                    costo_compra_default = float(menu_previo.get("Costo_Neto", costo_sugerido)) if existe_menu else float(costo_sugerido)
                    costo_compra = st.number_input(
                        "Costo de compra ($):",
                        min_value=0.0,
                        step=0.5,
                        value=costo_compra_default,
                        help="Lo que pagas por el producto para revenderlo."
                    )
                    if precio_venta > 0 and costo_compra > 0:
                        fc = costo_compra / precio_venta * 100
                        margen = precio_venta - costo_compra
                        st.caption(f"Food cost: **{fc:.1f}%** | Margen bruto: **${margen:,.2f}**")

                notas = st.text_area("Notas (opcional):", value=str(menu_previo.get("Notas", "")) if existe_menu else "")

                enviar = st.form_submit_button("💾 Guardar en Menú", type="primary", width="stretch")

            if enviar:
                if not producto_nombre_reventa.strip():
                    st.error("El nombre del producto es obligatorio.")
                elif precio_venta <= 0:
                    st.error("El precio de venta debe ser mayor a cero.")
                else:
                    menu_nombre_final = nuevo_menu_rev.strip() if menu_destino_rev == "Nuevo menú" and nuevo_menu_rev.strip() else menu_destino_rev
                    if not menu_nombre_final:
                        st.error("Debes escribir un nombre para el nuevo menú.")
                    else:
                        costo_neto = costo_compra
                        food_cost = (costo_neto / precio_venta * 100) if precio_venta > 0 else 0.0
                        margen_bruto = precio_venta - costo_neto

                        ws_menu, err_menu = _asegurar_hoja_menus()
                        if err_menu:
                            st.error(err_menu)
                        else:
                            try:
                                if existe_menu:
                                    menu_id = str(menu_previo.get("Menu_ID", ""))
                                    todos = ws_menu.get_all_values()
                                    fila_actualizar = None
                                    for i, fila in enumerate(todos[1:], start=2):
                                        if fila[0] == menu_id:
                                            fila_actualizar = i
                                            break
                                    if fila_actualizar is None:
                                        st.error("No se pudo localizar el registro en Menus.")
                                        st.stop()
                                    precio_anterior = limpiar_valor(menu_previo.get("Precio_Venta", 0))
                                    nueva_fila = [
                                        menu_id,
                                        menu_nombre_final,
                                        producto_nombre_reventa.strip(),
                                        categoria,
                                        "Reventa",
                                        producto_nombre_reventa.strip(),
                                        precio_venta,
                                        costo_neto,
                                        round(food_cost, 2),
                                        margen_bruto,
                                        "TRUE" if activo else "FALSE",
                                        menu_previo.get("Fecha_Captura", ts_hermosillo()),
                                        st.session_state.current_user,
                                        notas,
                                        "TRUE" if incluir_kpi else "FALSE"
                                    ]
                                    ws_menu.update(range_name=f"A{fila_actualizar}:O{fila_actualizar}", values=[nueva_fila])
                                    if abs(precio_anterior - precio_venta) > 0.001:
                                        _guardar_historial_menu(menu_id, producto_nombre_reventa.strip(), producto_nombre_reventa.strip(),
                                                                precio_anterior, precio_venta,
                                                                st.session_state.current_user)
                                    st.success(f"Producto '{producto_nombre_reventa.strip()}' actualizado en '{menu_nombre_final}'.")
                                else:
                                    menu_id = str(uuid.uuid4())[:8]
                                    nueva_fila = [
                                        menu_id,
                                        menu_nombre_final,
                                        producto_nombre_reventa.strip(),
                                        categoria,
                                        "Reventa",
                                        producto_nombre_reventa.strip(),
                                        precio_venta,
                                        costo_neto,
                                        round(food_cost, 2),
                                        margen_bruto,
                                        "TRUE" if activo else "FALSE",
                                        ts_hermosillo(),
                                        st.session_state.current_user,
                                        notas,
                                        "TRUE" if incluir_kpi else "FALSE"
                                    ]
                                    ok, msg = append_rows_con_retry(ws_menu, [nueva_fila])
                                    if not ok:
                                        st.error(msg)
                                        st.stop()
                                    _guardar_historial_menu(menu_id, producto_nombre_reventa.strip(), producto_nombre_reventa.strip(),
                                                            0.0, precio_venta,
                                                            st.session_state.current_user)
                                    st.success(f"Producto '{producto_nombre_reventa.strip()}' agregado a '{menu_nombre_final}'.")
                                cargar_menus.clear()
                                time.sleep(0.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al guardar en Menú: {e}")

        if not df_menus.empty:
            st.divider()
            st.subheader("📋 Productos existentes")
            cols_show = ["Menu_Nombre", "Nombre_Menu", "Categoria_Menu", "Tipo_Producto", "Precio_Venta", "Costo_Neto", "Food_Cost_Pct", "Margen_Bruto", "Activo", "Incluir_KPI"]
            cols_ok = [c for c in cols_show if c in df_menus.columns]
            st.dataframe(df_menus[cols_ok], hide_index=True, width="stretch")
    # ==================== TAB MENÚ ACTUAL ====================
    with tab_ver:
        st.subheader("📋 Menú Actual y KPIs")
        if df_menus.empty:
            st.info("No hay productos en el menú. Agrega uno en la pestaña anterior.")
        else:
            # Selector de menú
            menús_disponibles = sorted(df_menus["Menu_Nombre"].dropna().unique().tolist())
            if not menús_disponibles:
                menús_disponibles = ["Menú Actual"]
            menu_sel_ver = st.selectbox("Seleccionar menú:", menús_disponibles, key="menu_sel_ver")
            df_menu_filtrado = df_menus[df_menus["Menu_Nombre"] == menu_sel_ver].copy()

            # Filtro por categoría
            categorias_disponibles = sorted(df_menu_filtrado["Categoria_Menu"].dropna().unique().tolist())
            filtro_cat = st.selectbox("Filtrar por categoría:", ["Todas"] + categorias_disponibles, key="menu_filtro_cat")
            if filtro_cat != "Todas":
                df_menu_filtrado = df_menu_filtrado[df_menu_filtrado["Categoria_Menu"] == filtro_cat]

            df_activos = df_menu_filtrado[df_menu_filtrado["Activo"].astype(str).str.upper() == "TRUE"].copy()

            if df_activos.empty:
                st.warning("No hay productos activos en este menú con los filtros seleccionados.")
            else:
                # Calcular costos dinámicos
                def obtener_costo_dinamico(row):
                    tipo = str(row.get("Tipo_Producto", ""))
                    nombre = str(row.get("Producto", ""))
                    if tipo == "Receta":
                        return costo_por_receta.get(nombre, limpiar_valor(row.get("Costo_Neto", 0)))
                    elif tipo == "Combo":
                        return costo_por_combo.get(nombre, limpiar_valor(row.get("Costo_Neto", 0)))
                    else:
                        return limpiar_valor(row.get("Costo_Neto", 0))

                df_activos["Costo_Actual_Dinamico"] = df_activos.apply(obtener_costo_dinamico, axis=1)
                df_activos["Food_Cost_Actual_Dinamico"] = df_activos.apply(
                    lambda row: round((row["Costo_Actual_Dinamico"] / row["Precio_Venta"] * 100), 2)
                    if row["Precio_Venta"] > 0 else 0.0, axis=1
                )
                df_activos["Margen_Actual_Dinamico"] = df_activos["Precio_Venta"] - df_activos["Costo_Actual_Dinamico"]

                df_kpi = df_activos[df_activos["Incluir_KPI"] == True].copy()
                df_no_kpi = df_activos[df_activos["Incluir_KPI"] != True].copy()

                total_prod_activos = len(df_activos)
                total_prod_kpi = len(df_kpi)
                if total_prod_kpi > 0:
                    precio_prom = df_kpi["Precio_Venta"].mean()
                    costo_prom = df_kpi["Costo_Actual_Dinamico"].mean()
                    fc_prom = df_kpi["Food_Cost_Actual_Dinamico"].mean()
                    margen_prom = df_kpi["Margen_Actual_Dinamico"].mean()
                    margen_pct_prom = ((df_kpi["Precio_Venta"] - df_kpi["Costo_Actual_Dinamico"]) / df_kpi["Precio_Venta"] * 100).replace([float('inf')], 0).fillna(0).mean()
                else:
                    precio_prom = costo_prom = fc_prom = margen_prom = margen_pct_prom = 0.0

                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Productos activos", total_prod_activos)
                m2.metric("Incluidos en KPIs", total_prod_kpi)
                m3.metric("Precio promedio", f"${precio_prom:,.2f}")
                m4.metric("Food Cost promedio", f"{fc_prom:.1f}%")
                m5.metric("Margen bruto prom.", f"${margen_prom:,.2f}")

                if total_prod_kpi == 0:
                    st.info("No hay productos que contribuyan a los KPIs. Activa 'Incluir en KPIs' en algunos productos para ver métricas.")

                st.divider()
                st.subheader("📊 KPIs por categoría (solo activos)")

                if total_prod_kpi > 0:
                    # Asegurar que solo categorías con productos activos e incluidos
                    df_cat = df_kpi.groupby("Categoria_Menu").agg(
                        Productos=("Menu_ID", "count"),
                        Precio_Promedio=("Precio_Venta", "mean"),
                        Costo_Promedio=("Costo_Actual_Dinamico", "mean"),
                        Food_Cost_Promedio=("Food_Cost_Actual_Dinamico", "mean"),
                        Margen_Bruto_Total=("Margen_Actual_Dinamico", "sum")
                    ).reset_index()
                    df_cat["Margen_Promedio"] = df_cat["Margen_Bruto_Total"] / df_cat["Productos"]
                    df_cat["Factor_Promedio"] = df_cat["Precio_Promedio"] / df_cat["Costo_Promedio"].replace(0, float('nan'))
                    df_cat["Factor_Promedio"] = df_cat["Factor_Promedio"].fillna(0).round(2)
                    st.dataframe(df_cat, hide_index=True, width="stretch")
                else:
                    st.info("Sin datos de KPIs por categoría.")

                st.divider()
                st.subheader("📄 Detalle del menú activo (filtrable)")

                # Selector de categoría para el detalle (por defecto "Todas", pero con opción de limitar)
                cat_detalle = st.selectbox("Mostrar productos de la categoría:", ["Todas"] + sorted(df_activos["Categoria_Menu"].dropna().unique().tolist()), key="cat_detalle")
                if cat_detalle != "Todas":
                    df_detalle = df_activos[df_activos["Categoria_Menu"] == cat_detalle]
                else:
                    df_detalle = df_activos

                # Tabla con columnas calculadas
                df_detalle_show = df_detalle.copy()
                df_detalle_show["Factor"] = (df_detalle_show["Precio_Venta"] / df_detalle_show["Costo_Actual_Dinamico"].replace(0, float('nan'))).fillna(0).round(2)
                df_detalle_show["Estado_KPI"] = df_detalle_show["Incluir_KPI"].apply(lambda x: "✅" if x else "❌")
                cols_det = ["Nombre_Menu", "Categoria_Menu", "Tipo_Producto", "Precio_Venta",
                            "Costo_Actual_Dinamico", "Food_Cost_Actual_Dinamico", "Margen_Actual_Dinamico",
                            "Factor", "Estado_KPI", "Responsable"]
                cols_det_ok = [c for c in cols_det if c in df_detalle_show.columns]
                st.dataframe(df_detalle_show[cols_det_ok].sort_values("Categoria_Menu"), hide_index=True, width="stretch")

                # Editor de precios en tiempo real (solo para el menú seleccionado)
                st.divider()
                with st.expander("✏️ Editar precios de venta del menú", expanded=False):
                    st.markdown("Modifica los precios y guarda para actualizar KPIs. Los cambios no se aplican hasta presionar guardar.")
                    df_editar_precios = df_activos[["Menu_ID", "Nombre_Menu", "Categoria_Menu", "Precio_Venta", "Costo_Actual_Dinamico"]].copy()
                    df_editar_precios = df_editar_precios.rename(columns={"Costo_Actual_Dinamico": "Costo_Neto"})
                    editado = st.data_editor(
                        df_editar_precios,
                        column_config={
                            "Menu_ID": st.column_config.TextColumn(disabled=True),
                            "Nombre_Menu": st.column_config.TextColumn(disabled=True),
                            "Categoria_Menu": st.column_config.TextColumn(disabled=True),
                            "Precio_Venta": st.column_config.NumberColumn("Precio", min_value=0.0, step=1.0),
                            "Costo_Neto": st.column_config.NumberColumn("Costo", disabled=True),
                        },
                        hide_index=True,
                        width="stretch",
                        key="editor_precios_menu"
                    )

                    # Mostrar KPIs calculados con precios editados (sin guardar)
                    if not editado.empty:
                        editado["Food_Cost"] = (editado["Costo_Neto"] / editado["Precio_Venta"] * 100).replace([float('inf')], 0).round(2)
                        editado["Margen"] = editado["Precio_Venta"] - editado["Costo_Neto"]
                        editado["Factor"] = (editado["Precio_Venta"] / editado["Costo_Neto"].replace(0, float('nan'))).fillna(0).round(2)
                        st.write("**Vista previa de KPIs con precios editados:**")
                        st.dataframe(editado[["Nombre_Menu", "Categoria_Menu", "Precio_Venta", "Costo_Neto", "Food_Cost", "Margen", "Factor"]], hide_index=True, width="stretch")
                        st.metric("Food Cost promedio (vista previa)", f"{editado['Food_Cost'].mean():.1f}%")
                        st.metric("Margen bruto total (vista previa)", f"${editado['Margen'].sum():,.2f}")

                    if st.button("💾 Guardar precios editados", key="btn_guardar_precios_menu"):
                        ws_menu_precios, err_precios = _asegurar_hoja_menus()
                        if err_precios:
                            st.error(err_precios)
                        else:
                            try:
                                todos_precios = ws_menu_precios.get_all_values()
                                for _, row in editado.iterrows():
                                    menu_id = row["Menu_ID"]
                                    nuevo_precio = row["Precio_Venta"]
                                    # Buscar fila y actualizar precio y KPIs
                                    for i, fila in enumerate(todos_precios[1:], start=2):
                                        if fila[0] == menu_id:
                                            costo_neto = limpiar_valor(row["Costo_Neto"])
                                            food_cost = (costo_neto / nuevo_precio * 100) if nuevo_precio > 0 else 0.0
                                            margen = nuevo_precio - costo_neto
                                            ws_menu_precios.update(range_name=f"G{i}:J{i}", values=[[nuevo_precio, costo_neto, round(food_cost,2), margen]])
                                            break
                                cargar_menus.clear()
                                st.success("✅ Precios actualizados correctamente.")
                                time.sleep(0.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al guardar precios: {e}")

                # Productos inactivos
                with st.expander("Ver productos inactivos de este menú", expanded=False):
                    df_inactivos = df_menu_filtrado[df_menu_filtrado["Activo"].astype(str).str.upper() != "TRUE"]
                    if not df_inactivos.empty:
                        st.dataframe(df_inactivos, hide_index=True, width="stretch")
                    else:
                        st.caption("No hay productos inactivos en este menú.")

                if not df_no_kpi.empty:
                    st.caption(f"⚠️ {len(df_no_kpi)} producto(s) excluido(s) de los KPIs.")
    # ==================== TAB COMPARAR MENÚS ====================
    with tab_comparar:
        st.subheader("📊 Comparar Menús")
        if df_menus.empty or len(df_menus["Menu_Nombre"].dropna().unique()) < 2:
            st.info("Necesitas al menos dos menús para comparar. Crea productos en diferentes menús usando la pestaña 'Agregar / Editar'.")
        else:
            menús_disponibles = sorted(df_menus["Menu_Nombre"].dropna().unique().tolist())
            col_comp1, col_comp2 = st.columns(2)
            with col_comp1:
                menu_a = st.selectbox("Menú A:", menús_disponibles, key="menu_comp_a")
            with col_comp2:
                menu_b = st.selectbox("Menú B:", [m for m in menús_disponibles if m != menu_a], key="menu_comp_b")

            df_a = df_menus[df_menus["Menu_Nombre"] == menu_a].copy()
            df_b = df_menus[df_menus["Menu_Nombre"] == menu_b].copy()

            # Filtrar activos
            df_a = df_a[df_a["Activo"].astype(str).str.upper() == "TRUE"]
            df_b = df_b[df_b["Activo"].astype(str).str.upper() == "TRUE"]

            # Calcular costos dinámicos para cada uno
            def preparar_df_comparacion(df):
                df["Costo_Actual_Dinamico"] = df.apply(obtener_costo_dinamico, axis=1)
                df["Food_Cost_Actual"] = df.apply(lambda row: (row["Costo_Actual_Dinamico"] / row["Precio_Venta"] * 100) if row["Precio_Venta"] > 0 else 0.0, axis=1)
                df["Margen_Actual"] = df["Precio_Venta"] - df["Costo_Actual_Dinamico"]
                df["Factor"] = (df["Precio_Venta"] / df["Costo_Actual_Dinamico"].replace(0, float('nan'))).fillna(0).round(2)
                return df[["Nombre_Menu", "Categoria_Menu", "Precio_Venta", "Costo_Actual_Dinamico", "Food_Cost_Actual", "Margen_Actual", "Factor"]]

            df_a_prep = preparar_df_comparacion(df_a)
            df_b_prep = preparar_df_comparacion(df_b)

            resumen_a = {
                "Menú": menu_a,
                "Productos": len(df_a_prep),
                "Precio Prom.": df_a_prep["Precio_Venta"].mean(),
                "Costo Prom.": df_a_prep["Costo_Actual_Dinamico"].mean(),
                "Food Cost Prom.": df_a_prep["Food_Cost_Actual"].mean(),
                "Margen Total": df_a_prep["Margen_Actual"].sum(),
            }
            resumen_b = {
                "Menú": menu_b,
                "Productos": len(df_b_prep),
                "Precio Prom.": df_b_prep["Precio_Venta"].mean(),
                "Costo Prom.": df_b_prep["Costo_Actual_Dinamico"].mean(),
                "Food Cost Prom.": df_b_prep["Food_Cost_Actual"].mean(),
                "Margen Total": df_b_prep["Margen_Actual"].sum(),
            }

            df_resumen = pd.DataFrame([resumen_a, resumen_b])
            st.dataframe(df_resumen, hide_index=True, width="stretch")

            st.divider()
            st.subheader(f"Detalle {menu_a}")
            st.dataframe(df_a_prep, hide_index=True, width="stretch")
            st.subheader(f"Detalle {menu_b}")
            st.dataframe(df_b_prep, hide_index=True, width="stretch")
