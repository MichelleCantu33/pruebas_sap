from flask import request, jsonify, make_response
from config import app, get_hana_connection
from models import User
from hdbcli import dbapi 
from datetime import date
import requests
import pandas as pd
import json
from sqlalchemy import text
from flask_cors import CORS
from datetime import datetime
from werkzeug.utils import secure_filename
import os

# Configuración de credenciales de SAP
SAP_LOGIN_URL = "https://54.184.71.204:50000/b1s/v1/Login"
SAP_ITEMS_URL = "https://54.184.71.204:50000/b1s/v1/Items?$filter=ItemsGroupCode eq 116"
SAP_CREDENTIALS = {
    "CompanyDB": "PRU_BIOCELLS_20250509",
    "UserName": "manager",
    "Password": "Start1234"
}

CORS(app, supports_credentials=True)
def obtener_cookies_sap():
    """ Realiza el login en SAP y devuelve las cookies necesarias. """
    try:
        response = requests.post(SAP_LOGIN_URL, json=SAP_CREDENTIALS, verify=False)
        if response.status_code == 200:
            return response.cookies
        else:
            return None
    except requests.exceptions.RequestException as e:
        print("Error de conexión con SAP:", e)
        return None
# Ruta para el login
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    usuario = data.get('usuario')
    password = data.get('password')

    if not usuario or not password:
        return jsonify({'error': 'Faltan credenciales'}), 400

    # Buscar usuario en la base de datos
    user = User.query.filter_by(Usuario=usuario).first()
    
    if not user or user.Password != password:  # Comparar directamente sin encriptación
        return jsonify({'error': 'Usuario o contraseña incorrectos'}), 401

    # Conectar a SAP con credenciales fijas
    sap_url = "https://54.184.71.204:50000/b1s/v1/Login"
    sap_data = {
        "CompanyDB": "PRU_BIOCELLS_20250509",
        "UserName": "manager",  # Usuario fijo para SAP
        "Password": "Start1234"  # Contraseña fija para SAP
    }

    try:
        response = requests.post(sap_url, json=sap_data, verify=False)
        
        if response.status_code == 200:
            sap_response = response.json()
            set_cookie_header = response.headers.get('Set-Cookie')
            print(set_cookie_header)
            cookies_list = set_cookie_header.split(', ')
            resp = make_response(jsonify({
                'message': 'Login exitoso',
                'sap_response': sap_response,
                'rol': user.Rol
            }))   
            for cookie in cookies_list:
                resp.headers.add('Set-Cookie', cookie)
            return resp, 200
        else:
            return jsonify({'error': 'Error en SAP', 'details': response.json()}), 500
    except requests.exceptions.RequestException as e:
        return jsonify({'error': 'No se pudo conectar con SAP', 'details': str(e)}), 500

# Endpoint para autenticar y obtener los datos filtrados
@app.route('/check_inventory_transfer', methods=['GET'])
def check_inventory_transfer():
    # Realizamos la autenticación a SAP
    login_response = requests.post(SAP_LOGIN_URL, json=SAP_CREDENTIALS, verify=False)

    if login_response.status_code == 200:
        session_id = login_response.cookies['B1SESSION']
        headers = {
            "Cookie": f"B1SESSION={session_id}",
            "Content-Type": "application/json"
        }

        # Obtener los filtros desde los parámetros de la consulta
        document_status = request.args.get('DocumentStatus', 'bost_Open')
        sales_person_code = request.args.get('SalesPersonCode', '66')

        # Realizamos la solicitud al endpoint InventoryTransferRequests con los filtros
        filter_url = "https://54.184.71.204:50000/b1s/v1/InventoryTransferRequests"
        filter_params = {
            "$filter": f"DocumentStatus eq '{document_status}' and SalesPersonCode eq {sales_person_code}"
        }

        response = requests.get(filter_url, headers=headers, params=filter_params, verify=False)

        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({
                "error": "Error al obtener los datos",
                "status_code": response.status_code,
                "message": response.text
            }), response.status_code
    else:
        return jsonify({
            "error": "Error en la autenticación",
            "status_code": login_response.status_code,
            "message": login_response.text
        }), login_response.status_code


@app.route('/get_inventory_transfer_detail/<int:doc_entry>', methods=['GET'])
def get_inventory_transfer_detail(doc_entry):
    try:
        login_response = requests.post(SAP_LOGIN_URL, json=SAP_CREDENTIALS, verify=False)
        if login_response.status_code != 200:
            return jsonify({"error": "Error en la autenticación"}), login_response.status_code

        cookies = login_response.cookies
        session_id = cookies.get("B1SESSION")
        route_id = cookies.get("ROUTEID")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        cookies_dict = {
            "B1SESSION": session_id
        }
        if route_id:
            cookies_dict["ROUTEID"] = route_id

        url = f"https://54.184.71.204:50000/b1s/v1/InventoryTransferRequests({doc_entry})"
        response = requests.get(url, headers=headers, cookies=cookies_dict, verify=False)

        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({"error": "Error al obtener detalle", "status_code": response.status_code, "message": response.text}), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Ruta para la transferencia de stock
@app.route('/stock-transfer', methods=['POST'])
def stock_transfer():
    data = request.json

    login_sap_url = "https://54.184.71.204:50000/b1s/v1/Login"
    sap_data = {
        "CompanyDB": "PRU_BIOCELLS_20250509",
        "UserName": "manager",
        "Password": "Start1234"
    }

    try:
        response = requests.post(login_sap_url, json=sap_data, verify=False)

        if response.status_code == 200:
            cookies = response.cookies

            headers = {
                'Content-Type': 'application/json',
                'Cookie': f'B1SESSION={cookies.get("B1SESSION")}; ROUTEID={cookies.get("ROUTEID")}'
            }

            # Enviar la transferencia
            sap_url = "https://54.184.71.204:50000/b1s/v1/StockTransfers"
            transfer_response = requests.post(sap_url, json=data, headers=headers, verify=False)

            if transfer_response.status_code == 201:
                sap_response_data = transfer_response.json()

                doc_entry = sap_response_data.get("DocEntry")
                doc_num = sap_response_data.get("DocNum")
                doc_date = sap_response_data.get("DocDate")
                from_warehouse = sap_response_data.get("FromWarehouse")
                to_warehouse = sap_response_data.get("ToWarehouse")
                comments = sap_response_data.get("Comments")
                document_lines = sap_response_data.get("StockTransferLines", [])

                # Obtener nombres de las bodegas
                from_whs_name = obtener_nombre_bodega(from_warehouse, headers)
                to_whs_name = obtener_nombre_bodega(to_warehouse, headers)

                # Obtener datos del cliente si existe
                card_code = data.get("CardCode")
                card_name = obtener_nombre_cliente(card_code, headers) if card_code else "No especificado"

                return jsonify({
                    "mensaje": "Transferencia realizada con éxito",
                    "DocEntry": doc_entry,
                    "DocNum": doc_num,
                    "Fecha": doc_date,
                    "Desde": {"Codigo": from_warehouse, "Nombre": from_whs_name},
                    "Hacia": {"Codigo": to_warehouse, "Nombre": to_whs_name},
                    "Cliente": {"Codigo": card_code, "Nombre": card_name},
                    "Comentarios": comments,
                    "Detalles": document_lines
                }), 201

            else:
                return jsonify({'error': 'Error en SAP', 'details': transfer_response.text}), transfer_response.status_code

        else:
            return jsonify({'error': 'Error en el login de SAP', 'details': response.text}), response.status_code

    except requests.exceptions.RequestException as e:
        return jsonify({'error': 'No se pudo conectar con SAP', 'details': str(e)}), 500


# 🔍 Función para obtener el nombre de una bodega
def obtener_nombre_bodega(codigo, headers):
    try:
        url = f"https://54.184.71.204:50000/b1s/v1/Warehouses('{codigo}')"
        response = requests.get(url, headers=headers, verify=False)
        if response.status_code == 200:
            return response.json().get("WarehouseName", "No disponible")
    except:
        pass
    return "No disponible"


# 🔍 Función para obtener el nombre del cliente
def obtener_nombre_cliente(card_code, headers):
    try:
        url = f"https://54.184.71.204:50000/b1s/v1/BusinessPartners('{card_code}')"
        response = requests.get(url, headers=headers, verify=False)
        if response.status_code == 200:
            return response.json().get("CardName", "No disponible")
    except:
        pass
    return "No disponible"


    
# Ruta para obtener la lista de precios de un Business Partner
@app.route('/business-partner-price-list/<business_partner_id>', methods=['GET'])
def get_business_partner_price_list(business_partner_id):
    # URL del login
    login_sap_url = "https://54.184.71.204:50000/b1s/v1/Login"
    sap_data = {
        "CompanyDB": "PRU_BIOCELLS_20250509",
        "UserName": "manager",
        "Password": "Start1234"
    }

    try:
        login_response = requests.post(login_sap_url, json=sap_data, verify=False)

        if login_response.status_code == 200:
            cookies = login_response.cookies

            # 1. Obtener PriceListNum del Business Partner
            business_partner_url = f"https://54.184.71.204:50000/b1s/v1/BusinessPartners('{business_partner_id}')"
            headers = {
                'Content-Type': 'application/json',
                'Cookie': f'B1SESSION={cookies.get("B1SESSION")}; ROUTEID={cookies.get("ROUTEID")}'
            }

            bp_response = requests.get(business_partner_url, headers=headers, verify=False)

            if bp_response.status_code == 200:
                bp_data = bp_response.json()
                price_list_num = bp_data.get("PriceListNum")

                if price_list_num is None:
                    return jsonify({'error': 'No se encontró PriceListNum para este Business Partner'}), 404

                # 2. Obtener el nombre de la lista de precios
                price_list_url = f"https://54.184.71.204:50000/b1s/v1/PriceLists({price_list_num})"
                price_list_response = requests.get(price_list_url, headers=headers, verify=False)

                if price_list_response.status_code == 200:
                    price_list_data = price_list_response.json()
                    return jsonify({
                        "PriceListNum": price_list_num,
                        "PriceListName": price_list_data.get("PriceListName")
                    }), 200
                else:
                    return jsonify({'error': 'Error al obtener la lista de precios', 'details': price_list_response.text}), price_list_response.status_code
            else:
                return jsonify({'error': 'Error al obtener datos del Business Partner', 'details': bp_response.text}), bp_response.status_code
        else:
            return jsonify({'error': 'Error en el login de SAP', 'details': login_response.text}), login_response.status_code

    except requests.exceptions.RequestException as e:
        return jsonify({'error': 'No se pudo conectar con SAP', 'details': str(e)}), 500
# Ruta para obtener los datos de bodegas específicas
@app.route('/get-warehouses', methods=['GET'])
def get_warehouses():
    # Bodegas que queremos obtener
    warehouse_ids = ['2010', '1001', '1018', '2026','1090']

    # URL de login a SAP
    login_sap_url = "https://54.184.71.204:50000/b1s/v1/Login"
    sap_data = {
        "CompanyDB": "PRU_BIOCELLS_20250509",
        "UserName": "manager",  # Usuario fijo para SAP
        "Password": "Start1234"  # Contraseña fija para SAP
    }

    try:
        # Realizar la solicitud de login a SAP
        response = requests.post(login_sap_url, json=sap_data, verify=False)

        if response.status_code == 200:
            # Obtener las cookies de la respuesta del login
            cookies = response.cookies
            print("Cookies obtenidas del login:", cookies)

            # Lista para almacenar las bodegas
            warehouses = []

            # Obtener los datos de las bodegas especificadas
            for warehouse_id in warehouse_ids:
                # URL de la bodega
                warehouse_url = f"https://54.184.71.204:50000/b1s/v1/Warehouses('{warehouse_id}')"
                headers = {
                    'Content-Type': 'application/json',
                    'Cookie': f'B1SESSION={cookies.get("B1SESSION")}; ROUTEID={cookies.get("ROUTEID")}'
                }

                # Realizar la solicitud para obtener los datos de la bodega
                warehouse_response = requests.get(warehouse_url, headers=headers, verify=False)

                if warehouse_response.status_code == 200:
                    warehouse_data = warehouse_response.json()
                    warehouse_info = {
                        'WarehouseCode': warehouse_data.get('WarehouseCode'),
                        'WarehouseName': warehouse_data.get('WarehouseName')
                    }
                    warehouses.append(warehouse_info)
                else:
                    print(f"Error al obtener la bodega {warehouse_id}: {warehouse_response.text}")

            # Retornar los datos de las bodegas
            return jsonify({'warehouses': warehouses}), 200

        else:
            return jsonify({'error': 'Error en el login de SAP', 'details': response.text}), response.status_code

    except requests.exceptions.RequestException as e:
        return jsonify({'error': 'No se pudo conectar con SAP', 'details': str(e)}), 500



@app.route('/items', methods=['GET'])
def obtener_items():
    """ Endpoint para obtener los ítems del grupo 115 desde SAP. """
    cookies = obtener_cookies_sap()
    if not cookies:
        return jsonify({'error': 'No se pudo autenticar en SAP'}), 500

    headers = {
        'Content-Type': 'application/json',
        'Cookie': f'B1SESSION={cookies.get("B1SESSION")}; ROUTEID={cookies.get("ROUTEID")}'
    }

    try:
        response = requests.get(SAP_ITEMS_URL, headers=headers, verify=False)
        if response.status_code == 200:
            items_data = response.json().get('value', [])
            items_filtrados = []

            for item in items_data:
                # Filtramos solo los campos requeridos
                items_filtrados.append({
                    "ItemCode": item.get("ItemCode"),
                    "ItemName": item.get("ItemName"),
                    "ItemsGroupCode": item.get("ItemsGroupCode")
                })

            return jsonify(items_filtrados), 200
        else:
            return jsonify({'error': 'Error al obtener los ítems', 'details': response.text}), response.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({'error': 'No se pudo conectar con SAP', 'details': str(e)}), 500
    
# Endpoint para verificar la conexión a SAP HANA
@app.route('/api/test_hana', methods=['GET'])
def test_hana_connection():
    conn = get_hana_connection()
    if conn:
        conn.close()  # Cerrar la conexión después de la prueba
        return jsonify({"status": "success", "message": "Conexión a SAP HANA exitosa."}), 200
    else:
        return jsonify({"status": "error", "message": "Error al conectar a SAP HANA."}), 500
    
@app.route('/inventario', methods=['GET'])
def obtener_inventario():
    # Obtener los parámetros de consulta desde la URL
    codigo_item = request.args.get('codigo_item')  # Obtiene el parámetro "codigo_item"
    codigo_almacen = request.args.get('codigo_almacen')  # Obtiene el parámetro "codigo_almacen"

    # Verificar que ambos parámetros fueron proporcionados
    if not codigo_item or not codigo_almacen:
        return jsonify({"error": "Debe proporcionar 'codigo_item' y 'codigo_almacen' como parámetros de consulta."}), 400

    # Establecer la conexión a SAP HANA
    conn = get_hana_connection()
    if conn is None:
        return jsonify({"error": "No se pudo conectar a la base de datos HANA"}), 500

    # Consulta SQL con parámetros dinámicos
    query = """
    SELECT "Código Item", "Nombre Item", "Código Almacen", "Nombre Almacen", "Cantidad", "Cod Barras", "Lote", "Fecha Vencimiento"
    FROM PRU_BIOCELLS_20250509.BIOCELLS_INVENTARIO_BODEGA
    WHERE "Código Item" = ? AND "Código Almacen" = ?
    """

    try:
        # Crear un cursor y ejecutar la consulta con los parámetros dinámicos
        cursor = conn.cursor()
        cursor.execute(query, (codigo_item, codigo_almacen))  # Pasar los parámetros al ejecutar la consulta
        rows = cursor.fetchall()

        # Extraer los resultados y devolverlos en formato JSON
        resultado = []
        for row in rows:
            resultado.append({
                "Código Item": row[0],
                "Nombre Item": row[1],
                "Código Almacen": row[2],
                "Nombre Almacen": row[3],
                "Cantidad": row[4],
                "Cod Barras": row[5],
                "Lote": row[6],
                "Fecha Vencimiento": row[7]
            })

        # Cerrar la conexión
        cursor.close()
        conn.close()

        return jsonify(resultado)
    
    except Exception as e:
        return jsonify({"error": f"Error en la ejecución de la consulta: {e}"}), 500
    
@app.route('/reportinventario', methods=['GET'])
def obtener_reportinventario():
    fecha_actualizacion = request.args.get('fecha_actualizacion')
    grupo = request.args.get('grupo')
    codigo_item = request.args.get('codigo_item')
    bodega = request.args.get('bodega')

    if not fecha_actualizacion:
        return jsonify({"error": "Debe proporcionar 'fecha_actualizacion' como parámetro de consulta."}), 400

    conn = get_hana_connection()
    if conn is None:
        return jsonify({"error": "No se pudo conectar a la base de datos HANA"}), 500

    query = """
    SELECT "Código Item", "Nombre Item", "Costo", "Costo Total", "Partida Arancelaria", 
           "Código Almacen", "Nombre Almacen", "Cantidad", "Cantidad Comprometida", 
           "Stock Final", "Cod Barras", "Lote", "Fecha de Creación", "Fecha de Actualización", "Fecha Vencimiento", 
           "Grupo", "Subgrupo"
    FROM PRU_BIOCELLS_20250509.BIOCELLS_INVENTARIO_TEJIDOS_BODEGA
    WHERE "Fecha de Actualización" <= ?
    """

    params = [fecha_actualizacion]

    if grupo:
        query += ' AND "Grupo" = ?'
        params.append(grupo)
    if codigo_item:
        query += ' AND "Código Item" = ?'
        params.append(codigo_item)
    if bodega:
        query += ' AND "Código Almacen" = ?'
        params.append(bodega)

    try:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        resultado = [{
            "Código Item": row[0],
            "Nombre Item": row[1],
            "Costo": row[2],
            "Costo Total": row[3],
            "Partida Arancelaria": row[4],
            "Código Almacen": row[5],
            "Nombre Almacen": row[6],
            "Cantidad": row[7],
            "Cantidad Comprometida": row[8],
            "Stock Final": row[9],
            "Cod Barras": row[10],
            "Lote": row[11],
            "Fecha de Creación": row[12],
            "Fecha de Actualización": row[13],
            "Fecha Vencimiento": row[14],
            "Grupo": row[15],
            "Subgrupo": row[16]
        } for row in rows]

        cursor.close()
        conn.close()
        return jsonify(resultado)
    
    except Exception as e:
        return jsonify({"error": f"Error en la ejecución de la consulta: {e}"}), 500


@app.route('/stock-transfer-archivo', methods=['POST'])
def stock_transfer_archivo():
    if 'file' not in request.files:
        return jsonify({"error": "No se encontró ningún archivo"}), 400

    file = request.files['file']
    
    try:
        # Leer las hojas del Excel
        df_encabezado = pd.read_excel(file, sheet_name="Encabezado")
        df_lineas = pd.read_excel(file, sheet_name="Lineas")
        df_lotes = pd.read_excel(file, sheet_name="Lotes")

        # 🔹 Convertir fechas a string en el encabezado
        for col in ["DocDate", "DueDate", "TaxDate", "CreationDate", "UpdateDate"]:
            if col in df_encabezado.columns:
                df_encabezado[col] = df_encabezado[col].astype(str)

        # 🔹 Convertir encabezado a JSON
        encabezado = df_encabezado.iloc[0].to_dict()

        # Convertir líneas a JSON
        lineas_json = []
        for _, row in df_lineas.iterrows():
            # 🔹 Convertir fechas en las líneas si hay alguna
            for col in ["ExpiryDate"]:
                if col in row and not pd.isna(row[col]):
                    row[col] = str(row[col])

            # Filtrar los lotes correspondientes a esta línea
            lotes = df_lotes[df_lotes["BaseLineNumber"] == row["LineNum"]].copy()

            # 🔹 Convertir fechas en los lotes
            for col in ["ExpiryDate"]:
                if col in lotes.columns:
                    lotes[col] = lotes[col].astype(str)

            lotes_json = lotes.to_dict(orient="records")

            # Convertir línea a diccionario
            linea = row.to_dict()
            linea["BatchNumbers"] = lotes_json  # Agregar lotes a la línea

            lineas_json.append(linea)

        # Construir JSON final
        json_data = encabezado
        json_data["StockTransferLines"] = lineas_json

        # 🔹 CONEXIÓN A SAP 🔹
        login_sap_url = "https://54.184.71.204:50000/b1s/v1/Login"
        sap_data = {
            "CompanyDB": "PRU_BIOCELLS_20250509",
            "UserName": "manager",  # Usuario fijo para SAP
            "Password": "Start1234"  # Contraseña fija para SAP
        }

        # Realizar login en SAP
        response = requests.post(login_sap_url, json=sap_data, verify=False)

        if response.status_code == 200:
            # Obtener las cookies de sesión
            cookies = response.cookies
            print("Cookies obtenidas del login:", cookies)

            # URL de SAP para la transferencia de stock
            sap_url = "https://54.184.71.204:50000/b1s/v1/StockTransfers"

            # Construir los encabezados con las cookies obtenidas
            headers = {
                'Content-Type': 'application/json',
                'Cookie': f'B1SESSION={cookies.get("B1SESSION")}; ROUTEID={cookies.get("ROUTEID")}'
            }

            # Enviar solicitud a SAP
            transfer_response = requests.post(sap_url, json=json_data, headers=headers, verify=False)

            if transfer_response.status_code == 201:
                return jsonify(transfer_response.json()), transfer_response.status_code
            else:
                return jsonify({'error': 'Error en SAP', 'details': transfer_response.text}), transfer_response.status_code

        else:
            return jsonify({'error': 'Error en el login de SAP', 'details': response.text}), response.status_code

    except Exception as e:
        return jsonify({"error": "Error procesando el archivo", "details": str(e)}), 500
    
@app.route('/create_inventory_transfer/<int:doc_entry>', methods=['POST'])
def create_inventory_transfer(doc_entry):
    # Paso 1: Autenticarse
    login_response = requests.post(SAP_LOGIN_URL, json=SAP_CREDENTIALS, verify=False)

    if login_response.status_code != 200:
        log_audit(doc_entry, "Login", "Failed", f"Authentication failed: {login_response.text}")
        return jsonify({"error": "Error en la autenticación", "status_code": login_response.status_code, "message": login_response.text}), login_response.status_code

    session_id = login_response.cookies['B1SESSION']
    headers = {
        "Cookie": f"B1SESSION={session_id}",
        "Content-Type": "application/json"
    }

    # Paso 2: Obtener la solicitud de traslado (InventoryTransferRequest)
    request_url = f"https://54.184.71.204:50000/b1s/v1/InventoryTransferRequests({doc_entry})"
    request_response = requests.get(request_url, headers=headers, verify=False)

    if request_response.status_code != 200:
        log_audit(doc_entry, "Get Transfer Request", "Failed", f"Failed to get request: {request_response.text}")
        return jsonify({"error": "No se pudo obtener la solicitud", "status_code": request_response.status_code, "message": request_response.text}), request_response.status_code

    transfer_request = request_response.json()
    print(json.dumps(transfer_request, indent=4))

    # Paso 3: Construir el cuerpo del nuevo InventoryTransfer
    transfer_body = {
        "DocDate": date.today().isoformat(),
        "Comments": f"Creado desde solicitud #{transfer_request.get('DocNum')}",
        "U_BIO_EstadoTR": "A", 
        "StockTransferLines": []
    }

    # Paso 4: Manejar los números de lote (Batch Numbers)
    for line in transfer_request.get("StockTransferLines", []):
        transfer_line = {
            "ItemCode": line["ItemCode"],
            "Quantity": line["Quantity"],
            "FromWarehouseCode": line["FromWarehouseCode"],
            "WarehouseCode": line["WarehouseCode"],
            "BaseEntry": doc_entry,
            "BaseLine": line["LineNum"],
            "BaseType": 1250000001,  # InventoryTransferRequest
            "BatchNumbers": []
        }


        # Si hay números de lote, los agregamos
        if "BatchNumbers" in line:
            for batch in line["BatchNumbers"]:
                # Validar si el lote ya tiene la cantidad asignada
                batch_data = {
                    "BatchNumber": batch["BatchNumber"],  # Número de lote
                    "Quantity": batch["Quantity"]         # Cantidad de ese lote
                }

                # Si la cantidad de este lote ya fue asignada, es necesario manejar la lógica
                if batch["Quantity"] == 0:
                    continue  # Si la cantidad es 0, no lo agregamos
                else:
                    transfer_line["BatchNumbers"].append(batch_data)

        # Agregar la línea de transferencia al cuerpo
        transfer_body["StockTransferLines"].append(transfer_line)

    # Paso 5: Crear la transferencia (InventoryTransfers)
    transfer_url = "https://54.184.71.204:50000/b1s/v1/StockTransfers"
    transfer_response = requests.post(transfer_url, headers=headers, json=transfer_body, verify=False)

    if transfer_response.status_code == 201:
        log_audit(doc_entry, "Create Transfer", "Success", f"Transferencia creada: {json.dumps(transfer_response.json())}")
        return jsonify({"success": True, "message": "Transferencia creada exitosamente", "data": transfer_response.json()})
    else:
        log_audit(doc_entry, "Create Transfer", "Failed", f"Failed to create transfer: {transfer_response.text}")
        return jsonify({"error": "Error al crear la transferencia", "status_code": transfer_response.status_code, "message": transfer_response.text}), transfer_response.status_code

# Función para registrar la auditoría
def log_audit(doc_entry, action, status, details):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    audit_entry = {
        "timestamp": timestamp,
        "doc_entry": doc_entry,
        "action": action,
        "status": status,
        "details": details
    }
    with open("audit_log.txt", "a") as f:
        f.write(json.dumps(audit_entry) + "\n")
        
        
def obtener_cabecera_sesion_sap():
    """ Devuelve encabezados con la sesión de SAP si está autenticado """
    login_response = requests.post(SAP_LOGIN_URL, json=SAP_CREDENTIALS, verify=False)
    if login_response.status_code == 200:
        cookies = login_response.cookies
        return {
            'Content-Type': 'application/json',
            'Cookie': f'B1SESSION={cookies.get("B1SESSION")}; ROUTEID={cookies.get("ROUTEID")}'
        }
    return None

@app.route('/cajas-instrumental', methods=['POST'])
def crear_caja_instrumental():
    data = request.json
    conn = get_hana_connection()
    if conn is None:
        return jsonify({"error": "No se pudo conectar a HANA"}), 500
    try:
        cursor = conn.cursor()

        # 🔍 Validar si el Code ya existe
        cursor.execute("""
            SELECT COUNT(*) FROM "PRU_BIOCELLS_20250509"."@LS_CAJ_CAB" WHERE "Code" = ?
        """, (data["CodigoCaja"],))
        if cursor.fetchone()[0] > 0:
            return jsonify({"error": f"La caja con código '{data['CodigoCaja']}' ya existe"}), 409

        # 🆕 Obtener el nuevo DocEntry
        cursor.execute('SELECT MAX("DocEntry") FROM "PRU_BIOCELLS_20250509"."@LS_CAJ_CAB"')
        ultimo_docentry = cursor.fetchone()[0] or 0
        nuevo_docentry = ultimo_docentry + 1

        # 🧾 Insertar cabecera (ahora con U_LS_ITEM)
        cursor.execute("""
            INSERT INTO "PRU_BIOCELLS_20250509"."@LS_CAJ_CAB"
            ("DocEntry", "Code", "U_LS_FECHA", "U_LS_ALM", "U_LS_CLASECAJA", "U_LS_ITEM")
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            nuevo_docentry,
            data["CodigoCaja"],
            data["FechaCaja"],
            data["Almacen"],
            data["ClaseCaja"],
            data["CodigoCaja"]  # U_LS_ITEM ← Código Caja
        ))

        # 📦 Insertar líneas con campo opcional Descripcion (U_LS_ITEM_NAME)
        for i, linea in enumerate(data["Lineas"], start=1):
            descripcion = linea.get("Descripcion")  # puede ser None si no se envía
            cursor.execute("""
                INSERT INTO "PRU_BIOCELLS_20250509"."@LS_CAJ_LIN"
                ("Code", "LineId", "U_LS_ITEM", "U_LS_ITEM_NAME", "U_LS_CANT", "U_LS_TIPO", "U_LS_LOTE")
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                data["CodigoCaja"],
                i,
                linea["CodigoItem"],
                descripcion,
                linea["CantidadItem"],
                linea["TipoItem"],
                linea["LoteItem"]
            ))

        conn.commit()
        return jsonify({
            "mensaje": "Caja creada correctamente",
            "DocEntry": nuevo_docentry,
            "CodigoCaja": data["CodigoCaja"]
        }), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"error": f"Error al crear la caja: {str(e)}"}), 500
    finally:
        conn.close()

        
@app.route('/cajas-instrumental', methods=['GET'])
def obtener_cajas_instrumental():
    conn = get_hana_connection()
    if conn is None:
        return jsonify({"error": "No se pudo conectar a HANA"}), 500
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM "PRU_BIOCELLS_20250509"."BIOCELLS_CAJASINSTRUMENTAL"')
        columnas = [col[0] for col in cursor.description]
        datos = [dict(zip(columnas, row)) for row in cursor.fetchall()]
        return jsonify(datos), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/cajas-instrumental/<codigo>', methods=['PUT'])
def actualizar_caja_instrumental(codigo):
    data = request.json
    conn = get_hana_connection()
    if conn is None:
        return jsonify({"error": "No se pudo conectar a HANA"}), 500

    try:
        cursor = conn.cursor()

        # Verificar que la caja existe
        cursor.execute("""
            SELECT COUNT(*) FROM "PRU_BIOCELLS_20250509"."@LS_CAJ_CAB"
            WHERE "Code" = ?
        """, (codigo,))
        if cursor.fetchone()[0] == 0:
            return jsonify({"error": f"La caja '{codigo}' no existe"}), 404

        # Actualizar cabecera (incluyendo U_LS_ITEM con el mismo código)
        cursor.execute("""
            UPDATE "PRU_BIOCELLS_20250509"."@LS_CAJ_CAB"
            SET "U_LS_FECHA" = ?, "U_LS_ALM" = ?, "U_LS_CLASECAJA" = ?, "U_LS_ITEM" = ?
            WHERE "Code" = ?
        """, (
            data["FechaCaja"],
            data["Almacen"],
            data["ClaseCaja"],
            codigo,
            codigo
        ))

        # Eliminar líneas existentes
        cursor.execute("""
            DELETE FROM "PRU_BIOCELLS_20250509"."@LS_CAJ_LIN"
            WHERE "Code" = ?
        """, (codigo,))

        # Insertar nuevas líneas con campo opcional Descripcion (U_LS_ITEM_NAME)
        for i, linea in enumerate(data["Lineas"], start=1):
            descripcion = linea.get("Descripcion")
            cursor.execute("""
                INSERT INTO "PRU_BIOCELLS_20250509"."@LS_CAJ_LIN"
                ("Code", "LineId", "U_LS_ITEM", "U_LS_ITEM_NAME", "U_LS_CANT", "U_LS_TIPO", "U_LS_LOTE")
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                codigo,
                i,
                linea["CodigoItem"],
                descripcion,
                linea["CantidadItem"],
                linea["TipoItem"],
                linea["LoteItem"]
            ))

        conn.commit()
        return jsonify({"mensaje": f"Caja '{codigo}' actualizada correctamente"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": f"Error al actualizar la caja: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/cajas-instrumental/<codigo>', methods=['DELETE'])
def eliminar_caja_instrumental(codigo):
    conn = get_hana_connection()
    if conn is None:
        return jsonify({"error": "No se pudo conectar a HANA"}), 500

    try:
        cursor = conn.cursor()

        # Verificar que la caja existe
        cursor.execute("""
            SELECT COUNT(*) FROM "PRU_BIOCELLS_20250509"."@LS_CAJ_CAB"
            WHERE "Code" = ?
        """, (codigo,))
        if cursor.fetchone()[0] == 0:
            return jsonify({"error": f"La caja '{codigo}' no existe"}), 404

        # Eliminar líneas
        cursor.execute("""
            DELETE FROM "PRU_BIOCELLS_20250509"."@LS_CAJ_LIN"
            WHERE "Code" = ?
        """, (codigo,))

        # Eliminar cabecera
        cursor.execute("""
            DELETE FROM "PRU_BIOCELLS_20250509"."@LS_CAJ_CAB"
            WHERE "Code" = ?
        """, (codigo,))

        conn.commit()
        return jsonify({"mensaje": f"Caja '{codigo}' eliminada correctamente"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": f"Error al eliminar la caja: {str(e)}"}), 500
    finally:
        conn.close()


@app.route('/warehouses', methods=['GET'])
def warehouses():
    try:
        # Conexión a SAP HANA
        conn = get_hana_connection()
        cursor = conn.cursor()

        # Consulta para obtener bodegas desde la vista
        query = """
        SELECT "CodigoBodega", "NombreBodega"
        FROM "PRU_BIOCELLS_20250509"."BIOCELLS_Bodegas"
        """
        cursor.execute(query)

        # Obtener los resultados
        warehouses = cursor.fetchall()

        # Cerrar la conexión
        cursor.close()
        conn.close()

        # Formatear los resultados para la respuesta
        warehouses_list = [{"CodigoBodega": w[0], "NombreBodega": w[1]} for w in warehouses]

        return jsonify({'warehouses': warehouses_list})

    except Exception as e:
        return jsonify({'error': 'Fallo de conexión o excepción', 'details': str(e)}), 500
    
# Ruta para manejar la carga del archivo Excel


@app.route('/importar-cajas', methods=['POST'])
def importar_cajas():
    conn = None  # Asegúrate de que 'conn' esté definido aquí

    if 'file' not in request.files:
        return jsonify({"error": "No se ha enviado un archivo"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No se ha seleccionado un archivo"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        
        # Define la carpeta donde deseas guardar el archivo
        upload_folder = '/path/to/save'  # Cambia esta ruta por una válida en tu servidor

        # Verifica si la carpeta existe, si no, créala
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)

        # Guarda el archivo en la carpeta especificada
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)

        try:
            # Lee el archivo Excel con pandas
            df = pd.read_excel(filepath)

            # Limpiar los nombres de las columnas
            df.columns = df.columns.str.strip()

            # Imprimir las columnas leídas desde el archivo Excel
            print("Columnas limpias del archivo Excel:", df.columns)

            # Validar las columnas del archivo Excel
            required_columns = ["CodigoCaja", "FechaCaja", "Almacen", "ClaseCaja", "CodigoItem", "CantidadItem", "TipoItem", "LoteItem"]
            for col in required_columns:
                if col not in df.columns:
                    return jsonify({"error": f"Falta la columna '{col}' en el archivo Excel"}), 400

            # Conectar a SAP HANA
            conn = get_hana_connection()
            if conn is None:
                return jsonify({"error": "No se pudo conectar a HANA"}), 500

            cursor = conn.cursor()
            for index, row in df.iterrows():
                cursor.execute("""
                    SELECT COUNT(*) FROM "PRU_BIOCELLS_20250509"."@LS_CAJ_CAB" WHERE "Code" = ?
                """, (row["CodigoCaja"],))
                if cursor.fetchone()[0] > 0:
                    continue

                cursor.execute('SELECT MAX("DocEntry") FROM "PRU_BIOCELLS_20250509"."@LS_CAJ_CAB"')
                ultimo_docentry = cursor.fetchone()[0] or 0
                nuevo_docentry = ultimo_docentry + 1

                cursor.execute("""
                    INSERT INTO "PRU_BIOCELLS_20250509"."@LS_CAJ_CAB"
                    ("DocEntry", "Code", "U_LS_FECHA", "U_LS_ALM", "U_LS_CLASECAJA", "U_LS_ITEM")
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    nuevo_docentry,
                    row["CodigoCaja"],
                    row["FechaCaja"],
                    row["Almacen"],
                    row["ClaseCaja"],
                    row["CodigoCaja"]
                ))

                cursor.execute("""
                    INSERT INTO "PRU_BIOCELLS_20250509"."@LS_CAJ_LIN"
                    ("Code", "LineId", "U_LS_ITEM", "U_LS_ITEM_NAME", "U_LS_CANT", "U_LS_TIPO", "U_LS_LOTE")
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    row["CodigoCaja"],
                    index + 1,
                    row["CodigoItem"],
                    row.get("Descripcion", None),
                    row["CantidadItem"],
                    row["TipoItem"],
                    row["LoteItem"]
                ))

            conn.commit()
            return jsonify({"mensaje": "Cajas importadas correctamente"}), 201

        except Exception as e:
            return jsonify({"error": f"Error al procesar el archivo Excel: {str(e)}"}), 500

        finally:
            if conn:
                conn.close()  # Solo cierra la conexión si se creó correctamente
    else:
        return jsonify({"error": "Archivo no permitido. Debe ser un archivo Excel (.xlsx)"}), 400



# Función para permitir solo archivos Excel
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['xlsx']