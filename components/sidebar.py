import streamlit as st
import pandas as pd
import time
import uuid
from auth import USUARIOS_PIN, LISTA_RESPONSABLES, DF_USUARIOS, PERMISOS, tiene_permiso, cargar_permisos
from data_loaders import cargar_avisos, cargar_datos_integrales
from sheets import safe_worksheet, sh
from utils import ts_hermosillo, limpiar_valor, normalizar_dataframe
from config import (
    COLS_ACCESOS, COLS_AVISOS, COLS_INSUMOS, COLS_CRITICAS_INSUMOS,
    UNIDADES, GRUPOS, UNIDADES_MED, COLS_PERMISOS,
    COLOR_TARJETA, COLOR_BORDE, COLOR_TEXTO, COLOR_SUBTEXTO,
    COLOR_EXITO, COLOR_ERROR, COLOR_INFO
)

def render_sidebar(cambiar_pagina):
    with st.sidebar:
        # ── Bloque de sesión ──
        if not st.session_state.auth_status:
            with st.container(border=True):
                st.markdown("### 🔐 Acceso")
                with st.form("login_form"):
                    pin_input = st.text_input("Clave", type="password")
                    if st.form_submit_button("Ingresar", width="stretch", type="primary"):
                        if pin_input in USUARIOS_PIN:
                            st.session_state.auth_status = True
                            st.session_state.current_user = USUARIOS_PIN[pin_input]["nombre"]
                            st.session_state.user_role = USUARIOS_PIN[pin_input]["rol"]
                            st.rerun()
                        else:
                            st.error("Clave incorrecta")
        else:
            with st.container(border=True):
                st.markdown(f"**{st.session_state.current_user}**  \n<small style='color:{COLOR_SUBTEXTO}'>{st.session_state.user_role}</small>", unsafe_allow_html=True)
                if st.button("Cerrar sesión", width="stretch"):
                    for k in ["auth_status","current_user","user_role"]:
                        st.session_state[k] = False if k == "auth_status" else None
                    st.session_state.pagina = "Dashboard"
                    st.rerun()

        st.divider()

        # ── PRINCIPAL ──
        with st.container(border=True):
            st.caption("PRINCIPAL")
            if st.button("Dashboard", width="stretch"): cambiar_pagina("Dashboard")
            if st.button("Calendario", width="stretch"): cambiar_pagina("Calendario")

        # ── STOCK ──
        with st.container(border=True):
            st.caption("STOCK")
            if st.button("Capturar inventario", width="stretch"): cambiar_pagina("Inventario")
            if st.button("Entrada de compras", width="stretch"): cambiar_pagina("Ingresos")
            if st.button("Inventario actual", width="stretch"): cambiar_pagina("Consulta")

        # ── VENTAS ──
        with st.container(border=True):
            st.caption("VENTAS")
            if st.button("Registrar ventas", width="stretch"): cambiar_pagina("Ventas")
            if st.button("Dashboard ventas", width="stretch"): cambiar_pagina("DashboardVentas")
            if st.button("Importar histórico", width="stretch"): cambiar_pagina("ImportarVentas")

        # ── FINANZAS ──
        with st.container(border=True):
            st.caption("FINANZAS")
            if st.button("Registrar gasto", width="stretch"): cambiar_pagina("RegistrarGasto")
            if st.button("Presupuesto anual", width="stretch"): cambiar_pagina("Presupuesto")
            if st.button("Base de costos", width="stretch"): cambiar_pagina("BaseCostos")
            if st.button("Registrar merma", width="stretch"): cambiar_pagina("RegistrarMerma")
            if st.button("Dashboard financiero", width="stretch"): cambiar_pagina("DashboardFinanciero")

        # ── HERRAMIENTAS ──
        with st.container(border=True):
            st.caption("HERRAMIENTAS")
            if st.button("Lista de conteo", width="stretch"): cambiar_pagina("Impresion")
            if st.button("Lista de compra", width="stretch"): cambiar_pagina("ListaCompra")
            if st.button("Reporte de stock", width="stretch"): cambiar_pagina("ReporteStock")

        # ── ADMINISTRACIÓN (solo admin) ──
        if st.session_state.user_role == "admin":
            st.divider()
            with st.expander("Administración", expanded=False):
                if st.button("Corte de mes", width="stretch"): cambiar_pagina("CorteMes")
                if st.button("Limpiar caché", width="stretch"):
                    st.cache_data.clear()
                    st.rerun()

                st.divider()
                st.caption("Gestión de accesos")

                # Agregar / Actualizar usuario
                n_nombre = st.text_input("Nombre")
                n_clave = st.text_input("Clave")
                n_rol = st.selectbox("Rol", ["barista","admin"])
                if st.button("Guardar usuario"):
                    if n_nombre and n_clave:
                        ws_acc, err = safe_worksheet(sh, "Accesos")
                        if not err:
                            try:
                                nuevo_df = DF_USUARIOS.copy()
                                nuevo_df = nuevo_df[nuevo_df["Nombre"] != n_nombre]
                                nueva_fil = pd.DataFrame([{"Clave":str(n_clave),"Nombre":n_nombre,"Rol":n_rol}])
                                nuevo_df = pd.concat([nuevo_df, nueva_fil], ignore_index=True)
                                ws_acc.clear()
                                ws_acc.append_row(COLS_ACCESOS)
                                ws_acc.append_rows(nuevo_df[COLS_ACCESOS].values.tolist())
                                from auth import obtener_usuarios
                                obtener_usuarios.clear()
                                st.success(f"Usuario {n_nombre} guardado")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                    else:
                        st.warning("Nombre y clave requeridos")

                # Eliminar usuario
                if LISTA_RESPONSABLES:
                    u_del = st.selectbox("Eliminar usuario", LISTA_RESPONSABLES)
                    if st.button("Eliminar"):
                        ws_acc, err = safe_worksheet(sh, "Accesos")
                        if not err:
                            try:
                                nuevo_df = DF_USUARIOS[DF_USUARIOS["Nombre"] != u_del]
                                ws_acc.clear()
                                ws_acc.append_row(COLS_ACCESOS)
                                ws_acc.append_rows(nuevo_df[COLS_ACCESOS].values.tolist())
                                from auth import obtener_usuarios
                                obtener_usuarios.clear()
                                st.success(f"Usuario {u_del} eliminado")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")

                st.divider()
                st.caption("Avisos")
                df_av_mgr = cargar_avisos()
                # Nuevo aviso
                with st.form("f_aviso", clear_on_submit=True):
                    av_titulo = st.text_input("Título")
                    av_msg = st.text_area("Mensaje")
                    av_tipo = st.selectbox("Tipo", ["info","warning","urgent"])
                    av_pagina = st.multiselect("Páginas", 
                        ["Todas","Dashboard","Inventario","Ingresos","Consulta","Ventas","DashboardVentas",
                         "ImportarVentas","RegistrarGasto","Presupuesto","BaseCostos","RegistrarMerma",
                         "DashboardFinanciero","Calendario","Impresion","ListaCompra","ReporteStock","CorteMes"],
                        default=["Todas"])
                    if st.form_submit_button("Publicar"):
                        if av_titulo.strip() and av_msg.strip():
                            ws_av, err = safe_worksheet(sh, "Avisos")
                            if err:
                                try:
                                    ws_av = sh.add_worksheet(title="Avisos", rows="200", cols="8")
                                    ws_av.append_row(COLS_AVISOS)
                                except Exception as e:
                                    st.error(f"No se pudo crear hoja Avisos: {e}")
                                    ws_av = None
                            if ws_av:
                                ws_av.append_row([
                                    str(uuid.uuid4())[:8], av_titulo.strip(), av_msg.strip(),
                                    av_tipo, "TRUE", ts_hermosillo(), st.session_state.current_user,
                                    ", ".join(av_pagina)
                                ], value_input_option="USER_ENTERED")
                                cargar_avisos.clear()
                                st.success("Aviso publicado")
                                st.rerun()
                # Avisos existentes
                if not df_av_mgr.empty:
                    for _, av in df_av_mgr.iterrows():
                        activo = str(av.get("Activo","")).upper() == "TRUE"
                        estado = "🟢" if activo else "⚫"
                        av_id = str(av.get("ID",""))
                        st.caption(f"{estado} {av.get('Título','')}")
                        if st.button("Desactivar" if activo else "Activar", key=f"tog_{av_id}"):
                            ws_av, err = safe_worksheet(sh, "Avisos")
                            if not err:
                                try:
                                    celdas = ws_av.get_all_values()
                                    for i, fila in enumerate(celdas[1:], start=2):
                                        if fila[0] == av_id:
                                            ws_av.update(range_name=f"E{i}", values=[["FALSE" if activo else "TRUE"]])
                                            cargar_avisos.clear()
                                            st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")

                st.divider()
                st.caption("Permisos de módulos")
                all_pages = ["Dashboard","Inventario","Ingresos","Consulta","Ventas","DashboardVentas","ImportarVentas",
                             "RegistrarGasto","Presupuesto","BaseCostos","RegistrarMerma","DashboardFinanciero",
                             "Calendario","Impresion","ListaCompra","ReporteStock","CorteMes"]
                ws_perm, err_perm = safe_worksheet(sh, "Permisos")
                if err_perm:
                    try:
                        ws_perm = sh.add_worksheet(title="Permisos", rows="100", cols="2")
                        ws_perm.append_row(COLS_PERMISOS)
                    except Exception as e:
                        st.error(f"No se pudo crear hoja Permisos: {e}")
                with st.form("f_perm"):
                    rol_perm = st.selectbox("Rol", ["barista"])
                    paginas_activas = [p for p in all_pages if p in PERMISOS.get(rol_perm, [])]
                    paginas_sel = st.multiselect("Páginas permitidas", all_pages, default=paginas_activas)
                    if st.form_submit_button("Guardar permisos"):
                        if ws_perm:
                            try:
                                data = ws_perm.get_all_values()
                                if len(data) > 1:
                                    df_old = pd.DataFrame(data[1:], columns=data[0])
                                    df_old = df_old[df_old["Rol"] != rol_perm]
                                    ws_perm.clear()
                                    ws_perm.append_row(COLS_PERMISOS)
                                    if not df_old.empty:
                                        ws_perm.append_rows(df_old.values.tolist())
                                else:
                                    ws_perm.clear()
                                    ws_perm.append_row(COLS_PERMISOS)
                                new_rows = [[rol_perm, p] for p in paginas_sel]
                                if new_rows:
                                    ws_perm.append_rows(new_rows, value_input_option="USER_ENTERED")
                                global PERMISOS
                                PERMISOS = cargar_permisos()
                                st.success("Permisos actualizados")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")

        # ── CATÁLOGO (si está autenticado) ──
        if st.session_state.auth_status:
            @st.cache_data(ttl=60)
            def _cargar_catalogo_sidebar():
                if sh is None:
                    return pd.DataFrame()
                try:
                    ws_ins_sb, _ = safe_worksheet(sh, "Insumos")
                    if ws_ins_sb is not None:
                        val_ins_sb = ws_ins_sb.get_all_values()
                        if len(val_ins_sb) > 1:
                            df = pd.DataFrame(val_ins_sb[1:], columns=val_ins_sb[0])
                            df["Sheet_Row_Num"] = df.index + 2
                            return normalizar_dataframe(df, COLS_INSUMOS + ["Sheet_Row_Num"], cols_criticas=COLS_CRITICAS_INSUMOS)
                except Exception:
                    pass
                return pd.DataFrame()

            df_raw_sb = _cargar_catalogo_sidebar()

            st.divider()
            with st.expander("Catálogo de insumos", expanded=False):
                op_cat = st.radio("Acción", ["Añadir","Editar"])

                if op_cat == "Añadir":
                    with st.form("f_add", clear_on_submit=True):
                        u = st.selectbox("Unidad", UNIDADES)
                        n = st.text_input("Nombre")
                        m = st.text_input("Marca")
                        p = st.text_input("Proveedor")
                        g = st.selectbox("Grupo", GRUPOS)
                        uc = st.text_input("Presentación compra")
                        um = st.selectbox("Unidad medida", UNIDADES_MED)
                        sm = st.number_input("Stock mínimo", min_value=0.0)
                        tara_new = st.number_input("Tara (kg/gr)", min_value=0.0, value=0.0)
                        if st.form_submit_button("Crear insumo"):
                            if not n.strip():
                                st.error("Nombre obligatorio")
                            else:
                                ws_ins, err = safe_worksheet(sh, "Insumos")
                                if not err:
                                    try:
                                        ws_ins.append_row(
                                            [u, n.strip(), m, p, g, "", uc, um, "", "", "", sm, "", "", "", "", tara_new, "TRUE"],
                                            value_input_option="USER_ENTERED"
                                        )
                                        _cargar_catalogo_sidebar.clear()
                                        from data_loaders import cargar_datos_integrales
                                        cargar_datos_integrales.clear()
                                        st.success(f"Insumo '{n.strip()}' creado")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error: {e}")
                else:
                    if not df_raw_sb.empty:
                        ins_nombres = sorted(df_raw_sb["Nombre del Insumo"].dropna().unique().tolist())
                        if ins_nombres:
                            ins_edit = st.selectbox("Seleccionar insumo", ins_nombres)
                            mask = df_raw_sb["Nombre del Insumo"] == ins_edit
                            if mask.any():
                                d = df_raw_sb[mask].iloc[0]
                                with st.form("f_edit"):
                                    e_u = st.selectbox("Unidad", UNIDADES, index=UNIDADES.index(d.get("Unidad de Negocio", UNIDADES[0])) if d.get("Unidad de Negocio") in UNIDADES else 0)
                                    e_n = st.text_input("Nombre", value=str(d.get("Nombre del Insumo","")))
                                    e_m = st.text_input("Marca", value=str(d.get("Marca","")))
                                    e_p = st.text_input("Proveedor", value=str(d.get("Proveedor","")))
                                    e_g = st.selectbox("Grupo", GRUPOS, index=GRUPOS.index(str(d.get("Grupo","A"))) if str(d.get("Grupo","A")) in GRUPOS else 0)
                                    e_uc = st.text_input("Presentación compra", value=str(d.get("Presentación de Compra","")))
                                    e_um = st.selectbox("Medida", UNIDADES_MED, index=UNIDADES_MED.index(str(d.get("Unidad de Medida","pz")).lower()) if str(d.get("Unidad de Medida","pz")).lower() in UNIDADES_MED else 0)
                                    e_sm = st.number_input("Stock mínimo", min_value=0.0, value=limpiar_valor(d.get("Stock Mínimo",0)))
                                    e_tara = st.number_input("Tara (kg/gr)", min_value=0.0, value=limpiar_valor(d.get("Tara",0)))
                                    activo_actual = str(d.get("Activo", "TRUE")).strip().upper() == "TRUE"
                                    e_activo = st.toggle("Activo", value=activo_actual)
                                    if st.form_submit_button("Actualizar"):
                                        if not e_n.strip():
                                            st.error("Nombre obligatorio")
                                        else:
                                            ws_ins, err = safe_worksheet(sh, "Insumos")
                                            if not err:
                                                try:
                                                    idx = int(d.get("Sheet_Row_Num",0))
                                                    if idx >= 2:
                                                        ws_ins.update(
                                                            range_name=f"A{idx}:R{idx}",
                                                            values=[[e_u, e_n.strip(), e_m, e_p, e_g, "", e_uc, e_um, "", "", "", e_sm, "", "", "", "", e_tara, "TRUE" if e_activo else "FALSE"]]
                                                        )
                                                        _cargar_catalogo_sidebar.clear()
                                                        from data_loaders import cargar_datos_integrales
                                                        cargar_datos_integrales.clear()
                                                        st.success("Catálogo actualizado")
                                                        st.rerun()
                                                except Exception as e:
                                                    st.error(f"Error: {e}")

        # ── GUÍA RÁPIDA ──
        with st.expander("Grupos de clasificación"):
            st.markdown("""
**A** – Café, leches, lácteos (diario)  
**B** – Jarabes, salsas, bases (diario)  
**C** – Polvos, tés, tisanas (diario)  
**D** – Empaques, desechables (c/2 días)  
**E** – Limpieza (c/2 días)  
**F** – Comida, vitrina (c/2 días)  
**G** – Compras pendientes  
            """)
