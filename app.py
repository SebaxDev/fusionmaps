import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
from geopy.geocoders import Nominatim

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Mapa de Clientes - Fusion", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# CONFIGURACIÓN DE CONEXIÓN (USAR SHEET_ID)
# ==========================================
SHEET_ID = "13R_3Mdr25Jd-nGhK7CxdcbKkFWLc0LPdYrOLOY8sZJo"

# Nombres de las pestañas exactos dentro del archivo
WORKSHEET_CLIENTES = "Clientes"
WORKSHEET_RECLAMOS = "Reclamos"
WORKSHEET_USUARIOS = "usuarios" # Ajustá si tiene mayúsculas

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

# --- CARGA Y PROCESAMIENTO DE DATOS (CON CACHÉ) ---
@st.cache_data(ttl=600)
def cargar_datos():
    ws_clientes, ws_reclamos, ws_usuarios = init_google_sheets()
    
    df_clientes = pd.DataFrame(ws_clientes.get_all_records())
    df_reclamos = pd.DataFrame(ws_reclamos.get_all_records())
    df_usuarios = pd.DataFrame(ws_usuarios.get_all_records())
    
    # Renombrar columnas EXACTAMENTE como están en tu hoja (A-K)
    rename_dict = {
        'Nº Cliente': 'nro_cliente',      # Columna A (El número familiar)
        'Sector': 'sector',                # Columna B
        'Nombre': 'nombre',                # Columna C
        'Dirección': 'direccion',          # Columna D
        'Teléfono': 'telefono',            # Columna E
        'N° de Precinto': 'precinto',      # Columna F (Ojo con el ° vs º)
        'ID Cliente': 'id_cliente',        # Columna G (El hash aleatorio)
        'Última Modificación': 'ult_mod',  # Columna H
        'Anotaciones': 'anotaciones',      # Columna I
        'Latitud': 'lat',                  # Columna J
        'Longitud': 'lon'                  # Columna K
    }
    
    existing_cols = {k: v for k, v in rename_dict.items() if k in df_clientes.columns}
    df_c = df_clientes.rename(columns=existing_cols)
    
    # Asegurar que el Nº Cliente sea string para buscarlo bien
    df_c['nro_cliente'] = df_c['nro_cliente'].astype(str)
    
    # Limpiar coordenadas
    df_c['lat'] = df_c['lat'].replace(['*', '', ' '], None)
    df_c['lon'] = df_c['lon'].replace(['*', '', ' '], None)
    df_c['lat'] = pd.to_numeric(df_c['lat'].astype(str).str.replace(',', '.'), errors='coerce')
    df_c['lon'] = pd.to_numeric(df_c['lon'].astype(str).str.replace(',', '.'), errors='coerce')

    # Filtrar clientes con coordenadas válidas para el mapa
    df_mapa = df_c.dropna(subset=['lat', 'lon']).copy()

    # Lógica de colores: Cruzamos con la hoja Reclamos usando Nº Cliente
    df_reclamos['Nº Cliente'] = df_reclamos['Nº Cliente'].astype(str)
    reclamos_activos = df_reclamos[df_reclamos['Estado'] != 'Resuelto']['Nº Cliente'].unique()
    
    # Si el Nº Cliente está en reclamos activos -> Rojo, sino -> Verde
    df_mapa['color'] = df_mapa['nro_cliente'].apply(
        lambda x: 'red' if x in reclamos_activos else 'green'
    )

    return df_c, df_mapa, df_usuarios

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
                _, _, df_usuarios = cargar_datos()
                user_row = df_usuarios[(df_usuarios['username'] == username) & (df_usuarios['password'] == password)]
                if not user_row.empty:
                    st.session_state["authenticated"] = True
                    st.session_state["user_name"] = user_row.iloc[0]['nombre']
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
            except Exception as e:
                st.error(f"Error al cargar datos de usuarios: {e}")

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
        df_completo, df_mapa, _ = cargar_datos()
    except Exception as e:
        st.error(f"Error al cargar los datos: {e}")
        st.stop()

    ws_clientes, _, _ = init_google_sheets()
    
    # --- SIDEBAR Filtros ---
    st.sidebar.header("Filtros y Búsqueda")
    
    sectores_disponibles = sorted(df_completo['sector'].dropna().unique().tolist())
    sector_seleccionado = st.sidebar.selectbox("Filtrar por Sector", ["Todos"] + sectores_disponibles)
    
    # Buscador por Nº de Cliente (El número familiar)
    id_busqueda = st.sidebar.text_input("🔍 Buscar Nº de Cliente")
    
    df_filtrado = df_mapa.copy()
    
    if sector_seleccionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['sector'] == sector_seleccionado]
        
    cliente_encontrado = None
    mensaje_estado = ""
    
    if id_busqueda:
        # Buscamos usando la columna renombrada 'nro_cliente'
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
        
    # --- ASISTENTE DE GEOLOCALIZACIÓN (Idea 6) ---
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
                        # Busca el Nº Cliente en la hoja para saber en qué fila guardarlo
                        cell = ws_clientes.find(st.session_state.found_id)
                        if cell:
                            fila = cell.row
                            # Columna J = 10, Columna K = 11
                            ws_clientes.update_cell(fila, 10, st.session_state.found_lat)
                            ws_clientes.update_cell(fila, 11, st.session_state.found_lon)
                            st.sidebar.success("¡Guardado! Hacé clic en 'Actualizar datos'.")
                            st.cache_data.clear() 
                            if 'found_lat' in st.session_state: del st.session_state.found_lat
                            if 'found_lon' in st.session_state: del st.session_state.found_lon
                            if 'found_id' in st.session_state: del st.session_state.found_id
                        else:
                            st.sidebar.error("No se encontró la fila en Sheets.")
                    except Exception as e:
                        st.sidebar.error(f"Error al guardar: {e}")

    # --- MAPA PRINCIPAL ---
    if not df_filtrado.empty:
        if id_busqueda and not df_filtrado.empty:
            centro = [df_filtrado.iloc[0]['lat'], df_filtrado.iloc[0]['lon']]
            zoom = 16
        else:
            centro = [-27.45, -58.98] # Resistencia, Chaco
            zoom = 12
            
        m = folium.Map(location=centro, zoom_start=zoom)
        marker_cluster = MarkerCluster(name="Clientes").add_to(m)

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
            
            color_pin = row['color']
            folium.Marker(
                location=[row['lat'], row['lon']],
                popup=folium.Popup(html_popup, max_width=300),
                tooltip=f"{row['nombre']} (Nº {row['nro_cliente']})",
                icon=folium.Icon(color=color_pin, icon='user', prefix='fa')
            ).add_to(marker_cluster)
        
        st_folium(m, width=1200, height=700, returned_objects=[])
        
        st.markdown("### Leyenda del Mapa")
        st.markdown("🟢 **Verde:** Sin reclamos activos &nbsp;&nbsp; 🔴 **Rojo:** Reclamo Pendiente/En proceso")
        
    else:
        if not id_busqueda:
            st.warning("No hay clientes con coordenadas para el filtro seleccionado.")
        elif id_busqueda and cliente_encontrado is not None and (pd.isna(cliente_encontrado['lat']) or pd.isna(cliente_encontrado['lon'])):
            st.info("ℹ️ Este cliente no se muestra en el mapa porque no tiene coordenadas. Usá el asistente en el menú de la izquierda.")

# --- FLUJO DE EJECUCIÓN ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if st.session_state.authenticated:
    main_app()
else:
    login_screen()