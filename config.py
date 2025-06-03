from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from hdbcli import dbapi  # Importar el cliente para SAP HANA

app = Flask(__name__)

# Configurar SQL Server (manteniendo la conexión existente)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mssql+pyodbc://userti:Us3rT1$2024.@52.36.179.49/ReportesDB?driver=ODBC+Driver+17+for+SQL+Server'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializar la base de datos para SQL Server
db = SQLAlchemy(app)

CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Función para conectar a SAP HANA
def get_hana_connection():
    try:
        conn = dbapi.connect(
            address="54.184.71.204",  # Dirección del servidor HANA
            port=30015,               # Puerto de conexión
            user="B1ADMIN",           # Usuario de conexión
            password="B1AdminBIO$",    # Contraseña de conexión
        )
        return conn
    except Exception as e:
        print(f"Error al conectar a SAP HANA: {e}")
        return None
