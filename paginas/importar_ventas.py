import streamlit as st
import pandas as pd
import time
import calendar
from datetime import date as _date
from data_loaders import cargar_ventas
from sheets import _asegurar_hoja_ventas, append_rows_con_retry
from utils import limpiar_valor, ahora_hermosillo
from components.avisos import mostrar_avisos
from auth import tiene_permiso
from config import COLS_VENTAS

# Reutilizamos la función de construcción de fila de venta (definida en ventas_registro)
from paginas.ventas_registro import _construir_fila_venta

def show_importar_ventas():
    if not tiene_permiso("ImportarVentas"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    st.title("📥 Importar Histórico de Ventas")
    mostrar_avisos("ImportarVentas")
    if not st.session_state.auth_status:
        st.error("🔒 Autenticación requerida.")
        st.stop()
    st.info("Sube el Excel mensual con el formato estándar Noble. El sistema parsea automáticamente y guarda en Sheets.")
    col_imp1, col_imp2 = st.columns(2)
    with col_imp1:
        mes_imp = st.selectbox("Mes del archivo:", list(range(1,13)),
                               format_func=lambda m: calendar.month_name[m].capitalize(),
                               index=ahora_hermosillo().month - 1)
    with col_imp2:
        año_imp = st.number_input("Año:", min_value=2023, max_value=2030, value=ahora_hermosillo().year)
    col_meta1, col_meta2 = st.columns(2)
    with col_meta1:
        meta_imp = st.number_input("Meta mensual ($):", min_value=0.0, step=1000.0, value=145000.0)
    with col_meta2:
        dias_imp = st.number_input("Días hábiles del mes:", min_value=1, max_value=31, value=26)
    archivo = st.file_uploader("📂 Selecciona el archivo Excel (.xlsx):", type=["xlsx"])
    if archivo:
        try:
            df_raw_imp = pd.read_excel(archivo, sheet_name=0, header=None)
            filas_datos = []
            for _, fila in df_raw_imp.iterrows():
                try:
                    dia = int(float(str(fila.iloc[1]).strip()))
                    if 1 <= dia <= 31:
                        filas_datos.append(fila)
                except (ValueError, TypeError):
                    continue
            if not filas_datos:
                st.error("No se encontraron filas de datos válidas en el archivo.")
                st.stop()
            df_parse = pd.DataFrame(filas_datos)
            df_parse.columns = range(df_parse.shape[1])
            def _n(v):
                try:
                    f = float(str(v).strip())
                    return 0.0 if str(v).strip() in ['nan',''] else (0.0 if f != f else f)
                except Exception:
                    return 0.0
            filas_import    = []
            dias_sin_venta  = []
            for _, row in df_parse.iterrows():
                dia = int(_n(row.iloc[1]))
                if dia < 1 or dia > 31: continue
                efectivo_i       = _n(row.iloc[2])
                transferencias_i = _n(row.iloc[3])
                tarjeta_i        = _n(row.iloc[4])
                uber_i           = _n(row.iloc[6])
                rappi_i          = _n(row.iloc[7])
                tickets_pos_i    = int(_n(row.iloc[10]))
                tickets_uber_i   = int(_n(row.iloc[11]))
                tickets_rappi_i  = int(_n(row.iloc[12]))
                venta_d = efectivo_i + transferencias_i + tarjeta_i + uber_i + rappi_i
                if venta_d == 0 and tickets_pos_i == 0:
                    dias_sin_venta.append(dia)
                    continue
                try:
                    fecha_d = _date(int(año_imp), int(mes_imp), dia)
                except ValueError:
                    continue
                filas_import.append(_construir_fila_venta(
                    fecha=fecha_d, efectivo=efectivo_i, transferencias=transferencias_i,
                    tarjeta=tarjeta_i, uber=uber_i, rappi=rappi_i,
                    tickets_pos=tickets_pos_i, tickets_uber=tickets_uber_i,
                    tickets_rappi=tickets_rappi_i, meta_mensual=meta_imp,
                    dias_habiles=int(dias_imp), responsable="IMPORTADO", notas="",
                ))
            if filas_import:
                cols_prev = ["Fecha","Efectivo","Transferencias","Tarjeta","Total_POS",
                             "Uber_Eats","Rappi","Venta_Diaria","Total_Tickets","Ticket_Promedio"]
                idx_prev  = {c:i for i,c in enumerate(COLS_VENTAS)}
                rows_prev = [[f[idx_prev[c]] for c in cols_prev] for f in filas_import]
                df_prev   = pd.DataFrame(rows_prev, columns=cols_prev)
                total_imp = df_prev["Venta_Diaria"].apply(limpiar_valor).sum()
                st.success(f"✅ {len(filas_import)} día(s) con venta detectados. Venta acumulada: **${total_imp:,.2f}**")
                if dias_sin_venta:
                    st.caption(f"Días sin venta (omitidos): {dias_sin_venta}")
                st.dataframe(df_prev, hide_index=True, use_container_width=True)
                if st.button("📤 GUARDAR EN GOOGLE SHEETS", type="primary", use_container_width=True):
                    ws_v, err = _asegurar_hoja_ventas()
                    if err:
                        st.error(err)
                    else:
                        ok, msg = append_rows_con_retry(ws_v, filas_import)
                        if ok:
                            cargar_ventas.clear()
                            st.success(f"Histórico importado: {len(filas_import)} registros guardados.")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(msg)
            else:
                st.warning("No se encontraron días con venta en el archivo.")
        except Exception as e:
            st.error(f"Error al procesar el archivo: {e}")
            st.exception(e)
