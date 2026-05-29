import streamlit as st
import pandas as pd
import re
# Importación directa y segura
from data_loaders import cargar_datos_integrales

from inventario import obtener_ultimo_inventario, buscar_insumo_en_actual, construir_fila_historial
from sheets import safe_worksheet, sh, append_rows_con_retry
from utils import limpiar_valor, ts_hermosillo, normalizar_nombre
from config import UNIDADES, UNIDADES_MED, GRUPOS
from components.avisos import mostrar_avisos
from auth import tiene_permiso

def show_inventario():
    if not tiene_permiso("Inventario"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    try:
        df_raw, df_historial = cargar_datos_integrales()
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
        if st.button("➕ Nueva captura", use_container_width=True):
            for key in list(st.session_state.keys()):
                if key.startswith(("a_", "b_", "u_", "tara_", "p_", "c_", "inv_bulk_data")):
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
        r_sel = st.selectbox("👤 Responsable", responsables, index=resp_idx, disabled=(st.session_state.user_role != "admin"))
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

    modo_bulk_inv = st.toggle("🚀 Activar Captura Masiva (Bulk)")
    diferencias_grandes = False
    lista_sospechosos = []

    if modo_bulk_inv:
        st.subheader("Captura Masiva de Inventario")
        st.caption("Los datos se conservarán incluso si la página se recarga accidentalmente.")
        if "inv_bulk_data" not in st.session_state or st.session_state.inv_bulk_data is None:
            bulk_data = []
            for idx_row, row in df_f.iterrows():
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
                bulk_data.append({
                    "Insumo": nom,
                    "Almacén": v_alm_prev,
                    "Barra": v_bar_prev,
                    "Tara": v_tara_init,
                    "Unidad Medida": v_ud_med,
                    "Neto": v_alm_prev + max(0.0, v_bar_prev - v_tara_init),
                    "¿Pedir?": v_comp_prev,
                    "Observaciones": "",
                    "row": row,
                    "prev": prev,
                    "stock_min": v_min,
                    "anterior_neto": v_prev if prev is not None else 0.0
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
            use_container_width=True,
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

        if diferencias_grandes:
            st.error("🚨 Se detectaron diferencias mayores al 100% en los siguientes insumos:")
            for s in lista_sospechosos:
                st.write(f"• {s}")
            confirmar_bulk = st.checkbox("✅ Confirmo que quiero guardar estas diferencias grandes")
        else:
            confirmar_bulk = True

        if st.button("📥 PROCESAR INVENTARIO BULK", type="primary", use_container_width=True, disabled=(not confirmar_bulk)):
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
                    cargar_datos_integrales.clear()
                    st.session_state.inventario_guardado = True
                    st.session_state.inv_bulk_data = None
                    st.rerun()
                else:
                    st.error(msg)
    else:
        if "inv_bulk_data" in st.session_state:
            st.session_state.inv_bulk_data = None

        with st.form("form_inventario", clear_on_submit=False):
            h1,h2,h3,h4,h5,h6,h7,h8 = st.columns([2.8,1.0,1.0,1.0,1.0,1.0,1.2,2.5])
            for col, label in zip([h1,h2,h3,h4,h5,h6,h7,h8],
                                  ["Insumo / Ref","Almacén","Barra (bruto)","Medida","Tara (gr)","Neto*","¿Pedir?","Observaciones"]):
                col.write(f"**{label}**")
            st.markdown("*Neto = Alm + (Barra − Tara). La Tara se descuenta solo de Barra.")
            st.divider()
            regs_form = {}
            for idx_row, row in df_f.iterrows():
                nom      = str(row.get("Nombre del Insumo",""))
                safe_nom = re.sub(r'[^a-zA-Z0-9]','_', nom)[:35] + f"_{idx_row}"
                prev        = buscar_insumo_en_actual(df_actual, nom)
                v_prev      = prev["Stock Neto Calculado"] if prev is not None else 0.0
                v_alm_prev  = limpiar_valor(prev["Alm"])   if prev is not None else 0.0
                v_bar_prev  = limpiar_valor(prev["Barra"]) if prev is not None else 0.0
                v_min       = limpiar_valor(row.get("Stock Mínimo",0))
                v_tara_hist = limpiar_valor(prev.get("Tara",0)) if prev is not None else 0.0
                v_tara_cat  = limpiar_valor(row.get("Tara",0))
                v_tara_init = v_tara_hist if v_tara_hist > 0 else v_tara_cat
                ud_cat = str(row.get("Unidad de Medida","pz")).lower()
                c1,c2,c3,c4,c5,c6,c7,c8 = st.columns([2.8,1.0,1.0,1.0,1.0,1.0,1.2,2.5])
                with c1:
                    st.write(f"**{nom}**")
                    st.caption(f"Marca: {row.get('Marca','-')} | Prov: {row.get('Proveedor','-')}")
                    diff  = v_prev - v_min
                    color = "green" if diff >= 0 else "red"
                    tara_txt = f" | Tara: {v_tara_init}" if v_tara_init > 0 else ""
                    st.markdown(
                        f"<small>Anterior: {v_prev} | Mín: {v_min} (<span style='color:{color}'>{diff:+.1f}</span>){tara_txt}</small>",
                        unsafe_allow_html=True
                    )
                with c2:
                    alm_key = f"a_{safe_nom}"
                    if alm_key not in st.session_state: st.session_state[alm_key] = v_alm_prev
                    v_a = st.number_input("Alm", min_value=0.0, step=1.0, key=alm_key, label_visibility="collapsed")
                with c3:
                    bar_key = f"b_{safe_nom}"
                    if bar_key not in st.session_state: st.session_state[bar_key] = v_bar_prev
                    v_b = st.number_input("Bar", min_value=0.0, step=1.0, key=bar_key, label_visibility="collapsed")
                with c4:
                    u_act = str(row.get("Unidad de Medida","pz")).lower()
                    v_u = st.selectbox("U", UNIDADES_MED,
                                       index=UNIDADES_MED.index(u_act) if u_act in UNIDADES_MED else 0,
                                       key=f"u_{safe_nom}", label_visibility="collapsed")
                    if v_u != ud_cat:
                        st.warning(f"⚠️ Unidad del catálogo: {ud_cat}")
                with c5:
                    tara_key = f"tara_{safe_nom}"
                    if tara_key not in st.session_state: st.session_state[tara_key] = v_tara_init
                    v_tara_manual = st.number_input("Tara", min_value=0.0, step=0.1,
                                                    key=tara_key, label_visibility="collapsed")
                with c6:
                    v_b_neto    = max(0.0, v_b - v_tara_manual)
                    v_n_display = v_a + v_b_neto
                    st.write(f"**{v_n_display:.1f}**")
                    if v_prev > 0 and v_n_display > 0:
                        pct_diff = abs(v_n_display - v_prev) / v_prev * 100
                        if pct_diff > 100:
                            diferencias_grandes = True
                            lista_sospechosos.append(f"{nom}: anterior {v_prev:.1f}, nuevo {v_n_display:.1f} (+{pct_diff:.0f}%)")
                        elif pct_diff > 50:
                            st.warning(f"⚠️ Diferencia del {pct_diff:.0f}% respecto al anterior")
                with c7:
                    v_comprar_prev = bool(prev.get("Necesita Compra",False)) if prev is not None else False
                    ck_key = f"p_{safe_nom}"
                    if ck_key not in st.session_state: st.session_state[ck_key] = v_comprar_prev
                    v_p = st.checkbox("🛒", key=ck_key)
                with c8:
                    v_c = st.text_input("Obs", key=f"c_{safe_nom}", label_visibility="collapsed", placeholder="Opcional")
                regs_form[nom] = {"a":v_a,"b":v_b_neto,"n":v_n_display,"u":v_u,"p":v_p,"c":v_c,"tara":v_tara_manual,"row":row}

            if diferencias_grandes:
                st.error("🚨 Se detectaron diferencias mayores al 100%:")
                for s in lista_sospechosos:
                    st.write(f"• {s}")
                confirmar = st.checkbox("✅ Confirmo que quiero guardar estas diferencias grandes")
            else:
                confirmar = True

            btn_inv = st.form_submit_button("📥 PROCESAR INVENTARIO", use_container_width=True, type="primary", disabled=(not confirmar))

        if btn_inv:
            ws_his, err = safe_worksheet(sh, "Historial")
            if err:
                st.error(err)
            else:
                fh    = ts_hermosillo()
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
                    cargar_datos_integrales.clear()
                    st.session_state.inventario_guardado = True
                    st.rerun()
                else:
                    st.error(msg)
