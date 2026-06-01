import streamlit as st
import pandas as pd
from sheets import safe_worksheet, sh
from utils import normalizar_dataframe, limpiar_valor, normalizar_nombre
from config import (COLS_INSUMOS, COLS_HISTORIAL, COLS_VENTAS, COLS_GASTOS,
                    COLS_PRESUPUESTO, COLS_BASE_COSTOS, COLS_MERMA,
                    COLS_COSTOS_INSUMOS, COLS_RECETAS, COLS_CANALES_CONFIG,
                    COLS_AVISOS, COLS_CRITICAS_INSUMOS, COLS_CRITICAS_HISTORIAL)

@st.cache_data(ttl=30)
def cargar_datos_integrales():
    if sh is None:
        return pd.DataFrame(), pd.DataFrame()
    try:
        ws_ins, err_ins = safe_worksheet(sh, "Insumos")
        if err_ins: return pd.DataFrame(), pd.DataFrame()
        ws_his, err_his = safe_worksheet(sh, "Historial")
        if err_his: return pd.DataFrame(), pd.DataFrame()
        val_ins = ws_ins.get_all_values()
        val_his = ws_his.get_all_values()
        ws_cie, _ = safe_worksheet(sh, "Cierres")
        val_cie   = ws_cie.get_all_values() if ws_cie else []
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

@st.cache_data(ttl=30)
def cargar_ventas():
    if sh is None:
        return pd.DataFrame()
    ws, err = safe_worksheet(sh, "Ventas")
    if err:
        return pd.DataFrame()
    try:
        data = ws.get_all_values()
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

@st.cache_data(ttl=30)
def cargar_gastos():
    if sh is None:
        return pd.DataFrame(columns=COLS_GASTOS)
    ws, err = safe_worksheet(sh, "Gastos")
    if err:
        return pd.DataFrame(columns=COLS_GASTOS)
    try:
        data = ws.get_all_values()
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

@st.cache_data(ttl=30)
def cargar_presupuesto():
    if sh is None:
        return pd.DataFrame(columns=COLS_PRESUPUESTO)
    ws, err = safe_worksheet(sh, "Presupuesto")
    if err:
        return pd.DataFrame(columns=COLS_PRESUPUESTO)
    try:
        data = ws.get_all_values()
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

@st.cache_data(ttl=30)
def cargar_base_costos():
    if sh is None:
        return pd.DataFrame(columns=COLS_BASE_COSTOS)
    ws, err = safe_worksheet(sh, "BaseCostos")
    if err:
        return pd.DataFrame(columns=COLS_BASE_COSTOS)
    try:
        data = ws.get_all_values()
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

@st.cache_data(ttl=60)
def cargar_costos_insumos():
    if sh is None:
        return pd.DataFrame(columns=COLS_COSTOS_INSUMOS)
    ws, err = safe_worksheet(sh, "CostosInsumos")
    if err:
        return pd.DataFrame(columns=COLS_COSTOS_INSUMOS)
    try:
        data = ws.get_all_values()
        if len(data) < 2:
            return pd.DataFrame(columns=COLS_COSTOS_INSUMOS)
        df = pd.DataFrame(data[1:], columns=data[0])
        for col in COLS_COSTOS_INSUMOS:
            if col not in df.columns:
                df[col] = ""
        for col in ["Costo_Presentacion","Costo_Unitario"]:
            if col in df.columns:
                df[col] = df[col].apply(limpiar_valor)
        return df
    except Exception as e:
        st.warning(f"Error cargando costos insumos: {e}")
        return pd.DataFrame(columns=COLS_COSTOS_INSUMOS)

@st.cache_data(ttl=60)
def cargar_recetas():
    if sh is None:
        return pd.DataFrame(columns=COLS_RECETAS)
    ws, err = safe_worksheet(sh, "Recetas")
    if err:
        return pd.DataFrame(columns=COLS_RECETAS)
    try:
        data = ws.get_all_values()
        if len(data) < 2:
            return pd.DataFrame(columns=COLS_RECETAS)
        df = pd.DataFrame(data[1:], columns=data[0])
        for col in COLS_RECETAS:
            if col not in df.columns:
                df[col] = ""
        for col in ["Cantidad","Costo_Ingrediente"]:
            if col in df.columns:
                df[col] = df[col].apply(limpiar_valor)
        return df
    except Exception as e:
        st.warning(f"Error cargando recetas: {e}")
        return pd.DataFrame(columns=COLS_RECETAS)

@st.cache_data(ttl=60)
def cargar_config_canales():
    if sh is None:
        return pd.DataFrame(columns=COLS_CANALES_CONFIG)
    ws, err = safe_worksheet(sh, "Config_Canales")
    if err:
        return pd.DataFrame(columns=COLS_CANALES_CONFIG)
    try:
        data = ws.get_all_values()
        if len(data) < 2:
            return pd.DataFrame(columns=COLS_CANALES_CONFIG)
        df = pd.DataFrame(data[1:], columns=data[0])
        for col in COLS_CANALES_CONFIG:
            if col not in df.columns:
                df[col] = ""
        return df
    except Exception:
        return pd.DataFrame(columns=COLS_CANALES_CONFIG)

@st.cache_data(ttl=30)
def cargar_merma():
    if sh is None:
        return pd.DataFrame(columns=COLS_MERMA)
    ws, err = safe_worksheet(sh, "Merma")
    if err:
        return pd.DataFrame(columns=COLS_MERMA)
    try:
        data = ws.get_all_values()
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

@st.cache_data(ttl=30)
def cargar_avisos():
    if sh is None:
        return pd.DataFrame()
    ws, err = safe_worksheet(sh, "Avisos")
    if err:
        return pd.DataFrame()
    try:
        data = ws.get_all_values()
        if len(data) < 2:
            return pd.DataFrame(columns=COLS_AVISOS)
        df = pd.DataFrame(data[1:], columns=data[0])
        for col in COLS_AVISOS:
            if col not in df.columns:
                df[col] = ""
        return df
    except Exception:
        return pd.DataFrame()

# ─────────────────────────────────────────────────────────────────
# NUEVA FUNCIÓN: consolidar ventas de todos los canales
# ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def cargar_todas_ventas():
    """Lee las hojas Ventas, CoffeeStation y NobleToGo y las une."""
    hojas = ["Ventas", "CoffeeStation", "NobleToGo"]
    dfs = []
    for hoja in hojas:
        ws, err = safe_worksheet(sh, hoja)
        if ws:
            datos = ws.get_all_values()
            if len(datos) > 1:
                df = pd.DataFrame(datos[1:], columns=datos[0])
                # Asegurar que tenga la columna Canal
                if "Canal" not in df.columns:
                    df["Canal"] = "Noble" if hoja == "Ventas" else hoja
                else:
                    df["Canal"] = df["Canal"].fillna("Noble" if hoja == "Ventas" else hoja)
                # Normalizar nombres de columnas
                for col in COLS_VENTAS:
                    if col not in df.columns:
                        df[col] = "" if col not in ["Efectivo","Transferencias","Tarjeta","Total_POS","Uber_Eats","Rappi","Venta_Diaria","Tickets_POS","Tickets_Uber","Tickets_Rappi","Total_Tickets","Ticket_Promedio","Meta_Mensual","Dias_Habiles","Meta_Diaria"] else 0.0
                dfs.append(df[COLS_VENTAS])
    if dfs:
        df_total = pd.concat(dfs, ignore_index=True)
        df_total["Fecha"] = pd.to_datetime(df_total["Fecha"], errors="coerce")
        for col in ["Efectivo","Transferencias","Tarjeta","Total_POS","Uber_Eats","Rappi",
                    "Venta_Diaria","Tickets_POS","Tickets_Uber","Tickets_Rappi","Total_Tickets",
                    "Ticket_Promedio","Meta_Mensual","Dias_Habiles","Meta_Diaria"]:
            if col in df_total.columns:
                df_total[col] = df_total[col].apply(limpiar_valor)
        return df_total
    return pd.DataFrame(columns=COLS_VENTAS)
