import pandas as pd
import unicodedata
import re
import numpy as np
from datetime import datetime, timezone, timedelta

TZ_HERMOSILLO = timezone(timedelta(hours=-7))

def ahora_hermosillo() -> datetime:
    return datetime.now(tz=TZ_HERMOSILLO)

def ts_hermosillo() -> str:
    return ahora_hermosillo().strftime("%Y-%m-%d %H:%M:%S")

def fmt_fecha_hmo(dt) -> str:
    if dt is None or (hasattr(dt, 'isnull') and dt.isnull()):
        return ""
    try:
        if pd.isnull(dt):
            return ""
    except Exception:
        pass
    try:
        if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_hmo = dt.astimezone(TZ_HERMOSILLO)
        return dt_hmo.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(dt)[:16]

def limpiar_valor(valor) -> float:
    if valor is None:
        return 0.0
    if isinstance(valor, bool):
        return 1.0 if valor else 0.0
    if isinstance(valor, (int, float)):
        try:
            return 0.0 if pd.isna(valor) else float(valor)
        except (TypeError, ValueError):
            return 0.0
    try:
        s = str(valor).strip()
        if not s or s in ("-", "—", "–", "N/A", "n/a", "NA", "na", "None", "null"):
            return 0.0
        s = s.replace('%','').replace('$','').replace(',','').replace(' ','')
        return float(s)
    except (ValueError, TypeError):
        return 0.0

def normalizar_nombre(nombre) -> str:
    s = str(nombre).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'\s+', ' ', s)
    return s

def normalizar_dataframe(df: pd.DataFrame, columnas_esperadas: list,
                         cols_criticas: set = None) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=columnas_esperadas)
    df = df.copy()
    cols_en_sheet  = set(df.columns)
    cols_faltantes = [c for c in columnas_esperadas if c not in cols_en_sheet]
    if cols_criticas:
        faltantes_criticas = set(cols_faltantes) & cols_criticas
        if faltantes_criticas:
            import streamlit as st
            st.warning(
                f"⚠️ Columnas críticas no encontradas en el Sheet: {sorted(faltantes_criticas)}."
            )
    for col in cols_faltantes:
        df[col] = None
    return df[columnas_esperadas]

def _proyectar_tendencia(df_ventas: pd.DataFrame, meses_futuros: int = 6) -> pd.DataFrame:
    """Devuelve un DataFrame con ventas mensuales reales + proyección lineal."""
    if df_ventas.empty:
        return pd.DataFrame()
    df_v2 = df_ventas.copy()
    df_v2["Mes_num"] = df_v2["Mes"].apply(limpiar_valor).astype(int)
    df_v2["Año_num"] = df_v2["Año"].apply(limpiar_valor).astype(int)
    df_v2 = df_v2[(df_v2["Mes_num"] > 0) & (df_v2["Año_num"] > 0)]
    df_mensual = (
        df_v2.groupby(["Año_num","Mes_num"])["Venta_Diaria"]
        .sum()
        .reset_index()
        .sort_values(["Año_num","Mes_num"])
        .reset_index(drop=True)
    )
    df_mensual["idx"] = range(len(df_mensual))
    df_mensual["tipo"] = "real"
    if len(df_mensual) < 2:
        return df_mensual
    x = df_mensual["idx"].values.astype(float)
    y = df_mensual["Venta_Diaria"].values.astype(float)
    coef = np.polyfit(x, y, 1)
    poly = np.poly1d(coef)
    last_idx  = int(df_mensual["idx"].max())
    last_año  = int(df_mensual["Año_num"].iloc[-1])
    last_mes  = int(df_mensual["Mes_num"].iloc[-1])
    proyecciones = []
    for i in range(1, meses_futuros + 1):
        mes_abs = last_mes - 1 + i
        fut_mes = (mes_abs % 12) + 1
        fut_año = last_año + (mes_abs // 12)
        proyecciones.append({
            "Año_num": fut_año, "Mes_num": fut_mes,
            "idx": last_idx + i,
            "Venta_Diaria": max(0.0, float(poly(last_idx + i))),
            "tipo": "proyección"
        })
    df_proyecciones = pd.DataFrame(proyecciones)
    return pd.concat([df_mensual, df_proyecciones], ignore_index=True)
