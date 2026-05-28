import streamlit as st
import time
import calendar
import pandas as pd
from data_loaders import cargar_presupuesto
from sheets import _asegurar_hoja_presupuesto, append_rows_con_retry
from utils import limpiar_valor, ahora_hermosillo
from config import COLS_PRESUPUESTO
from auth import tiene_permiso

def show_presupuesto():
    if not tiene_permiso("Presupuesto"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    st.title("📋 Presupuesto Anual")
    if not st.session_state.auth_status:
        st.error("🔒 Autenticación requerida.")
        st.stop()
    df_ppto = cargar_presupuesto()
    año_actual_p = ahora_hermosillo().year
    años_opts    = list(range(2024, 2031))
    idx_año_def  = años_opts.index(año_actual_p) if año_actual_p in años_opts else 1
    año_sel      = st.selectbox("📅 Año:", años_opts, index=idx_año_def)
    ppto_año = {}
    if not df_ppto.empty:
        df_año_p = df_ppto[df_ppto["Año"].apply(limpiar_valor) == año_sel]
        for _, r in df_año_p.iterrows():
            mes_p = int(limpiar_valor(r["Mes"]))
            if 1 <= mes_p <= 12:
                ppto_año[mes_p] = {
                    "Meta_Total": limpiar_valor(r.get("Meta_Total", 0)),
                    "Meta_POS":   limpiar_valor(r.get("Meta_POS",   0)),
                    "Meta_Uber":  limpiar_valor(r.get("Meta_Uber",  0)),
                    "Meta_Rappi": limpiar_valor(r.get("Meta_Rappi", 0)),
                    "Notas":      str(r.get("Notas", "")),
                }
    desglose_p = st.toggle("🔀 Desglosar por canal (POS / Uber Eats / Rappi)", value=False)
    st.subheader(f"Metas mensuales — {año_sel}")
    meses_nombres_p = [calendar.month_name[m].capitalize() for m in range(1, 13)]
    entradas_p = {}
    for row_i in range(4):
        cols_p = st.columns(3)
        for col_i in range(3):
            mes_num_p = row_i * 3 + col_i + 1
            if mes_num_p > 12:
                break
            mes_nom_p = meses_nombres_p[mes_num_p - 1]
            prev_p    = ppto_año.get(mes_num_p, {})
            with cols_p[col_i]:
                st.write(f"**{mes_nom_p}**")
                meta_total_p = st.number_input(
                    f"Total ({mes_nom_p}):", min_value=0.0, step=1000.0,
                    value=float(prev_p.get("Meta_Total", 0)),
                    key=f"ppto_{año_sel}_{mes_num_p}_total"
                )
                meta_pos_p = meta_uber_p = meta_rappi_p = 0.0
                if desglose_p:
                    meta_pos_p   = st.number_input(f"POS:",   min_value=0.0, step=500.0, value=float(prev_p.get("Meta_POS",   0)), key=f"ppto_{año_sel}_{mes_num_p}_pos")
                    meta_uber_p  = st.number_input(f"Uber:",  min_value=0.0, step=500.0, value=float(prev_p.get("Meta_Uber",  0)), key=f"ppto_{año_sel}_{mes_num_p}_uber")
                    meta_rappi_p = st.number_input(f"Rappi:", min_value=0.0, step=500.0, value=float(prev_p.get("Meta_Rappi", 0)), key=f"ppto_{año_sel}_{mes_num_p}_rappi")
                entradas_p[mes_num_p] = {
                    "Meta_Total": meta_total_p, "Meta_POS": meta_pos_p,
                    "Meta_Uber": meta_uber_p, "Meta_Rappi": meta_rappi_p, "Notas": "",
                }
    total_anual_p = sum(v["Meta_Total"] for v in entradas_p.values())
    st.divider()
    st.metric("💰 Presupuesto Anual Total", f"${total_anual_p:,.2f}")
    if st.button("💾 GUARDAR PRESUPUESTO", type="primary", use_container_width=True):
        ws_ppto, err_ppto = _asegurar_hoja_presupuesto()
        if err_ppto:
            st.error(err_ppto)
        else:
            try:
                todos_ppto = ws_ppto.get_all_values()
                if len(todos_ppto) > 1:
                    df_todos_p = pd.DataFrame(todos_ppto[1:], columns=todos_ppto[0])
                    df_sin_año = df_todos_p[df_todos_p["Año"].astype(str).str.strip() != str(año_sel)]
                    ws_ppto.clear()
                    ws_ppto.append_row(COLS_PRESUPUESTO)
                    if not df_sin_año.empty:
                        ws_ppto.append_rows(df_sin_año.values.tolist(), value_input_option="USER_ENTERED")
                else:
                    ws_ppto.clear()
                    ws_ppto.append_row(COLS_PRESUPUESTO)
                nuevas_filas_p = [
                    [año_sel, mes_n, v["Meta_Total"], v["Meta_POS"], v["Meta_Uber"], v["Meta_Rappi"], v["Notas"]]
                    for mes_n, v in entradas_p.items()
                ]
                ws_ppto.append_rows(nuevas_filas_p, value_input_option="USER_ENTERED")
                cargar_presupuesto.clear()
                st.success(f"✅ Presupuesto {año_sel} guardado. Total anual: ${total_anual_p:,.2f}")
                time.sleep(0.5)
                st.rerun()
            except Exception as e_ppto:
                st.error(f"Error al guardar presupuesto: {e_ppto}")
