COLS_INSUMOS = [
    "Unidad de Negocio", "Nombre del Insumo", "Marca", "Proveedor", "Grupo",
    "Espacio_1", "Presentación de Compra", "Unidad de Medida",
    "Espacio_2", "Espacio_3", "Espacio_4", "Stock Mínimo",
    "Espacio_5", "Espacio_6", "Espacio_7", "Espacio_8", "Tara", "Activo",
]
COLS_HISTORIAL = [
    "Unidad de Negocio", "Nombre del Insumo", "Marca", "Proveedor", "Grupo",
    "Fecha de Entrada", "Presentación de Compra", "Unidad de Medida",
    "Alm", "Barra", "Stock Neto", "Stock Mínimo", "¿Comprar?",
    "Responsable", "Fecha de Inventario", "Tara", "Observaciones",
]
COLS_ACCESOS = ["Clave", "Nombre", "Rol"]
COLS_AVISOS  = ["ID", "Título", "Mensaje", "Tipo", "Activo", "Fecha", "Autor", "Pagina"]
COLS_VENTAS  = [
    "Unidad", "Fecha", "Día", "Mes", "Año",
    "Efectivo", "Transferencias", "Tarjeta", "Total_POS",
    "Uber_Eats", "Rappi", "Venta_Diaria",
    "Tickets_POS", "Tickets_Uber", "Tickets_Rappi", "Total_Tickets",
    "Ticket_Promedio", "Meta_Mensual", "Dias_Habiles", "Meta_Diaria",
    "Responsable", "Notas", "Canal",
]
COLS_GASTOS = [
    "ID", "Fecha", "Periodo", "Tipo", "Categoria", "Concepto",
    "Monto", "Responsable", "Notas"
]
COLS_PRESUPUESTO = [
    "Año", "Mes", "Meta_Total", "Meta_POS", "Meta_Uber", "Meta_Rappi",
    "Meta_CoffeeStation", "Meta_ToGo", "Notas"
]
COLS_BASE_COSTOS = [
    "Producto", "Ingrediente", "Marca", "Proveedor", "Unidad_Medida",
    "Presentacion", "Costo_Total", "Costo_Unitario", "Unidad_Costo",
    "Precio_Venta", "Food_Cost_Pct", "Fecha_Captura", "Responsable"
]
COLS_MERMA = [
    "ID", "Fecha", "Producto", "Ingrediente", "Cantidad", "Unidad_Medida",
    "Motivo", "Comentarios", "Costo_Unitario", "Costo_Total", "Responsable"
]
COLS_COSTOS_INSUMOS = [
    "Nombre_Insumo", "Marca", "Proveedor", "Unidad_Medida", "Presentacion",
    "Costo_Presentacion", "Costo_Unitario", "Unidad_Costo", "Fecha_Captura", "Responsable"
]
COLS_RECETAS = [
    "Receta", "Ingrediente", "Cantidad", "Unidad_Medida", "Costo_Ingrediente",
    "Precio_Venta", "Food_Cost_Pct", "Fecha_Captura", "Responsable"
]
COLS_CALENDARIO = [
    "ID", "Fecha", "Tipo", "Título", "Cliente", "Contacto",
    "Ubicacion", "Descripcion", "Total_Cotizado", "Adeudo",
    "Metodo_Pago", "Fecha_Contratacion", "Fecha_Entrega",
    "Abonos", "Notas", "Color", "Responsable", "Anticipo", "Fecha_Fin"
]
COLS_PERMISOS = ["Rol", "Pagina"]

COLS_CRITICAS_INSUMOS   = {"Nombre del Insumo", "Grupo", "Stock Mínimo"}
COLS_CRITICAS_HISTORIAL = {"Nombre del Insumo", "Alm", "Barra", "Fecha de Inventario"}

GRUPOS       = ["A", "B", "C", "D", "E", "F", "G"]
UNIDADES     = ["Noble", "Coffee Station"]
UNIDADES_MED = ["pz", "ml", "gr", "kg", "lt"]

CANALES_VENTA = ["Noble", "Coffee Station", "Noble To Go"]

SPREADSHEET_ID = "1VZV81p-JqoaRPzMzsRurF6wntVefyaN5ozs3RJe6uJs"
