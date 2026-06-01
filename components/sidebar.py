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
    UNIDADES, GRUPOS, UNIDADES_MED, COLS_PERMISOS
)

def render_sidebar(cambiar_pagina):
    with st.sidebar:
        if not st.session_state.auth_status:
            st.subheader("🔒 Identificación")
            st.write("Inicia sesión para editar datos.")
            with st.form("login_form"):
                pin_input = st.text_input("Ingresa tu Clave:", type="password")
                submitted = st.form_submit_button("Desbloquear Sistema", type="primary", use_container_width=True)
                if submitted:
                    if pin_input in USUARIOS_PIN:
                        st.session_state.auth_status = True
                        st.session_state.current_user = USUARIOS_PIN[pin_input]["nombre"]
                        st.session_state.user_role = USUARIOS_PIN[pin_input]["rol"]
                        st.rerun()
                    else:
                        st.error("⚠️ Clave incorrecta o no registrada.")
        else:
            st.write(f"👤 Operador: **{st.session_state.current_user}**")
            if st.button("🚪 Cerrar Sesión", use_container_width=True):
                for k in ["auth_status","current_user","user_role"]:
                    st.session_state[k] = False if k == "auth_status" else None
                st.session_state.pagina = "Dashboard"
                st.rerun()

        st.divider()
        st.title("⚙️ Operaciones Noble")
        if st.button("📊 Dashboard Principal", use_container_width=True): cambiar_pagina("Dashboard")
        st.divider()
        st.write("**📦 Movimientos de Stock:**")
        if st.button("📝 Capturar inventario", use_container_width=True): cambiar_pagina("Inventario")
        if st.button("📥 Entrada de compras", use_container_width=True): cambiar_pagina("Ingresos")
        if st.button("📦 Inventario actual", use_container_width=True): cambiar_pagina("Consulta")
        st.divider()
        st.write("**💰 Ventas:**")
        if st.button("📈 Registrar Ventas", use_container_width=True): cambiar_pagina("Ventas")
        if st.button("📊 Dashboard de Ventas", use_container_width=True): cambiar_pagina("DashboardVentas")
        if st.button("📥 Importar Histórico", use_container_width=True): cambiar_pagina("ImportarVentas")
        st.divider()
        st.write("**💸 Finanzas:**")
        if st.button("💰 Registrar Gasto", use_container_width=True): cambiar_pagina("RegistrarGasto")
        if st.button("📋 Presupuesto Anual", use_container_width=True): cambiar_pagina("Presupuesto")
        if st.button("🧾 Base de Costos", use_container_width=True): cambiar_pagina("BaseCostos")
        if st.button("📉 Registrar Merma", use_container_width=True): cambiar_pagina("RegistrarMerma")
        if st.button("📊 Dashboard Financiero", use_container_width=True): cambiar_pagina("DashboardFinanciero")
        if st.button("🛒 Canales de Venta", use_container_width=True): cambiar_pagina("CanalesVenta")
        st.divider()
        st.write("**📅 Calendario:**")
        if st.button("📅 Calendario", use_container_width=True): cambiar_pagina("Calendario")
        st.divider()
        st.write("**🖨️ Tickets (58mm):**")
        if st.button("📋 Lista de Conteo", use_container_width=True): cambiar_pagina("Impresion")
        if st.button("🛒 Lista de Compra", use_container_width=True): cambiar_pagina("ListaCompra")
        if st.button("📦 Reporte de Stock", use_container_width=True): cambiar_pagina("ReporteStock")

        st.divider()
        with st.expander("ℹ️ Guía de Clasificación (Grupos)"):
            st.markdown("""
**🔴 Rutina Diaria — Perecederos y Alta Rotación**

**Grupo A — Café, Leches y Lácteos**
Insumos de uso constante en cada turno. Caducan o se agotan rápido. Conteo obligatorio todos los días antes de abrir.
Ejemplos: café en grano, café molido, leche entera, leche de avena, leche de almendra, crema para batir, mantequilla.

**Grupo B — Jarabes, Salsas y Bases Líquidas**
Productos abiertos que se contaminan con el tiempo. Revisar nivel y estado del envase diariamente.
Ejemplos: jarabes Monin/Torani, salsa de caramelo, salsa de chocolate, base de matcha líquida, concentrados de fruta.

**Grupo C — Polvos, Tés y Tisanas**
Sensibles a humedad. Contar en bolsa/bote cerrado. Incluye todo lo que se pesa o dosifica en scoop.
Ejemplos: matcha en polvo, chocolate en polvo, canela, cúrcuma, chai spice, tés de caja, tisanas sueltas.

---

**🟡 Rutina cada 2 Días — Secos y Suministros**

**Grupo D — Empaques y Desechables**
Conteo por pieza o rollo. Incluye todo lo que sale de la tienda con el producto.
Ejemplos: vasos 8/12/16/20 oz, tapas, popotes, servilletas, bolsas de papel, etiquetas térmicas, mangas de cartón.

**Grupo E — Suministros de Limpieza**
Incluye lo que se usa en el área de barra y en el área de preparación. Conteo en mililitros o piezas según presentación.
Ejemplos: desengrasante, cloro, gel antibacterial, franelas, esponjas, cepillos portafiltro, pastillas de limpieza.

**Grupo F — Comida y Vitrina**
Productos para venta directa o preparación de alimentos. Revisión de fecha de caducidad en cada conteo.
Ejemplos: pan para sándwich, pan dulce, muffins, galletas empacadas, snacks, fruta para decoración.

**Grupo G — Compras pendientes**
Todo lo que hace falta comprar para mejorar la operación de Noble.
            """)

        with st.expander("📊 Tabla Resumen de Grupos"):
            grupos_info = [
                {"Grupo":"A","Nombre":"Café, Leches y Lácteos","Rutina":"Diaria","Riesgo":"Alto","Almacén":"Refrigerador / Bodega seca","Nota":"Contar antes de abrir"},
                {"Grupo":"B","Nombre":"Jarabes, Salsas y Bases","Rutina":"Diaria","Riesgo":"Alto","Almacén":"Repisa barra / Refrigerador","Nota":"Revisar envases abiertos"},
                {"Grupo":"C","Nombre":"Polvos, Tés y Tisanas","Rutina":"Diaria","Riesgo":"Medio","Almacén":"Bodega seca hermética","Nota":"Proteger de humedad"},
                {"Grupo":"D","Nombre":"Empaques y Desechables","Rutina":"Cada 2 días","Riesgo":"Medio","Almacén":"Bodega empaques","Nota":"Contar en piezas/rollos"},
                {"Grupo":"E","Nombre":"Suministros de Limpieza","Rutina":"Cada 2 días","Riesgo":"Bajo","Almacén":"Bodega limpieza","Nota":"Separar de alimentos"},
                {"Grupo":"F","Nombre":"Comida y Vitrina","Rutina":"Cada 2 días","Riesgo":"Alto","Almacén":"Vitrina / Refrigerador","Nota":"Verificar caducidad"},
                {"Grupo":"G","Nombre":"Compras","Rutina":"Cada 2 días","Riesgo":"Bajo","Almacén":"Bodega general / Mostrador","Nota":"Registrar cada entrada"},
            ]
            st.dataframe(pd.DataFrame(grupos_info), hide_index=True, use_container_width=True)

        # ZONA ADMIN
        if st.session_state.user_role == "admin":
            st.divider()
            st.write("**🛠️ Administración Avanzada:**")
            if st.button("🔒 Corte de Mes", use_container_width=True): cambiar_pagina("CorteMes")

            st.divider()
            with st.expander("👤 Gestión de Accesos"):
                st.write("**Agregar / Actualizar Barista**")
                n_nombre = st.text_input("Nombre de Usuario:")
                n_clave  = st.text_input("Clave de Acceso:")
                n_rol    = st.selectbox("Nivel de Permisos:", ["barista","admin"])
                if st.button("➕ Guardar Usuario", use_container_width=True):
                    if n_nombre and n_clave:
                        ws_acc, err = safe_worksheet(sh, "Accesos")
                        if err:
                            st.error(err)
                        else:
                            try:
                                nuevo_df  = DF_USUARIOS.copy()
                                nuevo_df  = nuevo_df[nuevo_df["Nombre"] != n_nombre]
                                nueva_fil = pd.DataFrame([{"Clave":str(n_clave),"Nombre":n_nombre,"Rol":n_rol}])
                                nuevo_df  = pd.concat([nuevo_df, nueva_fil], ignore_index=True)
                                ws_acc.clear()
                                ws_acc.append_row(COLS_ACCESOS)
                                ws_acc.append_rows(nuevo_df[COLS_ACCESOS].values.tolist())
                                from auth import obtener_usuarios
                                obtener_usuarios.clear()
                                st.success(f"Permisos para '{n_nombre}' guardados.")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al guardar: {e}")
                    else:
                        st.warning("Completa nombre y clave.")
                st.divider()
                st.write("**Eliminar Barista**")
                if LISTA_RESPONSABLES:
                    u_del = st.selectbox("Seleccionar:", LISTA_RESPONSABLES)
                    if st.button("❌ Borrar Acceso", use_container_width=True):
                        ws_acc, err = safe_worksheet(sh, "Accesos")
                        if err:
                            st.error(err)
                        else:
                            try:
                                nuevo_df = DF_USUARIOS[DF_USUARIOS["Nombre"] != u_del]
                                ws_acc.clear()
                                ws_acc.append_row(COLS_ACCESOS)
                                ws_acc.append_rows(nuevo_df[COLS_ACCESOS].values.tolist())
                                from auth import obtener_usuarios
                                obtener_usuarios.clear()
                                st.success(f"Acceso revocado para {u_del}.")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                else:
                    st.info("No hay responsables registrados.")

            st.divider()
            with st.expander("📢 Gestión de Avisos"):
                df_av_mgr = cargar_avisos()
                st.write("**Nuevo aviso**")
                with st.form("f_aviso", clear_on_submit=True):
                    av_titulo = st.text_input("Título")
                    av_msg    = st.text_area("Mensaje", height=80)
                    av_tipo   = st.selectbox("Tipo", ["info","warning","urgent"],
                                             format_func=lambda x: {"info":"ℹ️ Informativo","warning":"⚠️ Advertencia","urgent":"🚨 Urgente"}[x])
                    av_pagina = st.multiselect("Mostrar en páginas:", 
                        ["Todas","Dashboard","Inventario","Ingresos","Consulta","Ventas","DashboardVentas",
                         "ImportarVentas","RegistrarGasto","Presupuesto","BaseCostos","RegistrarMerma",
                         "DashboardFinanciero","CanalesVenta","Calendario","Impresion","ListaCompra","ReporteStock","CorteMes"],
                        default=["Todas"])
                    if st.form_submit_button("📢 Publicar aviso", use_container_width=True):
                        if not av_titulo.strip() or not av_msg.strip():
                            st.error("Título y mensaje son obligatorios.")
                        else:
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
                                st.success("Aviso publicado.")
                                time.sleep(0.5)
                                st.rerun()
                if not df_av_mgr.empty:
                    st.divider()
                    st.write("**Avisos existentes**")
                    for _, av in df_av_mgr.iterrows():
                        activo = str(av.get("Activo","")).upper() == "TRUE"
                        tipo   = str(av.get("Tipo","info"))
                        icono  = {"info":"ℹ️","warning":"⚠️","urgent":"🚨"}.get(tipo,"ℹ️")
                        estado = "🟢" if activo else "⚫"
                        col_a, col_b = st.columns([3,1])
                        with col_a:
                            st.write(f"{estado} {icono} **{av.get('Título','')}**")
                            st.caption(str(av.get("Mensaje",""))[:80])
                        with col_b:
                            av_id = str(av.get("ID",""))
                            if st.button("Desactivar" if activo else "Activar", key=f"tog_{av_id}", use_container_width=True):
                                ws_av, err = safe_worksheet(sh, "Avisos")
                                if not err:
                                    try:
                                        celdas = ws_av.get_all_values()
                                        for i, fila in enumerate(celdas[1:], start=2):
                                            if fila[0] == av_id:
                                                ws_av.update(range_name=f"E{i}", values=[["FALSE" if activo else "TRUE"]])
                                                cargar_avisos.clear()
                                                st.rerun()
                                                break
                                    except Exception as e:
                                        st.error(f"Error: {e}")

            # Gestión de Permisos de Páginas
            st.divider()
            with st.expander("🔐 Permisos de Módulos"):
                st.write("Asigna qué páginas puede ver cada rol.")
                all_pages = ["Dashboard","Inventario","Ingresos","Consulta","Ventas","DashboardVentas","ImportarVentas",
                             "RegistrarGasto","Presupuesto","BaseCostos","RegistrarMerma","DashboardFinanciero",
                             "CanalesVenta","Calendario","Impresion","ListaCompra","ReporteStock","CorteMes"]
                ws_perm, err_perm = safe_worksheet(sh, "Permisos")
                if err_perm:
                    try:
                        ws_perm = sh.add_worksheet(title="Permisos", rows="100", cols="2")
                        ws_perm.append_row(COLS_PERMISOS)
                    except Exception as e:
                        st.error(f"No se pudo crear hoja Permisos: {e}")
                with st.form("f_perm"):
                    rol_perm = st.selectbox("Rol:", ["barista"])
                    paginas_activas = [p for p in all_pages if p in PERMISOS.get(rol_perm, [])]
                    paginas_sel = st.multiselect("Páginas permitidas:", all_pages, default=paginas_activas)
                    if st.form_submit_button("💾 Guardar Permisos"):
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
                                st.success("Permisos actualizados.")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")

        # CATÁLOGO (cacheado)
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
            st.subheader("🛠️ Gestión del Catálogo")
            op_cat = st.radio("Acción:", ["Añadir Insumo","Editar Insumo"])

            if op_cat == "Añadir Insumo":
                with st.form("f_add", clear_on_submit=True):
                    u  = st.selectbox("Unidad", UNIDADES)
                    n  = st.text_input("Nombre del Insumo")
                    m  = st.text_input("Marca")
                    p  = st.text_input("Proveedor")
                    g  = st.selectbox("Grupo", GRUPOS)
                    uc = st.text_input("Presentación de Compra")
                    um = st.selectbox("Unidad de Medida", UNIDADES_MED)
                    sm = st.number_input("Stock Mínimo", min_value=0.0)
                    tara_new = st.number_input("Tara (kg/gr)", min_value=0.0, value=0.0)
                    if st.form_submit_button("✨ Crear Insumo"):
                        if not n.strip():
                            st.error("El nombre del insumo es obligatorio.")
                        else:
                            ws_ins, err = safe_worksheet(sh, "Insumos")
                            if err:
                                st.error(err)
                            else:
                                try:
                                    ws_ins.append_row(
                                        [u, n.strip(), m, p, g, "", uc, um, "", "", "", sm, "", "", "", "", tara_new, "TRUE"],
                                        value_input_option="USER_ENTERED"
                                    )
                                    _cargar_catalogo_sidebar.clear()
                                    from data_loaders import cargar_datos_integrales
                                    cargar_datos_integrales.clear()
                                    st.success(f"Insumo '{n.strip()}' creado.")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al crear insumo: {e}")
            else:
                if df_raw_sb.empty or "Nombre del Insumo" not in df_raw_sb.columns:
                    st.info("Sin insumos disponibles para editar.")
                else:
                    ins_nombres = df_raw_sb["Nombre del Insumo"].dropna().unique().tolist()
                    if not ins_nombres:
                        st.info("El catálogo está vacío.")
                    else:
                        def _label_insumo(nombre):
                            mask = df_raw_sb["Nombre del Insumo"] == nombre
                            if not mask.any():
                                return nombre
                            val_activo = str(df_raw_sb[mask].iloc[0].get("Activo", "TRUE")).strip().upper()
                            return nombre if val_activo == "TRUE" else f"⛔ {nombre} (inactivo)"

                        ins_edit = st.selectbox("Seleccionar Insumo a Editar:", sorted(ins_nombres), format_func=_label_insumo)
                        mask = df_raw_sb["Nombre del Insumo"] == ins_edit
                        if not mask.any():
                            st.warning("Insumo no encontrado.")
                        else:
                            d = df_raw_sb[mask].iloc[0]
                            with st.form("f_edit"):
                                unidad_val = d.get("Unidad de Negocio", UNIDADES[0])
                                e_u  = st.selectbox("Unidad", UNIDADES, index=UNIDADES.index(unidad_val) if unidad_val in UNIDADES else 0)
                                e_n  = st.text_input("Nombre", value=str(d.get("Nombre del Insumo","")))
                                e_m  = st.text_input("Marca", value=str(d.get("Marca","")))
                                e_p  = st.text_input("Proveedor", value=str(d.get("Proveedor","")))
                                grupo_val = str(d.get("Grupo","A"))
                                e_g  = st.selectbox("Grupo", GRUPOS, index=GRUPOS.index(grupo_val) if grupo_val in GRUPOS else 0)
                                e_uc = st.text_input("Presentación Compra", value=str(d.get("Presentación de Compra","")))
                                u_val = str(d.get("Unidad de Medida","pz")).lower()
                                e_um = st.selectbox("Medida", UNIDADES_MED, index=UNIDADES_MED.index(u_val) if u_val in UNIDADES_MED else 0)
                                e_sm = st.number_input("Stock Mínimo", min_value=0.0, value=limpiar_valor(d.get("Stock Mínimo",0)))
                                e_tara = st.number_input("Tara (kg/gr)", min_value=0.0, value=limpiar_valor(d.get("Tara",0)))
                                activo_actual = str(d.get("Activo", "TRUE")).strip().upper() == "TRUE"
                                e_activo = st.toggle("Insumo Activo", value=activo_actual, help="Desactiva para ocultarlo de Captura e Inventario sin borrar su historial.")
                                if st.form_submit_button("💾 Actualizar Insumo"):
                                    if not e_n.strip():
                                        st.error("El nombre no puede quedar vacío.")
                                    else:
                                        ws_ins, err = safe_worksheet(sh, "Insumos")
                                        if err:
                                            st.error(err)
                                        else:
                                            try:
                                                idx = int(d.get("Sheet_Row_Num",0))
                                                if idx < 2:
                                                    raise ValueError("Número de fila inválido.")
                                                ws_ins.update(
                                                    range_name=f"A{idx}:R{idx}",
                                                    values=[[e_u, e_n.strip(), e_m, e_p, e_g, "", e_uc, e_um, "", "", "", e_sm, "", "", "", "", e_tara, "TRUE" if e_activo else "FALSE"]]
                                                )
                                                _cargar_catalogo_sidebar.clear()
                                                from data_loaders import cargar_datos_integrales
                                                cargar_datos_integrales.clear()
                                                st.success("Catálogo actualizado.")
                                                time.sleep(1)
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"Error al actualizar: {e}")
