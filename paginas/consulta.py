import streamlit as st
import pandas as pd
from data_loaders import cargar_datos_integrales
from inventario import obtener_ultimo_inventario
from utils import limpiar_valor, ahora_hermosillo
from config import UNIDADES
from auth import tiene_permiso
from sheets import safe_worksheet, sh

def show_consulta():
    if not tiene_permiso("Consulta"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    df_raw, df_historial = cargar_datos_integrales()
    st.title("📦 Inventario actual")
    u_sel     = st.selectbox("🏢 Unidad:", UNIDADES)
    df_actual = obtener_ultimo_inventario(df_historial, u_sel)
    if df_actual.empty:
        st.warning("No hay registros en la base de datos para esta unidad.")
        st.stop()

    # ------------------------------------------------------------------
    # INVENTARIO ACTUAL (vista existente)
    # ------------------------------------------------------------------
    bajo_min = df_actual[df_actual["Necesita Compra"] == True]
    m1,m2,m3 = st.columns(3)
    m1.metric("Total Referencias", len(df_actual))
    m2.metric("Alertas de Compra", len(bajo_min), delta=-len(bajo_min), delta_color="inverse")
    m3.metric("Volumen Global",    f"{df_actual['Stock Neto Calculado'].sum():,.1f}")

    st.divider()
    col_s, col_p = st.columns([2,1])
    with col_s:
        busqueda = st.text_input("🔍 Búsqueda rápida:")
    with col_p:
        col_prov = "Proveedor" if "Proveedor" in df_actual.columns else None
        if col_prov:
            provs    = ["Todos"] + sorted(df_actual[col_prov].dropna().unique().tolist())
            prov_sel = st.selectbox("🚛 Filtro Proveedor:", provs)
        else:
            prov_sel = "Todos"

    df_display = df_actual.copy()
    if busqueda:
        df_display = df_display[df_display["Nombre del Insumo"].astype(str).str.contains(busqueda, case=False, na=False)]
    if prov_sel != "Todos" and col_prov:
        df_display = df_display[df_display[col_prov] == prov_sel]

    col_map = {
        "Grupo":"Grupo","Nombre del Insumo":"Insumo","Marca":"Marca","Proveedor":"Proveedor",
        "Alm":"Almacén","Barra":"Barra","Stock Neto Calculado":"Stock Total","Tara":"Tara",
        "Unidad de Medida":"Medida","Stock Mínimo":"Mínimo","Necesita Compra":"¿Comprar?",
        "Responsable":"Responsable","Fecha de Inventario":"Último Corte","Observaciones":"Observaciones",
    }
    cols_ok  = [c for c in col_map if c in df_display.columns]
    df_final = df_display[cols_ok].rename(columns=col_map)

    def highlight_low(row):
        total  = row.get("Stock Total",9999)
        minimo = row.get("Mínimo",0)
        color  = "background-color: rgba(255, 75, 75, 0.2)" if total < minimo else ""
        return [color] * len(row)

    st.dataframe(df_final.style.apply(highlight_low, axis=1), width="stretch", hide_index=True)

    st.divider()
    csv = df_final.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Descargar Reporte (CSV)", data=csv,
                       file_name=f"Inventario_{u_sel}_{ahora_hermosillo().strftime('%Y%m%d_%H%M')}.csv",
                       mime="text/csv", width="stretch")

    # ------------------------------------------------------------------
    # NUEVO: HISTORIAL DE INSUMO + EDICIÓN DE CAPTURA
    # ------------------------------------------------------------------
    st.divider()
    st.subheader("📜 Historial de insumo (últimas 5 capturas)")

    nombres_actuales = sorted(df_actual["Nombre del Insumo"].dropna().unique().tolist())
    if not nombres_actuales:
        st.info("No hay insumos para mostrar historial.")
    else:
        insumo_sel = st.selectbox("Selecciona un insumo:", nombres_actuales)

        # Filtrar historial para la unidad y el insumo seleccionado
        df_hist_filtrado = df_historial[
            (df_historial["Unidad de Negocio"] == u_sel) &
            (df_historial["Nombre del Insumo"] == insumo_sel)
        ].copy()

        if df_hist_filtrado.empty:
            st.info("Sin historial para este insumo.")
        else:
            # Crear una fecha efectiva para ordenar
            df_hist_filtrado["_fecha_efectiva"] = df_hist_filtrado["Fecha de Inventario"].combine_first(
                df_hist_filtrado["Fecha de Entrada"]
            )
            df_hist_filtrado = df_hist_filtrado.sort_values("_fecha_efectiva", ascending=False).head(5)

            # Columnas a mostrar
            cols_hist = [
                "_fecha_efectiva", "Responsable", "Unidad de Medida",
                "Alm", "Barra", "Stock Neto", "Tara", "¿Comprar?", "Observaciones"
            ]
            cols_hist_ok = [c for c in cols_hist if c in df_hist_filtrado.columns]
            df_hist_mostrar = df_hist_filtrado[cols_hist_ok].rename(columns={
                "_fecha_efectiva": "Fecha",
                "Alm": "Almacén",
                "Barra": "Barra",
                "Stock Neto": "Stock Neto",
                "Tara": "Tara",
                "¿Comprar?": "¿Pedir?",
                "Unidad de Medida": "Medida",
            })

            st.dataframe(df_hist_mostrar, hide_index=True, width="stretch")

            # ---------- EDICIÓN DE UN REGISTRO ----------
            st.markdown("#### ✏️ Editar una captura")

            # Crear opciones legibles para cada fila histórica
            opciones_edicion = {}
            for _, fila in df_hist_filtrado.iterrows():
                fecha_str = fila.get("Fecha de Inventario", "")
                if not fecha_str or pd.isna(fecha_str):
                    fecha_str = fila.get("Fecha de Entrada", "")
                fecha_str = str(fecha_str)[:16]
                responsable = str(fila.get("Responsable", ""))
                etiqueta = f"{fecha_str} — {responsable}"
                opciones_edicion[etiqueta] = fila

            if not opciones_edicion:
                st.info("No hay registros para editar.")
            else:
                sel_editar = st.selectbox("Registro a editar:", list(opciones_edicion.keys()))
                registro = opciones_edicion[sel_editar]

                with st.form("f_editar_captura"):
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        nuevo_alm = st.number_input(
                            "Almacén", min_value=0.0, step=1.0,
                            value=limpiar_valor(registro.get("Alm", 0.0)),
                            key="edit_alm"
                        )
                    with c2:
                        nuevo_bar = st.number_input(
                            "Barra (bruta)", min_value=0.0, step=1.0,
                            value=limpiar_valor(registro.get("Barra", 0.0)),
                            key="edit_bar"
                        )
                    with c3:
                        nueva_tara = st.number_input(
                            "Tara", min_value=0.0, step=0.1,
                            value=limpiar_valor(registro.get("Tara", 0.0)),
                            key="edit_tara"
                        )
                    with c4:
                        nueva_medida = st.selectbox(
                            "Medida", ["pz", "ml", "gr", "kg", "lt"],
                            index=["pz", "ml", "gr", "kg", "lt"].index(
                                str(registro.get("Unidad de Medida", "pz")).lower()
                            ) if str(registro.get("Unidad de Medida", "pz")).lower() in ["pz", "ml", "gr", "kg", "lt"] else 0,
                            key="edit_unidad"
                        )

                    col5, col6 = st.columns(2)
                    with col5:
                        nueva_observacion = st.text_input(
                            "Observaciones", value=str(registro.get("Observaciones", "")),
                            key="edit_obs"
                        )
                    with col6:
                        nuevo_pedir = st.checkbox(
                            "¿Pedir?", value=bool(str(registro.get("¿Comprar?", "FALSE")).strip().upper() == "TRUE"),
                            key="edit_pedir"
                        )

                    # Calcular el nuevo stock neto
                    nuevo_neto = nuevo_alm + max(0.0, nuevo_bar - nueva_tara)

                    if st.form_submit_button("💾 Guardar cambios"):
                        # Localizar la fila en la hoja Historial
                        ws_hist, err_hist = safe_worksheet(sh, "Historial")
                        if err_hist:
                            st.error(err_hist)
                        else:
                            datos_crudos = ws_hist.get_all_values()
                            fila_encontrada = None
                            for i, fila in enumerate(datos_crudos[1:], start=2):
                                # Columnas 0: Unidad, 1: Nombre, 15: Fecha de Inventario
                                if (fila[0] == u_sel and fila[1] == insumo_sel and
                                    fila[15] == str(registro.get("Fecha de Inventario", "")) and
                                    fila[14] == str(registro.get("Responsable", ""))):
                                    fila_encontrada = i
                                    break

                            if fila_encontrada is None:
                                st.error("No se pudo localizar el registro en Sheets.")
                            else:
                                # Actualizar columnas: Alm(9), Barra(10), Stock Neto(11), Tara(16), Unidad Medida(8), ¿Comprar?(13), Observaciones(17)
                                range_actualizar = f"I{fila_encontrada}:K{fila_encontrada}"
                                ws_hist.update(range_name=range_actualizar,
                                               values=[[nuevo_alm, max(0.0, nuevo_bar - nueva_tara), nuevo_neto]])
                                ws_hist.update(range_name=f"Q{fila_encontrada}", values=[[nueva_tara]])
                                ws_hist.update(range_name=f"H{fila_encontrada}", values=[[nueva_medida]])
                                ws_hist.update(range_name=f"M{fila_encontrada}", values=[["TRUE" if nuevo_pedir else "FALSE"]])
                                ws_hist.update(range_name=f"R{fila_encontrada}", values=[[nueva_observacion]])

                                dl.cargar_datos_integrales.clear()
                                st.success("✅ Captura actualizada correctamente.")
                                st.rerun()
