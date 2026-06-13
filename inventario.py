import pandas as pd
from utils import limpiar_valor, normalizar_nombre

def obtener_ultimo_inventario(df_hist: pd.DataFrame, unidad: str = None) -> pd.DataFrame:
    if df_hist.empty:
        return pd.DataFrame()
    df_u = df_hist.copy()
    if unidad:
        df_u = df_u[df_u["Unidad de Negocio"] == unidad]
    if df_u.empty:
        return pd.DataFrame()
    df_u["_fecha_efectiva"] = df_u["Fecha de Inventario"].combine_first(df_u["Fecha de Entrada"])
    df_u["_nombre_norm"]    = df_u["Nombre del Insumo"].apply(normalizar_nombre)
    df_actual = (
        df_u.sort_values("_fecha_efectiva", ascending=True, na_position="first")
            .drop_duplicates(subset=["Unidad de Negocio","_nombre_norm"], keep="last")
            .copy()
    )
    for col in ["Alm","Barra","Stock Neto","Stock Mínimo"]:
        df_actual[col] = df_actual[col].apply(limpiar_valor)
    df_actual["Tara"] = df_actual["Tara"].apply(limpiar_valor) if "Tara" in df_actual.columns else 0.0
    df_actual["Cantidad Ingresada"] = df_actual["Cantidad Ingresada"].apply(limpiar_valor) if "Cantidad Ingresada" in df_actual.columns else 0.0
    df_actual["Stock Neto Calculado"] = df_actual["Alm"] + df_actual["Barra"]
    if "¿Comprar?" in df_actual.columns:
        df_actual["Necesita Compra"] = df_actual["¿Comprar?"].astype(str).str.strip().str.upper() == "TRUE"
    else:
        df_actual["Necesita Compra"] = df_actual["Stock Neto Calculado"] < df_actual["Stock Mínimo"]
    df_actual["Fecha de Inventario"] = df_actual["_fecha_efectiva"]
    df_actual.drop(columns=["_fecha_efectiva","_nombre_norm"], inplace=True, errors="ignore")
    return df_actual

def buscar_insumo_en_actual(df_actual: pd.DataFrame, nombre: str) -> pd.Series:
    if df_actual.empty:
        return None
    nom_norm = normalizar_nombre(nombre)
    mascaras = df_actual["Nombre del Insumo"].apply(normalizar_nombre) == nom_norm
    if not mascaras.any():
        return None
    return df_actual[mascaras].iloc[0]

def construir_fila_historial(
    unidad, nombre, marca, proveedor, grupo, fecha_entrada,
    presentacion, unidad_medida, alm, barra, stock_neto,
    stock_minimo, comprar, responsable, fecha_inventario, tara, observaciones,
    cantidad_ingresada=0.0,
) -> list:
    def _s(v):
        if v is None: return ""
        try:
            if pd.isna(v): return ""
        except Exception: pass
        return str(v).strip()
    def _n(v): return limpiar_valor(v)
    return [
        _s(unidad), _s(nombre), _s(marca), _s(proveedor), _s(grupo),
        _s(fecha_entrada), _s(presentacion), _s(unidad_medida),
        _n(alm), _n(barra), _n(stock_neto), _n(stock_minimo),
        "TRUE" if comprar else "FALSE",
        _s(responsable), _s(fecha_inventario),
        max(0.0, _n(tara)), _s(observaciones),
        _n(cantidad_ingresada),
    ]

def fecha_max_segura(serie: pd.Series) -> str:
    from utils import fmt_fecha_hmo
    validas = serie.dropna()
    if validas.empty:
        return "Sin registros"
    return fmt_fecha_hmo(validas.max())
