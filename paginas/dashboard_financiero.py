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
from config import CANALES_VENTA, COLS_PRESUPUESTO

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
    df_vf     = cargar_todas_ventas()
    df_gf     = cargar_gastos()
    df_pptof  = cargar_presupuesto()
    df_bcf    = cargar_costos_insumos()
    df_mermaf = cargar_merma()
    if df_vf.empty:
        st.info("Sin datos de ventas. Comienza registrando ventas diarias.")
        st.stop()

    tab_comp, tab_proy, tab_fc, tab_merma_d, tab_pe, tab_tablas = st.tabs([
        "📊 Comparativo",
        "🔮 Proyecciones",
        "🍽️ Food Cost & Margen",
        "📉 Merma",
        "⚖️ Punto de Equilibrio",
        "📋 Tablas Comparativas",
    ])

    # ==================== TAB COMPARATIVO (EXISTENTE) ====================
    with tab_comp:
        # ... (todo el código existente del comparativo sin cambios) ...
        st.subheader("📊 Ventas vs Gastos por Período")
        periodo_comp = st.radio("Agrupar por:", ["Mes","Trimestre","Cuatrimestre","Año"], horizontal=True)
        df_vm = df_vf.copy()
        df_vm["Mes_num"] = df_vm["Mes"].apply(limpiar_valor).astype(int)
        df_vm["Año_num"] = df_vm["Año"].apply(limpiar_valor).astype(int)
        df_vm = df_vm[(df_vm["Mes_num"] > 0) & (df_vm["Año_num"] > 0)]
        ventas_mens = (
            df_vm.groupby(["Año_num","Mes_num"])
            .agg(Ventas=("Venta_Diaria","sum"),
                 POS=("Total_POS","sum"),
                 Uber=("Uber_Eats","sum"),
                 Rappi=("Rappi","sum"))
            .reset_index()
        )
        if "Canal" in df_vm.columns:
            ventas_por_canal = (
                df_vm.groupby(["Año_num","Mes_num","Canal"])["Venta_Diaria"]
                .sum().reset_index()
                .pivot(index=["Año_num","Mes_num"], columns="Canal", values="Venta_Diaria")
                .fillna(0).reset_index()
            )
            for c in CANALES_VENTA:
                if c not in ventas_por_canal.columns:
                    ventas_por_canal[c] = 0.0
            ventas_mens = ventas_mens.merge(ventas_por_canal, on=["Año_num","Mes_num"], how="left").fillna(0)
        else:
            for c in CANALES_VENTA:
                ventas_mens[c] = 0.0
            ventas_mens["Noble"] = ventas_mens["Ventas"]

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
                 POS=("POS","sum"), Uber=("Uber","sum"), Rappi=("Rappi","sum"),
                 Noble=("Noble","sum"), CoffeeStation=("Coffee Station","sum"), ToGo=("Noble To Go","sum"),
                 _sort=("_sort","min"))
            .reset_index()
            .sort_values("_sort")
            .drop(columns=["_sort"])
        )

        try:
            fig_comp = go.Figure()
            fig_comp.add_trace(go.Bar(name="Ventas",   x=df_agrup["Grupo"], y=df_agrup["Ventas"],   marker_color="#48B065"))
            fig_comp.add_trace(go.Bar(name="Gastos",   x=df_agrup["Grupo"], y=df_agrup["Gastos"],   marker_color="#E24B4A"))
            fig_comp.add_trace(go.Bar(name="Utilidad", x=df_agrup["Grupo"], y=df_agrup["Utilidad"], marker_color="#4A90D9"))
            fig_comp.update_layout(barmode="group", title="Ventas vs Gastos vs Utilidad", height=400,
                                    legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(fig_comp, use_container_width=True)

            st.subheader("🥧 Canales principales (Noble / Coffee Station / To Go)")
            fig_can2 = go.Figure()
            colores_canal = {"Noble": "#48B065", "Coffee Station": "#9B59B6", "Noble To Go": "#E24B4A"}
            for canal in CANALES_VENTA:
                if canal in df_agrup.columns:
                    fig_can2.add_trace(go.Bar(name=canal, x=df_agrup["Grupo"], y=df_agrup[canal],
                                              marker_color=colores_canal.get(canal, "#AAAAAA")))
            fig_can2.update_layout(barmode="stack", title="Mix por canal principal", height=350,
                                   legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(fig_can2, use_container_width=True)
        except Exception:
            st.bar_chart(df_agrup.set_index("Grupo")[["Ventas","Gastos","Utilidad"]])

        st.subheader("📋 Tabla de datos")
        st.dataframe(df_agrup, hide_index=True, use_container_width=True)

    # ==================== TAB PROYECCIONES (EXISTENTE) ====================
    with tab_proy:
        # ... (código existente sin cambios) ...
        st.subheader("🔮 Proyecciones de Ventas por Canal")
        hoy_pr        = ahora_hermosillo().date()
        dias_en_mes_pr = calendar.monthrange(hoy_pr.year, hoy_pr.month)[1]
        df_vf_mes_pr = df_vf[
            (df_vf["Mes"].apply(limpiar_valor) == hoy_pr.month) &
            (df_vf["Año"].apply(limpiar_valor) == hoy_pr.year)
        ].copy()
        venta_acum_pr = df_vf_mes_pr["Venta_Diaria"].sum() if not df_vf_mes_pr.empty else 0.0
        dias_con_v_pr = int((df_vf_mes_pr["Venta_Diaria"] > 0).sum()) if not df_vf_mes_pr.empty else 0
        dias_restantes_pr = dias_en_mes_pr - hoy_pr.day
        avg_diario_pr = venta_acum_pr / dias_con_v_pr if dias_con_v_pr > 0 else 0.0
        proyeccion_cierre = venta_acum_pr + (avg_diario_pr * dias_restantes_pr)

        metas_canal = {"Noble": 145000.0, "Coffee Station": 0.0, "Noble To Go": 0.0}
        if not df_pptof.empty:
            ppto_mes_pr = df_pptof[
                (df_pptof["Mes"].apply(limpiar_valor) == hoy_pr.month) &
                (df_pptof["Año"].apply(limpiar_valor) == hoy_pr.year)
            ]
            if not ppto_mes_pr.empty:
                metas_canal["Noble"] = limpiar_valor(ppto_mes_pr["Meta_Total"].iloc[-1]) or 145000.0
                metas_canal["Coffee Station"] = limpiar_valor(ppto_mes_pr["Meta_CoffeeStation"].iloc[-1]) or 0.0
                metas_canal["Noble To Go"] = limpiar_valor(ppto_mes_pr["Meta_ToGo"].iloc[-1]) or 0.0

        ventas_por_canal_mes = {}
        for canal in CANALES_VENTA:
            if "Canal" in df_vf_mes_pr.columns:
                ventas_por_canal_mes[canal] = df_vf_mes_pr[df_vf_mes_pr["Canal"] == canal]["Venta_Diaria"].sum()
            else:
                ventas_por_canal_mes[canal] = venta_acum_pr if canal == "Noble" else 0.0

        st.subheader(f"📅 {calendar.month_name[hoy_pr.month].capitalize()} {hoy_pr.year}")
        cols_meta = st.columns(len(CANALES_VENTA))
        for i, canal in enumerate(CANALES_VENTA):
            acum = ventas_por_canal_mes.get(canal, 0.0)
            meta = metas_canal.get(canal, 0.0)
            avance = (acum / meta * 100) if meta > 0 else 0.0
            cols_meta[i].metric(f"{canal}", f"${acum:,.2f}", f"Meta: ${meta:,.0f} ({avance:.0f}%)")

        st.divider()
        st.subheader("📈 Datos para tus propias gráficas")
        st.markdown("Descarga el archivo CSV con las ventas mensuales y crea tus propias visualizaciones en Excel.")
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

    # ==================== TAB FOOD COST (EXISTENTE) ====================
    with tab_fc:
        # ... (código existente sin cambios) ...
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

    # ==================== TAB MERMA (EXISTENTE) ====================
    with tab_merma_d:
        # ... (código existente sin cambios) ...
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

    # ==================== TAB PUNTO DE EQUILIBRIO (EXISTENTE) ====================
    with tab_pe:
        # ... (código existente sin cambios) ...
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
        with st.expander("✏️ Ajuste manual de gastos", expanded=(gastos_fijos_pe + gastos_var_pe == 0)):
            col_gf_pe, col_gv_pe = st.columns(2)
            with col_gf_pe:
                gastos_fijos_pe = st.number_input("Gastos Fijos ($):", min_value=0.0, step=100.0, value=float(gastos_fijos_pe))
            with col_gv_pe:
                gastos_var_pe = st.number_input("Gastos Variables ($):", min_value=0.0, step=100.0, value=float(gastos_var_pe))
        gastos_tot_pe = gastos_fijos_pe + gastos_var_pe
        ratio_var_pe  = (gastos_var_pe / ventas_pe) if ventas_pe > 0 else 0.0
        pe_val = 0.0
        pe_calculable = False
        if gastos_fijos_pe > 0 and ventas_pe > 0 and ratio_var_pe < 1:
            pe_val = gastos_fijos_pe / (1 - ratio_var_pe)
            pe_calculable = True
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
                _gauge(cobertura_pe, 0, 150, f"Cobertura del PE — {calendar.month_name[mes_pe].capitalize()} {año_pe}", sufijo="%", umbral_verde=100, umbral_amarillo=80)
            except Exception:
                st.metric("Cobertura PE", f"{cobertura_pe:.1f}%")
        elif gastos_fijos_pe > 0 and ratio_var_pe >= 1:
            st.error("⚠️ Los gastos variables superan o igualan las ventas. El punto de equilibrio no es alcanzable.")
        else:
            st.info("Ingresa los gastos del período para calcular el punto de equilibrio.")
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

    # ==================== NUEVA PESTAÑA: TABLAS COMPARATIVAS ====================
    with tab_tablas:
        st.subheader("📋 Tablas Comparativas por Canal")

        # --- Datos necesarios ---
        hoy_tab = ahora_hermosillo().date()
        año_actual = hoy_tab.year
        año_anterior = año_actual - 1

        # Ventas por mes y año para POS (Noble)
        df_pos = df_vf[df_vf["Canal"] == "Noble"].copy()
        # Ventas Coffee Station
        df_cs = df_vf[df_vf["Canal"] == "Coffee Station"].copy()

        # Metas desde presupuesto
        metas_pos = {}
        metas_cs = {}
        if not df_pptof.empty:
            for año in [año_anterior, año_actual]:
                df_ppto_año = df_pptof[df_pptof["Año"].apply(limpiar_valor) == año]
                for _, r in df_ppto_año.iterrows():
                    mes = int(limpiar_valor(r["Mes"]))
                    if 1 <= mes <= 12:
                        if año == año_actual:
                            metas_pos[mes] = limpiar_valor(r.get("Meta_Total", 0))
                            metas_cs[mes] = limpiar_valor(r.get("Meta_CoffeeStation", 0))
                        # Para año anterior solo se usará en comparativa POS

        # Tabla 1: Resultados generales POS (solo año actual vs anterior)
        st.markdown("### 🏢 Resultados Generales – POS (Noble)")
        meses_nombres = [calendar.month_name[m].capitalize() for m in range(1,13)]

        filas_pos = []
        for mes in range(1, 13):
            venta_ant = df_pos[(df_pos["Mes"].apply(limpiar_valor) == mes) & (df_pos["Año"].apply(limpiar_valor) == año_anterior)]["Venta_Diaria"].sum()
            venta_act = df_pos[(df_pos["Mes"].apply(limpiar_valor) == mes) & (df_pos["Año"].apply(limpiar_valor) == año_actual)]["Venta_Diaria"].sum()
            meta = metas_pos.get(mes, 0)
            cumpl = (venta_act / meta * 100) if meta > 0 else 0
            var = ((venta_act - venta_ant) / venta_ant * 100) if venta_ant > 0 else None
            var_str = f"{var:+.2f}%" if var is not None else "—"
            filas_pos.append({
                "MES": meses_nombres[mes-1],
                f"VENTA {año_anterior}": f"${venta_ant:,.0f}",
                f"VENTA {año_actual}": f"${venta_act:,.0f}",
                "META MENSUAL": f"${meta:,.0f}",
                "CUMPLIMIENTO": f"{cumpl:.2f}%",
                f"{año_anterior} VS {año_actual}": var_str
            })
        # Totales
        total_ant = sum(limpiar_valor(float(r[f"VENTA {año_anterior}"].replace("$","").replace(",",""))) for r in filas_pos)
        total_act = sum(limpiar_valor(float(r[f"VENTA {año_actual}"].replace("$","").replace(",",""))) for r in filas_pos)
        total_meta = sum(metas_pos.values())
        total_cumpl = (total_act / total_meta * 100) if total_meta > 0 else 0
        total_var = ((total_act - total_ant) / total_ant * 100) if total_ant > 0 else None
        total_var_str = f"{total_var:+.2f}%" if total_var is not None else "—"
        filas_pos.append({
            "MES": "TOTAL",
            f"VENTA {año_anterior}": f"${total_ant:,.0f}",
            f"VENTA {año_actual}": f"${total_act:,.0f}",
            "META MENSUAL": f"${total_meta:,.0f}",
            "CUMPLIMIENTO": f"{total_cumpl:.2f}%",
            f"{año_anterior} VS {año_actual}": total_var_str
        })
        df_pos_tabla = pd.DataFrame(filas_pos)
        st.dataframe(df_pos_tabla, hide_index=True, use_container_width=True)

        # Tabla 2: Métricas operativas POS (solo año actual)
        st.markdown("### 🎫 Métricas Operativas – POS")
        filas_met = []
        for mes in range(1, 13):
            df_mes_pos = df_pos[(df_pos["Mes"].apply(limpiar_valor) == mes) & (df_pos["Año"].apply(limpiar_valor) == año_actual)]
            transacciones = int(df_mes_pos["Total_Tickets"].sum()) if not df_mes_pos.empty else 0
            venta_mes = df_mes_pos["Venta_Diaria"].sum() if not df_mes_pos.empty else 0
            ticket_prom = round(venta_mes / transacciones, 2) if transacciones > 0 else 0
            # Mix canales (Efectivo, Transferencias, Tarjeta, Uber, Rappi)
            efect = df_mes_pos["Efectivo"].sum()
            trans = df_mes_pos["Transferencias"].sum()
            tarj = df_mes_pos["Tarjeta"].sum()
            uber = df_mes_pos["Uber_Eats"].sum()
            rapp = df_mes_pos["Rappi"].sum()
            total_pagos = efect + trans + tarj + uber + rapp
            if total_pagos > 0:
                mix_efect = f"{efect/total_pagos*100:.0f}%"
                mix_trans = f"{trans/total_pagos*100:.0f}%"
                mix_tarj = f"{tarj/total_pagos*100:.0f}%"
                mix_uber = f"{uber/total_pagos*100:.0f}%"
                mix_rapp = f"{rapp/total_pagos*100:.0f}%"
            else:
                mix_efect = mix_trans = mix_tarj = mix_uber = mix_rapp = "—"
            filas_met.append({
                "MES": meses_nombres[mes-1],
                "TRANSACCIONES": transacciones,
                "TICKET PROMEDIO": f"${ticket_prom:,.2f}",
                "EFECTIVO": mix_efect,
                "TRANSFERENCIA": mix_trans,
                "TARJETA": mix_tarj,
                "UBER": mix_uber,
                "RAPPI": mix_rapp,
            })
        # Totales
        total_trans = sum(r["TRANSACCIONES"] for r in filas_met)
        total_venta_met = total_act
        prom_total = round(total_venta_met / total_trans, 2) if total_trans > 0 else 0
        filas_met.append({
            "MES": "TOTAL",
            "TRANSACCIONES": total_trans,
            "TICKET PROMEDIO": f"${prom_total:,.2f}",
            "EFECTIVO": "", "TRANSFERENCIA": "", "TARJETA": "", "UBER": "", "RAPPI": ""
        })
        df_met_tabla = pd.DataFrame(filas_met)
        st.dataframe(df_met_tabla, hide_index=True, use_container_width=True)

        # Tabla 3: Coffee Station
        st.markdown("### ☕ Coffee Station")
        filas_cs = []
        for mes in range(1, 13):
            df_mes_cs = df_cs[(df_cs["Mes"].apply(limpiar_valor) == mes) & (df_cs["Año"].apply(limpiar_valor) == año_actual)]
            venta_cs_mes = df_mes_cs["Venta_Diaria"].sum() if not df_mes_cs.empty else 0
            servicios = len(df_mes_cs) if not df_mes_cs.empty else 0
            ticket_prom_cs = round(venta_cs_mes / servicios, 2) if servicios > 0 else 0
            meta_cs_mes = metas_cs.get(mes, 0)
            cumpl_cs = (venta_cs_mes / meta_cs_mes * 100) if meta_cs_mes > 0 else 0
            filas_cs.append({
                "MES": meses_nombres[mes-1],
                "VENTA": f"${venta_cs_mes:,.0f}",
                "META MENSUAL": f"${meta_cs_mes:,.0f}",
                "CUMPLIMIENTO": f"{cumpl_cs:.2f}%",
                "SERVICIOS": servicios,
                "TICKET PROMEDIO": f"${ticket_prom_cs:,.2f}"
            })
        total_cs_venta = sum(limpiar_valor(float(r["VENTA"].replace("$","").replace(",",""))) for r in filas_cs)
        total_cs_serv = sum(r["SERVICIOS"] for r in filas_cs)
        total_cs_meta = sum(metas_cs.values())
        total_cs_cumpl = (total_cs_venta / total_cs_meta * 100) if total_cs_meta > 0 else 0
        total_cs_ticket = round(total_cs_venta / total_cs_serv, 2) if total_cs_serv > 0 else 0
        filas_cs.append({
            "MES": "TOTAL",
            "VENTA": f"${total_cs_venta:,.0f}",
            "META MENSUAL": f"${total_cs_meta:,.0f}",
            "CUMPLIMIENTO": f"{total_cs_cumpl:.2f}%",
            "SERVICIOS": total_cs_serv,
            "TICKET PROMEDIO": f"${total_cs_ticket:,.2f}"
        })
        df_cs_tabla = pd.DataFrame(filas_cs)
        st.dataframe(df_cs_tabla, hide_index=True, use_container_width=True)

        # Tabla 4: Resumen por canal (anual actual)
        st.markdown("### 📊 Resumen por Canal")
        total_noble = df_pos[df_pos["Año"].apply(limpiar_valor) == año_actual]["Venta_Diaria"].sum()
        total_cs_anual = df_cs[df_cs["Año"].apply(limpiar_valor) == año_actual]["Venta_Diaria"].sum()
        # Noble To Go
        df_ntg = df_vf[df_vf["Canal"] == "Noble To Go"]
        total_ntg_anual = df_ntg[df_ntg["Año"].apply(limpiar_valor) == año_actual]["Venta_Diaria"].sum() if not df_ntg.empty else 0
        meta_noble_anual = sum(metas_pos.values())
        meta_cs_anual = sum(metas_cs.values())
        # Meta To Go desde presupuesto
        meta_ntg_anual = 0
        if not df_pptof.empty:
            df_ppto_act = df_pptof[df_pptof["Año"].apply(limpiar_valor) == año_actual]
            if not df_ppto_act.empty:
                meta_ntg_anual = df_ppto_act["Meta_ToGo"].apply(limpiar_valor).sum()
        cumpl_noble = (total_noble / meta_noble_anual * 100) if meta_noble_anual > 0 else 0
        cumpl_cs_anual = (total_cs_anual / meta_cs_anual * 100) if meta_cs_anual > 0 else 0
        cumpl_ntg = (total_ntg_anual / meta_ntg_anual * 100) if meta_ntg_anual > 0 else 0
        total_general = total_noble + total_cs_anual + total_ntg_anual
        meta_total_anual = meta_noble_anual + meta_cs_anual + meta_ntg_anual
        cumpl_total = (total_general / meta_total_anual * 100) if meta_total_anual > 0 else 0

        resumen_canal = [
            {"CANAL": "Cafetería (Noble)", "VENTA": f"${total_noble:,.0f}", "META": f"${meta_noble_anual:,.0f}", "CUMPLIMIENTO": f"{cumpl_noble:.2f}%"},
            {"CANAL": "Coffee Station", "VENTA": f"${total_cs_anual:,.0f}", "META": f"${meta_cs_anual:,.0f}", "CUMPLIMIENTO": f"{cumpl_cs_anual:.2f}%"},
            {"CANAL": "Noble To Go", "VENTA": f"${total_ntg_anual:,.0f}", "META": f"${meta_ntg_anual:,.0f}", "CUMPLIMIENTO": f"{cumpl_ntg:.2f}%"},
            {"CANAL": "TOTAL", "VENTA": f"${total_general:,.0f}", "META": f"${meta_total_anual:,.0f}", "CUMPLIMIENTO": f"{cumpl_total:.2f}%"},
        ]
        df_resumen = pd.DataFrame(resumen_canal)
        st.dataframe(df_resumen, hide_index=True, use_container_width=True)

        # --- CAPTURA RÁPIDA DE METAS MENSUALES (Coffee Station y To Go) ---
        st.divider()
        with st.expander("⚙️ Ajustar metas mensuales de canales adicionales", expanded=False):
            st.markdown("Actualiza las metas de Coffee Station y Noble To Go para el año actual. Se guardan en la hoja Presupuesto.")
            with st.form("f_metas_canales"):
                col_cs, col_ntg = st.columns(2)
                with col_cs:
                    st.write("**☕ Coffee Station**")
                    meta_cs_mensual = {}
                    for m in range(1, 13):
                        meta_cs_mensual[m] = st.number_input(
                            f"{calendar.month_name[m].capitalize()}:",
                            min_value=0.0, step=100.0,
                            value=float(metas_cs.get(m, 0)),
                            key=f"meta_cs_{m}"
                        )
                with col_ntg:
                    st.write("**🥤 Noble To Go**")
                    # Cargar metas existentes de To Go
                    metas_ntg = {}
                    if not df_pptof.empty:
                        df_ppto_act = df_pptof[df_pptof["Año"].apply(limpiar_valor) == año_actual]
                        for _, r in df_ppto_act.iterrows():
                            mes = int(limpiar_valor(r["Mes"]))
                            if 1 <= mes <= 12:
                                metas_ntg[mes] = limpiar_valor(r.get("Meta_ToGo", 0))
                    meta_ntg_mensual = {}
                    for m in range(1, 13):
                        meta_ntg_mensual[m] = st.number_input(
                            f"{calendar.month_name[m].capitalize()}:",
                            min_value=0.0, step=100.0,
                            value=float(metas_ntg.get(m, 0)),
                            key=f"meta_ntg_{m}"
                        )
                if st.form_submit_button("💾 Guardar metas"):
                    ws_ppto, err_ppto = _asegurar_hoja_presupuesto()
                    if err_ppto:
                        st.error(err_ppto)
                    else:
                        try:
                            # Leer datos actuales y quitar filas del año actual para estos canales (solo actualizamos Coffee y To Go, sin tocar POS/Uber/Rappi)
                            todos_ppto = ws_ppto.get_all_values()
                            if len(todos_ppto) > 1:
                                df_old = pd.DataFrame(todos_ppto[1:], columns=todos_ppto[0])
                                # Conservamos filas que no sean del año actual, o que sean del año actual pero no tengan mes (poco probable)
                                mask_año_act = df_old["Año"].astype(str).str.strip() == str(año_actual)
                                df_old = df_old[~mask_año_act]  # eliminamos todo el año actual
                            else:
                                df_old = pd.DataFrame()
                            # Construir nuevas filas para el año actual con metas de POS (mantener las que ya existen) y actualizar CS/ToGo
                            # Pero para no perder las metas POS, Uber, Rappi del año actual, debemos conservarlas del presupuesto existente.
                            # En su lugar, vamos a hacer un merge: para cada mes, si ya existe una fila en df_pptof para ese mes y año, actualizamos; si no, creamos.
                            # Primero obtenemos las metas POS/Uber/Rappi actuales del año actual desde df_pptof (que está en memoria)
                            metas_pos_exist = {}
                            metas_uber_exist = {}
                            metas_rappi_exist = {}
                            metas_cs_exist = {}
                            metas_ntg_exist = {}
                            if not df_pptof.empty:
                                df_ppto_act_mem = df_pptof[df_pptof["Año"].apply(limpiar_valor) == año_actual]
                                for _, r in df_ppto_act_mem.iterrows():
                                    mes = int(limpiar_valor(r["Mes"]))
                                    if 1 <= mes <= 12:
                                        metas_pos_exist[mes] = limpiar_valor(r.get("Meta_Total", 0))
                                        metas_uber_exist[mes] = limpiar_valor(r.get("Meta_Uber", 0))
                                        metas_rappi_exist[mes] = limpiar_valor(r.get("Meta_Rappi", 0))
                                        metas_cs_exist[mes] = limpiar_valor(r.get("Meta_CoffeeStation", 0))
                                        metas_ntg_exist[mes] = limpiar_valor(r.get("Meta_ToGo", 0))
                            # Ahora construimos filas nuevas para cada mes del año actual
                            nuevas_filas = []
                            for m in range(1, 13):
                                # Conservar las metas originales de POS/Uber/Rappi, y actualizar CS y ToGo con los valores del formulario
                                meta_total = metas_pos_exist.get(m, 0)
                                meta_pos = metas_pos_exist.get(m, 0)  # en el presupuesto Meta_POS está separado
                                meta_uber = metas_uber_exist.get(m, 0)
                                meta_rappi = metas_rappi_exist.get(m, 0)
                                meta_cs_nuevo = meta_cs_mensual[m]
                                meta_ntg_nuevo = meta_ntg_mensual[m]
                                nuevas_filas.append([
                                    año_actual, m, meta_total, meta_pos, meta_uber, meta_rappi,
                                    meta_cs_nuevo, meta_ntg_nuevo, ""
                                ])
                            # Limpiar hoja y reescribir todo
                            ws_ppto.clear()
                            ws_ppto.append_row(COLS_PRESUPUESTO)
                            if not df_old.empty:
                                ws_ppto.append_rows(df_old.values.tolist(), value_input_option="USER_ENTERED")
                            ws_ppto.append_rows(nuevas_filas, value_input_option="USER_ENTERED")
                            cargar_presupuesto.clear()
                            st.success("✅ Metas de Coffee Station y Noble To Go actualizadas.")
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al guardar: {e}")
