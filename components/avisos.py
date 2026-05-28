import streamlit as st
from data_loaders import cargar_avisos

def mostrar_avisos(pagina: str):
    df_av = cargar_avisos()
    if df_av.empty:
        return
    activos = df_av[df_av["Activo"].astype(str).str.upper() == "TRUE"]
    if activos.empty:
        return
    if "Pagina" in activos.columns:
        activos = activos[(activos["Pagina"] == pagina) | (activos["Pagina"].astype(str).str.strip() == "Todas")]
    if activos.empty:
        return
    ICONOS = {"info":"ℹ️","warning":"⚠️","urgent":"🚨"}
    FNS    = {"info":st.info,"warning":st.warning,"urgent":st.error}
    for _, av in activos.iterrows():
        tipo = str(av.get("Tipo","info")).lower()
        FNS.get(tipo, st.info)(
            f"{ICONOS.get(tipo,'ℹ️')} **{av.get('Título','')}**  \n{av.get('Mensaje','')}"
        )
