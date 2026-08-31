import streamlit as st
import pandas as pd
import time
import uuid
from data_loaders import cargar_recetas, cargar_costos_insumos, cargar_combos
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
            return pd.DataFrame(columns=COLS_MENUS + ["Incluir_KPI"])
        return pd.DataFrame(columns=COLS_MENUS + ["Incluir_KPI"])
    try:
        datos = ws.get_all_values()
        if len(datos) <= 1:
            return pd.DataFrame(columns=COLS_MENUS + ["Incluir_KPI"])
        headers = datos[0]
        df = pd.DataFrame(datos[1:], columns=headers)
        for col in COLS_MENUS + ["Incluir_KPI"]:
            if col not in df.columns:
                df[col] = "TRUE" if col == "Incluir_KPI" else ""
        for col in ["Precio_Venta", "Costo_Neto", "Food_Cost_Pct", "Margen_Bruto"]:
            if col in df.columns:
                df[col] = df[col].apply(limpiar_valor)
        return df
    except Exception as e:
        st.warning(f"Error cargando menú: {e}")
        return pd.DataFrame(columns=COLS_MENUS + ["Incluir_KPI"])


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

    tab_crear, tab_ver = st.tabs(["➕ Agregar / Editar Producto", "📋 Menú Actual"])

    # ==================== TAB AGREGAR / EDITAR ====================
    with tab_crear:
        st.subheader("Agregar o actualizar producto del menú")

        # ⚡ CARGAR MENÚ DESDE LISTADO
        with st.expander("⚡ Cargar menú desde listado", expanded=False):
            st.markdown("""
            Pega una lista de nombres de productos (uno por línea).  
            El sistema buscará coincidencias con recetas y combos existentes.  
            Podrás guardar automáticamente los que encuentre.
            """)
            texto_menu = st.text_area("Lista de productos:", height=200, key="menu_carga_texto")

            if st.button("🔍 Previsualizar coincidencias"):
                nombres = [n.strip() for n in texto_menu.splitlines() if n.strip()]
                if not nombres:
                    st.error("Pega al menos un nombre.")
                else:
                    recetas_norm = {normalizar_nombre(r): r for r in df_rec["Receta"].unique()} if not df_rec.empty else {}
                    combos_norm = {normalizar_nombre(c): c for c in df_combos["Combo"].unique()} if not df_combos.empty else {}
                    resultados = []
                    for n in nombres:
                        n_norm = normalizar_nombre(n)
                        tipo = None
                        nombre_real = ""
                        precio = 0.0
                        if n_norm in recetas_norm:
                            tipo = "Receta"
                            nombre_real = recetas_norm[n_norm]
                            df_fila = df_rec[df_rec["Receta"] == nombre_real].iloc[0]
                            precio = limpiar_valor(df_fila.get("Precio_Venta", 0))
                        elif n_norm in combos_norm:
                            tipo = "Combo"
                            nombre_real = combos_norm[n_norm]
                            df_fila = df_combos[df_combos["Combo"] == nombre_real].iloc[0]
                            precio = limpiar_valor(df_fila.get("Precio_Venta", 0))
                        resultados.append({"nombre": n, "tipo": tipo, "nombre_real": nombre_real, "precio": precio})
                    st.session_state["menu_carga_resultados"] = resultados
                    st.rerun()

            if "menu_carga_resultados" in st.session_state and st.session_state["menu_carga_resultados"]:
                st.write("**Resultados**")
                for res in st.session_state["menu_carga_resultados"]:
                    col1, col2, col3 = st.columns([2,1,1])
                    with col1:
                        st.write(res["nombre"])
                    with col2:
                        st.write(res["tipo"] if res["tipo"] else "No encontrado")
                    with col3:
                        if res["tipo"]:
                            st.write(f"${res['precio']:,.2f}")
                        else:
                            st.write("—")

                if st.button("💾 Guardar coincidencias en menú"):
                    ws_menu, err_menu = _asegurar_hoja_menus()
                    if err_menu:
                        st.error(err_menu)
                    else:
                        guardados = 0
                        for res in st.session_state["menu_carga_resultados"]:
                            if res["tipo"] not in ["Receta", "Combo"]:
                                continue
                            nombre_producto = res["nombre_real"]
                            tipo_interno = res["tipo"]
                            if tipo_interno == "Receta":
                                df_fila = df_rec[df_rec["Receta"] == nombre_producto].iloc[0]
                                categoria = str(df_fila.get("Linea", ""))
                                costo_neto = limpiar_valor(df_fila.get("Costo_Neto_Receta", 0)) or limpiar_valor(df_fila.get("Costo_Ingrediente", 0))
                            else:
                                df_fila = df_combos[df_combos["Combo"] == nombre_producto].iloc[0]
                                categoria = str(df_fila.get("Linea", ""))
                                costo_neto = limpiar_valor(df_fila.get("Costo_Neto_Combo", 0))
                            precio_venta = res["precio"]
                            if precio_venta <= 0:
                                continue
                            food_cost = (costo_neto / precio_venta * 100) if precio_venta > 0 else 0.0
                            margen_bruto = precio_venta - costo_neto
                            menu_id = str(uuid.uuid4())[:8]
                            nueva_fila = [
                                menu_id,
                                nombre_producto,
                                categoria,
                                tipo_interno,
                                nombre_producto,
                                precio_venta,
                                costo_neto,
                                round(food_cost, 2),
                                margen_bruto,
                                "TRUE",
                                ts_hermosillo(),
                                st.session_state.current_user,
                                "",
                                "TRUE"
                            ]
                            append_rows_con_retry(ws_menu, [nueva_fila])
                            guardados += 1
                        cargar_menus.clear()
                        st.success(f"{guardados} productos guardados en el menú.")
                        del st.session_state["menu_carga_resultados"]
                        time.sleep(0.5)
                        st.rerun()

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
                costo_neto_prod = limpiar_valor(df_fila.get("Costo_Neto_Receta", 0)) or limpiar_valor(df_fila.get("Costo_Ingrediente", 0))
                precio_prod = limpiar_valor(df_fila.get("Precio_Venta", 0))
                linea_prod = str(df_fila.get("Linea", ""))
                nombre_producto = prod_sel
            else:
                df_fila = df_combos[df_combos["Combo"] == prod_sel].iloc[0]
                costo_neto_prod = limpiar_valor(df_fila.get("Costo_Neto_Combo", 0))
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
                        value=bool(str(menu_previo.get("Incluir_KPI", "TRUE")).strip().upper() == "TRUE") if existe_menu else True,
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
                                ws_menu.update(range_name=f"A{fila_actualizar}:N{fila_actualizar}", values=[nueva_fila])
                                if abs(precio_anterior - precio_venta) > 0.001:
                                    _guardar_historial_menu(menu_id, nombre_producto, nombre_producto,
                                                            precio_anterior, precio_venta,
                                                            st.session_state.current_user)
                                st.success(f"Producto '{nombre_producto}' actualizado.")
                            else:
                                menu_id = str(uuid.uuid4())[:8]
                                nueva_fila = [
                                    menu_id,
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
                                st.success(f"Producto '{nombre_producto}' agregado al menú.")
                            cargar_menus.clear()
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al guardar en Menú: {e}")

        else:  # REVENTA
            st.markdown("Producto de reventa (no requiere receta ni combo).")

            # --- Vinculación opcional con catálogo ---
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

            producto_nombre_reventa = st.text_input(
                "Nombre del producto:",
                value=nombre_sugerido,
                key="rev_nombre"
            )

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
                        value=bool(str(menu_previo.get("Incluir_KPI", "TRUE")).strip().upper() == "TRUE") if existe_menu else True,
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
                                ws_menu.update(range_name=f"A{fila_actualizar}:N{fila_actualizar}", values=[nueva_fila])
                                if abs(precio_anterior - precio_venta) > 0.001:
                                    _guardar_historial_menu(menu_id, producto_nombre_reventa.strip(), producto_nombre_reventa.strip(),
                                                            precio_anterior, precio_venta,
                                                            st.session_state.current_user)
                                st.success(f"Producto '{producto_nombre_reventa.strip()}' actualizado.")
                            else:
                                menu_id = str(uuid.uuid4())[:8]
                                nueva_fila = [
                                    menu_id,
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
                                st.success(f"Producto '{producto_nombre_reventa.strip()}' agregado al menú.")
                            cargar_menus.clear()
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al guardar en Menú: {e}")

        # Tabla de productos existentes
        if not df_menus.empty:
            st.divider()
            st.subheader("📋 Productos existentes")
            cols_show = ["Menu_ID", "Nombre_Menu", "Categoria_Menu", "Tipo_Producto",
                         "Precio_Venta", "Costo_Neto", "Food_Cost_Pct", "Margen_Bruto",
                         "Activo", "Incluir_KPI", "Responsable"]
            cols_ok = [c for c in cols_show if c in df_menus.columns]
            st.dataframe(df_menus[cols_ok], hide_index=True, width="stretch")

    # ==================== TAB MENÚ ACTUAL ====================
    with tab_ver:
        st.subheader("📋 Menú actual y KPIs")
        if df_menus.empty:
            st.info("No hay productos en el menú. Agrega uno en la pestaña anterior.")
        else:
            categorias_disponibles = sorted(df_menus["Categoria_Menu"].dropna().unique().tolist())
            filtro_cat = st.selectbox("Filtrar por categoría:", ["Todas"] + categorias_disponibles, key="menu_filtro_cat")

            df_filtrado = df_menus.copy()
            if filtro_cat != "Todas":
                df_filtrado = df_filtrado[df_filtrado["Categoria_Menu"] == filtro_cat]

            df_activos = df_filtrado[df_filtrado["Activo"].astype(str).str.upper() == "TRUE"].copy()

            if df_activos.empty:
                st.warning("No hay productos activos en este filtro.")
            else:
                df_kpi = df_activos[df_activos["Incluir_KPI"].astype(str).str.upper() == "TRUE"].copy()
                df_no_kpi = df_activos[df_activos["Incluir_KPI"].astype(str).str.upper() != "TRUE"]

                total_prod_activos = len(df_activos)
                total_prod_kpi = len(df_kpi)
                if total_prod_kpi > 0:
                    precio_prom = df_kpi["Precio_Venta"].mean()
                    costo_prom = df_kpi["Costo_Neto"].mean()
                    fc_prom = df_kpi["Food_Cost_Pct"].mean()
                    margen_prom = df_kpi["Margen_Bruto"].mean()
                    margen_pct_prom = ((df_kpi["Precio_Venta"] - df_kpi["Costo_Neto"]) / df_kpi["Precio_Venta"] * 100).replace([float('inf')], 0).fillna(0).mean()
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
                st.subheader("📊 KPIs por categoría")

                if total_prod_kpi > 0:
                    df_cat = df_kpi.groupby("Categoria_Menu").agg(
                        Productos=("Menu_ID", "count"),
                        Precio_Promedio=("Precio_Venta", "mean"),
                        Costo_Promedio=("Costo_Neto", "mean"),
                        Food_Cost_Promedio=("Food_Cost_Pct", "mean"),
                        Margen_Bruto_Total=("Margen_Bruto", "sum")
                    ).reset_index()
                    df_cat["Margen_Promedio"] = df_cat["Margen_Bruto_Total"] / df_cat["Productos"]
                    st.dataframe(df_cat, hide_index=True, width="stretch")
                else:
                    st.info("Sin datos de KPIs por categoría.")

                st.divider()
                st.subheader("📄 Detalle del menú activo")
                cols_det = ["Nombre_Menu", "Categoria_Menu", "Tipo_Producto", "Precio_Venta",
                            "Costo_Neto", "Food_Cost_Pct", "Margen_Bruto", "Incluir_KPI", "Responsable"]
                cols_det_ok = [c for c in cols_det if c in df_activos.columns]
                st.dataframe(df_activos[cols_det_ok].sort_values("Categoria_Menu"), hide_index=True, width="stretch")

                with st.expander("Ver productos inactivos", expanded=False):
                    df_inactivos = df_filtrado[df_filtrado["Activo"].astype(str).str.upper() != "TRUE"]
                    if not df_inactivos.empty:
                        st.dataframe(df_inactivos, hide_index=True, width="stretch")
                    else:
                        st.caption("No hay productos inactivos en este filtro.")

                if not df_no_kpi.empty:
                    st.caption(f"⚠️ {len(df_no_kpi)} producto(s) excluido(s) de los KPIs.")
