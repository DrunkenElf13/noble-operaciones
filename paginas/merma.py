import streamlit as st
import time
import uuid
from data_loaders import cargar_merma, cargar_costos_insumos
from sheets import _asegurar_hoja_merma, append_rows_con_retry
from utils import limpiar_valor, ahora_hermosillo
from config import UNIDADES_MED
from components.avisos import mostrar_avisos
from auth import tiene_permiso

def show_merma():
    if not tiene_permiso("RegistrarMerma"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    st.title("📉 Registrar Merma")
    mostrar_avisos("RegistrarMerma")
    if not st.session_state.auth_status:
        st.error("🔒 Autenticación requerida.")
        st.stop()
    df_merma_reg = cargar_merma()
    df_bc_m      = cargar_costos_insumos()
    ingredientes_con_costo = []
    if not df_bc_m.empty:
        ingredientes_con_costo = df_bc_m["Nombre_Insumo"].dropna().tolist()
    with st.form("f_merma", clear_on_submit=True):
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            fecha_m    = st.date_input("📅 Fecha:", value=ahora_hermosillo().date())
            producto_m = st.text_input("🍵 Producto afectado:", placeholder="Ej: Latte, Croissant...")
            ingr_m_opts = ["(Escribir manualmente)"] + sorted(ingredientes_con_costo)
            ingr_m_sel  = st.selectbox("🥛 Ingrediente (desde Costos de Insumos):", ingr_m_opts)
            ingr_m_manual = ""
            if ingr_m_sel == "(Escribir manualmente)":
                ingr_m_manual = st.text_input("Nombre del ingrediente:")
            ingr_m_final = ingr_m_manual if ingr_m_sel == "(Escribir manualmente)" else ingr_m_sel
        with col_m2:
            cantidad_m = st.number_input("📦 Cantidad de merma:", min_value=0.0, step=0.1)
            unidad_m   = st.selectbox("Unidad:", UNIDADES_MED)
            motivo_m   = st.text_input("🔍 Motivo:", placeholder="Ej: Vencido, Error de preparación, Derrame...")
            comentarios_m = st.text_area("💬 Comentarios:", height=80)
        costo_unit_m  = 0.0
        costo_total_m = 0.0
        if ingr_m_final and not df_bc_m.empty:
            mask_ingr_m = df_bc_m["Nombre_Insumo"].astype(str).str.strip().str.lower() == ingr_m_final.strip().lower()
            if mask_ingr_m.any():
                df_bc_ingr_m = df_bc_m[mask_ingr_m].copy()
                df_bc_ingr_m["Fecha_Captura"] = pd.to_datetime(df_bc_ingr_m["Fecha_Captura"], errors="coerce")
                ultimo_costo_m = df_bc_ingr_m.sort_values("Fecha_Captura").iloc[-1]
                costo_unit_m   = limpiar_valor(ultimo_costo_m.get("Costo_Unitario", 0))
                costo_total_m  = round(cantidad_m * costo_unit_m, 4)
                if costo_unit_m > 0:
                    st.info(f"💵 Costo estimado: **${costo_total_m:,.4f}** ({cantidad_m} × ${costo_unit_m}/unidad)")
                else:
                    st.warning("⚠️ Ingrediente encontrado pero sin costo unitario.")
        responsables_m = st.session_state.responsables or ["Raúl"]
        resp_idx_m = responsables_m.index(st.session_state.current_user) if st.session_state.current_user in responsables_m else 0
        resp_m = st.selectbox("👤 Responsable:", responsables_m, index=resp_idx_m,
                               disabled=(st.session_state.user_role != "admin"))
        if st.form_submit_button("📉 REGISTRAR MERMA", type="primary", use_container_width=True):
            if not ingr_m_final.strip():
                st.error("El ingrediente es obligatorio.")
            elif cantidad_m <= 0:
                st.error("La cantidad debe ser mayor a cero.")
            elif not motivo_m.strip():
                st.error("El motivo es obligatorio.")
            else:
                ws_merma, err_merma = _asegurar_hoja_merma()
                if err_merma:
                    st.error(err_merma)
                else:
                    fila_merma = [
                        str(uuid.uuid4())[:8],
                        fecha_m.strftime("%Y-%m-%d"),
                        producto_m.strip(), ingr_m_final.strip(), cantidad_m, unidad_m,
                        motivo_m.strip(), comentarios_m.strip(),
                        costo_unit_m, costo_total_m, resp_m
                    ]
                    ok, msg = append_rows_con_retry(ws_merma, [fila_merma])
                    if ok:
                        cargar_merma.clear()
                        cargar_costos_insumos.clear()
                        st.success(f"✅ Merma registrada: {cantidad_m} {unidad_m} de {ingr_m_final.strip()} — Costo: ${costo_total_m:,.4f}")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(msg)
    st.divider()
    st.subheader("📋 Merma reciente")
    if not df_merma_reg.empty:
        cols_mr_show = ["Fecha","Producto","Ingrediente","Cantidad","Unidad_Medida","Motivo","Costo_Unitario","Costo_Total","Responsable"]
        cols_mr_ok   = [c for c in cols_mr_show if c in df_merma_reg.columns]
        df_mr_disp   = df_merma_reg[cols_mr_ok].copy()
        df_mr_disp["Fecha"] = pd.to_datetime(df_mr_disp["Fecha"], errors="coerce")
        st.dataframe(df_mr_disp.sort_values("Fecha", ascending=False).head(30), hide_index=True, use_container_width=True)
        hoy_mr = ahora_hermosillo().date()
        df_mr_disp["_fecha_dt"] = df_mr_disp["Fecha"]
        df_mr_mes = df_mr_disp[
            (df_mr_disp["_fecha_dt"].dt.month == hoy_mr.month) &
            (df_mr_disp["_fecha_dt"].dt.year  == hoy_mr.year)
        ]
        total_merma_mes = df_mr_mes["Costo_Total"].apply(limpiar_valor).sum() if not df_mr_mes.empty and "Costo_Total" in df_mr_mes.columns else 0.0
        st.metric("📉 Costo total de merma este mes", f"${total_merma_mes:,.2f}")
    else:
        st.info("Sin registros de merma.")
