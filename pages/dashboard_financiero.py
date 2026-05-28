import streamlit as st
import pandas as pd
import numpy as np
import calendar
import plotly.graph_objects as go
import plotly.express as px
from data_loaders import cargar_ventas, cargar_gastos, cargar_presupuesto, cargar_costos_insumos, cargar_merma, cargar_config_canales, cargar_recetas
from sheets import safe_worksheet, sh
from utils import limpiar_valor, ahora_hermosillo
from auth import tiene_permiso

def _gauge(valor, minimo, maximo, titulo, sufijo="%", umbral_verde=80, umbral_amarillo=60):
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.metric(titulo, f"{valor:.1f}{sufijo}")
        return
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
    st.plotly_chart(fig, use_container_width=True)

def show_dashboard_financiero():
    if not tiene_permiso("DashboardFinanciero"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    st.title("📊 Dashboard Financiero")
    df_vf     = cargar_ventas()
    df_gf     = cargar_gastos()
    df_pptof  = cargar_presupuesto()
    df_bcf    = cargar_costos_insumos()
    df_mermaf = cargar_merma()
    df_cfg_canales = cargar_config_canales()
    if df_vf.empty:
        st.info("Sin datos de ventas. Comienza registrando ventas diarias.")
        st.stop()
    tab_comp, tab_proy, tab_fc, tab_merma_d, tab_pe, tab_canales = st.tabs([
        "📊 Comparativo",
        "🔮 Proyecciones",
        "🍽️ Food Cost & Margen",
        "📉 Merma",
        "⚖️ Punto de Equilibrio",
        "🛒 Canales Adicionales"
    ])
    with tab_comp:
        st.subheader("📊 Ventas vs Gastos por Período")
        periodo_comp = st.radio("Agrupar por:", ["Mes","Trimestre","Cuatrimestre","Año"], horizontal=True)
        df_vm = df_vf.copy()
        df_vm["Mes_num"] = df_vm["Mes"].apply(limpiar_valor).astype(int)
        df_vm["Año_num"] = df_vm["Año"].apply(limpiar_valor).astype(int)
        df_vm = df_vm[(df_vm["Mes_num"] > 0) & (df_vm["Año_num"] > 0)]
        ventas_mens = (
            df_vm.groupby(["Año_num","Mes_num"])
            .agg(Ventas=("Venta_Diaria","sum"), POS=("Total_POS","sum"),
                 Uber=("Uber_Eats","sum"), Rappi=("Rappi","sum"))
            .reset_index()
        )
        if not df_gf.empty and "Fecha" in df_gf.columns:
            df_gm = df_gf.copy()
            df_gm["_fecha"] = pd.to_datetime(df_gm["Fecha"], errors="coerce")
            df_gm["Mes_num"] = df_gm["_fecha"].dt.month
            df_gm["Año_num"] = df_gm["_fecha"].dt.year
            df_gm["Monto_v"] = df_gm["Monto"].apply(limpiar_valor)
            g_tot  = df_gm.groupby(["Año_num","Mes_num"])["Monto_v"].sum().reset_index().rename(columns={"Monto_v":"Gastos"})
            g_fijo = df_gm[df_gm["Tipo"]=="Fijo"].groupby(["Año_num","Mes_num"])["Monto_v"].sum().reset_index().rename(columns={"Monto_v":"Fijos"})
            g_var  = df_gm[df_gm["Tipo"]=="Variable"].groupby(["Año_num","Mes_num"])["Monto_v"].sum().reset_index().rename(columns={"Monto_v":"Variables"})
            gastos_mens = g_tot.merge(g_fijo, on=["Año_num","Mes_num"], how="left").merge(g_var, on=["Año_num","Mes_num"], how="left").fillna(0)
        else:
            gastos_mens = pd.DataFrame(columns=["Año_num","Mes_num","Gastos","Fijos","Variables"])
        df_comp = ventas_mens.merge(gastos_mens, on=["Año_num","Mes_num"], how="left").fillna(0)
        df_comp = df_comp.sort_values(["Año_num","Mes_num"])
        df_comp["Utilidad"] = df_comp["Ventas"] - df_comp["Gastos"]
        df_comp["_sort"]    = df_comp["Año_num"] * 100 + df_comp["Mes_num"]
        if periodo_comp == "Trimestre":
            df_comp["Grupo"] = df_comp.apply(lambda r: f"Q{((int(r['Mes_num'])-1)//3)+1} {int(r['Año_num'])}", axis=1)
        elif periodo_comp == "Cuatrimestre":
            df_comp["Grupo"] = df_comp.apply(lambda r: f"P{((int(r['Mes_num'])-1)//4)+1} {int(r['Año_num'])}", axis=1)
        elif periodo_comp == "Año":
            df_comp["Grupo"] = df_comp["Año_num"].astype(str)
        else:
            df_comp["Grupo"] = df_comp.apply(
                lambda r: f"{calendar.month_abbr[int(r['Mes_num'])]} {int(r['Año_num'])}", axis=1
            )
        df_agrup = (
            df_comp.groupby("Grupo", sort=False)
            .agg(Ventas=("Ventas","sum"), Gastos=("Gastos","sum"), Utilidad=("Utilidad","sum"),
                 POS=("POS","sum"), Uber=("Uber","sum"), Rappi=("Rappi","sum"), _sort=("_sort","min"))
            .reset_index()
            .sort_values("_sort")
            .drop(columns=["_sort"])
        )
        try:
            import plotly.graph_objects as go
            fig_comp = go.Figure()
            fig_comp.add_trace(go.Bar(name="Ventas",   x=df_agrup["Grupo"], y=df_agrup["Ventas"],   marker_color="#48B065"))
            fig_comp.add_trace(go.Bar(name="Gastos",   x=df_agrup["Grupo"], y=df_agrup["Gastos"],   marker_color="#E24B4A"))
            fig_comp.add_trace(go.Bar(name="Utilidad", x=df_agrup["Grupo"], y=df_agrup["Utilidad"], marker_color="#4A90D9"))
            fig_comp.update_layout(barmode="group", title="Ventas vs Gastos vs Utilidad", height=400,
                                    legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(fig_comp, use_container_width=True)
            st.subheader("🥧 Canales de venta por período")
            fig_can = go.Figure()
            fig_can.add_trace(go.Bar(name="POS",      x=df_agrup["Grupo"], y=df_agrup["POS"],   marker_color="#48B065"))
            fig_can.add_trace(go.Bar(name="Uber Eats",x=df_agrup["Grupo"], y=df_agrup["Uber"],  marker_color="#EF9F27"))
            fig_can.add_trace(go.Bar(name="Rappi",    x=df_agrup["Grupo"], y=df_agrup["Rappi"], marker_color="#E24B4A"))
            fig_can.update_layout(barmode="stack", title="Mix de canales", height=350,
                                   legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(fig_can, use_container_width=True)
        except Exception:
            st.bar_chart(df_agrup.set_index("Grupo")[["Ventas","Gastos","Utilidad"]])
        st.subheader("📋 Tabla de datos")
        st.dataframe(df_agrup, hide_index=True, use_container_width=True)
    with tab_proy:
        st.subheader("🔮 Proyecciones de Ventas")
        hoy_pr        = ahora_hermosillo().date()
        dias_en_mes_pr = calendar.monthrange(hoy_pr.year, hoy_pr.month)[1]
        df_vf_mes_pr = df_vf[
            (df_vf["Mes"].apply(limpiar_valor) == hoy_pr.month) &
            (df_vf["Año"].apply(limpiar_valor) == hoy_pr.year)
        ].copy()
        venta_acum_pr    = df_vf_mes_pr["Venta_Diaria"].sum() if not df_vf_mes_pr.empty else 0.0
        dias_con_v_pr    = int((df_vf_mes_pr["Venta_Diaria"] > 0).sum()) if not df_vf_mes_pr.empty else 0
        dias_restantes_pr = dias_en_mes_pr - hoy_pr.day
        avg_diario_pr    = venta_acum_pr / dias_con_v_pr if dias_con_v_pr > 0 else 0.0
        proyeccion_cierre = venta_acum_pr + (avg_diario_pr * dias_restantes_pr)
        meta_pr = 145000.0
        if not df_vf_mes_pr.empty and "Meta_Mensual" in df_vf_mes_pr.columns:
            meta_pr = limpiar_valor(df_vf_mes_pr["Meta_Mensual"].iloc[-1]) or meta_pr
        if not df_pptof.empty:
            ppto_mes_pr = df_pptof[
                (df_pptof["Mes"].apply(limpiar_valor) == hoy_pr.month) &
                (df_pptof["Año"].apply(limpiar_valor) == hoy_pr.year)
            ]
            if not ppto_mes_pr.empty:
                meta_ppto_pr = limpiar_valor(ppto_mes_pr["Meta_Total"].iloc[-1])
                if meta_ppto_pr > 0:
                    meta_pr = meta_ppto_pr
        cumpl_actual_pr   = min((venta_acum_pr   / meta_pr * 100), 150) if meta_pr > 0 else 0.0
        cumpl_proy_pr     = min((proyeccion_cierre / meta_pr * 100), 150) if meta_pr > 0 else 0.0
        st.subheader(f"📅 {calendar.month_name[hoy_pr.month].capitalize()} {hoy_pr.year}")
        pm1, pm2, pm3 = st.columns(3)
        pm1.metric("Venta acumulada",    f"${venta_acum_pr:,.2f}")
        pm2.metric("Promedio diario",    f"${avg_diario_pr:,.2f}", f"({dias_con_v_pr} días con venta)")
        pm3.metric("Proyección cierre",  f"${proyeccion_cierre:,.2f}",
                    f"Meta: ${meta_pr:,.0f}", delta_color="normal" if proyeccion_cierre >= meta_pr else "inverse")
        try:
            import plotly.graph_objects as go
            gc1, gc2 = st.columns(2)
            with gc1:
                _gauge(cumpl_actual_pr, 0, 150, "Cumplimiento actual del mes", sufijo="%")
            with gc2:
                _gauge(cumpl_proy_pr, 0, 150, "Cumplimiento proyectado al cierre", sufijo="%")
        except Exception:
            cc1, cc2 = st.columns(2)
            cc1.metric("Cumplimiento actual",    f"{cumpl_actual_pr:.1f}%")
            cc2.metric("Cumplimiento proyectado", f"{cumpl_proy_pr:.1f}%")
        st.divider()
        st.subheader("📈 Datos para tus propias gráficas")
        st.markdown("Descarga el archivo CSV con las ventas mensuales y crea tus propias visualizaciones en Excel.")
        from utils import _proyectar_tendencia
        df_trend = _proyectar_tendencia(df_vf, meses_futuros=6)
        if not df_trend.empty:
            csv_proy = df_trend.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Descargar CSV con ventas mensuales",
                data=csv_proy,
                file_name="ventas_mensuales.csv",
                mime="text/csv",
                use_container_width=True
            )
        st.divider()
        st.subheader(f"📊 Cumplimiento anual vs presupuesto — {hoy_pr.year}")
        venta_anual_pr = df_vf[df_vf["Año"].apply(limpiar_valor) == hoy_pr.year]["Venta_Diaria"].sum()
        ppto_anual_pr  = 0.0
        if not df_pptof.empty:
            ppto_año_pr = df_pptof[df_pptof["Año"].apply(limpiar_valor) == hoy_pr.year]
            if not ppto_año_pr.empty:
                ppto_anual_pr = ppto_año_pr["Meta_Total"].apply(limpiar_valor).sum()
        if ppto_anual_pr > 0:
            cumpl_anual_pr = min(venta_anual_pr / ppto_anual_pr * 100, 150)
            try:
                _gauge(cumpl_anual_pr, 0, 150, f"Cumplimiento Presupuesto Anual {hoy_pr.year}", sufijo="%")
            except Exception:
                st.metric("Cumplimiento anual", f"{cumpl_anual_pr:.1f}%")
            ga1, ga2 = st.columns(2)
            ga1.metric("Venta anual acumulada", f"${venta_anual_pr:,.2f}")
            ga2.metric("Presupuesto anual",     f"${ppto_anual_pr:,.2f}")
        else:
            st.info("Configura el presupuesto anual en '📋 Presupuesto Anual' para ver el velocímetro anual.")
    with tab_fc:
        st.subheader("🍽️ Food Cost & Margen por Producto")
        if df_bcf.empty:
            st.info("Sin datos en Costos de Insumos. Ve a '🧾 Base de Costos' para registrar tus costos.")
        else:
            df_rec_fc = cargar_recetas()
            if not df_rec_fc.empty:
                df_por_prod = (
                    df_rec_fc.groupby("Receta")
                    .agg(
                        Costo_Receta=("Costo_Ingrediente", "sum"),
                        Precio_Venta=("Precio_Venta", "max"),
                    )
                    .reset_index()
                )
                df_por_prod["Costo_Receta"] = pd.to_numeric(df_por_prod["Costo_Receta"], errors="coerce").fillna(0.0)
                df_por_prod["Precio_Venta"] = pd.to_numeric(df_por_prod["Precio_Venta"], errors="coerce").fillna(0.0)
                df_por_prod["Food_Cost_Pct"] = np.where(
                    df_por_prod["Precio_Venta"] > 0,
                    df_por_prod["Costo_Receta"] / df_por_prod["Precio_Venta"] * 100,
                    0.0
                ).round(1)
                df_por_prod["Margen_Bruto"] = df_por_prod["Precio_Venta"] - df_por_prod["Costo_Receta"]
                df_por_prod["Margen_Pct"]   = np.where(
                    df_por_prod["Precio_Venta"] > 0,
                    (df_por_prod["Margen_Bruto"] / df_por_prod["Precio_Venta"]) * 100,
                    0.0
                ).round(1)
                st.success("Datos tomados de recetas registradas.")
                df_por_prod.rename(columns={"Receta":"Producto"}, inplace=True)
            else:
                df_bcf_s = df_bcf.copy()
                df_bcf_s["Fecha_Captura"] = pd.to_datetime(df_bcf_s["Fecha_Captura"], errors="coerce")
                df_bcf_latest = (
                    df_bcf_s.sort_values("Fecha_Captura")
                    .drop_duplicates(subset=["Nombre_Insumo"], keep="last")
                )
                df_por_prod = df_bcf_latest[["Nombre_Insumo"]].copy()
                df_por_prod["Producto"] = df_por_prod["Nombre_Insumo"]
                df_por_prod["Costo_Receta"] = df_bcf_latest["Costo_Presentacion"]
                df_por_prod["Precio_Venta"] = df_bcf_latest["Costo_Presentacion"] * 2
                df_por_prod["Food_Cost_Pct"] = 50.0
                df_por_prod["Margen_Bruto"] = df_por_prod["Precio_Venta"] - df_por_prod["Costo_Receta"]
                df_por_prod["Margen_Pct"] = 50.0
                st.info("No hay recetas aún. Mostrando costos de insumos con precio estimado.")
            fc_prom_tab = df_por_prod["Food_Cost_Pct"].mean()
            margen_prom_tab = df_por_prod["Margen_Pct"].mean()
            tf1, tf2, tf3 = st.columns(3)
            tf1.metric("Food Cost Promedio", f"{fc_prom_tab:.1f}%",
                        delta="Alto" if fc_prom_tab > 35 else ("Aceptable" if fc_prom_tab > 25 else "Óptimo"),
                        delta_color="inverse" if fc_prom_tab > 35 else ("off" if fc_prom_tab > 25 else "normal"))
            tf2.metric("Margen Bruto Promedio", f"{margen_prom_tab:.1f}%")
            tf3.metric("Productos en base", len(df_por_prod))
            try:
                import plotly.graph_objects as go
                colores_fc_tab = [
                    "#E24B4A" if fc > 35 else ("#EF9F27" if fc > 25 else "#48B065")
                    for fc in df_por_prod["Food_Cost_Pct"]
                ]
                fig_fc_tab = go.Figure()
                fig_fc_tab.add_trace(go.Bar(
                    x=df_por_prod["Producto"], y=df_por_prod["Food_Cost_Pct"],
                    marker_color=colores_fc_tab, name="Food Cost %"
                ))
                fig_fc_tab.add_hline(y=35, line_dash="dash", line_color="#E24B4A", annotation_text="Límite alto 35%")
                fig_fc_tab.add_hline(y=25, line_dash="dash", line_color="#EF9F27", annotation_text="Óptimo 25%")
                fig_fc_tab.update_layout(title="Food Cost % por Producto", height=380, yaxis_ticksuffix="%")
                st.plotly_chart(fig_fc_tab, use_container_width=True)
            except Exception:
                st.bar_chart(df_por_prod.set_index("Producto")["Food_Cost_Pct"])
            st.subheader("📋 Detalle por producto")
            def _color_fc_prod(row):
                fc = limpiar_valor(row.get("Food_Cost_Pct", 0))
                if fc > 35:   return ["background-color: rgba(226,75,74,0.2)"] * len(row)
                elif fc > 25: return ["background-color: rgba(239,159,39,0.2)"] * len(row)
                return ["background-color: rgba(80,200,120,0.15)"] * len(row)
            st.dataframe(
                df_por_prod.style.apply(_color_fc_prod, axis=1),
                hide_index=True, use_container_width=True
            )
    with tab_merma_d:
        st.subheader("📉 Análisis de Merma")
        if df_mermaf.empty:
            st.info("Sin registros de merma. Ve a '📉 Registrar Merma' para comenzar.")
        else:
            df_md = df_mermaf.copy()
            df_md["Fecha"]     = pd.to_datetime(df_md["Fecha"], errors="coerce")
            df_md["Mes_num"]   = df_md["Fecha"].dt.month
            df_md["Año_num"]   = df_md["Fecha"].dt.year
            df_md["Costo_Total"] = df_md["Costo_Total"].apply(limpiar_valor)
            años_md   = sorted([int(a) for a in df_md["Año_num"].dropna().unique() if a > 0], reverse=True)
            año_md    = st.selectbox("Año:", años_md if años_md else [ahora_hermosillo().year], key="año_md")
            mes_md_op = st.selectbox("Mes:", ["Todos"] + [calendar.month_name[m].capitalize() for m in range(1,13)], key="mes_md")
            df_md_fil = df_md[df_md["Año_num"] == año_md]
            mes_md_num = None
            if mes_md_op != "Todos":
                mes_md_num = next((m for m in range(1,13) if calendar.month_name[m].capitalize() == mes_md_op), None)
                if mes_md_num:
                    df_md_fil = df_md_fil[df_md_fil["Mes_num"] == mes_md_num]
            costo_merma_d = df_md_fil["Costo_Total"].sum()
            ventas_periodo_md = df_vf[df_vf["Año"].apply(limpiar_valor) == año_md]["Venta_Diaria"].sum()
            if mes_md_num:
                ventas_periodo_md = df_vf[
                    (df_vf["Año"].apply(limpiar_valor) == año_md) &
                    (df_vf["Mes"].apply(limpiar_valor) == mes_md_num)
                ]["Venta_Diaria"].sum()
            pct_merma_d = (costo_merma_d / ventas_periodo_md * 100) if ventas_periodo_md > 0 else 0.0
            mm1, mm2, mm3 = st.columns(3)
            mm1.metric("Costo total de merma",   f"${costo_merma_d:,.2f}")
            mm2.metric("Ventas del período",      f"${ventas_periodo_md:,.2f}")
            mm3.metric("% Merma vs Ventas",       f"{pct_merma_d:.2f}%",
                        delta_color="inverse" if pct_merma_d > 3 else "normal")
            try:
                import plotly.express as px
                if not df_md_fil.empty:
                    cc_md1, cc_md2 = st.columns(2)
                    with cc_md1:
                        df_by_ingr = (
                            df_md_fil.groupby("Ingrediente")["Costo_Total"].sum()
                            .reset_index().sort_values("Costo_Total", ascending=False).head(10)
                        )
                        if not df_by_ingr.empty:
                            fig_ingr = px.bar(df_by_ingr, x="Costo_Total", y="Ingrediente", orientation="h",
                                               title="Top 10 ingredientes con más merma ($)",
                                               color_discrete_sequence=["#E24B4A"])
                            fig_ingr.update_layout(height=380)
                            st.plotly_chart(fig_ingr, use_container_width=True)
                    with cc_md2:
                        df_by_mot = (
                            df_md_fil.groupby("Motivo")["Costo_Total"].sum()
                            .reset_index().sort_values("Costo_Total", ascending=False)
                        )
                        if not df_by_mot.empty:
                            fig_mot = px.pie(df_by_mot, values="Costo_Total", names="Motivo",
                                              title="Distribución por motivo de merma")
                            fig_mot.update_layout(height=380)
                            st.plotly_chart(fig_mot, use_container_width=True)
            except Exception:
                pass
            st.subheader("📋 Detalle de merma")
            cols_md_show = ["Fecha","Producto","Ingrediente","Cantidad","Unidad_Medida","Motivo","Costo_Unitario","Costo_Total","Comentarios"]
            cols_md_ok   = [c for c in cols_md_show if c in df_md_fil.columns]
            st.dataframe(df_md_fil[cols_md_ok].sort_values("Fecha", ascending=False), hide_index=True, use_container_width=True)
    with tab_pe:
        st.subheader("⚖️ Punto de Equilibrio Mensual")
        hoy_pe     = ahora_hermosillo().date()
        años_pe_op = sorted(set([int(limpiar_valor(a)) for a in df_vf["Año"].unique() if limpiar_valor(a) > 0]), reverse=True)
        if not años_pe_op:
            años_pe_op = [hoy_pe.year]
        col_pe1, col_pe2 = st.columns(2)
        with col_pe1:
            año_pe = st.selectbox("Año:", años_pe_op, key="año_pe")
        with col_pe2:
            mes_pe = st.selectbox("Mes:", list(range(1,13)), index=hoy_pe.month - 1,
                                   format_func=lambda m: calendar.month_name[m].capitalize(), key="mes_pe")
        gastos_fijos_pe = gastos_var_pe = 0.0
        if not df_gf.empty and "Fecha" in df_gf.columns:
            df_gpe = df_gf.copy()
            df_gpe["_fecha"] = pd.to_datetime(df_gpe["Fecha"], errors="coerce")
            df_gpe_mes = df_gpe[
                (df_gpe["_fecha"].dt.month == mes_pe) &
                (df_gpe["_fecha"].dt.year  == año_pe)
            ]
            gastos_fijos_pe = df_gpe_mes[df_gpe_mes["Tipo"]=="Fijo"]["Monto"].apply(limpiar_valor).sum()
            gastos_var_pe   = df_gpe_mes[df_gpe_mes["Tipo"]=="Variable"]["Monto"].apply(limpiar_valor).sum()
        ventas_pe = df_vf[
            (df_vf["Mes"].apply(limpiar_valor) == mes_pe) &
            (df_vf["Año"].apply(limpiar_valor) == año_pe)
        ]["Venta_Diaria"].sum()
        with st.expander("✏️ Ajuste manual de gastos (opcional — se usa si no hay datos en el módulo de Gastos)",
                         expanded=(gastos_fijos_pe + gastos_var_pe == 0)):
            col_gf_pe, col_gv_pe = st.columns(2)
            with col_gf_pe:
                gastos_fijos_pe = st.number_input("Gastos Fijos ($):", min_value=0.0, step=100.0,
                                                   value=float(gastos_fijos_pe),
                                                   help="Renta, nómina, servicios fijos, etc.")
            with col_gv_pe:
                gastos_var_pe = st.number_input("Gastos Variables ($):", min_value=0.0, step=100.0,
                                                 value=float(gastos_var_pe),
                                                 help="Insumos, empaques, comisiones, etc.")
        gastos_tot_pe = gastos_fijos_pe + gastos_var_pe
        ratio_var_pe  = (gastos_var_pe / ventas_pe) if ventas_pe > 0 else 0.0
        pe_val = 0.0
        pe_calculable = False
        if gastos_fijos_pe > 0 and ventas_pe > 0 and ratio_var_pe < 1:
            pe_val = gastos_fijos_pe / (1 - ratio_var_pe)
            pe_calculable = True
        elif gastos_fijos_pe > 0 and ventas_pe == 0:
            pe_calculable = False
        st.divider()
        if pe_calculable:
            st.markdown(f"""
**Fórmula aplicada:** PE = Gastos Fijos ÷ (1 − Gastos Variables / Ventas)

| Concepto | Valor |
|---|---|
| Gastos Fijos | **${gastos_fijos_pe:,.2f}** |
| Gastos Variables | **${gastos_var_pe:,.2f}** |
| Ventas del período | **${ventas_pe:,.2f}** |
| Razón Costo Variable | **{ratio_var_pe*100:.1f}%** |
| **Punto de Equilibrio** | **${pe_val:,.2f}** |
            """)
            utilidad_pe   = ventas_pe - gastos_tot_pe
            cobertura_pe  = min((ventas_pe / pe_val * 100), 150) if pe_val > 0 else 0.0
            pp1, pp2, pp3 = st.columns(3)
            pp1.metric("Punto de Equilibrio",  f"${pe_val:,.2f}")
            pp2.metric("Ventas del período",   f"${ventas_pe:,.2f}")
            pp3.metric("Utilidad neta estimada", f"${utilidad_pe:,.2f}",
                        delta_color="normal" if utilidad_pe >= 0 else "inverse")
            try:
                _gauge(cobertura_pe, 0, 150,
                       f"Cobertura del PE — {calendar.month_name[mes_pe].capitalize()} {año_pe}",
                       sufijo="%", umbral_verde=100, umbral_amarillo=80)
            except Exception:
                st.metric("Cobertura PE", f"{cobertura_pe:.1f}%")
        elif gastos_fijos_pe > 0 and ratio_var_pe >= 1:
            st.error("⚠️ Los gastos variables superan o igualan las ventas. El punto de equilibrio no es alcanzable con esta estructura de costos.")
        else:
            st.info("Ingresa los gastos del período para calcular el punto de equilibrio. Si ya registraste gastos en el módulo de Gastos, selecciona el mes y año correspondientes.")
        st.divider()
        st.subheader(f"📊 Cumplimiento anual vs presupuesto — {año_pe}")
        venta_anual_pe = df_vf[df_vf["Año"].apply(limpiar_valor) == año_pe]["Venta_Diaria"].sum()
        ppto_anual_pe  = 0.0
        if not df_pptof.empty:
            ppto_pe_data = df_pptof[df_pptof["Año"].apply(limpiar_valor) == año_pe]
            if not ppto_pe_data.empty:
                ppto_anual_pe = ppto_pe_data["Meta_Total"].apply(limpiar_valor).sum()
        if ppto_anual_pe > 0:
            cumpl_anual_pe = min(venta_anual_pe / ppto_anual_pe * 100, 150)
            try:
                _gauge(cumpl_anual_pe, 0, 150, f"Cumplimiento Presupuesto Anual {año_pe}", sufijo="%")
            except Exception:
                st.metric("Cumplimiento anual", f"{cumpl_anual_pe:.1f}%")
            pa1, pa2 = st.columns(2)
            pa1.metric("Venta anual acumulada", f"${venta_anual_pe:,.2f}")
            pa2.metric("Presupuesto anual",     f"${ppto_anual_pe:,.2f}")
        else:
            st.info("Configura el presupuesto anual en '📋 Presupuesto Anual' para ver el velocímetro de cumplimiento anual.")
        if not df_gf.empty:
            st.divider()
            st.subheader("📋 Detalle de gastos del período seleccionado")
            df_gf2 = df_gf.copy()
            df_gf2["_fecha"] = pd.to_datetime(df_gf2["Fecha"], errors="coerce")
            df_gf2_fil = df_gf2[
                (df_gf2["_fecha"].dt.month == mes_pe) &
                (df_gf2["_fecha"].dt.year  == año_pe)
            ]
            if not df_gf2_fil.empty:
                cols_gf2 = ["Fecha","Tipo","Categoria","Concepto","Monto","Responsable"]
                cols_gf2_ok = [c for c in cols_gf2 if c in df_gf2_fil.columns]
                st.dataframe(df_gf2_fil[cols_gf2_ok].sort_values("Tipo"), hide_index=True, use_container_width=True)
            else:
                st.info("Sin gastos registrados para este período en el módulo de Gastos.")
    with tab_canales:
        st.subheader("🛒 Canales de Venta Adicionales")
        if df_cfg_canales.empty:
            st.info("No hay canales configurados. Usa la página 'Canales de Venta' para crear tus canales adicionales.")
        else:
            canales_data = {}
            for _, canal_row in df_cfg_canales.iterrows():
                cn = canal_row["Canal"]
                ws_cn, _ = safe_worksheet(sh, cn)
                if ws_cn:
                    data = ws_cn.get_all_values()
                    if len(data) > 1:
                        df_cn = pd.DataFrame(data[1:], columns=data[0])
                        df_cn["Monto"] = df_cn["Monto"].apply(limpiar_valor)
                        df_cn["Fecha"] = pd.to_datetime(df_cn["Fecha"], errors="coerce")
                        canales_data[cn] = df_cn
            if not canales_data:
                st.info("Aún no hay eventos registrados en los canales.")
            else:
                acum_can = []
                total_general = 0.0
                for cn, df_cn in canales_data.items():
                    total_cn = df_cn["Monto"].sum()
                    acum_can.append({"Canal": cn, "Total": total_cn, "Eventos": len(df_cn)})
                    total_general += total_cn
                df_acum = pd.DataFrame(acum_can)
                st.subheader("Totales por canal")
                st.dataframe(df_acum, hide_index=True, use_container_width=True)
                st.metric("Total General Canales Adicionales", f"${total_general:,.2f}")
                try:
                    import plotly.express as px
                    fig_can_adic = px.bar(df_acum, x="Canal", y="Total", title="Ventas por Canal Adicional", color="Total")
                    st.plotly_chart(fig_can_adic, use_container_width=True)
                except Exception:
                    st.bar_chart(df_acum.set_index("Canal")["Total"])
                st.subheader("Ventas mensuales de canales adicionales")
                df_all_ev = pd.concat(canales_data.values(), ignore_index=True)
                df_all_ev["Mes"] = df_all_ev["Fecha"].dt.month
                df_all_ev["Año"] = df_all_ev["Fecha"].dt.year
                ventas_mens_can = df_all_ev.groupby(["Año","Mes"])["Monto"].sum().reset_index()
                ventas_mens_can = ventas_mens_can.sort_values(["Año","Mes"])
                ventas_mens_can["label"] = ventas_mens_can.apply(
                    lambda r: f"{calendar.month_abbr[int(r['Mes'])]} {int(r['Año'])}", axis=1
                )
                st.bar_chart(ventas_mens_can.set_index("label")["Monto"])
