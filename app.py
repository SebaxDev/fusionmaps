import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster, HeatMap, FeatureGroupSubGroup
from geopy.geocoders import Nominatim

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Mapa de Clientes - Fusion", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# CONFIGURACIÓN DE CONEXIÓN Y UBICACIÓN BASE
# ==========================================
SHEET_ID = "13R_3Mdr25Jd-nGhK7CxdcbKkFWLc0LPdYrOLOY8sZJo"

WORKSHEET_CLIENTES = "Clientes"
WORKSHEET_RECLAMOS = "Reclamos"
WORKSHEET_USUARIOS = "usuarios"

# 📍 UBICACIÓN DE TU OFICINA (Nuevo punto 2.3 / Ajuste de vista)
OFICINA_LAT = -26.538165
OFICINA_LON = -59.341487
ZOOM_INICIAL = 15  # Zoom de cerca (12 era muy lejos, 15 es nivel de calles)

# --- CONEXIÓN CON GOOGLE SHEETS ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource(show_spinner="Conectando a la base de datos...")
def init_google_sheets():
    try:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=SCOPES
        )
        client = gspread.authorize(creds)
        
        ws_clientes = client.open_by_key(SHEET_ID).worksheet(WORKSHEET_CLIENTES)
        ws_reclamos = client.open_by_key(SHEET_ID).worksheet(WORKSHEET_RECLAMOS)
        ws_usuarios = client.open_by_key(SHEET_ID).worksheet(WORKSHEET_USUARIOS)
        
        return ws_clientes, ws_reclamos, ws_usuarios
    except Exception as e:
        st.error(f"Error de conexión con Google Sheets: {e}")
        st.stop()

# --- CARGA Y PROCESAMIENTO DE DATOS ---
@st.cache_data(ttl=600)
def cargar_datos():
    ws_clientes, ws_reclamos, ws_usuarios = init_google_sheets()
    
    df_clientes = pd.DataFrame(ws_clientes.get_all_records())
    df_reclamos = pd.DataFrame(ws_reclamos.get_all_records())
    df_usuarios = pd.DataFrame(ws_usuarios.get_all_records())
    
    rename_dict = {
        'Nº Cliente': 'nro_cliente', 'Sector': 'sector', 'Nombre': 'nombre',
        'Dirección': 'direccion', 'Teléfono': 'telefono', 'N° de Precinto': 'precinto',
        'ID Cliente': 'id_cliente', 'Última Modificación': 'ult_mod',
        'Anotaciones': 'anotaciones', 'Latitud': 'lat', 'Longitud': 'lon'
    }
    
    existing_cols = {k: v for k, v in rename_dict.items() if k in df_clientes.columns}
    df_c = df_clientes.rename(columns=existing_cols)
    
    df_c['nro_cliente'] = df_c['nro_cliente'].astype(str)
    
    df_c['lat'] = df_c['lat'].replace(['*', '', ' '], None)
    df_c['lon'] = df_c['lon'].replace(['*', '', ' '], None)
    df_c['lat'] = pd.to_numeric(df_c['lat'].astype(str).str.replace(',', '.'), errors='coerce')
    df_c['lon'] = pd.to_numeric(df_c['lon'].astype(str).str.replace(',', '.'), errors='coerce')

    df_mapa = df_c.dropna(subset=['lat', 'lon']).copy()

    df_reclamos['Nº Cliente'] = df_reclamos['Nº Cliente'].astype(str)
    reclamos_activos = df_reclamos[df_reclamos['Estado'] != 'Resuelto']['Nº Cliente'].unique()
    
    df_mapa['color'] = df_mapa['nro_cliente'].apply(
        lambda x: 'red' if x in reclamos_activos else 'green'
    )

    # Devolvemos también df_reclamos completo para el panel de detalle
    return df_c, df_mapa, df_usuarios, df_reclamos, reclamos_activos

# --- SISTEMA DE LOGIN ---
def login_screen():
    st.title("🔒 Acceso a Plataforma Fusion Mapas")
    st.write("Ingresá tus credenciales para acceder al mapa.")
    
    with st.form("login_form"):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submit = st.form_submit_button("Ingresar")
        
        if submit:
            try:
                _, _, df_usuarios, _, _ = cargar_datos()
                user_row = df_usuarios[(df_usuarios['username'] == username) & (df_usuarios['password'] == password)]
                if not user_row.empty:
                    st.session_state["authenticated"] = True
                    st.session_state["user_name"] = user_row.iloc[0]['nombre']
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
            except Exception as e:
                st.error(f"Error al cargar datos de usuarios: {e}")

# ========================================================
# NUEVO: Panel de Estadísticas (Punto 2.2)
# ========================================================
def mostrar_estadisticas(df_completo, df_mapa, reclamos_activos):
    st.markdown("### 📊 Resumen General")
    col1, col2, col3, col4 = st.columns(4)
    
    total_clientes = len(df_completo)
    con_coords = len(df_mapa)
    sin_coords = total_clientes - con_coords
    total_reclamos = len(reclamos_activos)
    
    with col1:
        st.metric("👥 Total Clientes", total_clientes)
    with col2:
        st.metric("📍 En el Mapa", con_coords)
    with col3:
        st.metric("❌ Sin Coordenadas", sin_coords, delta=f"{sin_coords} pendientes", delta_color="inverse")
    with col4:
        st.metric("🔴 Reclamos Activos", total_reclamos, delta=None if total_reclamos == 0 else "Requiere atención", delta_color="inverse")
    st.divider()

# ========================================================
# NUEVO: Panel de Detalle Lateral (Punto 2.1)
# ========================================================
def mostrar_panel_detalle(cliente, df_reclamos):
    st.subheader(f"📋 {cliente['nombre']}")
    st.markdown(f"**Nº Cliente:** {cliente['nro_cliente']}")
    st.markdown(f"**Sector:** {cliente['sector']}")
    st.markdown(f"**Dirección:** {cliente['direccion']}")
    st.markdown(f"**Teléfono:** {cliente['telefono']}")
    st.markdown(f"**Precinto:** {cliente['precinto']}")
    st.markdown(f"**Últ. Modificación:** {cliente.get('ult_mod', 'N/A')}")
    
    st.divider()
    st.subheader("📝 Anotaciones")
    anotacion = str(cliente.get('anotaciones', ''))
    st.info(anotacion if anotacion and anotacion != 'nan' else "Sin anotaciones registradas.")
    
    st.divider()
    st.subheader("🔧 Historial de Reclamos")
    # Buscar los reclamos de este cliente
    reclamos_cliente = df_reclamos[df_reclamos['Nº Cliente'] == str(cliente['nro_cliente'])]
    
    if not reclamos_cliente.empty:
        # Mostrar como una lista visual en lugar de tabla para ahorrar espacio lateral
        for _, r in reclamos_cliente.iterrows():
            estado = r.get('Estado', 'Desconocido')
            icono = "🔴" if estado != "Resuelto" else "✅"
            st.markdown(f"{icono} **{r.get('Motivo', r.get('Descripción', 'Sin detalle'))}** - *Estado: {estado}*")
    else:
        st.success("✅ Sin reclamos registrados.")

# --- APLICACIÓN PRINCIPAL ---
def main_app():
    st.title("🗺️ Mapa Interactivo de Clientes - Fusion")
    
    with st.sidebar:
        st.write(f"👤 **{st.session_state.user_name}**")
        if st.button("🔄 Actualizar datos"):
            st.cache_data.clear()
            st.rerun()
        if st.button("🚪 Cerrar sesión"):
            st.session_state.authenticated = False
            st.rerun()
        st.divider()

    try:
        df_completo, df_mapa, _, df_reclamos, reclamos_activos = cargar_datos()
    except Exception as e:
        st.error(f"Error al cargar los datos: {e}")
        st.stop()

    ws_clientes, _, _ = init_google_sheets()
    
    # --- DASHBOARD DE ESTADÍSTICAS (Punto 2.2) ---
    mostrar_estadisticas(df_completo, df_mapa, reclamos_activos)
    
    # --- SIDEBAR Filtros ---
    st.sidebar.header("Filtros y Búsqueda")
    sectores_disponibles = sorted(df_completo['sector'].dropna().unique().tolist())
    sector_seleccionado = st.sidebar.selectbox("Filtrar por Sector", ["Todos"] + sectores_disponibles)
    id_busqueda = st.sidebar.text_input("🔍 Buscar Nº de Cliente")
    
    df_filtrado = df_mapa.copy()
    
    if sector_seleccionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['sector'] == sector_seleccionado]
        
    cliente_encontrado = None
    mensaje_estado = ""
    
    if id_busqueda:
        resultado_busqueda = df_completo[df_completo['nro_cliente'] == id_busqueda]
        
        if resultado_busqueda.empty:
            mensaje_estado = "⚠️ El cliente no existe en la base de datos."
            df_filtrado = pd.DataFrame() 
        else:
            cliente_encontrado = resultado_busqueda.iloc[0]
            if pd.isna(cliente_encontrado['lat']) or pd.isna(cliente_encontrado['lon']):
                mensaje_estado = "📍 El cliente existe, pero **NO tiene coordenadas** registradas."
                df_filtrado = pd.DataFrame() 
            else:
                mensaje_estado = "✅ Cliente encontrado y centrado en el mapa."
                df_filtrado = resultado_busqueda[resultado_busqueda['lat'].notna()] 

    if mensaje_estado:
        st.sidebar.info(mensaje_estado)
        
    # --- ASISTENTE DE GEOLOCALIZACIÓN ---
    if id_busqueda and cliente_encontrado is not None and (pd.isna(cliente_encontrado['lat']) or pd.isna(cliente_encontrado['lon'])):
        st.sidebar.markdown("### 🛠️ Asistente de Ubicación")
        direccion_actual = cliente_encontrado['direccion']
        dir_input = st.sidebar.text_input("Ingresá la dirección para buscar coordenadas:", value=str(direccion_actual))
        
        if st.sidebar.button("Buscar Coordenadas"):
            with st.sidebar.spinner("Buscando ubicación..."):
                try:
                    geolocator = Nominatim(user_agent="fusion_map_app")
                    location = geolocator.geocode(f"{dir_input}, Chaco, Argentina") 
                    if location:
                        st.sidebar.success(f"¡Encontrado! Lat: {location.latitude:.6f}, Lon: {location.longitude:.6f}")
                        st.session_state.found_lat = location.latitude
                        st.session_state.found_lon = location.longitude
                        st.session_state.found_id = id_busqueda
                    else:
                        st.sidebar.error("No se encontraron coordenadas para esa dirección.")
                except Exception as e:
                    st.sidebar.error(f"Error en la búsqueda: {e}")

        if 'found_lat' in st.session_state and st.session_state.get('found_id') == id_busqueda:
            if st.sidebar.button("💾 Guardar en Google Sheets"):
                with st.sidebar.spinner("Guardando..."):
                    try:
                        cell = ws_clientes.find(st.session_state.found_id)
                        if cell:
                            fila = cell.row
                            
                            # ========================================================
                            # MEJORA Punto 1.5: Escritura batch (1 sola llamada API)
                            # ========================================================
                            ws_clientes.update(
                                values=[[st.session_state.found_lat, st.session_state.found_lon]],
                                range_name=f'J{fila}:K{fila}'
                            )
                            
                            st.sidebar.success("¡Guardado! Hacé clic en 'Actualizar datos'.")
                            st.cache_data.clear() 
                            if 'found_lat' in st.session_state: del st.session_state.found_lat
                            if 'found_lon' in st.session_state: del st.session_state.found_lon
                            if 'found_id' in st.session_state: del st.session_state.found_id
                        else:
                            st.sidebar.error("No se encontró la fila en Sheets.")
                    except Exception as e:
                        st.sidebar.error(f"Error al guardar: {e}")

    # --- LAYOUT PRINCIPAL: Mapa y Panel de Detalle ---
    # Creamos 2 columnas: 75% para el mapa, 25% para el panel de detalle (Punto 2.1)
    col_mapa, col_detalle = st.columns([3, 1], gap="small")

    with col_mapa:
        if not df_filtrado.empty:
            # Si buscaste un cliente, centrar ahí. Si no, centrar en la OFICINA
            if id_busqueda and not df_filtrado.empty:
                centro = [df_filtrado.iloc[0]['lat'], df_filtrado.iloc[0]['lon']]
                zoom = 16
            else:
                centro = [OFICINA_LAT, OFICINA_LON] # 📍 Ubicación de tu oficina
                zoom = ZOOM_INICIAL
                
            # ========================================================
            # MEJORA Punto 2.3: Capas Múltiples y Mapa de Calor
            # ========================================================
            m = folium.Map(location=centro, zoom_start=zoom, tiles=None)
            
            # 1. Capas Base de Mapa (Tiles)
            folium.TileLayer('OpenStreetMap', name='🗺️ Mapa Estándar').add_to(m)
            folium.TileLayer('CartoDB positron', name='⚪ Mapa Claro').add_to(m)
            folium.TileLayer('CartoDB dark_matter', name='⚫ Mapa Oscuro').add_to(m)
            
            # 2. Grupos de Capas (Para prender/apagar marcadores)
            marker_cluster = MarkerCluster(name="Todos los Clientes", show=True).add_to(m)
            
            fg_verde = FeatureGroupSubGroup(marker_cluster, name='🟢 Sin Reclamos')
            m.add_child(fg_verde)
            
            fg_rojo = FeatureGroupSubGroup(marker_cluster, name='🔴 Con Reclamos')
            m.add_child(fg_rojo)
            
            fg_heat = folium.FeatureGroup(name='🔥 Mapa de Calor (Reclamos)', show=False)
            m.add_child(fg_heat)
            
            # 3. Marcador de la Oficina (Para que siempre sepas dónde estás parado)
            folium.Marker(
                location=[OFICINA_LAT, OFICINA_LON],
                popup="<b>🏢 Oficina Fusion</b>",
                tooltip="Mi Oficina",
                icon=folium.Icon(color='black', icon='building', prefix='fa')
            ).add_to(m)

            # 4. Agregar Marcadores de Clientes
            for idx, row in df_filtrado.iterrows():
                html_popup = f"""
                <div style="font-family: Arial; min-width: 200px;">
                    <h4 style="margin:0 0 5px 0;">{row['nombre']}</h4>
                    <b>Nº Cliente:</b> {row['nro_cliente']}<br>
                    <b>Dirección:</b> {row['direccion']}<br>
                    <b>Teléfono:</b> {row['telefono']}<br>
                    <b>Precinto:</b> {row['precinto']}<br>
                </div>
                """
                
                target_group = fg_rojo if row['color'] == 'red' else fg_verde
                
                # Simplificamos el tooltip para poder leerlo fácilmente en el panel lateral
                folium.Marker(
                    location=[row['lat'], row['lon']],
                    popup=folium.Popup(html_popup, max_width=300),
                    tooltip=row['nro_cliente'], 
                    icon=folium.Icon(color=row['color'], icon='user', prefix='fa')
                ).add_to(target_group)
            
            # 5. Mapa de Calor (Solo con los clientes rojos/pendientes)
            reclamos_coords = df_filtrado[df_filtrado['color'] == 'red'][['lat', 'lon']].values.tolist()
            if reclamos_coords:
                HeatMap(reclamos_coords, radius=15, blur=20, max_zoom=13).add_to(fg_heat)
            
            # 6. Control de Capas (El menú para prender/apagar)
            folium.LayerControl(collapsed=False).add_to(m)
            
            # Capturamos el click en el mapa (Punto 2.1)
            map_data = st_folium(m, width=900, height=650, returned_objects=["last_object_clicked"])
            
            st.markdown("**Leyenda:** 🟢 Sin reclamos &nbsp;&nbsp; 🔴 Con reclamo pendiente &nbsp;&nbsp; 🏢 Oficina")
            
        else:
            map_data = None
            if not id_busqueda:
                st.warning("No hay clientes con coordenadas para el filtro seleccionado.")
            elif id_busqueda and cliente_encontrado is not None and (pd.isna(cliente_encontrado['lat']) or pd.isna(cliente_encontrado['lon'])):
                st.info("ℹ️ Este cliente no se muestra en el mapa porque no tiene coordenadas. Usá el asistente en el menú de la izquierda.")

    # ========================================================
    # Punto 2.1: Panel de Detalle Lateral
    # ========================================================
    with col_detalle:
        st.subheader("Detalle de Cliente")
        
        # Verificamos si el usuario hizo click en un marcador
        if map_data and map_data.get("last_object_clicked"):
            tooltip_clickeado = map_data["last_object_clicked"].get("tooltip")
            
            # Si el click fue en un cliente (tiene Nº de cliente de tooltip) y no en la oficina
            if tooltip_clickeado and tooltip_clickeado != "Mi Oficina":
                cliente_sel = df_completo[df_completo['nro_cliente'] == tooltip_clickeado]
                if not cliente_sel.empty:
                    mostrar_panel_detalle(cliente_sel.iloc[0], df_reclamos)
                else:
                    st.info("Hacé clic en un marcador del mapa para ver sus detalles aquí.")
            elif tooltip_clickeado == "Mi Oficina":
                st.markdown("🏢 **Estás en la oficina central.**")
            else:
                st.info("Hacé clic en un marcador del mapa para ver sus detalles aquí.")
        else:
            st.info("👆 Hacé clic en un marcador del mapa para ver sus detalles aquí.")

# --- FLUJO DE EJECUCIÓN ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if st.session_state.authenticated:
    main_app()
else:
    login_screen()