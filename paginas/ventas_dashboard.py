import streamlit as st
import calendar
from data_loaders import cargar_ventas
from utils import limpiar_valor
from auth import tiene_permiso

def show_dashboard_ventas():
    if not tiene_permiso("DashboardVentas"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    st.title("📊 Dashboard de Ventas — Noble")
    df_v = cargar_ventas()
    if df_v.empty:
        st.info("Sin registros de venta. Comienza capturando el primer día.")
        st.stop()
    meses_disp = sorted(
        df_v[["Mes","Año"]].drop_duplicates().apply(
            lambda r: (int(limpiar_valor(r["Mes"])), int(limpiar_valor(r["Año"]))), axis=1
        ).tolist(), reverse=True
    )
    meses_disp = [(m,a) for m,a in meses_disp if m > 0 and a > 0]
    opciones_mes = [f"{calendar.month_name[m].capitalize()} {a}" for m,a in meses_disp]
    mes_sel_str = st.selectbox("📅 Mes:", opciones_mes) if opciones_mes else None
    if not mes_sel_str:
        st.info("Sin datos de mes disponibles.")
        st.stop()
    mes_idx = opciones_mes.index(mes_sel_str)
    mes_num, año_num = meses_disp[mes_idx]
    df_mes = df_v[
        (df_v["Mes"].apply(limpiar_valor) == mes_num) &
        (df_v["Año"].apply(limpiar_valor) == año_num)
    ].copy().sort_values("Fecha")
    if df_mes.empty:
        st.warning("Sin registros para ese mes.")
        st.stop()
    meta_m     = limpiar_valor(df_mes["Meta_Mensual"].iloc[-1])
    dias_hab   = int(limpiar_valor(df_mes["Dias_Habiles"].iloc[-1])) or 1
    venta_acum = df_mes["Venta_Diaria"].sum()
    tix_total  = int(df_mes["Total_Tickets"].sum())
    tix_prom_g = round(venta_acum / tix_total, 2) if tix_total > 0 else 0
    faltante   = meta_m - venta_acum
    avance_pct = (venta_acum / meta_m * 100) if meta_m > 0 else 0
    dias_con_venta_cnt  = int((df_mes["Venta_Diaria"] > 0).sum())
    dias_sin_venta_cnt  = int((df_mes["Venta_Diaria"] == 0).sum())
    df_con_tix          = df_mes[df_mes["Total_Tickets"] > 0]
    tix_acum_con_venta  = int(df_con_tix["Total_Tickets"].sum())
    venta_acum_con_tix  = df_con_tix["Venta_Diaria"].sum()
    tix_prom_real       = round(venta_acum_con_tix / tix_acum_con_venta, 2) if tix_acum_con_venta > 0 else 0
    st.subheader(f"Resumen — {mes_sel_str}")
    k1,k2,k3,k4 = st.columns(4)
    k1.metric("Venta Acumulada", f"${venta_acum:,.2f}")
    k2.metric("Meta Mensual",    f"${meta_m:,.2f}")
    k3.metric("Faltante",        f"${faltante:,.2f}", delta=f"{avance_pct:.1f}% avance",
              delta_color="normal" if faltante <= 0 else "inverse")
    k4.metric("Ticket Promedio", f"${tix_prom_g:,.2f}")
    st.divider()
    st.subheader("🎫 Métricas de Tickets")
    tk1, tk2, tk3, tk4 = st.columns(4)
    tk1.metric("Tickets Acumulados", f"{tix_total:,}", help="Total de transacciones registradas en el mes (POS + Uber + Rappi).")
    tk2.metric("Ticket Promedio Real", f"${tix_prom_real:,.2f}" if tix_prom_real > 0 else "—",
               help="Promedio calculado únicamente sobre días con al menos un ticket.")
    tk3.metric("Días con Venta", f"{dias_con_venta_cnt}", delta=f"de {len(df_mes)} registrados", delta_color="off")
    tk4.metric("Días sin Venta", f"{dias_sin_venta_cnt}", delta_color="inverse" if dias_sin_venta_cnt > 0 else "off")
    st.divider()
    if not df_mes.empty:
        mejor = df_mes.loc[df_mes["Venta_Diaria"].idxmax()]
        df_con_venta = df_mes[df_mes["Venta_Diaria"] > 0]
        peor = df_con_venta.loc[df_con_venta["Venta_Diaria"].idxmin()] if not df_con_venta.empty else None
        b1,b2,b3 = st.columns(3)
        b1.metric("📈 Mejor día", f"${limpiar_valor(mejor['Venta_Diaria']):,.0f}", f"Día {int(limpiar_valor(mejor['Día']))}")
        if peor is not None:
            b2.metric("📉 Día más bajo (con venta)", f"${limpiar_valor(peor['Venta_Diaria']):,.0f}", f"Día {int(limpiar_valor(peor['Día']))}")
        b3.metric("📅 Días registrados", len(df_mes))
    st.divider()
    st.subheader("📋 Detalle diario")
    df_disp = df_mes[["Día","Fecha","Efectivo","Transferencias","Tarjeta","Total_POS",
                       "Uber_Eats","Rappi","Venta_Diaria","Total_Tickets",
                       "Ticket_Promedio","Meta_Diaria","Responsable","Notas"]].copy()
    df_disp["Fecha"] = df_disp["Fecha"].apply(lambda x: x.strftime("%d/%m/%Y") if pd.notna(x) else "")
    df_disp["vs Meta"] = df_disp.apply(
        lambda r: f"{(r['Venta_Diaria']/r['Meta_Diaria']*100):.0f}%" if r['Meta_Diaria'] > 0 else "—", axis=1
    )
    df_disp["Ticket_Promedio"] = df_disp["Ticket_Promedio"].apply(lambda x: f"${x:,.2f}" if x > 0 else "—")
    def color_meta_row(row):
        try:
            vd = limpiar_valor(row.get("Venta_Diaria",0))
            md = limpiar_valor(row.get("Meta_Diaria",0))
            if md == 0: return [""] * len(row)
            ratio = vd / md
            c = ("background-color: rgba(80,200,120,0.15)" if ratio >= 1.0
                 else "background-color: rgba(239,159,39,0.15)" if ratio >= 0.7
                 else "background-color: rgba(226,75,74,0.12)")
            return [c] * len(row)
        except Exception:
            return [""] * len(row)
    st.dataframe(df_disp.style.apply(color_meta_row, axis=1), hide_index=True, use_container_width=True)
    st.divider()
    st.subheader("🥧 Mix de canales")
    tot_pos  = df_mes["Total_POS"].sum()
    tot_uber = df_mes["Uber_Eats"].sum()
    tot_rapp = df_mes["Rappi"].sum()
    tot_all  = tot_pos + tot_uber + tot_rapp or 1
    c_pos, c_uber, c_rapp = st.columns(3)
    c_pos.metric( "POS",       f"${tot_pos:,.2f}",  f"{tot_pos/tot_all*100:.1f}%")
    c_uber.metric("Uber Eats", f"${tot_uber:,.2f}", f"{tot_uber/tot_all*100:.1f}%")
    c_rapp.metric("Rappi",     f"${tot_rapp:,.2f}", f"{tot_rapp/tot_all*100:.1f}%")
    st.divider()
    csv_v = df_disp.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Descargar CSV del mes", data=csv_v,
                       file_name=f"Ventas_Noble_{mes_sel_str.replace(' ','_')}.csv",
                       mime="text/csv", use_container_width=True)
