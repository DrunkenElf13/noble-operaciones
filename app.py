import streamlit as st
import threading
import time as _time
import pandas as pd
import numpy as np

# Configuración inicial
st.set_page_config(layout="wide")

# Keepalive
def _keepalive_thread(intervalo_seg: int = 90):
    while True:
        _time.sleep(intervalo_seg)
        _ = _time.time()

def iniciar_keepalive(intervalo_seg: int = 90):
    if not st.session_state.get("_keepalive_iniciado", False):
        hilo = threading.Thread(target=_keepalive_thread, args=(intervalo_seg,), daemon=True, name="streamlit-keepalive")
        hilo.start()
        st.session_state["_keepalive_iniciado"] = True

iniciar_keepalive(intervalo_seg=90)

# Importar módulos propios
from auth import USUARIOS_PIN, LISTA_RESPONSABLES, DF_USUARIOS, tiene_permiso, PERMISOS
from components.sidebar import render_sidebar
from components.avisos import mostrar_avisos
from pages.dashboard import show_dashboard
from pages.inventario_captura import show_inventario
from pages.ingresos import show_ingresos
from pages.consulta import show_consulta
from pages.ventas_registro import show_ventas
from pages.ventas_dashboard import show_dashboard_ventas
from pages.importar_ventas import show_importar_ventas
from pages.impresion import show_impresion
from pages.lista_compra import show_lista_compra
from pages.reporte_stock import show_reporte_stock
from pages.corte_mes import show_corte_mes
from pages.gastos import show_gastos
from pages.presupuesto import show_presupuesto
from pages.base_costos import show_base_costos
from pages.merma import show_merma
from pages.canales import show_canales
from pages.dashboard_financiero import show_dashboard_financiero

# Estado de sesión
_defaults = {
    "auth_status": False,
    "current_user": None,
    "user_role": None,
    "pagina": "Dashboard",
    "ingredientes_receta": [],
    "receta_nombre": "",
    "receta_precio": 0.0,
    "receta_factor": 2.5,
    "receta_modo": "Nueva receta",
    "receta_original": "",
    "inventario_guardado": False,
    "inv_bulk_data": None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if "responsables" not in st.session_state:
    st.session_state.responsables = LISTA_RESPONSABLES if LISTA_RESPONSABLES else ["Raúl"]

def cambiar_pagina(nombre: str):
    st.session_state.pagina = nombre
    st.rerun()

# Renderizar sidebar (incluye autenticación)
render_sidebar()

# Página de bienvenida si no ha iniciado sesión
if not st.session_state.auth_status:
    st.markdown("""
    <div style='text-align: center; padding: 4rem 1rem;'>
        <h1 style='font-size: 2.8rem;'>☕ Noble · Sistema de Gestión</h1>
        <p style='font-size: 1.3rem; color: #666;'>Inventario, Ventas, Finanzas y más</p>
        <hr style='width: 50%; margin: 2rem auto; opacity: 0.3;'>
        <p style='font-size: 1.1rem;'>🔒 Usa el <b>panel lateral</b> para iniciar sesión con tu clave.<br>Si no tienes una, solicítala a tu administrador.</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# Enrutamiento
pagina = st.session_state.pagina
if pagina == "Dashboard":
    if tiene_permiso("Dashboard"):
        show_dashboard()
elif pagina == "Inventario":
    if tiene_permiso("Inventario"):
        show_inventario()
elif pagina == "Ingresos":
    if tiene_permiso("Ingresos"):
        show_ingresos()
elif pagina == "Consulta":
    if tiene_permiso("Consulta"):
        show_consulta()
elif pagina == "Ventas":
    if tiene_permiso("Ventas"):
        show_ventas()
elif pagina == "DashboardVentas":
    if tiene_permiso("DashboardVentas"):
        show_dashboard_ventas()
elif pagina == "ImportarVentas":
    if tiene_permiso("ImportarVentas"):
        show_importar_ventas()
elif pagina == "Impresion":
    if tiene_permiso("Impresion"):
        show_impresion()
elif pagina == "ListaCompra":
    if tiene_permiso("ListaCompra"):
        show_lista_compra()
elif pagina == "ReporteStock":
    if tiene_permiso("ReporteStock"):
        show_reporte_stock()
elif pagina == "CorteMes":
    if tiene_permiso("CorteMes"):
        show_corte_mes()
elif pagina == "RegistrarGasto":
    if tiene_permiso("RegistrarGasto"):
        show_gastos()
elif pagina == "Presupuesto":
    if tiene_permiso("Presupuesto"):
        show_presupuesto()
elif pagina == "BaseCostos":
    if tiene_permiso("BaseCostos"):
        show_base_costos()
elif pagina == "RegistrarMerma":
    if tiene_permiso("RegistrarMerma"):
        show_merma()
elif pagina == "CanalesVenta":
    if tiene_permiso("CanalesVenta"):
        show_canales()
elif pagina == "DashboardFinanciero":
    if tiene_permiso("DashboardFinanciero"):
        show_dashboard_financiero()
