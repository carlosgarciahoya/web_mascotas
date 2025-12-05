# -*- coding: utf-8 -*-
"""
Created on Sun Sep 22 08:09:34 2024

@author: CGH
"""
from openai import OpenAI
import requests
import os

# TEST TEST TEST *** CLAVE PARA GASTAR EN PRUEBAS PROYECTO PERSONAL rag basico y el predeterminado 
#os.environ["OPENAI_API_KEY"] = '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' 
#from openai import OpenAI
#client = OpenAI(api_key="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")

# *************  CLAVE BUENA DEL PROYECTO OPOSICIONES NIVEL 5 LIMITE 1.000 $
os.environ["OPENAI_API_KEY"] = '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' 
from openai import OpenAI
client = OpenAI(api_key="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")


# Función para realizar una consulta a la API y capturar los headers
def get_api_rate_limits():
    headers = {
        "Authorization": f"Bearer {client.api_key}",  # Acceder a la API key desde el cliente
    }

    # Realiza una solicitud POST a la API de completions
    response = requests.post(
        "https://api.openai.com/v1/completions",
        headers=headers,
        json={
            "model": "o1-preview-2024-09-12",  # Puedes cambiar el modelo
            #"model": "gpt-4o-mini",  # Puedes cambiar el modelo
            # "model": "gpt-4",  # Puedes cambiar el modelo
            "prompt": "Dime los límites de uso de OpenAI.",
            "max_tokens": 10
        }
    )

    # Obtener los headers de la respuesta
    rate_limit_requests = response.headers.get("x-ratelimit-limit-requests")
    rate_limit_tokens = response.headers.get("x-ratelimit-limit-tokens")
    rate_limit_remaining_requests = response.headers.get("x-ratelimit-remaining-requests")
    rate_limit_remaining_tokens = response.headers.get("x-ratelimit-remaining-tokens")

    # Mostrar los valores obtenidos
    print(f"Límite de solicitudes por minuto (RPM): {rate_limit_requests}")
    print(f"Límite de tokens por minuto (TPM): {rate_limit_tokens}")
    print(f"Solicitudes restantes en el periodo actual: {rate_limit_remaining_requests}")
    print(f"Tokens restantes en el periodo actual: {rate_limit_remaining_tokens}")

# Llamar a la función para obtener los límites de uso
get_api_rate_limits()
