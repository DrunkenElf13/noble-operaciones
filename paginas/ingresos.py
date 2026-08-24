import streamlit as st
import pandas as pd
import time
import data_loaders as dl

from inventario import obtener_ultimo_inventario, buscar_insumo_en_actual, construir_fila_historial
from sheets import safe_worksheet, sh, append_rows_con_retry, _asegurar_hoja_costos_insumos
from utils import limpiar_valor, ts_hermosillo
from config import UNIDADES, UNIDADES_MED
from components.avisos import mostrar_avisos
from auth import tiene_permiso


def _guardar_costos(filas_costos: list, r_sel: str):
    """
    Registra costos en la hoja CostosInsumos.
    filas_costos: lista de dicts con:
        nombre, marca, proveedor, unidad_medida, presentacion,
        costo_presentacion, costo_unitario, unidad_base,
        contenido_base_por_unidad, costo_base_unitario
    Devuelve (ok, mensaje).
    """
    if not filas_costos:
        return True, "Sin costos para registrar."

    ws_costos, err_costos = _asegurar_hoja_costos_insumos()
    if err_costos:
        return False, f"No se pudo acceder a la hoja CostosInsumos: {err_costos}"

    try:
        fecha_captura = ts_hermosillo()
        filas_listas = []
        for costo in filas_costos:
            nombre = costo.get("nombre", "")
            costo_presentacion = costo.get("costo_presentacion", 0.0)
            costo_unitario = costo.get("costo_unitario", 0.0)
            unidad_medida = costo.get("unidad_medida", "pz")
            unidad_base = costo.get("unidad_base", unidad_medida)
            contenido_base = costo.get("contenido_base_por_unidad", 0.0)
            costo_base = costo.get("costo_base_unitario", 0.0)

            # Si no se proporcionó costo unitario manual, se calcula automáticamente
            if costo_unitario <= 0 and costo_presentacion > 0 and costo.get("cantidad_neta", 0) > 0:
                costo_unitario = round(costo_presentacion / costo["cantidad_neta"], 4)

            # ✅ VALIDACIÓN NUEVA: conversión de unidades
            if unidad_base != unidad_medida:
                if contenido_base <= 0:
                    return False, f"Para {nombre}, debes indicar cuántas unidades de {unidad_base} contiene 1 {unidad_medida}."
                if costo_base <= 0:
                    costo_base = round(costo_unitario / contenido_base, 6)
            else:
                contenido_base = 1.0
                if costo_base <= 0:
                    costo_base = costo_unitario

            unidad_costo = f"$/{unidad_medida}"

            filas_listas.append([
                nombre,
                costo.get("marca", ""),
                costo.get("proveedor", ""),
                unidad_medida,
                costo.get("presentacion", ""),
                costo_presentacion,
                costo_unitario,
                unidad_costo,
                unidad_base,
                contenido_base,
                costo_base,
                fecha_captura,
                r_sel
            ])

        ok, msg = append_rows_con_retry(ws_costos, filas_listas)
        if ok:
            dl.cargar_costos_insumos.clear()
            return True, f"{len(filas_listas)} costo(s) registrado(s) correctamente."
        return False, msg
    except Exception as e:
        return False, f"Error al registrar costos: {e}"
def show_ingresos():
    if not tiene_permiso("Ingresos"):
        st.error("No tienes permiso para esta página.")
        st.stop()
    try:
        df_raw, df_historial = dl.cargar_datos_integrales()
    except Exception as e:
        st.error(f"Error al cargar los datos: {e}")
        st.stop()
    st.title("📥 Entrada de compras")
    mostrar_avisos("Ingresos")
    if not st.session_state.auth_status:
        st.error("🔒 Autenticación requerida.")
        st.stop()
    st.info("Ingresa insumos recibidos. Se sumarán al último stock de Almacén registrado.")

    col_u, col_r = st.columns(2)
    with col_u:
        u_sel = st.selectbox("🏢 Unidad receptora:", UNIDADES)
    responsables = st.session_state.responsables or ["Raúl"]
    resp_idx = responsables.index(st.session_state.current_user) if st.session_state.current_user in responsables else 0
    with col_r:
        r_sel = st.selectbox("👤 Responsable:", responsables, index=resp_idx,
                             disabled=(st.session_state.user_role != "admin"))

    df_u = df_raw[df_raw["Unidad de Negocio"] == u_sel] if not df_raw.empty else pd.DataFrame()
    if df_u.empty:
        st.warning("Sin insumos registrados para esta unidad.")
        st.stop()

    df_actual    = obtener_ultimo_inventario(df_historial, u_sel)
    nombres_ins  = df_u["Nombre del Insumo"].dropna().unique().tolist()

    st.divider()
    modo_bulk = st.toggle("🚀 Activar Ingreso Masivo Rápido (Bulk)")

    if modo_bulk:
        st.subheader("Carga Bulk")
        bulk_data = []
        for _, r in df_u.iterrows():
            nom = r["Nombre del Insumo"]
            prev = buscar_insumo_en_actual(df_actual, nom)
            # Sugerencia automática de unidad base según unidad de inventario
            unidad_inv = str(r.get("Unidad de Medida", "pz")).lower()
            if unidad_inv in ["pz", "paquete"]:
                default_base = "pieza"
            elif unidad_inv == "kg":
                default_base = "gr"
            elif unidad_inv == "lt":
                default_base = "ml"
            else:
                default_base = unidad_inv

            bulk_data.append({
                "Insumo": nom,
                "Stock Alm": limpiar_valor(prev["Alm"]) if prev is not None else 0.0,
                "Stock Barra": limpiar_valor(prev["Barra"]) if prev is not None else 0.0,
                "+ Ingreso": 0.0,
                "Costo Presentación": 0.0,
                "Unidad Base": default_base,
                "Contenido Base": 0.0,
                "row": r,
                "prev": prev,
            })

        df_edit = pd.DataFrame(bulk_data)
        edited_df = st.data_editor(
            df_edit[["Insumo", "Stock Alm", "Stock Barra", "+ Ingreso",
                     "Costo Presentación", "Unidad Base", "Contenido Base"]],
            hide_index=True,
            width="stretch",
            disabled=["Insumo", "Stock Alm", "Stock Barra"],
            column_config={
                "Insumo": st.column_config.TextColumn(disabled=True),
                "Stock Alm": st.column_config.NumberColumn(disabled=True),
                "Stock Barra": st.column_config.NumberColumn(disabled=True),
                "+ Ingreso": st.column_config.NumberColumn(min_value=0.0, step=1.0),
                "Costo Presentación": st.column_config.NumberColumn(
                    min_value=0.0, step=0.5,
                    help="Costo total pagado por la presentación recibida. Deja en 0 para omitir costo."
                ),
                "Unidad Base": st.column_config.SelectboxColumn(
                    options=UNIDADES_MED,
                    help="Unidad que usarás en recetas (ml, gr, pieza, paquete, etc.)"
                ),
                "Contenido Base": st.column_config.NumberColumn(
                    min_value=0.0, step=1.0,
                    help="Cuántas unidades base hay en 1 unidad de inventario. Ej: 1 paquete = 100 piezas"
                )
            }
        )

        proc_bulk = st.session_state.get("_procesando_bulk", False)
        btn_bulk  = st.button("📦 EJECUTAR INGRESO BULK", type="primary", disabled=proc_bulk)

        if btn_bulk and not proc_bulk:
            st.session_state["_procesando_bulk"] = True
            ws_his, err = safe_worksheet(sh, "Historial")
            if err:
                st.error(err)
                st.session_state["_procesando_bulk"] = False
            else:
                fh = ts_hermosillo()
                filas_bulk = []
                filas_costos_bulk = []
                for _, r_ed in edited_df.iterrows():
                    ingreso = limpiar_valor(r_ed["+ Ingreso"])
                    if ingreso <= 0:
                        continue

                    nom  = r_ed["Insumo"]
                    orig = next((x for x in bulk_data if x["Insumo"] == nom), None)
                    if orig is None:
                        continue

                    row_ins = orig["row"]
                    v_min   = limpiar_valor(row_ins.get("Stock Mínimo", 0))
                    tara_bulk = limpiar_valor(row_ins.get("Tara", 0))
                    nuevo_a   = orig["Stock Alm"] + ingreso
                    nuevo_n   = nuevo_a + orig["Stock Barra"]

                    filas_bulk.append(construir_fila_historial(
                        unidad=u_sel, nombre=nom, marca=row_ins.get("Marca", ""),
                        proveedor=row_ins.get("Proveedor", ""), grupo=row_ins.get("Grupo", ""),
                        fecha_entrada=fh, presentacion=row_ins.get("Presentación de Compra", ""),
                        unidad_medida=row_ins.get("Unidad de Medida", "pz"),
                        alm=nuevo_a, barra=orig["Stock Barra"], stock_neto=nuevo_n,
                        stock_minimo=v_min, comprar=nuevo_n < v_min,
                        responsable=r_sel, fecha_inventario="",
                        tara=tara_bulk, observaciones="", cantidad_ingresada=ingreso,
                    ))

                    # Costo opcional desde la columna "Costo Presentación"
                    costo_presentacion_bulk = limpiar_valor(r_ed.get("Costo Presentación", 0.0))
                    if costo_presentacion_bulk > 0:
                        unidad_base_bulk = r_ed.get("Unidad Base", default_base)
                        contenido_base_bulk = limpiar_valor(r_ed.get("Contenido Base", 0.0))
                        filas_costos_bulk.append({
                            "nombre": nom,
                            "marca": row_ins.get("Marca", ""),
                            "proveedor": row_ins.get("Proveedor", ""),
                            "unidad_medida": row_ins.get("Unidad de Medida", "pz"),
                            "presentacion": row_ins.get("Presentación de Compra", ""),
                            "cantidad_neta": ingreso,
                            "costo_presentacion": costo_presentacion_bulk,
                            "costo_unitario": 0.0,
                            "unidad_base": unidad_base_bulk,
                            "contenido_base_por_unidad": contenido_base_bulk,
                            "costo_base_unitario": 0.0,
                        })

                st.session_state["_procesando_bulk"] = False

                if not filas_bulk:
                    st.warning("No ingresaste cantidades mayores a 0.")
                else:
                    ok, msg = append_rows_con_retry(ws_his, filas_bulk)
                    if ok:
                        dl.cargar_datos_integrales.clear()
                        mensaje_final = f"Ingreso masivo registrado: {len(filas_bulk)} refs. {msg}"

                        if filas_costos_bulk:
                            ok_costos, msg_costos = _guardar_costos(filas_costos_bulk, r_sel)
                            if ok_costos:
                                mensaje_final += f" | {msg_costos}"
                            else:
                                st.warning(f"Inventario guardado, pero no se pudo registrar costos: {msg_costos}")

                        st.success(mensaje_final)
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)
    else:
        insumos_llegados = st.multiselect("🔍 Insumos recibidos:", sorted(nombres_ins))
        if insumos_llegados:
            regs_ingreso = {}
            st.divider()
            h1, h2, h3, h4, h5 = st.columns([3, 2, 1.5, 1.5, 2])
            for col, label in zip([h1, h2, h3, h4, h5],
                                  ["Insumo", "Stock Ant (Alm+Bar)", "+ Cantidad", "Tara", "= Nuevo Total"]):
                col.write(f"**{label}**")
            st.divider()

            for i, nom in enumerate(insumos_llegados):
                row_matches = df_u[df_u["Nombre del Insumo"] == nom]
                if row_matches.empty:
                    continue

                row_ins  = row_matches.iloc[0]
                prev     = buscar_insumo_en_actual(df_actual, nom)
                v_a_prev = limpiar_valor(prev["Alm"])   if prev is not None else 0.0
                v_b_prev = limpiar_valor(prev["Barra"]) if prev is not None else 0.0
                v_min    = limpiar_valor(row_ins.get("Stock Mínimo", 0))

                c1, c2, c3, c4, c5 = st.columns([3, 2, 1.5, 1.5, 2])
                with c1:
                    st.write(f"**{nom}**")
                    st.caption(f"Marca: {row_ins.get('Marca', '-')} | Prov: {row_ins.get('Proveedor', '-')}")
                with c2:
                    st.write(f"Almacén: {v_a_prev} | Barra: {v_b_prev}")
                    st.write(f"**Total Ant: {v_a_prev + v_b_prev}**")
                with c3:
                    cant_ingreso = st.number_input(
                        "Ingreso", min_value=0.0, step=1.0, value=None,
                        key=f"ing_{i}", label_visibility="collapsed", placeholder="0"
                    )
                    cant_ingreso = cant_ingreso if cant_ingreso is not None else 0.0
                with c4:
                    tara_ingreso = st.number_input(
                        "Tara", min_value=0.0, step=0.1, value=None,
                        key=f"tara_ing_{i}", label_visibility="collapsed", placeholder="tara"
                    )
                    tara_ingreso = tara_ingreso if tara_ingreso is not None else 0.0
                with c5:
                    cant_neta  = max(0.0, cant_ingreso - tara_ingreso)
                    nuevo_alm  = v_a_prev + cant_neta
                    nuevo_neto = nuevo_alm + v_b_prev
                    st.success(f"**{nuevo_neto:.1f}**")

                # --- Sección opcional de costo ---
                col_costo = st.columns([1, 1, 1, 1])
                with col_costo[0]:
                    registrar_costo = st.checkbox(
                        "💰 Registrar costo",
                        key=f"reg_costo_{i}",
                        help="Activa para guardar el costo de esta compra en CostosInsumos."
                    )
                with col_costo[1]:
                    costo_presentacion = st.number_input(
                        "Costo Presentación ($)",
                        min_value=0.0, step=0.5, value=0.0,
                        key=f"costo_pres_{i}",
                        help="Costo total pagado por la presentación recibida."
                    )
                with col_costo[2]:
                    costo_unitario_manual = st.number_input(
                        "Costo Unitario (opcional)",
                        min_value=0.0, step=0.001, value=0.0,
                        key=f"costo_unit_{i}",
                        help="Si dejas 0, se calculará automáticamente con la cantidad neta recibida."
                    )

                if registrar_costo:
                    col_costo2 = st.columns([1, 1, 1, 1])
                    with col_costo2[0]:
                        unidad_inv = str(row_ins.get("Unidad de Medida", "pz")).lower()
                        if unidad_inv in ["pz", "paquete"]:
                            default_base = "pieza"
                        elif unidad_inv == "kg":
                            default_base = "gr"
                        elif unidad_inv == "lt":
                            default_base = "ml"
                        else:
                            default_base = unidad_inv

                        unidad_base = st.selectbox(
                            "Unidad base para recetas",
                            UNIDADES_MED,
                            index=UNIDADES_MED.index(default_base) if default_base in UNIDADES_MED else 0,
                            key=f"unidad_base_{i}",
                            help="Unidad en la que usarás el insumo en recetas (ml, gr, pieza, paquete, etc.)"
                        )
                    with col_costo2[1]:
                        contenido_base = st.number_input(
                            f"Contenido en {unidad_base} por unidad",
                            min_value=0.0, step=1.0, value=0.0,
                            key=f"contenido_base_{i}",
                            help=f"Cuántas unidades de {unidad_base} hay en 1 unidad de inventario. Ej: 1 paquete = 100 piezas"
                        )
                    with col_costo2[2]:
                        costo_base_manual = st.number_input(
                            f"Costo base unitario ($/{unidad_base}) (opcional)",
                            min_value=0.0, step=0.0001, value=0.0,
                            key=f"costo_base_{i}",
                            format="%.6f",
                            help="Si dejas 0, se calculará automáticamente."
                        )
                else:
                    unidad_base = str(row_ins.get("Unidad de Medida", "pz")).lower()
                    contenido_base = 0.0
                    costo_base_manual = 0.0

                regs_ingreso[nom] = {
                    "nuevo_a": nuevo_alm,
                    "b": v_b_prev,
                    "nuevo_n": nuevo_neto,
                    "row": row_ins,
                    "min": v_min,
                    "tara": tara_ingreso,
                    "cant_ingreso": cant_ingreso,
                    "cant_neta": cant_neta,
                    "registrar_costo": registrar_costo,
                    "costo_presentacion": costo_presentacion,
                    "costo_unitario_manual": costo_unitario_manual,
                    "unidad_base": unidad_base,
                    "contenido_base": contenido_base,
                    "costo_base_manual": costo_base_manual,
                }
                st.divider()

            proc_ing = st.session_state.get("_procesando_ingreso", False)
            btn_ing  = st.button("📦 EJECUTAR INGRESO", width="stretch", type="primary", disabled=proc_ing)

            if btn_ing and not proc_ing:
                st.session_state["_procesando_ingreso"] = True
                ws_his, err = safe_worksheet(sh, "Historial")
                if err:
                    st.error(err)
                    st.session_state["_procesando_ingreso"] = False
                else:
                    fh    = ts_hermosillo()
                    filas = []
                    filas_costos = []
                    for n, info in regs_ingreso.items():
                        dm = info["row"]

                        filas.append(construir_fila_historial(
                            unidad=u_sel, nombre=n, marca=dm.get("Marca", ""),
                            proveedor=dm.get("Proveedor", ""), grupo=dm.get("Grupo", ""),
                            fecha_entrada=fh, presentacion=dm.get("Presentación de Compra", ""),
                            unidad_medida=dm.get("Unidad de Medida", "pz"),
                            alm=info["nuevo_a"], barra=info["b"], stock_neto=info["nuevo_n"],
                            stock_minimo=info["min"], comprar=info["nuevo_n"] < info["min"],
                            responsable=r_sel, fecha_inventario="", tara=info["tara"],
                            observaciones="", cantidad_ingresada=info["cant_ingreso"],
                        ))

                        if info["registrar_costo"] and info["costo_presentacion"] > 0:
                            filas_costos.append({
                                "nombre": n,
                                "marca": dm.get("Marca", ""),
                                "proveedor": dm.get("Proveedor", ""),
                                "unidad_medida": dm.get("Unidad de Medida", "pz"),
                                "presentacion": dm.get("Presentación de Compra", ""),
                                "cantidad_neta": info["cant_neta"],
                                "costo_presentacion": info["costo_presentacion"],
                                "costo_unitario": info["costo_unitario_manual"],
                                "unidad_base": info["unidad_base"],
                                "contenido_base_por_unidad": info["contenido_base"],
                                "costo_base_unitario": info["costo_base_manual"],
                            })

                    ok, msg = append_rows_con_retry(ws_his, filas)
                    st.session_state["_procesando_ingreso"] = False

                    if ok:
                        dl.cargar_datos_integrales.clear()
                        mensaje_final = f"Ingreso registrado. {msg}"

                        if filas_costos:
                            ok_costos, msg_costos = _guardar_costos(filas_costos, r_sel)
                            if ok_costos:
                                mensaje_final += f" | {msg_costos}"
                            else:
                                st.warning(f"Inventario guardado, pero no se pudo registrar costos: {msg_costos}")

                        st.success(mensaje_final)
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(msg)
