import streamlit as st
import time
import data_loaders as dl
from inventario import obtener_ultimo_inventario, construir_fila_historial
from sheets import safe_worksheet, sh, append_rows_con_retry
from utils import ts_hermosillo
from config import COLS_HISTORIAL
from auth import tiene_permiso

def show_corte_mes():
    if not tiene_permiso("CorteMes"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    _, df_historial = dl.cargar_datos_integrales()
    if st.session_state.user_role != "admin":
        st.error("🚫 Acceso denegado. Solo administradores.")
        st.stop()
    st.title("🔒 Corte de Mes")
    st.warning(
        "Este proceso consolidará el stock actual como saldo inicial y archivará "
        "los registros previos. **Acción irreversible.** "
        "Asegúrate de que todos los conteos del día estén registrados antes de continuar."
    )
    confirmar = st.checkbox("Confirmo que deseo ejecutar el cierre de mes.")
    if confirmar and st.button("🚀 Ejecutar Cierre", type="primary"):
        with st.status("Ejecutando protocolo de cierre...", expanded=True) as status:
            try:
                st.write("1/4 — Calculando estados finales de stock...")
                df_corte = obtener_ultimo_inventario(df_historial)
                if df_corte.empty:
                    st.error("No hay datos de inventario para cerrar.")
                    st.stop()
                fh          = ts_hermosillo()
                encabezados = COLS_HISTORIAL
                filas_corte = []
                for _, r in df_corte.iterrows():
                    filas_corte.append(construir_fila_historial(
                        unidad=r.get("Unidad de Negocio",""), nombre=r.get("Nombre del Insumo",""),
                        marca=r.get("Marca",""), proveedor=r.get("Proveedor",""),
                        grupo=r.get("Grupo",""), fecha_entrada="",
                        presentacion=r.get("Presentación de Compra",""),
                        unidad_medida=r.get("Unidad de Medida",""),
                        alm=r.get("Alm",0), barra=r.get("Barra",0),
                        stock_neto=r.get("Stock Neto Calculado",0), stock_minimo=r.get("Stock Mínimo",0),
                        comprar=bool(r.get("Necesita Compra",False)), responsable="SISTEMA-CIERRE",
                        fecha_inventario=fh, tara=r.get("Tara",0), observaciones="Corte consolidado",
                    ))
                st.write("2/4 — Archivando historial previo...")
                ws_his, err = safe_worksheet(sh, "Historial")
                if err: raise RuntimeError(err)
                datos_hist = ws_his.get_all_values()
                if len(datos_hist) <= 1:
                    st.warning("El Historial ya está vacío.")
                    status.update(label="⚠️ Historial ya estaba vacío", state="error")
                    st.stop()
                ws_arc, _ = safe_worksheet(sh, "Archivo_Historial")
                if ws_arc is None:
                    ws_arc = sh.add_worksheet(title="Archivo_Historial", rows="10000", cols="20")
                    ws_arc.append_row(encabezados)
                ws_arc.append_row([f"=== CORTE {fh} ==="] + [""] * (len(encabezados) - 1))
                ws_arc.append_rows(datos_hist[1:])
                st.write("3/4 — Consolidando saldos iniciales...")
                ws_cie, _ = safe_worksheet(sh, "Cierres")
                if ws_cie is None:
                    ws_cie = sh.add_worksheet(title="Cierres", rows="1000", cols="20")
                ws_cie.clear()
                ws_cie.append_row(encabezados)
                ws_cie.append_rows(filas_corte)
                st.write("4/4 — Reiniciando Historial...")
                ws_his.clear()
                ws_his.append_row(encabezados)
                dl.cargar_datos_integrales.clear()
                status.update(label="✅ Cierre completado", state="complete")
                st.success(f"{len(filas_corte)} referencias consolidadas en 'Cierres'.")
                time.sleep(2)
                st.rerun()
            except Exception as e:
                status.update(label="❌ Falla en el cierre", state="error")
                st.error(f"Error durante el cierre: {e}\n\nEl Historial NO fue eliminado.")
