import streamlit as st
import pandas as pd
import re
import json
import uuid
import data_loaders as dl

from inventario import obtener_ultimo_inventario, buscar_insumo_en_actual, construir_fila_historial
from sheets import safe_worksheet, sh, append_rows_con_retry, _asegurar_hoja_borradores
from utils import limpiar_valor, ts_hermosillo, normalizar_nombre
from config import UNIDADES, UNIDADES_MED, GRUPOS
from components.avisos import mostrar_avisos
from auth import tiene_permiso

def _generar_session_id():
    if "inv_session_id" not in st.session_state:
        st.session_state.inv_session_id = str(uuid.uuid4())
    return st.session_state.inv_session_id

def _guardar_borrador_inventario(session_id, u_sel, fecha, modo, data_dict):
    ws, err = _asegurar_hoja_borradores()
    if err:
        return False
    try:
        datos_json = json.dumps(data_dict)
        todos = ws.get_all_values()
        fila_idx = None
        for i, fila in enumerate(todos[1:], start=2):
            if fila[0] == session_id and fila[1] == u_sel:
                fila_idx = i
                break
        if fila_idx:
            ws.update(range_name=f"A{fila_idx}:F{fila_idx}",
                      values=[[session_id, u_sel, fecha, modo, datos_json, ts_hermosillo()]])
        else:
            ws.append_row([session_id, u_sel, fecha, modo, datos_json, ts_hermosillo()],
                          value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        st.warning(f"No se pudo autoguardar borrador: {e}")
        return False

def _cargar_borrador_inventario(session_id, u_sel):
    ws, err = _asegurar_hoja_borradores()
    if err:
        return None
    try:
        datos = ws.get_all_values()
        for fila in reversed(datos[1:]):
            if fila[0] == session_id and fila[1] == u_sel:
                fecha_captura = fila[2]
                modo = fila[3]
                data_json = fila[4]
                if data_json:
                    return {
                        "fecha_captura": fecha_captura,
                        "modo": modo,
                        "data": json.loads(data_json)
                    }
        return None
    except Exception:
        return None

def _eliminar_borrador_inventario(session_id, u_sel):
    ws, err = _asegurar_hoja_borradores()
    if err:
        return
    try:
        todos = ws.get_all_values()
        fila_idx = None
        for i, fila in enumerate(todos[1:], start=2):
            if fila[0] == session_id and fila[1] == u_sel:
                fila_idx = i
                break
        if fila_idx:
            ws.delete_rows(fila_idx)
    except Exception:
        pass

def show_inventario():
    if not tiene_permiso("Inventario"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    try:
        df_raw, df_historial = dl.cargar_datos_integrales()
    except Exception as e:
        st.error(f"Error al cargar los datos: {e}")
        st.stop()
    st.title("📝 Capturar inventario")
    mostrar_avisos("Inventario")
    if not st.session_state.auth_status:
        st.error("🔒 Autenticación requerida.")
        st.stop()

    if st.session_state.get("inventario_guardado", False):
        st.success("✅ Inventario registrado correctamente.")
        if st.button("➕ Nueva captura", width="stretch"):
            for key in list(st.session_state.keys()):
                if key.startswith(("a_", "b_", "u_", "tara_", "p_", "c_", "inv_bulk_data", "inv_campos")):
                    del st.session_state[key]
            st.session_state.inventario_guardado = False
            st.rerun()
        st.stop()

    col_u, col_r, col_g = st.columns([1,1,2])
    with col_u:
        u_sel = st.selectbox("🏢 Unidad de Negocio", UNIDADES)
    responsables = st.session_state.responsables or ["Raúl"]
    resp_idx = responsables.index(st.session_state.current_user) if st.session_state.current_user in responsables else 0
    with col_r:
        r_sel = st.selectbox("👤 Responsable", responsables, index=resp_idx,
                             disabled=(st.session_state.user_role != "admin"))

    if "ultima_unidad_inv" not in st.session_state:
        st.session_state.ultima_unidad_inv = u_sel

    if st.session_state.ultima_unidad_inv != u_sel:
        for key in list(st.session_state.keys()):
            if key.startswith(("a_", "b_", "u_", "tara_", "p_", "c_", "inv_bulk_data", "inv_campos")):
                del st.session_state[key]
        st.session_state.ultima_unidad_inv = u_sel
        st.session_state.pop("borrador_consultado", None)

    session_id = _generar_session_id()
    hoy_str = ts_hermosillo().split(" ")[0]

    # Preguntar por borrador si existe y es de hoy
    if "borrador_consultado" not in st.session_state:
        borrador = _cargar_borrador_inventario(session_id, u_sel)
        if borrador and borrador["fecha_captura"] == hoy_str:
            st.warning("📋 Hay un borrador de inventario del día de hoy para esta unidad.")
            col_bor1, col_bor2 = st.columns(2)
            with col_bor1:
                if st.button("✅ Cargar borrador", width="stretch"):
                    if borrador["modo"] == "bulk":
                        st.session_state.inv_bulk_data = borrador["data"].get("bulk_data")
                    else:
                        st.session_state.inv_campos = borrador["data"].get("campos", {})
                    st.session_state.borrador_consultado = True
                    st.rerun()
            with col_bor2:
                if st.button("❌ Ignorar", width="stretch"):
                    st.session_state.borrador_consultado = True
                    st.rerun()
        else:
            st.session_state.borrador_consultado = True

    df_u = df_raw[df_raw["Unidad de Negocio"] == u_sel] if not df_raw.empty else pd.DataFrame()
    with col_g:
        grps  = sorted(df_u["Grupo"].dropna().unique().tolist()) if not df_u.empty and "Grupo" in df_u.columns else GRUPOS
        g_sel = st.multiselect("📂 Grupos a contar", grps, default=grps[:1] if grps else [])
    st.divider()
    busqueda_inv = st.text_input("🔍 Buscar insumo:", placeholder="Escribe el nombre...")
    df_actual = obtener_ultimo_inventario(df_historial, u_sel)
    df_f = (
        df_u[df_u["Grupo"].isin(g_sel)].sort_values(["Grupo","Nombre del Insumo"]).reset_index(drop=True)
        if not df_u.empty and g_sel else pd.DataFrame()
    )
    if busqueda_inv and not df_f.empty:
        df_f = df_f[df_f["Nombre del Insumo"].astype(str).str.contains(busqueda_inv, case=False, na=False)]
    if df_f.empty:
        st.info("Selecciona al menos un grupo para mostrar insumos.")
        return

    # Inicializar estructura centralizada de campos manuales con TODA la unidad
    if "inv_campos" not in st.session_state:
        inv_campos = {}
        for _, row in df_u.iterrows():
            nom = str(row.get("Nombre del Insumo",""))
            safe_nom = re.sub(r'[^a-zA-Z0-9]','_', nom)[:35]
            prev = buscar_insumo_en_actual(df_actual, nom)
            v_alm_prev = limpiar_valor(prev["Alm"]) if prev is not None else 0.0
            v_bar_prev = limpiar_valor(prev["Barra"]) if prev is not None else 0.0
            v_tara_hist = limpiar_valor(prev.get("Tara",0)) if prev is not None else 0.0
            v_tara_cat = limpiar_valor(row.get("Tara",0))
            v_tara_init = v_tara_hist if v_tara_hist > 0 else v_tara_cat
            ud_cat = str(row.get("Unidad de Medida","pz")).lower()
            inv_campos[safe_nom] = {
                "a": v_alm_prev,
                "b": v_bar_prev,
                "u": ud_cat,
                "tara": v_tara_init,
                "p": bool(prev.get("Necesita Compra", False)) if prev is not None else False,
                "c": "",
                "nombre": nom,
                "row": row.to_dict()
            }
        st.session_state.inv_campos = inv_campos
    else:
        inv_campos = st.session_state.inv_campos

    modo_bulk_inv = st.toggle("🚀 Activar Captura Masiva (Bulk)")

    # Autoguardado silencioso cada 5 minutos
    @st.fragment(run_every=300)
    def autoguardar_inventario():
        if modo_bulk_inv:
            data = {"modo": "bulk", "bulk_data": st.session_state.get("inv_bulk_data")}
        else:
            data = {"modo": "manual", "campos": st.session_state.get("inv_campos", {})}
        _guardar_borrador_inventario(session_id, u_sel, hoy_str, data["modo"], data)

    autoguardar_inventario()

    diferencias_grandes = False
    lista_sospechosos = []

    if modo_bulk_inv:
        st.subheader("Captura Masiva de Inventario")
        st.caption("Los datos se conservarán incluso si la página se recarga accidentalmente.")
        if "inv_bulk_data" not in st.session_state or st.session_state.inv_bulk_data is None:
            bulk_data = []
            for _, row in df_u.iterrows():  # toda la unidad, sin filtro de grupo
                nom = str(row.get("Nombre del Insumo",""))
                prev = buscar_insumo_en_actual(df_actual, nom)
                v_alm_prev = limpiar_valor(prev["Alm"]) if prev is not None else 0.0
                v_bar_prev = limpiar_valor(prev["Barra"]) if prev is not None else 0.0
                v_min = limpiar_valor(row.get("Stock Mínimo",0))
                v_tara_hist = limpiar_valor(prev.get("Tara",0)) if prev is not None else 0.0
                v_tara_cat = limpiar_valor(row.get("Tara",0))
                v_tara_init = v_tara_hist if v_tara_hist > 0 else v_tara_cat
                v_ud_med = str(row.get("Unidad de Medida","pz")).lower()
                v_comp_prev = bool(prev.get("Necesita Compra",False)) if prev is not None else False
                anterior_neto = v_alm_prev + v_bar_prev
                bulk_data.append({
                    "Insumo": nom,
                    "Almacén": v_alm_prev,
                    "Barra": v_bar_prev,
                    "Tara": v_tara_init,
                    "Unidad Medida": v_ud_med,
                    "Neto": anterior_neto,
                    "¿Pedir?": v_comp_prev,
                    "Observaciones": "",
                    "row": row,
                    "prev": prev,
                    "stock_min": v_min,
                    "anterior_neto": anterior_neto,
                })
            st.session_state.inv_bulk_data = bulk_data
        else:
            bulk_data = st.session_state.inv_bulk_data

        df_bulk = pd.DataFrame(bulk_data)
        edited_df = st.data_editor(
            df_bulk[["Insumo","Almacén","Barra","Tara","Unidad Medida","Neto","¿Pedir?","Observaciones"]],
            column_config={
                "Insumo": st.column_config.TextColumn(disabled=True),
                "Almacén": st.column_config.NumberColumn(min_value=0.0, step=1.0),
                "Barra": st.column_config.NumberColumn(min_value=0.0, step=1.0),
                "Tara": st.column_config.NumberColumn(min_value=0.0, step=0.1),
                "Unidad Medida": st.column_config.SelectboxColumn(options=UNIDADES_MED),
                "Neto": st.column_config.NumberColumn(min_value=0.0, step=0.1),
                "¿Pedir?": st.column_config.CheckboxColumn(),
                "Observaciones": st.column_config.TextColumn()
            },
            hide_index=True,
            width="stretch",
            disabled=["Insumo"],
            key="inv_bulk_editor"
        )

        for idx, row in edited_df.iterrows():
            neto_actual = limpiar_valor(row.get("Neto", 0))
            anterior = limpiar_valor(bulk_data[idx].get("anterior_neto", 0))
            if anterior > 0 and neto_actual > 0:
                diff_pct = abs(neto_actual - anterior) / anterior * 100
                if diff_pct > 100:
                    diferencias_grandes = True
                    lista_sospechosos.append(f"{row['Insumo']}: anterior {anterior:.1f}, nuevo {neto_actual:.1f} (+{diff_pct:.0f}%)")
                elif diff_pct > 50:
                    st.warning(f"⚠️ {row['Insumo']}: diferencia del {diff_pct:.0f}% respecto al anterior ({anterior:.1f} → {neto_actual:.1f})")

        st.session_state.inv_bulk_data = edited_df.to_dict(orient="records")

        if lista_sospechosos:
            st.divider()
            st.subheader("📋 Insumos con diferencias grandes")
            st.caption("Revisa estos valores antes de procesar. No se bloquea el guardado.")
            filas_diff = []
            for s in lista_sospechosos:
                try:
                    partes = s.split(": ")
                    nombre_diff = partes[0]
                    resto = partes[1]
                    anterior_diff = float(resto.split("anterior ")[1].split(",")[0])
                    nuevo_diff = float(resto.split("nuevo ")[1].split(" ")[0])
                    pct_diff = float(resto.split("+")[1].rstrip("%)"))
                except Exception:
                    continue
                color_diff = "🔴" if pct_diff > 100 else "🟡"
                filas_diff.append({
                    "Insumo": nombre_diff,
                    "Anterior": f"{anterior_diff:.1f}",
                    "Nuevo": f"{nuevo_diff:.1f}",
                    "Dif. %": f"+{pct_diff:.1f}%",
                    "Alerta": color_diff
                })
            if filas_diff:
                df_diff = pd.DataFrame(filas_diff)
                st.dataframe(df_diff, hide_index=True, width="stretch")
        else:
            st.success("No se detectaron diferencias mayores al 50%.")

        if st.button("📥 PROCESAR INVENTARIO BULK", type="primary", width="stretch"):
            ws_his, err = safe_worksheet(sh, "Historial")
            if err:
                st.error(err)
            else:
                fh = ts_hermosillo()
                filas = []
                for _, r_ed in edited_df.iterrows():
                    nom = r_ed["Insumo"]
                    orig = next((x for x in bulk_data if x["Insumo"] == nom), None)
                    if orig is None: continue
                    alm = limpiar_valor(r_ed["Almacén"])
                    barra = limpiar_valor(r_ed["Barra"])
                    tara = limpiar_valor(r_ed["Tara"])
                    neto_input = limpiar_valor(r_ed["Neto"])
                    if neto_input == 0.0 and (alm > 0 or barra > 0 or tara > 0):
                        neto = alm + max(0.0, barra - tara)
                    else:
                        neto = neto_input
                    comprar = bool(r_ed["¿Pedir?"])
                    obs = str(r_ed.get("Observaciones",""))
                    dm = orig["row"]
                    filas.append(construir_fila_historial(
                        unidad=u_sel, nombre=nom, marca=dm.get("Marca",""),
                        proveedor=dm.get("Proveedor",""), grupo=dm.get("Grupo",""),
                        fecha_entrada="", presentacion=dm.get("Presentación de Compra",""),
                        unidad_medida=r_ed["Unidad Medida"], alm=alm, barra=barra,
                        stock_neto=neto, stock_minimo=orig["stock_min"],
                        comprar=comprar, responsable=r_sel, fecha_inventario=fh,
                        tara=tara, observaciones=obs,
                    ))
                ok, msg = append_rows_con_retry(ws_his, filas)
                if ok:
                    dl.cargar_datos_integrales.clear()
                    st.session_state.inventario_guardado = True
                    st.session_state.inv_bulk_data = None
                    _eliminar_borrador_inventario(session_id, u_sel)
                    st.rerun()
                else:
                    st.error(msg)
    else:
        if "inv_bulk_data" in st.session_state:
            st.session_state.inv_bulk_data = None

        if "mostrar_vista_previa" not in st.session_state:
            st.session_state.mostrar_vista_previa = False

        with st.form("form_inventario", clear_on_submit=False):
            h1,h2,h3,h4,h5,h6,h7,h8 = st.columns([2.8,1.0,1.0,1.0,1.0,1.0,1.2,2.5])
            headers = [
                ("Insumo / Ref", "Nombre del insumo y su unidad esperada."),
                ("Almacén", "Cantidad de producto cerrado. Se registra en la unidad definida para este insumo. Ej. 3 pz."),
                ("Barra (bruto)", "Peso bruto del producto abierto en uso. Aquí se descuenta la tara. Ej. 250 gr."),
                ("Medida", "Unidad en la que se está capturando este valor: pz, gr, ml, kg o lt. Debe coincidir con la unidad del catálogo."),
                ("Tara (gr)", "Peso del envase/empaque que se descuenta de la Barra. Si no hay tara, dejar en 0."),
                ("Neto*", "Resultado automático: Almacén + (Barra − Tara). No se escribe manualmente."),
                ("¿Pedir?", "Actívalo si el insumo necesita reabastecimiento. Se reflejará en la Lista de Compra."),
                ("Observaciones", "Cualquier nota adicional para este conteo.")
            ]
            columnas = [h1,h2,h3,h4,h5,h6,h7,h8]
            for col, (label, tooltip) in zip(columnas, headers):
                with col:
                    st.markdown(
                        f'<span title="{tooltip}"><strong>{label}</strong></span>',
                        unsafe_allow_html=True
                    )
            st.markdown("*Neto = Alm + (Barra − Tara). La Tara se descuenta solo de Barra.")
            st.divider()
            regs_form = {}
            for idx_row, row in df_f.iterrows():
                nom      = str(row.get("Nombre del Insumo",""))
                safe_nom = re.sub(r'[^a-zA-Z0-9]','_', nom)[:35]

                # Obtener valores desde inv_campos
                campos = st.session_state.inv_campos.get(safe_nom)
                if campos is None:
                    prev = buscar_insumo_en_actual(df_actual, nom)
                    v_alm_prev = limpiar_valor(prev["Alm"]) if prev is not None else 0.0
                    v_bar_prev = limpiar_valor(prev["Barra"]) if prev is not None else 0.0
                    v_tara_hist = limpiar_valor(prev.get("Tara",0)) if prev is not None else 0.0
                    v_tara_cat = limpiar_valor(row.get("Tara",0))
                    v_tara_init = v_tara_hist if v_tara_hist > 0 else v_tara_cat
                    ud_cat = str(row.get("Unidad de Medida","pz")).lower()
                    campos = {
                        "a": v_alm_prev,
                        "b": v_bar_prev,
                        "u": ud_cat,
                        "tara": v_tara_init,
                        "p": bool(prev.get("Necesita Compra", False)) if prev is not None else False,
                        "c": "",
                        "nombre": nom,
                        "row": row.to_dict()
                    }
                    st.session_state.inv_campos[safe_nom] = campos

                c1,c2,c3,c4,c5,c6,c7,c8 = st.columns([2.8,1.0,1.0,1.0,1.0,1.0,1.2,2.5])
                with c1:
                    st.write(f"**{nom}** *({campos['u']})*")
                    st.caption(f"Marca: {row.get('Marca','-')} | Prov: {row.get('Proveedor','-')}")
                    v_prev = campos.get("a",0.0) + max(0.0, campos.get("b",0.0) - campos.get("tara",0.0))
                    v_min = limpiar_valor(row.get("Stock Mínimo",0))
                    diff = v_prev - v_min
                    color = "green" if diff >= 0 else "red"
                    tara_txt = f" | Tara: {campos.get('tara',0.0)}" if campos.get('tara',0.0) > 0 else ""
                    st.markdown(
                        f"<small>Anterior: {v_prev} | Mín: {v_min} (<span style='color:{color}'>{diff:+.1f}</span>){tara_txt}</small>",
                        unsafe_allow_html=True
                    )
                with c2:
                    v_a = st.number_input("Alm", min_value=0.0, step=1.0, value=float(campos.get("a",0.0)),
                                          key=f"a_{safe_nom}", label_visibility="collapsed")
                with c3:
                    v_b = st.number_input("Bar", min_value=0.0, step=1.0, value=float(campos.get("b",0.0)),
                                          key=f"b_{safe_nom}", label_visibility="collapsed")
                with c4:
                    u_actual = str(campos.get("u","pz")).lower()
                    v_u = st.selectbox("U", UNIDADES_MED,
                                       index=UNIDADES_MED.index(u_actual) if u_actual in UNIDADES_MED else 0,
                                       key=f"u_{safe_nom}", label_visibility="collapsed")
                with c5:
                    v_tara_manual = st.number_input("Tara", min_value=0.0, step=0.1, value=float(campos.get("tara",0.0)),
                                                    key=f"tara_{safe_nom}", label_visibility="collapsed")
                with c6:
                    v_b_neto = max(0.0, v_b - v_tara_manual)
                    v_n_display = v_a + v_b_neto
                    st.write(f"**{v_n_display:.1f}**")
                with c7:
                    v_p = st.checkbox("🛒", value=bool(campos.get("p", False)), key=f"p_{safe_nom}")
                with c8:
                    v_c = st.text_input("Obs", value=str(campos.get("c","")), key=f"c_{safe_nom}", label_visibility="collapsed")

                # Actualizar inv_campos
                st.session_state.inv_campos[safe_nom] = {
                    "a": v_a,
                    "b": v_b,
                    "u": v_u,
                    "tara": v_tara_manual,
                    "p": v_p,
                    "c": v_c,
                    "nombre": nom,
                    "row": row.to_dict()
                }

                regs_form[nom] = {
                    "a": v_a,
                    "b": v_b_neto,
                    "n": v_n_display,
                    "u": v_u,
                    "p": v_p,
                    "c": v_c,
                    "tara": v_tara_manual,
                    "row": row,
                    "anterior": v_prev,
                }

            revisar = st.form_submit_button("🔍 Revisar captura", width="stretch")
            if revisar:
                st.session_state.mostrar_vista_previa = True
                _guardar_borrador_inventario(session_id, u_sel, hoy_str, "manual", {"campos": st.session_state.inv_campos})
                st.rerun()

            if st.session_state.mostrar_vista_previa:
                st.divider()
                st.subheader("📋 Resumen de captura")
                filas_vp = []
                for n, info in regs_form.items():
                    anterior = info.get("anterior", 0.0)
                    nuevo = info["n"]
                    if anterior > 0 and nuevo > 0:
                        diff_pct = (nuevo - anterior) / anterior * 100
                    else:
                        diff_pct = 0
                    if diff_pct > 20:
                        color = "🔴"
                    elif diff_pct > 10:
                        color = "🟡"
                    else:
                        color = "⚪"
                    filas_vp.append({
                        "Insumo": n,
                        "Anterior": f"{anterior:.1f}",
                        "Nuevo": f"{nuevo:.1f}",
                        "Dif. %": f"{diff_pct:+.1f}%",
                        "Alerta": color
                    })
                df_vp = pd.DataFrame(filas_vp)
                st.dataframe(df_vp, hide_index=True, width="stretch")
                st.caption("🔴 >20% de diferencia  |  🟡 >10%  |  ⚪ ≤10%")

            if lista_sospechosos:
                st.divider()
                st.subheader("📋 Insumos con diferencias grandes")
                st.caption("Revisa estos valores antes de procesar. No se bloquea el guardado.")
                filas_diff = []
                for s in lista_sospechosos:
                    try:
                        partes = s.split(": ")
                        nombre_diff = partes[0]
                        resto = partes[1]
                        anterior_diff = float(resto.split("anterior ")[1].split(",")[0])
                        nuevo_diff = float(resto.split("nuevo ")[1].split(" ")[0])
                        pct_diff = float(resto.split("+")[1].rstrip("%)"))
                    except Exception:
                        continue
                    color_diff = "🔴" if pct_diff > 100 else "🟡"
                    filas_diff.append({
                        "Insumo": nombre_diff,
                        "Anterior": f"{anterior_diff:.1f}",
                        "Nuevo": f"{nuevo_diff:.1f}",
                        "Dif. %": f"+{pct_diff:.1f}%",
                        "Alerta": color_diff
                    })
                if filas_diff:
                    df_diff = pd.DataFrame(filas_diff)
                    st.dataframe(df_diff, hide_index=True, width="stretch")

            btn_inv = st.form_submit_button("📥 PROCESAR INVENTARIO", width="stretch", type="primary")
            if btn_inv:
                ws_his, err = safe_worksheet(sh, "Historial")
                if err:
                    st.error(err)
                else:
                    fh = ts_hermosillo()
                    filas = []
                    for n, info in regs_form.items():
                        dm = info["row"]
                        filas.append(construir_fila_historial(
                            unidad=u_sel, nombre=n, marca=dm.get("Marca",""),
                            proveedor=dm.get("Proveedor",""), grupo=dm.get("Grupo",""),
                            fecha_entrada="", presentacion=dm.get("Presentación de Compra",""),
                            unidad_medida=info["u"], alm=info["a"], barra=info["b"],
                            stock_neto=info["n"], stock_minimo=dm.get("Stock Mínimo",0),
                            comprar=info["p"], responsable=r_sel, fecha_inventario=fh,
                            tara=info["tara"], observaciones=info["c"],
                        ))
                    ok, msg = append_rows_con_retry(ws_his, filas)
                    if ok:
                        dl.cargar_datos_integrales.clear()
                        st.session_state.inventario_guardado = True
                        st.session_state.mostrar_vista_previa = False
                        _eliminar_borrador_inventario(session_id, u_sel)
                        st.rerun()
                    else:
                        st.error(msg)
