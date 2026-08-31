import streamlit as st
import pandas as pd
import time
import uuid
from data_loaders import cargar_recetas, cargar_costos_insumos
from sheets import _asegurar_hoja_menus, _asegurar_hoja_historial_menus, append_rows_con_retry, safe_worksheet, sh
from utils import limpiar_valor, ts_hermosillo
from config import COLS_MENUS, COLS_MENUS_HISTORIAL
from components.avisos import mostrar_avisos
from auth import tiene_permiso


@st.cache_data(ttl=120)
def cargar_menus():
    """Lee la hoja Menus y devuelve un DataFrame con los productos del menú."""
    ws, err = safe_worksheet(sh, "Menus")
    if err:
        # Si no existe, intentar crearla vacía
        ws, err2 = _asegurar_hoja_menus()
        if err2:
            return pd.DataFrame(columns=COLS_MENUS)
        return pd.DataFrame(columns=COLS_MENUS)
    try:
        datos = ws.get_all_values()
        if len(datos) <= 1:
            return pd.DataFrame(columns=COLS_MENUS)
        df = pd.DataFrame(datos[1:], columns=datos[0])
        for col in COLS_MENUS:
            if col not in df.columns:
                df[col] = ""
        # Convertir columnas numéricas
        for col in ["Precio_Venta", "Costo_Neto", "Food_Cost_Pct", "Margen_Bruto"]:
            if col in df.columns:
                df[col] = df[col].apply(limpiar_valor)
        return df
    except Exception as e:
        st.warning(f"Error cargando menú: {e}")
        return pd.DataFrame(columns=COLS_MENUS)


def _guardar_historial_menu(menu_id, nombre_menu, producto, precio_anterior, precio_nuevo, responsable):
    """Registra el cambio de precio en Menus_Historial."""
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
    df_menus = cargar_menus()

    if df_rec.empty:
        st.warning("No hay recetas capturadas. Primero crea recetas en 'Base de Costos' → pestaña 'Recetas'.")
        st.stop()

    # ─── PESTAÑAS ───
    tab_crear, tab_ver = st.tabs(["➕ Agregar / Editar Producto", "📋 Menú Actual"])

    # ==================== TAB AGREGAR / EDITAR ====================
    with tab_crear:
        st.subheader("Agregar o actualizar producto del menú")

        # Selector de receta fuera del formulario
        recetas_disponibles = sorted(df_rec["Receta"].unique().tolist())
        if not recetas_disponibles:
            st.info("No hay recetas para mostrar.")
            st.stop()

        receta_sel = st.selectbox("Selecciona una receta existente:", recetas_disponibles, key="menu_receta_sel")

        # Datos de la receta
        df_receta = df_rec[df_rec["Receta"] == receta_sel].iloc[0]
        costo_neto_receta = limpiar_valor(df_receta.get("Costo_Neto_Receta", 0)) or limpiar_valor(df_receta.get("Costo_Ingrediente", 0))
        precio_receta = limpiar_valor(df_receta.get("Precio_Venta", 0))
        linea_receta = str(df_receta.get("Linea", ""))

        # Ver si ya existe en menú
        existe_menu = False
        menu_previo = None
        if not df_menus.empty:
            mask = df_menus["Producto"] == receta_sel
            if mask.any():
                existe_menu = True
                menu_previo = df_menus[mask].iloc[0]

        with st.form("f_menu_maker", clear_on_submit=False):
            col1, col2 = st.columns(2)
            with col1:
                categoria = st.text_input(
                    "Categoría del menú:",
                    value=str(menu_previo.get("Categoria_Menu", linea_receta)) if existe_menu else linea_receta,
                    help="Puedes usar la línea de la receta o escribir una categoría propia."
                )
                tipo_producto = st.selectbox(
                    "Tipo de producto:",
                    ["Bebida", "Alimento", "Postre", "Snack", "Combo", "Otro"],
                    index=["Bebida", "Alimento", "Postre", "Snack", "Combo", "Otro"].index(
                        str(menu_previo.get("Tipo_Producto", "Bebida"))
                    ) if existe_menu and str(menu_previo.get("Tipo_Producto", "Bebida")) in
                       ["Bebida", "Alimento", "Postre", "Snack", "Combo", "Otro"] else 0,
                    help="Clasificación interna del producto."
                )
                activo = st.toggle(
                    "Producto activo en menú",
                    value=bool(str(menu_previo.get("Activo", "TRUE")).strip().upper() == "TRUE") if existe_menu else True,
                    help="Desactiva para ocultarlo sin borrarlo."
                )
            with col2:
                precio_venta = st.number_input(
                    "Precio de venta ($):",
                    min_value=0.0,
                    step=1.0,
                    value=float(menu_previo.get("Precio_Venta", precio_receta)) if existe_menu else float(precio_receta),
                    help="Precio al cliente. Se precarga desde la receta, pero puedes ajustarlo."
                )
                st.caption(f"Costo neto de receta: **${costo_neto_receta:,.2f}**")
                if precio_venta > 0 and costo_neto_receta > 0:
                    fc = costo_neto_receta / precio_venta * 100
                    margen = precio_venta - costo_neto_receta
                    st.caption(f"Food cost: **{fc:.1f}%** | Margen bruto: **${margen:,.2f}**")
                else:
                    st.caption("⚠️ Precio o costo insuficiente para calcular KPIs.")

            notas = st.text_area("Notas (opcional):", value=str(menu_previo.get("Notas", "")) if existe_menu else "")

            enviar = st.form_submit_button("💾 Guardar en Menú", type="primary", width="stretch")

        if enviar:
            if precio_venta <= 0:
                st.error("El precio de venta debe ser mayor a cero.")
            else:
                costo_neto = costo_neto_receta
                food_cost = (costo_neto / precio_venta * 100) if precio_venta > 0 else 0.0
                margen_bruto = precio_venta - costo_neto

                ws_menu, err_menu = _asegurar_hoja_menus()
                if err_menu:
                    st.error(err_menu)
                else:
                    try:
                        if existe_menu:
                            # Actualizar el registro existente
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
                                receta_sel,          # Nombre_Menu = receta
                                categoria,
                                tipo_producto,
                                receta_sel,          # Producto = receta
                                precio_venta,
                                costo_neto,
                                round(food_cost, 2),
                                margen_bruto,
                                "TRUE" if activo else "FALSE",
                                menu_previo.get("Fecha_Captura", ts_hermosillo()),
                                st.session_state.current_user,
                                notas
                            ]
                            ws_menu.update(range_name=f"A{fila_actualizar}:M{fila_actualizar}", values=[nueva_fila])
                            # Guardar historial si cambió el precio
                            if abs(precio_anterior - precio_venta) > 0.001:
                                _guardar_historial_menu(menu_id, receta_sel, receta_sel,
                                                        precio_anterior, precio_venta,
                                                        st.session_state.current_user)
                            st.success(f"Producto '{receta_sel}' actualizado.")
                        else:
                            # Agregar nuevo
                            menu_id = str(uuid.uuid4())[:8]
                            nueva_fila = [
                                menu_id,
                                receta_sel,
                                categoria,
                                tipo_producto,
                                receta_sel,
                                precio_venta,
                                costo_neto,
                                round(food_cost, 2),
                                margen_bruto,
                                "TRUE" if activo else "FALSE",
                                ts_hermosillo(),
                                st.session_state.current_user,
                                notas
                            ]
                            ok, msg = append_rows_con_retry(ws_menu, [nueva_fila])
                            if not ok:
                                st.error(msg)
                                st.stop()
                            # Historial de alta (precio anterior 0)
                            _guardar_historial_menu(menu_id, receta_sel, receta_sel,
                                                    0.0, precio_venta,
                                                    st.session_state.current_user)
                            st.success(f"Producto '{receta_sel}' agregado al menú.")

                        cargar_menus.clear()
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al guardar en Menú: {e}")

        # Mostrar menú existente en tabla editable rápidamente (solo para referencia)
        if not df_menus.empty:
            st.divider()
            st.subheader("📋 Productos existentes")
            cols_show = ["Menu_ID", "Nombre_Menu", "Categoria_Menu", "Tipo_Producto",
                         "Precio_Venta", "Costo_Neto", "Food_Cost_Pct", "Margen_Bruto",
                         "Activo", "Responsable"]
            cols_ok = [c for c in cols_show if c in df_menus.columns]
            st.dataframe(df_menus[cols_ok], hide_index=True, width="stretch")

    # ==================== TAB MENÚ ACTUAL ====================
    with tab_ver:
        st.subheader("📋 Menú actual y KPIs")
        if df_menus.empty:
            st.info("No hay productos en el menú. Agrega uno en la pestaña anterior.")
        else:
            # Filtrar activos
            df_activos = df_menus[df_menus["Activo"].astype(str).str.upper() == "TRUE"].copy()
            if df_activos.empty:
                st.warning("No hay productos activos. Activa alguno en la pestaña 'Agregar / Editar'.")
            else:
                # KPIs globales
                total_prod = len(df_activos)
                precio_prom = df_activos["Precio_Venta"].mean()
                costo_prom = df_activos["Costo_Neto"].mean()
                fc_prom = df_activos["Food_Cost_Pct"].mean()
                margen_prom = df_activos["Margen_Bruto"].mean()
                margen_pct_prom = ((df_activos["Precio_Venta"] - df_activos["Costo_Neto"]) / df_activos["Precio_Venta"] * 100).replace([float('inf')], 0).fillna(0).mean()

                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Productos activos", total_prod)
                m2.metric("Precio promedio", f"${precio_prom:,.2f}")
                m3.metric("Costo promedio", f"${costo_prom:,.2f}")
                m4.metric("Food Cost promedio", f"{fc_prom:.1f}%")
                m5.metric("Margen bruto prom.", f"{margen_prom:,.2f}")

                st.divider()
                st.subheader("📊 KPIs por categoría")
                if "Categoria_Menu" in df_activos.columns:
                    df_cat = df_activos.groupby("Categoria_Menu").agg(
                        Productos=("Menu_ID", "count"),
                        Precio_Promedio=("Precio_Venta", "mean"),
                        Costo_Promedio=("Costo_Neto", "mean"),
                        Food_Cost_Promedio=("Food_Cost_Pct", "mean"),
                        Margen_Bruto_Total=("Margen_Bruto", "sum")
                    ).reset_index()
                    df_cat["Margen_Promedio"] = df_cat["Margen_Bruto_Total"] / df_cat["Productos"]
                    st.dataframe(df_cat, hide_index=True, width="stretch")
                else:
                    st.info("No hay columna de categoría.")

                st.divider()
                st.subheader("📄 Detalle del menú activo")
                cols_det = ["Nombre_Menu", "Categoria_Menu", "Tipo_Producto", "Precio_Venta",
                            "Costo_Neto", "Food_Cost_Pct", "Margen_Bruto", "Responsable"]
                cols_det_ok = [c for c in cols_det if c in df_activos.columns]
                st.dataframe(df_activos[cols_det_ok].sort_values("Categoria_Menu"), hide_index=True, width="stretch")

            # Opción para ver todos (incluyendo inactivos)
            with st.expander("Ver productos inactivos", expanded=False):
                df_inactivos = df_menus[df_menus["Activo"].astype(str).str.upper() != "TRUE"]
                if not df_inactivos.empty:
                    st.dataframe(df_inactivos, hide_index=True, width="stretch")
                else:
                    st.caption("No hay productos inactivos.")
