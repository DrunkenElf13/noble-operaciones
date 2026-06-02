import streamlit as st
import pandas as pd
import time
import uuid
from data_loaders import cargar_gastos
from sheets import _asegurar_hoja_gastos, append_rows_con_retry
from utils import limpiar_valor, ahora_hermosillo
from components.avisos import mostrar_avisos
from auth import tiene_permiso

def show_gastos():
    if not tiene_permiso("RegistrarGasto"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    st.title("Registrar Gasto")
    mostrar_avisos("RegistrarGasto")
    if not st.session_state.auth_status:
        st.error("Autenticación requerida.")
        st.stop()
    df_gastos = cargar_gastos()
    with st.form("f_gasto", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            fecha_g   = st.date_input("Fecha", value=ahora_hermosillo().date())
            periodo_g = st.selectbox("Período", ["Día", "Mes"])
            tipo_g    = st.selectbox("Tipo", ["Fijo", "Variable"],
                                     help="Fijo: se repite cada período (renta, nómina). Variable: depende del volumen o circunstancias.")
        with col2:
            categoria_g = st.text_input("Categoría", placeholder="Ej: Renta, Nómina, Gas, Servicios, Insumos...")
            concepto_g  = st.text_input("Concepto", placeholder="Descripción específica del gasto")
            monto_g     = st.number_input("Monto ($)", min_value=0.0, step=10.0)
        responsables_g = st.session_state.responsables or ["Raúl"]
        resp_idx_g = responsables_g.index(st.session_state.current_user) if st.session_state.current_user in responsables_g else 0
        responsable_g = st.selectbox("Responsable", responsables_g, index=resp_idx_g,
                                      disabled=(st.session_state.user_role != "admin"))
        notas_g = st.text_input("Notas (opcional)")
        if st.form_submit_button("Registrar gasto", width="stretch", type="primary"):
            if not categoria_g.strip():
                st.error("La categoría es obligatoria.")
            elif not concepto_g.strip():
                st.error("El concepto es obligatorio.")
            elif monto_g <= 0:
                st.error("El monto debe ser mayor a cero.")
            else:
                ws_g, err = _asegurar_hoja_gastos()
                if err:
                    st.error(err)
                else:
                    fila_g = [
                        str(uuid.uuid4())[:8],
                        fecha_g.strftime("%Y-%m-%d"),
                        periodo_g, tipo_g, categoria_g.strip(), concepto_g.strip(),
                        monto_g, responsable_g, notas_g.strip()
                    ]
                    ok, msg = append_rows_con_retry(ws_g, [fila_g])
                    if ok:
                        cargar_gastos.clear()
                        st.success(f"Gasto registrado: ${monto_g:,.2f} — {concepto_g.strip()}")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(msg)
    st.divider()
    st.subheader("Gastos recientes")
    if not df_gastos.empty:
        cols_g_show = ["Fecha","Periodo","Tipo","Categoria","Concepto","Monto","Responsable","Notas"]
        cols_g_ok   = [c for c in cols_g_show if c in df_gastos.columns]
        df_g_disp   = df_gastos[cols_g_ok].copy()
        df_g_disp["Fecha"] = pd.to_datetime(df_g_disp["Fecha"], errors="coerce")
        st.dataframe(df_g_disp.sort_values("Fecha", ascending=False).head(30), hide_index=True, width="stretch")
        hoy_g = ahora_hermosillo().date()
        df_gastos["_fecha_dt"] = pd.to_datetime(df_gastos["Fecha"], errors="coerce")
        df_g_mes = df_gastos[
            (df_gastos["_fecha_dt"].dt.month == hoy_g.month) &
            (df_gastos["_fecha_dt"].dt.year  == hoy_g.year)
        ]
        total_mes_g   = df_g_mes["Monto"].apply(limpiar_valor).sum()
        total_fijos   = df_g_mes[df_g_mes["Tipo"]=="Fijo"]["Monto"].apply(limpiar_valor).sum()
        total_var     = df_g_mes[df_g_mes["Tipo"]=="Variable"]["Monto"].apply(limpiar_valor).sum()
        mg1, mg2, mg3 = st.columns(3)
        mg1.metric("Total gastado este mes", f"${total_mes_g:,.2f}")
        mg2.metric("Gastos Fijos",           f"${total_fijos:,.2f}")
        mg3.metric("Gastos Variables",       f"${total_var:,.2f}")
    else:
        st.info("Sin gastos registrados aún.")
