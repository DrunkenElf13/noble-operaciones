import pandas as pd
import unicodedata
import re
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
