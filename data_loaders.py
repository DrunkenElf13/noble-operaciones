import streamlit as st
import pandas as pd
import re
import time as _time
from datetime import datetime
from sheets import safe_worksheet, sh
from utils import normalizar_dataframe, limpiar_valor, normalizar_nombre
from config import (COLS_INSUMOS, COLS_HISTORIAL, COLS_VENTAS, COLS_GASTOS,
                    COLS_PRESUPUESTO, COLS_BASE_COSTOS, COLS_MERMA,
                    COLS_COSTOS_INSUMOS, COLS_RECETAS, COLS_COMBOS, COLS_AVISOS,
                    COLS_CRITICAS_INSUMOS, COLS_CRITICAS_HISTORIAL)

def _safe_get_all_values(ws, retries=3, delay=2):
    """Obtiene todos los valores de una worksheet con reintentos ante error 429."""
    for intento in range(retries):
        try:
            return ws.get_all_values()
        except Exception as e:
            if "429" in str(e) and intento < retries - 1:
                _time.sleep(delay * (2 ** intento))
                continue
            raise
    return []

@st.cache_data(ttl=120)
def cargar_datos_integrales():
    if sh is None:
        return pd.DataFrame(), pd.DataFrame()
    try:
        ws_ins, err_ins = safe_worksheet(sh, "Insumos")
        if err_ins: return pd.DataFrame(), pd.DataFrame()
        ws_his, err_his = safe_worksheet(sh, "Historial")
        if err_his: return pd.DataFrame(), pd.DataFrame()
        val_ins = _safe_get_all_values(ws_ins)
        val_his = _safe_get_all_values(ws_his)
        ws_cie, _ = safe_worksheet(sh, "Cierres")
        val_cie   = _safe_get_all_values(ws_cie) if ws_cie else []
        def _to_df(vals):
            if len(vals) > 1:
                return pd.DataFrame(vals[1:], columns=vals[0])
            return pd.DataFrame(columns=vals[0] if vals else [])
        df_ins = _to_df(val_ins)
        df_his = _to_df(val_his)
        df_cie = _to_df(val_cie) if val_cie else pd.DataFrame()
        df_ins["Sheet_Row_Num"] = df_ins.index + 2
        df_ins = normalizar_dataframe(df_ins, COLS_INSUMOS + ["Sheet_Row_Num"], cols_criticas=COLS_CRITICAS_INSUMOS)
        if "Activo" in df_ins.columns:
            df_ins_activos = df_ins[df_ins["Activo"].astype(str).str.strip().str.upper() == "TRUE"].copy()
        else:
            df_ins_activos = df_ins.copy()
        df_his = normalizar_dataframe(df_his, COLS_HISTORIAL, cols_criticas=COLS_CRITICAS_HISTORIAL)
        if not df_cie.empty:
            df_cie = normalizar_dataframe(df_cie, COLS_HISTORIAL)
            df_total = pd.concat([df_cie, df_his], ignore_index=True)
        else:
            df_total = df_his
        if not df_total.empty:
            df_total["Fecha de Inventario"] = pd.to_datetime(df_total["Fecha de Inventario"], errors="coerce")
            df_total["Fecha de Entrada"]    = pd.to_datetime(df_total["Fecha de Entrada"], errors="coerce")
            if not df_ins_activos.empty:
                df_ins_m = df_ins_activos.copy()
            elif not df_ins.empty:
                df_ins_m = df_ins.copy()
            else:
                df_ins_m = pd.DataFrame()
            if not df_ins_m.empty:
                df_ins_m["_nom_norm"] = df_ins_m["Nombre del Insumo"].apply(normalizar_nombre)
                df_ins_m["_clave"]   = df_ins_m["Unidad de Negocio"].fillna("") + "||" + df_ins_m["_nom_norm"]
                COLS_ESTATICAS = ["_clave","Nombre del Insumo","Marca","Proveedor","Grupo","Presentación de Compra","Unidad de Medida","Stock Mínimo","Tara"]
                df_ins_m = df_ins_m[[c for c in COLS_ESTATICAS if c in df_ins_m.columns]].copy()
                df_ins_m["Stock Mínimo"] = df_ins_m["Stock Mínimo"].apply(limpiar_valor)
                df_ins_m["Tara"] = df_ins_m["Tara"].apply(limpiar_valor) if "Tara" in df_ins_m.columns else 0.0
                df_ins_m = df_ins_m.drop_duplicates(subset=["_clave"], keep="last")
                df_total["_nom_norm"] = df_total["Nombre del Insumo"].apply(normalizar_nombre)
                df_total["_clave"]   = df_total["Unidad de Negocio"].fillna("") + "||" + df_total["_nom_norm"]
                COLS_CIFRAS = ["_clave","Unidad de Negocio","Alm","Barra","Stock Neto","¿Comprar?","Responsable","Fecha de Inventario","Fecha de Entrada","Tara","Observaciones"]
                cols_cifras_ok = [c for c in COLS_CIFRAS if c in df_total.columns]
                df_cifras = df_total[cols_cifras_ok].copy()
                df_total  = df_cifras.merge(df_ins_m, on="_clave", how="left", suffixes=("_hist","_cat"))
                tara_hist = df_total.get("Tara_hist", pd.Series(0.0, index=df_total.index))
                tara_cat  = df_total.get("Tara_cat",  df_total.get("Tara", pd.Series(0.0, index=df_total.index)))
                df_total["Tara"] = tara_hist.apply(limpiar_valor).where(tara_hist.apply(limpiar_valor) > 0, tara_cat.apply(limpiar_valor))
                df_total.drop(columns=["Tara_hist","Tara_cat","_clave","_nom_norm"], inplace=True, errors="ignore")
        return df_ins_activos, df_total
    except Exception as e:
        st.error(f"Falla en extracción de datos: {e}")
        return pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=120)
def cargar_ventas():
    if sh is None:
        return pd.DataFrame()
    ws, err = safe_worksheet(sh, "Ventas")
    if err:
        return pd.DataFrame()
    try:
        data = _safe_get_all_values(ws)
        if len(data) < 2:
            return pd.DataFrame(columns=COLS_VENTAS)
        df = pd.DataFrame(data[1:], columns=data[0])
        for col in COLS_VENTAS:
            if col not in df.columns:
                df[col] = ""
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
        for col in ["Efectivo","Transferencias","Tarjeta","Total_POS","Uber_Eats","Rappi",
                    "Venta_Diaria","Tickets_POS","Tickets_Uber","Tickets_Rappi","Total_Tickets",
                    "Ticket_Promedio","Meta_Mensual","Dias_Habiles","Meta_Diaria"]:
            if col in df.columns:
                df[col] = df[col].apply(limpiar_valor)
        return df
    except Exception as e:
        st.warning(f"Error cargando ventas: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=120)
def cargar_gastos():
    if sh is None:
        return pd.DataFrame(columns=COLS_GASTOS)
    ws, err = safe_worksheet(sh, "Gastos")
    if err:
        return pd.DataFrame(columns=COLS_GASTOS)
    try:
        data = _safe_get_all_values(ws)
        if len(data) < 2:
            return pd.DataFrame(columns=COLS_GASTOS)
        df = pd.DataFrame(data[1:], columns=data[0])
        for col in COLS_GASTOS:
            if col not in df.columns:
                df[col] = ""
        df["Monto"] = df["Monto"].apply(limpiar_valor)
        return df
    except Exception as e:
        st.warning(f"Error cargando gastos: {e}")
        return pd.DataFrame(columns=COLS_GASTOS)

@st.cache_data(ttl=120)
def cargar_presupuesto():
    if sh is None:
        return pd.DataFrame(columns=COLS_PRESUPUESTO)
    ws, err = safe_worksheet(sh, "Presupuesto")
    if err:
        return pd.DataFrame(columns=COLS_PRESUPUESTO)
    try:
        data = _safe_get_all_values(ws)
        if len(data) < 2:
            return pd.DataFrame(columns=COLS_PRESUPUESTO)
        df = pd.DataFrame(data[1:], columns=data[0])
        for col in COLS_PRESUPUESTO:
            if col not in df.columns:
                df[col] = ""
        for col in ["Meta_Total","Meta_POS","Meta_Uber","Meta_Rappi"]:
            if col in df.columns:
                df[col] = df[col].apply(limpiar_valor)
        return df
    except Exception as e:
        st.warning(f"Error cargando presupuesto: {e}")
        return pd.DataFrame(columns=COLS_PRESUPUESTO)

@st.cache_data(ttl=120)
def cargar_base_costos():
    if sh is None:
        return pd.DataFrame(columns=COLS_BASE_COSTOS)
    ws, err = safe_worksheet(sh, "BaseCostos")
    if err:
        return pd.DataFrame(columns=COLS_BASE_COSTOS)
    try:
        data = _safe_get_all_values(ws)
        if len(data) < 2:
            return pd.DataFrame(columns=COLS_BASE_COSTOS)
        df = pd.DataFrame(data[1:], columns=data[0])
        for col in COLS_BASE_COSTOS:
            if col not in df.columns:
                df[col] = ""
        for col in ["Costo_Total","Costo_Unitario","Precio_Venta","Food_Cost_Pct"]:
            if col in df.columns:
                df[col] = df[col].apply(limpiar_valor)
        return df
    except Exception as e:
        st.warning(f"Error cargando base de costos: {e}")
        return pd.DataFrame(columns=COLS_BASE_COSTOS)

@st.cache_data(ttl=120)
def cargar_costos_insumos():
    if sh is None:
        return pd.DataFrame(columns=COLS_COSTOS_INSUMOS)
    ws, err = safe_worksheet(sh, "CostosInsumos")
    if err:
        return pd.DataFrame(columns=COLS_COSTOS_INSUMOS)
    try:
        data = _safe_get_all_values(ws)
        if len(data) < 2:
            return pd.DataFrame(columns=COLS_COSTOS_INSUMOS)
        df = pd.DataFrame(data[1:], columns=data[0])
        for col in COLS_COSTOS_INSUMOS:
            if col not in df.columns:
                df[col] = ""
        for col in ["Costo_Presentacion","Costo_Unitario","Contenido_Base_por_Unidad","Costo_Base_Unitario"]:
            if col in df.columns:
                df[col] = df[col].apply(limpiar_valor)
        return df
    except Exception as e:
        st.warning(f"Error cargando costos insumos: {e}")
        return pd.DataFrame(columns=COLS_COSTOS_INSUMOS)

@st.cache_data(ttl=120)
def cargar_recetas():
    if sh is None:
        return pd.DataFrame(columns=COLS_RECETAS)
    ws, err = safe_worksheet(sh, "Recetas")
    if err:
        return pd.DataFrame(columns=COLS_RECETAS)
    try:
        data = _safe_get_all_values(ws)
        if len(data) < 2:
            return pd.DataFrame(columns=COLS_RECETAS)
        df = pd.DataFrame(data[1:], columns=data[0])
        for col in COLS_RECETAS:
            if col not in df.columns:
                df[col] = "" if col not in ["Rinde","Costo_Porcion"] else 1.0
        for col in ["Cantidad","Costo_Ingrediente","Precio_Venta","Food_Cost_Pct",
                    "Precio_Insumo","Costo_Neto_Receta","Rinde","Costo_Porcion"]:
            if col in df.columns:
                df[col] = df[col].apply(limpiar_valor)
        if "Tipo_Componente" in df.columns:
            df["Tipo_Componente"] = df["Tipo_Componente"].replace("", "Insumo")
        return df
    except Exception as e:
        st.warning(f"Error cargando recetas: {e}")
        return pd.DataFrame(columns=COLS_RECETAS)

@st.cache_data(ttl=120)
def cargar_combos():
    if sh is None:
        return pd.DataFrame(columns=COLS_COMBOS)
    ws, err = safe_worksheet(sh, "Combos")
    if err:
        return pd.DataFrame(columns=COLS_COMBOS)
    try:
        data = _safe_get_all_values(ws)
        if len(data) < 2:
            return pd.DataFrame(columns=COLS_COMBOS)
        df = pd.DataFrame(data[1:], columns=data[0])
        for col in COLS_COMBOS:
            if col not in df.columns:
                df[col] = ""
        for col in ["Cantidad","Costo_Unitario","Costo_Total_Componente",
                    "Costo_Neto_Combo","Precio_Venta","Food_Cost_Pct"]:
            if col in df.columns:
                df[col] = df[col].apply(limpiar_valor)
        return df
    except Exception as e:
        st.warning(f"Error cargando combos: {e}")
        return pd.DataFrame(columns=COLS_COMBOS)

@st.cache_data(ttl=120)
def cargar_merma():
    if sh is None:
        return pd.DataFrame(columns=COLS_MERMA)
    ws, err = safe_worksheet(sh, "Merma")
    if err:
        return pd.DataFrame(columns=COLS_MERMA)
    try:
        data = _safe_get_all_values(ws)
        if len(data) < 2:
            return pd.DataFrame(columns=COLS_MERMA)
        df = pd.DataFrame(data[1:], columns=data[0])
        for col in COLS_MERMA:
            if col not in df.columns:
                df[col] = ""
        for col in ["Cantidad","Costo_Unitario","Costo_Total"]:
            if col in df.columns:
                df[col] = df[col].apply(limpiar_valor)
        return df
    except Exception as e:
        st.warning(f"Error cargando merma: {e}")
        return pd.DataFrame(columns=COLS_MERMA)

@st.cache_data(ttl=120)
def cargar_avisos():
    if sh is None:
        return pd.DataFrame()
    ws, err = safe_worksheet(sh, "Avisos")
    if err:
        return pd.DataFrame()
    try:
        data = _safe_get_all_values(ws)
        if len(data) < 2:
            return pd.DataFrame(columns=COLS_AVISOS)
        df = pd.DataFrame(data[1:], columns=data[0])
        for col in COLS_AVISOS:
            if col not in df.columns:
                df[col] = ""
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=120)
def cargar_todas_ventas():
    """Lee las hojas Ventas, Coffee Station y Noble To Go y las une."""
    hojas = ["Ventas", "Coffee Station", "Noble To Go"]
    dfs = []
    for hoja in hojas:
        ws, err = safe_worksheet(sh, hoja)
        if ws is None:
            continue
        datos = _safe_get_all_values(ws)
        if len(datos) <= 1:
            continue
        df = pd.DataFrame(datos[1:], columns=datos[0])
        if hoja in ["Coffee Station", "Noble To Go"]:
            total_cotizado = df["Total_Cotizado"].apply(limpiar_valor) if "Total_Cotizado" in df.columns else 0.0
            adeudo = df["Adeudo"].apply(limpiar_valor) if "Adeudo" in df.columns else 0.0
            anticipo = df["Anticipo"].apply(limpiar_valor) if "Anticipo" in df.columns else 0.0

            if "Tipo" in df.columns:
                mask_abono = df["Tipo"].astype(str).str.strip() == "💰 Abono"
                df.loc[mask_abono, "Venta_Diaria"] = total_cotizado[mask_abono]
                df.loc[mask_abono, "Venta_Total"] = total_cotizado[mask_abono]
                df.loc[~mask_abono, "Venta_Diaria"] = anticipo[~mask_abono]
                df.loc[~mask_abono, "Venta_Total"] = total_cotizado[~mask_abono]
            else:
                df["Venta_Diaria"] = anticipo
                df["Venta_Total"] = total_cotizado

            if "Anticipo" in df.columns:
                df["Anticipo"] = df["Anticipo"].apply(limpiar_valor)
            else:
                df["Anticipo"] = 0.0
            df["Adeudo"] = adeudo

            if "Fecha_Contratacion" in df.columns:
                fecha_ref = df["Fecha_Contratacion"].astype(str).str.strip()
                mask_empty = (fecha_ref == "") | (fecha_ref.isna())
                if mask_empty.any():
                    fecha_ref.loc[mask_empty] = df.loc[mask_empty, "Fecha"].astype(str).str.strip()
            else:
                fecha_ref = df["Fecha"].astype(str).str.strip()

            fechas_dt = pd.to_datetime(fecha_ref, errors="coerce")
            mask_na = fechas_dt.isna()
            if mask_na.any():
                extracted = fecha_ref[mask_na].str.extract(r'(\d{4})-(\d{2})-(\d{2})')
                for idx, row in extracted.iterrows():
                    try:
                        y, m, d = int(row[0]), int(row[1]), int(row[2])
                        fechas_dt.at[idx] = datetime(y, m, d)
                    except:
                        pass
            df["Mes"] = fechas_dt.dt.month.fillna(0).astype(int).astype(str)
            df["Año"] = fechas_dt.dt.year.fillna(0).astype(int).astype(str)

            for col in COLS_VENTAS:
                if col not in df.columns:
                    if col in ["Efectivo","Transferencias","Tarjeta","Total_POS","Uber_Eats","Rappi",
                               "Venta_Diaria","Venta_Total","Tickets_POS","Tickets_Uber","Tickets_Rappi",
                               "Total_Tickets","Ticket_Promedio","Meta_Mensual","Dias_Habiles","Meta_Diaria",
                               "Adeudo","Anticipo"]:
                        df[col] = 0.0
                    else:
                        df[col] = ""
            df["Canal"] = hoja
        else:
            if "Canal" not in df.columns:
                df["Canal"] = "Noble"
            else:
                df["Canal"] = df["Canal"].fillna("Noble")
            if "Venta_Diaria" in df.columns:
                df["Venta_Total"] = df["Venta_Diaria"].apply(limpiar_valor)
            else:
                df["Venta_Total"] = 0.0
            for col in ["Adeudo","Anticipo"]:
                if col not in df.columns:
                    df[col] = 0.0
            for col in COLS_VENTAS:
                if col not in df.columns:
                    df[col] = "" if col not in ["Efectivo","Transferencias","Tarjeta","Total_POS","Uber_Eats","Rappi","Venta_Diaria","Tickets_POS","Tickets_Uber","Tickets_Rappi","Total_Tickets","Ticket_Promedio","Meta_Mensual","Dias_Habiles","Meta_Diaria","Adeudo","Anticipo","Venta_Total"] else 0.0
        dfs.append(df[COLS_VENTAS])

    if dfs:
        df_total = pd.concat(dfs, ignore_index=True)
        df_total["Fecha"] = pd.to_datetime(df_total["Fecha"], errors="coerce")
        for col in ["Efectivo","Transferencias","Tarjeta","Total_POS","Uber_Eats","Rappi",
                    "Venta_Diaria","Venta_Total","Tickets_POS","Tickets_Uber","Tickets_Rappi","Total_Tickets",
                    "Ticket_Promedio","Meta_Mensual","Dias_Habiles","Meta_Diaria",
                    "Adeudo","Anticipo"]:
            if col in df_total.columns:
                df_total[col] = df_total[col].apply(limpiar_valor)
        return df_total
    return pd.DataFrame(columns=COLS_VENTAS)

def cargar_costos_actuales_recetas():
    """
    Devuelve un DataFrame con el costo actual de cada receta,
    calculado sumando el último costo de cada ingrediente.
    """
    df_rec = cargar_recetas()
    df_costos = cargar_costos_insumos()
    if df_rec.empty:
        return pd.DataFrame()

    # Obtener último costo por insumo
    if df_costos.empty:
        ultimo_costo = pd.DataFrame()
    else:
        ultimo_costo = (
            df_costos.sort_values("Fecha_Captura")
            .drop_duplicates(subset=["Nombre_Insumo"], keep="last")
        )

    # Mapear insumo -> costo unitario preferido (Costo_Base_Unitario si >0, si no Costo_Unitario)
    costo_map = {}
    if not ultimo_costo.empty:
        for _, row in ultimo_costo.iterrows():
            insumo = row["Nombre_Insumo"]
            costo_base = limpiar_valor(row.get("Costo_Base_Unitario", 0))
            if costo_base > 0:
                costo_map[insumo] = costo_base
            else:
                costo_map[insumo] = limpiar_valor(row.get("Costo_Unitario", 0))

    # Calcular costo por receta sumando ingredientes
    filas_recetas = []
    for receta, grupo in df_rec.groupby("Receta"):
        costo_total = 0.0
        for _, row in grupo.iterrows():
            ing = row.get("Ingrediente", "")
            cantidad = limpiar_valor(row.get("Cantidad", 0))
            costo_unit = costo_map.get(ing, 0.0)
            # Si no se encontró en el mapa, buscar en df_costos
            if costo_unit == 0.0 and not df_costos.empty:
                mask = df_costos["Nombre_Insumo"] == ing
                if mask.any():
                    ultimo_ing = df_costos[mask].sort_values("Fecha_Captura").iloc[-1]
                    costo_unit = limpiar_valor(ultimo_ing.get("Costo_Unitario", 0))
            costo_total += cantidad * costo_unit

        precio_venta = limpiar_valor(grupo.iloc[0].get("Precio_Venta", 0))
        food_cost = (costo_total / precio_venta * 100) if precio_venta > 0 else 0.0
        filas_recetas.append({
            "Receta": receta,
            "Linea": str(grupo.iloc[0].get("Linea", "")),
            "Presentacion": str(grupo.iloc[0].get("Presentacion", "")),
            "Precio_Venta": precio_venta,
            "Costo_Actual": round(costo_total, 4),
            "Food_Cost_Actual": round(food_cost, 2),
            "Margen_Actual": round(precio_venta - costo_total, 2),
            "Factor_Actual": round(precio_venta / costo_total, 2) if costo_total > 0 else 0.0,
        })
    return pd.DataFrame(filas_recetas)
