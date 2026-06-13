import streamlit as st
import pandas as pd
import time
import data_loaders as dl

from inventario import obtener_ultimo_inventario, buscar_insumo_en_actual, construir_fila_historial
from sheets import safe_worksheet, sh, append_rows_con_retry
from utils import limpiar_valor, ts_hermosillo
from config import UNIDADES
from components.avisos import mostrar_avisos
from auth import tiene_permiso

def show_ingresos():
    if not tiene_permiso("Ingresos"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    try:
        df_raw, df_historial = dl.cargar_datos_integrales()
    except Exception as e:
        st.error(f"Error al cargar los datos: {e}")
        st.stop()
    st.title("📥 Entrada de compras")
    mostrar_avisos("Ingresos")
    if not st.session_state.auth_status:
        st.error("🔒 Autenticación requerida.")
        st.stop()
    st.info("Ingresa insumos recibidos. Se sumarán al último stock de Almacén registrado.")
    col_u, col_r = st.columns(2)
    with col_u:
        u_sel = st.selectbox("🏢 Unidad receptora:", UNIDADES)
    responsables = st.session_state.responsables or ["Raúl"]
    resp_idx = responsables.index(st.session_state.current_user) if st.session_state.current_user in responsables else 0
    with col_r:
        r_sel = st.selectbox("👤 Responsable:", responsables, index=resp_idx,
                             disabled=(st.session_state.user_role != "admin"))
    df_u = df_raw[df_raw["Unidad de Negocio"] == u_sel] if not df_raw.empty else pd.DataFrame()
    if df_u.empty:
        st.warning("Sin insumos registrados para esta unidad.")
        st.stop()
    df_actual    = obtener_ultimo_inventario(df_historial, u_sel)
    nombres_ins  = df_u["Nombre del Insumo"].dropna().unique().tolist()
    st.divider()
    modo_bulk = st.toggle("🚀 Activar Ingreso Masivo Rápido (Bulk)")
    if modo_bulk:
        st.subheader("Carga Bulk")
        bulk_data = []
        for _, r in df_u.iterrows():
            nom = r["Nombre del Insumo"]
            prev = buscar_insumo_en_actual(df_actual, nom)
            bulk_data.append({"Insumo":nom,
                              "Stock Alm":limpiar_valor(prev["Alm"]) if prev is not None else 0.0,
                              "Stock Barra":limpiar_valor(prev["Barra"]) if prev is not None else 0.0,
                              "+ Ingreso":0.0})
        df_edit   = pd.DataFrame(bulk_data)
        edited_df = st.data_editor(df_edit[["Insumo","Stock Alm","Stock Barra","+ Ingreso"]],
                                   hide_index=True, width="stretch",
                                   disabled=["Insumo","Stock Alm","Stock Barra"])
        proc_bulk = st.session_state.get("_procesando_bulk", False)
        btn_bulk  = st.button("📦 EJECUTAR INGRESO BULK", type="primary", disabled=proc_bulk)
        if btn_bulk and not proc_bulk:
            st.session_state["_procesando_bulk"] = True
            ws_his, err = safe_worksheet(sh, "Historial")
            if err:
                st.error(err)
                st.session_state["_procesando_bulk"] = False
            else:
                fh = ts_hermosillo()
                filas_bulk = []
                for _, r_ed in edited_df.iterrows():
                    ingreso = limpiar_valor(r_ed["+ Ingreso"])
                    if ingreso <= 0: continue
                    nom  = r_ed["Insumo"]
                    orig = next((x for x in bulk_data if x["Insumo"] == nom), None)
                    if orig is None: continue
                    row_matches = df_u[df_u["Nombre del Insumo"] == nom]
                    if row_matches.empty: continue
                    row_ins = row_matches.iloc[0]
                    v_min   = limpiar_valor(row_ins.get("Stock Mínimo",0))
                    tara_bulk = limpiar_valor(row_ins.get("Tara",0))
                    nuevo_a   = orig["Stock Alm"] + ingreso
                    nuevo_n   = nuevo_a + orig["Stock Barra"]
                    filas_bulk.append(construir_fila_historial(
                        unidad=u_sel, nombre=nom, marca=row_ins.get("Marca",""),
                        proveedor=row_ins.get("Proveedor",""), grupo=row_ins.get("Grupo",""),
                        fecha_entrada=fh, presentacion=row_ins.get("Presentación de Compra",""),
                        unidad_medida=row_ins.get("Unidad de Medida","pz"), alm=nuevo_a,
                        barra=orig["Stock Barra"], stock_neto=nuevo_n, stock_minimo=v_min,
                        comprar=nuevo_n < v_min, responsable=r_sel, fecha_inventario="",
                        tara=tara_bulk, observaciones="",
                        cantidad_ingresada=ingreso,
                    ))
                st.session_state["_procesando_bulk"] = False
                if not filas_bulk:
                    st.warning("No ingresaste cantidades mayores a 0.")
                else:
                    ok, msg = append_rows_con_retry(ws_his, filas_bulk)
                    if ok:
                        dl.cargar_datos_integrales.clear()
                        st.success(f"Ingreso masivo registrado: {len(filas_bulk)} refs. {msg}")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)
    else:
        insumos_llegados = st.multiselect("🔍 Insumos recibidos:", sorted(nombres_ins))
        if insumos_llegados:
            regs_ingreso = {}
            st.divider()
            h1,h2,h3,h4,h5 = st.columns([3,2,1.5,1.5,2])
            for col, label in zip([h1,h2,h3,h4,h5],["Insumo","Stock Ant (Alm+Bar)","+ Cantidad","Tara","= Nuevo Total"]):
                col.write(f"**{label}**")
            st.divider()
            for i, nom in enumerate(insumos_llegados):
                row_matches = df_u[df_u["Nombre del Insumo"] == nom]
                if row_matches.empty: continue
                row_ins  = row_matches.iloc[0]
                prev     = buscar_insumo_en_actual(df_actual, nom)
                v_a_prev = limpiar_valor(prev["Alm"])   if prev is not None else 0.0
                v_b_prev = limpiar_valor(prev["Barra"]) if prev is not None else 0.0
                v_min    = limpiar_valor(row_ins.get("Stock Mínimo",0))
                c1,c2,c3,c4,c5 = st.columns([3,2,1.5,1.5,2])
                with c1:
                    st.write(f"**{nom}**")
                    st.caption(f"Marca: {row_ins.get('Marca','-')} | Prov: {row_ins.get('Proveedor','-')}")
                with c2:
                    st.write(f"Almacén: {v_a_prev} | Barra: {v_b_prev}")
                    st.write(f"**Total Ant: {v_a_prev + v_b_prev}**")
                with c3:
                    cant_ingreso = st.number_input("Ingreso", min_value=0.0, step=1.0, value=None,
                                                   key=f"ing_{i}", label_visibility="collapsed", placeholder="0")
                    cant_ingreso = cant_ingreso if cant_ingreso is not None else 0.0
                with c4:
                    tara_ingreso = st.number_input("Tara", min_value=0.0, step=0.1, value=None,
                                                   key=f"tara_ing_{i}", label_visibility="collapsed", placeholder="tara")
                    tara_ingreso = tara_ingreso if tara_ingreso is not None else 0.0
                with c5:
                    cant_neta  = max(0.0, cant_ingreso - tara_ingreso)
                    nuevo_alm  = v_a_prev + cant_neta
                    nuevo_neto = nuevo_alm + v_b_prev
                    st.success(f"**{nuevo_neto:.1f}**")
                regs_ingreso[nom] = {"nuevo_a":nuevo_alm,"b":v_b_prev,"nuevo_n":nuevo_neto,"row":row_ins,"min":v_min,"tara":tara_ingreso,"cant_ingreso":cant_ingreso}
                st.divider()
            proc_ing = st.session_state.get("_procesando_ingreso", False)
            btn_ing  = st.button("📦 EJECUTAR INGRESO", width="stretch", type="primary", disabled=proc_ing)
            if btn_ing and not proc_ing:
                st.session_state["_procesando_ingreso"] = True
                ws_his, err = safe_worksheet(sh, "Historial")
                if err:
                    st.error(err)
                    st.session_state["_procesando_ingreso"] = False
                else:
                    fh    = ts_hermosillo()
                    filas = []
                    for n, info in regs_ingreso.items():
                        dm = info["row"]
                        filas.append(construir_fila_historial(
                            unidad=u_sel, nombre=n, marca=dm.get("Marca",""),
                            proveedor=dm.get("Proveedor",""), grupo=dm.get("Grupo",""),
                            fecha_entrada=fh, presentacion=dm.get("Presentación de Compra",""),
                            unidad_medida=dm.get("Unidad de Medida","pz"),
                            alm=info["nuevo_a"], barra=info["b"], stock_neto=info["nuevo_n"],
                            stock_minimo=info["min"], comprar=info["nuevo_n"] < info["min"],
                            responsable=r_sel, fecha_inventario="", tara=info["tara"], observaciones="",
                            cantidad_ingresada=info["cant_ingreso"],
                        ))
                    ok, msg = append_rows_con_retry(ws_his, filas)
                    st.session_state["_procesando_ingreso"] = False
                    if ok:
                        dl.cargar_datos_integrales.clear()
                        st.success(f"Ingreso registrado. {msg}")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(msg)
