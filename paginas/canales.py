import streamlit as st
import pandas as pd
import time
from data_loaders import cargar_config_canales
from sheets import _asegurar_hoja_config_canales, _asegurar_hoja_canal, safe_worksheet, sh, append_rows_con_retry
from utils import ahora_hermosillo
from components.avisos import mostrar_avisos
from auth import tiene_permiso

def show_canales():
    if not tiene_permiso("CanalesVenta"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    st.title("🛒 Canales de Venta Adicionales")
    mostrar_avisos("CanalesVenta")
    if not st.session_state.auth_status:
        st.error("🔒 Autenticación requerida.")
        st.stop()
    df_cfg = cargar_config_canales()
    _asegurar_hoja_config_canales()
    tab_can1, tab_can2 = st.tabs(["📋 Registrar Evento", "⚙️ Gestionar Canales"])
    with tab_can2:
        st.subheader("Configuración de Canales")
        if not df_cfg.empty:
            st.dataframe(df_cfg, hide_index=True, width="stretch")
        with st.form("f_new_canal"):
            canal_nombre = st.text_input("Nombre del Canal:")
            tipo_meta = st.selectbox("Tipo de Meta:", ["mensual", "fija"])
            meta_valor = st.number_input("Meta ($):", min_value=0.0, step=100.0)
            notas_canal = st.text_input("Notas:")
            if st.form_submit_button("➕ Crear Canal"):
                if not canal_nombre.strip():
                    st.error("El nombre del canal es obligatorio.")
                else:
                    ws_cfg, err = _asegurar_hoja_config_canales()
                    if not err:
                        if not df_cfg.empty and canal_nombre in df_cfg["Canal"].values:
                            st.error("El canal ya existe.")
                        else:
                            ws_cfg.append_row([canal_nombre, tipo_meta, meta_valor, notas_canal], value_input_option="USER_ENTERED")
                            _asegurar_hoja_canal(canal_nombre)
                            cargar_config_canales.clear()
                            st.success(f"Canal '{canal_nombre}' creado.")
                            time.sleep(1)
                            st.rerun()
                    else:
                        st.error(err)
    with tab_can1:
        st.subheader("Registrar Venta por Evento")
        canales_list = df_cfg["Canal"].tolist() if not df_cfg.empty else []
        if not canales_list:
            st.warning("No hay canales configurados. Ve a la pestaña 'Gestionar Canales' para crear uno.")
        else:
            canal_sel = st.selectbox("Canal:", canales_list)
            with st.form("f_evento_canal"):
                col_ev1, col_ev2 = st.columns(2)
                with col_ev1:
                    fecha_ev = st.date_input("Fecha:", value=ahora_hermosillo().date())
                    monto_ev = st.number_input("Monto ($):", min_value=0.0, step=10.0)
                with col_ev2:
                    desc_ev = st.text_input("Descripción / Cliente:")
                    fecha_serv_ev = st.date_input("Fecha del Servicio / Entrega:", value=fecha_ev)
                metodo_pago_ev = st.text_input("Método de Pago (opcional):")
                adeudo_ev = st.number_input("Adeudo / Saldo pendiente ($):", min_value=0.0, step=10.0, value=0.0)
                resp_ev = st.selectbox("Responsable:", st.session_state.responsables, index=st.session_state.responsables.index(st.session_state.current_user) if st.session_state.current_user in st.session_state.responsables else 0)
                if st.form_submit_button("💾 Registrar Evento"):
                    if monto_ev <= 0:
                        st.error("El monto debe ser mayor a cero.")
                    else:
                        ws_canal, err = _asegurar_hoja_canal(canal_sel)
                        if err:
                            st.error(err)
                        else:
                            fila_ev = [
                                canal_sel, fecha_ev.strftime("%Y-%m-%d"), monto_ev,
                                desc_ev, fecha_serv_ev.strftime("%Y-%m-%d"),
                                metodo_pago_ev, resp_ev, str(adeudo_ev)
                            ]
                            ok, msg = append_rows_con_retry(ws_canal, [fila_ev])
                            if ok:
                                cargar_config_canales.clear()
                                st.success(f"Evento registrado en {canal_sel}: ${monto_ev:,.2f}")
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error(msg)
        st.divider()
        st.subheader("📋 Eventos recientes")
        if canales_list:
            all_events = []
            for cn in canales_list:
                ws_cn, _ = safe_worksheet(sh, cn)
                if ws_cn:
                    data = ws_cn.get_all_values()
                    if len(data) > 1:
                        df_cn = pd.DataFrame(data[1:], columns=data[0])
                        expected_cols = ["Canal","Fecha","Monto","Descripcion","Fecha_Servicio_Entrega","Metodo_Pago","Adeudo_Saldo_Pendiente"]
                        for col in expected_cols:
                            if col not in df_cn.columns:
                                df_cn[col] = ""
                        df_cn = df_cn[expected_cols]
                        # ELIMINAR COLUMNAS DUPLICADAS (corrección del error)
                        df_cn = df_cn.loc[:, ~df_cn.columns.duplicated()]
                        all_events.append(df_cn)
            if all_events:
                df_all_events = pd.concat(all_events, ignore_index=True)
                df_all_events["Fecha"] = pd.to_datetime(df_all_events["Fecha"], errors="coerce")
                st.dataframe(df_all_events.sort_values("Fecha", ascending=False).head(50), hide_index=True, width="stretch")
            else:
                st.info("No hay eventos registrados aún.")
