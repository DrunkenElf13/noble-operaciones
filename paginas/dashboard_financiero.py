import streamlit as st
import pandas as pd
import numpy as np
import calendar
import plotly.graph_objects as go
import plotly.express as px
import time
from data_loaders import (
    cargar_todas_ventas, cargar_gastos, cargar_presupuesto,
    cargar_costos_insumos, cargar_merma, cargar_recetas
)
from sheets import safe_worksheet, sh, append_rows_con_retry, _asegurar_hoja_presupuesto
from utils import limpiar_valor, ahora_hermosillo, _proyectar_tendencia
from auth import tiene_permiso
from config import CANALES_VENTA, COLS_PRESUPUESTO, PALETA_CANALES, COLOR_TARJETA, COLOR_SUBTEXTO, COLOR_EXITO

def _tarjeta(titulo, valor, delta=None, color=COLOR_TARJETA):
    delta_html = ""
    if delta:
        delta_html = f"<br><small style='color:{COLOR_SUBTEXTO}'>{delta}</small>"
    st.markdown(
        f"""
        <div style="border-left:4px solid {color}; padding:8px 12px; margin:4px 0; background:{COLOR_TARJETA}; border-radius:4px;">
            <div style="color:{COLOR_SUBTEXTO}; font-size:0.75rem;">{titulo}</div>
            <div style="font-size:1.25rem; font-weight:600;">{valor}{delta_html}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

def _gauge(valor, minimo, maximo, titulo, sufijo="%", umbral_verde=80, umbral_amarillo=60):
    color = "#48B065" if valor >= umbral_verde else ("#EF9F27" if valor >= umbral_amarillo else "#E24B4A")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=valor,
        title={"text": titulo, "font": {"size": 14}},
        number={"suffix": sufijo, "font": {"size": 24}},
        gauge={
            "axis": {"range": [minimo, maximo], "tickwidth": 1},
            "bar": {"color": color},
            "steps": [
                {"range": [minimo, umbral_amarillo], "color": "rgba(226,75,74,0.12)"},
                {"range": [umbral_amarillo, umbral_verde], "color": "rgba(239,159,39,0.12)"},
                {"range": [umbral_verde, maximo], "color": "rgba(72,176,101,0.12)"},
            ],
            "threshold": {"line": {"color": "white", "width": 2}, "thickness": 0.75, "value": umbral_verde},
        }
    ))
    fig.update_layout(height=230, margin=dict(l=20, r=20, t=50, b=10))
    st.plotly_chart(fig, width="stretch")

def show_dashboard_financiero():
    if not tiene_permiso("DashboardFinanciero"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    st.title("Dashboard Financiero")
    df_vf     = cargar_todas_ventas()
    df_gf     = cargar_gastos()
    df_pptof  = cargar_presupuesto()
    df_bcf    = cargar_costos_insumos()
    df_mermaf = cargar_merma()
    if df_vf.empty:
        st.info("Sin datos de ventas. Comienza registrando ventas diarias.")
        st.stop()

    tab_comp, tab_proy, tab_fc, tab_merma_d, tab_pe, tab_tablas = st.tabs([
        "Comparativo", "Proyecciones", "Food Cost", "Merma", "Punto Equilibrio", "Tablas"
    ])

    # ── COMPARATIVO ──
    with tab_comp:
        st.subheader("Ventas vs Gastos por Período")
        periodo_comp = st.radio("Agrupar por:", ["Mes","Trimestre","Cuatrimestre","Año"], horizontal=True)
        df_vm = df_vf.copy()
        df_vm["Mes_num"] = df_vm["Mes"].apply(limpiar_valor).astype(int)
        df_vm["Año_num"] = df_vm["Año"].apply(limpiar_valor).astype(int)
        df_vm = df_vm[(df_vm["Mes_num"] > 0) & (df_vm["Año_num"] > 0)]
        ventas_mens = df_vm.groupby(["Año_num","Mes_num"]).agg(
            Ventas=("Venta_Diaria","sum"), POS=("Total_POS","sum"),
            Uber=("Uber_Eats","sum"), Rappi=("Rappi","sum")).reset_index()
        if "Canal" in df_vm.columns:
            vp = df_vm.groupby(["Año_num","Mes_num","Canal"])["Venta_Diaria"].sum().reset_index()
            vp = vp.pivot(index=["Año_num","Mes_num"], columns="Canal", values="Venta_Diaria").fillna(0).reset_index()
            for c in CANALES_VENTA:
                if c not in vp.columns: vp[c] = 0.0
            ventas_mens = ventas_mens.merge(vp, on=["Año_num","Mes_num"], how="left").fillna(0)
        else:
            for c in CANALES_VENTA: ventas_mens[c] = 0.0
            ventas_mens["Noble"] = ventas_mens["Ventas"]

        if not df_gf.empty and "Fecha" in df_gf.columns:
            df_gm = df_gf.copy()
            df_gm["_fecha"] = pd.to_datetime(df_gm["Fecha"], errors="coerce")
            df_gm["Mes_num"] = df_gm["_fecha"].dt.month
            df_gm["Año_num"] = df_gm["_fecha"].dt.year
            df_gm["Monto_v"] = df_gm["Monto"].apply(limpiar_valor)
            g_tot = df_gm.groupby(["Año_num","Mes_num"])["Monto_v"].sum().reset_index().rename(columns={"Monto_v":"Gastos"})
            g_fijo = df_gm[df_gm["Tipo"]=="Fijo"].groupby(["Año_num","Mes_num"])["Monto_v"].sum().reset_index().rename(columns={"Monto_v":"Fijos"})
            g_var = df_gm[df_gm["Tipo"]=="Variable"].groupby(["Año_num","Mes_num"])["Monto_v"].sum().reset_index().rename(columns={"Monto_v":"Variables"})
            gastos_mens = g_tot.merge(g_fijo, on=["Año_num","Mes_num"], how="left").merge(g_var, on=["Año_num","Mes_num"], how="left").fillna(0)
        else:
            gastos_mens = pd.DataFrame(columns=["Año_num","Mes_num","Gastos","Fijos","Variables"])

        df_comp = ventas_mens.merge(gastos_mens, on=["Año_num","Mes_num"], how="left").fillna(0)
        df_comp = df_comp.sort_values(["Año_num","Mes_num"])
        df_comp["Utilidad"] = df_comp["Ventas"] - df_comp["Gastos"]
        df_comp["_sort"] = df_comp["Año_num"] * 100 + df_comp["Mes_num"]

        if periodo_comp == "Trimestre":
            df_comp["Grupo"] = df_comp.apply(lambda r: f"Q{((int(r['Mes_num'])-1)//3)+1} {int(r['Año_num'])}", axis=1)
        elif periodo_comp == "Cuatrimestre":
            df_comp["Grupo"] = df_comp.apply(lambda r: f"P{((int(r['Mes_num'])-1)//4)+1} {int(r['Año_num'])}", axis=1)
        elif periodo_comp == "Año":
            df_comp["Grupo"] = df_comp["Año_num"].astype(str)
        else:
            df_comp["Grupo"] = df_comp.apply(lambda r: f"{calendar.month_abbr[int(r['Mes_num'])]} {int(r['Año_num'])}", axis=1)

        df_agrup = df_comp.groupby("Grupo", sort=False).agg(
            Ventas=("Ventas","sum"), Gastos=("Gastos","sum"), Utilidad=("Utilidad","sum"),
            POS=("POS","sum"), Uber=("Uber","sum"), Rappi=("Rappi","sum"),
            Noble=("Noble","sum"), CoffeeStation=("Coffee Station","sum"), ToGo=("Noble To Go","sum"),
            _sort=("_sort","min")).reset_index().sort_values("_sort").drop(columns=["_sort"])

        try:
            fig_comp = go.Figure()
            fig_comp.add_trace(go.Bar(name="Ventas", x=df_agrup["Grupo"], y=df_agrup["Ventas"], marker_color="#22c55e"))
            fig_comp.add_trace(go.Bar(name="Gastos", x=df_agrup["Grupo"], y=df_agrup["Gastos"], marker_color="#ef4444"))
            fig_comp.add_trace(go.Bar(name="Utilidad", x=df_agrup["Grupo"], y=df_agrup["Utilidad"], marker_color="#3b82f6"))
            fig_comp.update_layout(barmode="group", height=400)
            st.plotly_chart(fig_comp, width="stretch")
        except:
            st.bar_chart(df_agrup.set_index("Grupo")[["Ventas","Gastos","Utilidad"]])

    # ── PROYECCIONES ──
    with tab_proy:
        st.subheader("Proyecciones de Ventas por Canal")
        hoy_pr = ahora_hermosillo().date()
        años_pr = sorted(df_vf["Año"].apply(limpiar_valor).astype(int).unique(), reverse=True)
        año_pr = st.selectbox("Año", años_pr, key="año_proy")
        mes_pr = st.selectbox("Mes", list(range(1,13)), index=hoy_pr.month-1,
                              format_func=lambda m: calendar.month_name[m], key="mes_proy")
        df_vf_mes_pr = df_vf[(df_vf["Mes"].apply(limpiar_valor) == mes_pr) & (df_vf["Año"].apply(limpiar_valor) == año_pr)]
        venta_acum_pr = df_vf_mes_pr["Venta_Diaria"].sum()

        metas_canal = {"Noble": 145000.0, "Coffee Station": 0.0, "Noble To Go": 0.0}
        if not df_pptof.empty:
            ppto_mes_pr = df_pptof[(df_pptof["Mes"].apply(limpiar_valor) == mes_pr) & (df_pptof["Año"].apply(limpiar_valor) == año_pr)]
            if not ppto_mes_pr.empty:
                metas_canal["Noble"] = limpiar_valor(ppto_mes_pr["Meta_Total"].iloc[-1]) or 145000.0
                metas_canal["Coffee Station"] = limpiar_valor(ppto_mes_pr["Meta_CoffeeStation"].iloc[-1]) or 0.0
                metas_canal["Noble To Go"] = limpiar_valor(ppto_mes_pr["Meta_ToGo"].iloc[-1]) or 0.0

        for canal in CANALES_VENTA:
            venta_canal = df_vf_mes_pr[df_vf_mes_pr["Canal"]==canal]["Venta_Diaria"].sum()
            meta = metas_canal[canal]
            avance = (venta_canal / meta * 100) if meta > 0 else 0
            _tarjeta(canal, f"${venta_canal:,.0f}", f"Meta: ${meta:,.0f} ({avance:.0f}%)", PALETA_CANALES.get(canal, COLOR_TARJETA))

        st.divider()
        st.subheader("Cumplimiento anual")
        venta_anual_pr = df_vf[df_vf["Año"].apply(limpiar_valor)==año_pr]["Venta_Diaria"].sum()
        ppto_anual_pr = 0.0
        if not df_pptof.empty:
            ppto_año_pr = df_pptof[df_pptof["Año"].apply(limpiar_valor)==año_pr]
            if not ppto_año_pr.empty: ppto_anual_pr = ppto_año_pr["Meta_Total"].apply(limpiar_valor).sum()
        if ppto_anual_pr > 0:
            cumpl_anual_pr = min(venta_anual_pr / ppto_anual_pr * 100, 150)
            _gauge(cumpl_anual_pr, 0, 150, f"Cumplimiento {año_pr}")

    # ── FOOD COST ──
    with tab_fc:
        st.subheader("Food Cost & Margen por Producto")
        if df_bcf.empty:
            st.info("Sin datos en Costos de Insumos.")
        else:
            df_rec_fc = cargar_recetas()
            if not df_rec_fc.empty:
                df_por_prod = df_rec_fc.groupby("Receta").agg(
                    Costo_Receta=("Costo_Ingrediente","sum"),
                    Precio_Venta=("Precio_Venta","max")).reset_index()
                df_por_prod["Food_Cost_Pct"] = np.where(
                    df_por_prod["Precio_Venta"]>0,
                    df_por_prod["Costo_Receta"]/df_por_prod["Precio_Venta"]*100, 0).round(1)
                df_por_prod["Margen_Bruto"] = df_por_prod["Precio_Venta"] - df_por_prod["Costo_Receta"]
                df_por_prod["Margen_Pct"] = np.where(
                    df_por_prod["Precio_Venta"]>0,
                    df_por_prod["Margen_Bruto"]/df_por_prod["Precio_Venta"]*100, 0).round(1)
                st.success("Datos tomados de recetas registradas.")
            else:
                st.info("No hay recetas aún.")
            st.dataframe(df_por_prod, hide_index=True, width="stretch")

    # ── MERMA ──
    with tab_merma_d:
        st.subheader("Análisis de Merma")
        if df_mermaf.empty:
            st.info("Sin registros de merma.")
        else:
            df_md = df_mermaf.copy()
            df_md["Fecha"] = pd.to_datetime(df_md["Fecha"], errors="coerce")
            df_md["Mes_num"] = df_md["Fecha"].dt.month
            df_md["Año_num"] = df_md["Fecha"].dt.year
            df_md["Costo_Total"] = df_md["Costo_Total"].apply(limpiar_valor)
            año_md = st.selectbox("Año", sorted(df_md["Año_num"].dropna().unique().astype(int), reverse=True), key="año_md")
            mes_md_op = st.selectbox("Mes", ["Todos"]+[calendar.month_name[m] for m in range(1,13)], key="mes_md")
            df_fil = df_md[df_md["Año_num"]==año_md]
            if mes_md_op != "Todos":
                mes_num = list(calendar.month_name).index(mes_md_op)
                df_fil = df_fil[df_fil["Mes_num"]==mes_num]
            st.metric("Costo total merma", f"${df_fil['Costo_Total'].sum():,.2f}")

    # ── PUNTO DE EQUILIBRIO ──
    with tab_pe:
        st.subheader("Punto de Equilibrio Mensual")
        hoy_pe = ahora_hermosillo().date()
        años_pe = sorted(df_vf["Año"].apply(limpiar_valor).astype(int).unique(), reverse=True)
        año_pe = st.selectbox("Año", años_pe, key="año_pe")
        mes_pe = st.selectbox("Mes", list(range(1,13)), index=hoy_pe.month-1,
                              format_func=lambda m: calendar.month_name[m], key="mes_pe")
        gastos_fijos_pe = 0.0
        if not df_gf.empty:
            df_gpe = df_gf.copy()
            df_gpe["_fecha"] = pd.to_datetime(df_gpe["Fecha"], errors="coerce")
            df_gpe_mes = df_gpe[(df_gpe["_fecha"].dt.month==mes_pe)&(df_gpe["_fecha"].dt.year==año_pe)]
            gastos_fijos_pe = df_gpe_mes[df_gpe_mes["Tipo"]=="Fijo"]["Monto"].apply(limpiar_valor).sum()
        ventas_pe = df_vf[(df_vf["Mes"].apply(limpiar_valor)==mes_pe)&(df_vf["Año"].apply(limpiar_valor)==año_pe)]["Venta_Diaria"].sum()
        if gastos_fijos_pe > 0 and ventas_pe > 0:
            pe_val = gastos_fijos_pe / (1 - 0.3)  # simplificado
            st.metric("Punto de Equilibrio", f"${pe_val:,.2f}")

    # ── TABLAS COMPARATIVAS ──
    with tab_tablas:
        st.subheader("Tablas Comparativas por Canal")
        hoy_tab = ahora_hermosillo().date()
        año_actual = hoy_tab.year
        año_anterior = año_actual - 1
        df_pos = df_vf[df_vf["Canal"]=="Noble"]
        df_cs = df_vf[df_vf["Canal"]=="Coffee Station"]
        df_ntg = df_vf[df_vf["Canal"]=="Noble To Go"]

        metas_pos = {}
        metas_cs = {}
        metas_ntg = {}
        if not df_pptof.empty:
            for año in [año_anterior, año_actual]:
                df_ppto_año = df_pptof[df_pptof["Año"].apply(limpiar_valor)==año]
                for _, r in df_ppto_año.iterrows():
                    mes = int(limpiar_valor(r["Mes"]))
                    if 1<=mes<=12 and año==año_actual:
                        metas_pos[mes] = limpiar_valor(r.get("Meta_Total",0))
                        metas_cs[mes] = limpiar_valor(r.get("Meta_CoffeeStation",0))
                        metas_ntg[mes] = limpiar_valor(r.get("Meta_ToGo",0))

        # Tabla POS
        st.subheader("POS (Noble)")
        filas_pos = []
        for mes in range(1,13):
            venta_ant = df_pos[(df_pos["Mes"].apply(limpiar_valor)==mes)&(df_pos["Año"].apply(limpiar_valor)==año_anterior)]["Venta_Diaria"].sum()
            venta_act = df_pos[(df_pos["Mes"].apply(limpiar_valor)==mes)&(df_pos["Año"].apply(limpiar_valor)==año_actual)]["Venta_Diaria"].sum()
            meta = metas_pos.get(mes,0)
            cumpl = (venta_act/meta*100) if meta>0 else 0
            var = ((venta_act-venta_ant)/venta_ant*100) if venta_ant>0 else None
            filas_pos.append({"MES":calendar.month_name[mes].capitalize(),
                              f"VENTA {año_anterior}":f"${venta_ant:,.0f}",
                              f"VENTA {año_actual}":f"${venta_act:,.0f}",
                              "META":f"${meta:,.0f}","CUMPLIMIENTO":f"{cumpl:.2f}%",
                              "VAR":f"{var:+.2f}%" if var else "—"})
        st.dataframe(pd.DataFrame(filas_pos), hide_index=True, width="stretch")

        # Tabla Coffee Station
        st.subheader("Coffee Station")
        filas_cs = []
        for mes in range(1,13):
            df_mes_cs = df_cs[(df_cs["Mes"].apply(limpiar_valor)==mes)&(df_cs["Año"].apply(limpiar_valor)==año_actual)]
            venta_total = df_mes_cs["Venta_Total"].sum()
            venta_cobrada = df_mes_cs["Venta_Diaria"].sum()
            servicios = len(df_mes_cs)
            meta = metas_cs.get(mes,0)
            cumpl = (venta_cobrada/meta*100) if meta>0 else 0
            filas_cs.append({"MES":calendar.month_name[mes].capitalize(),
                             "VENTA TOTAL":f"${venta_total:,.0f}",
                             "VENTA COBRADA":f"${venta_cobrada:,.0f}",
                             "META":f"${meta:,.0f}","CUMPLIMIENTO":f"{cumpl:.2f}%",
                             "SERVICIOS":servicios})
        st.dataframe(pd.DataFrame(filas_cs), hide_index=True, width="stretch")

        # Ajuste de metas de canales adicionales
        st.divider()
        with st.expander("Ajustar metas mensuales de canales adicionales"):
            with st.form("f_metas_canales"):
                col_cs, col_ntg = st.columns(2)
                with col_cs:
                    st.write("**Coffee Station**")
                    meta_cs_mensual = {}
                    for m in range(1,13):
                        meta_cs_mensual[m] = st.number_input(
                            f"{calendar.month_name[m].capitalize()}:",
                            min_value=0.0, step=100.0,
                            value=float(metas_cs.get(m,0)), key=f"meta_cs_{m}")
                with col_ntg:
                    st.write("**Noble To Go**")
                    meta_ntg_mensual = {}
                    for m in range(1,13):
                        meta_ntg_mensual[m] = st.number_input(
                            f"{calendar.month_name[m].capitalize()}:",
                            min_value=0.0, step=100.0,
                            value=float(metas_ntg.get(m,0)), key=f"meta_ntg_{m}")
                if st.form_submit_button("Guardar metas", width="stretch"):
                    ws_ppto, err_ppto = _asegurar_hoja_presupuesto()
                    if not err_ppto:
                        try:
                            todos_ppto = ws_ppto.get_all_values()
                            if len(todos_ppto)>1:
                                df_old = pd.DataFrame(todos_ppto[1:], columns=todos_ppto[0])
                                df_old = df_old[df_old["Año"].astype(str).str.strip()!=str(año_actual)]
                            else:
                                df_old = pd.DataFrame()
                            nuevas_filas = []
                            for m in range(1,13):
                                nuevas_filas.append([
                                    año_actual, m, 0, 0, 0, 0,
                                    meta_cs_mensual[m], meta_ntg_mensual[m], ""
                                ])
                            ws_ppto.clear()
                            ws_ppto.append_row(COLS_PRESUPUESTO)
                            if not df_old.empty:
                                ws_ppto.append_rows(df_old.values.tolist(), value_input_option="USER_ENTERED")
                            ws_ppto.append_rows(nuevas_filas, value_input_option="USER_ENTERED")
                            cargar_presupuesto.clear()
                            st.success("Metas actualizadas.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
