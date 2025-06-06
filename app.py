from config import app, db
from flask import Flask
import routes  # Importa las rutas

@app.route('/')
def index():
    return 'Hola Bio, desde Flask en Render'

# Iniciar la aplicación Flask
#if __name__ == '__main__':
#   app.run(host='0.0.0.0', port=5000, debug=True)