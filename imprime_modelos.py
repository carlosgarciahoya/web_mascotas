import os
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
import time
import chardet

# TEST TEST TEST *** CLAVE PARA GASTAR EN PRUEBAS PROYECTO PERSONAL rag basico y el predeterminado 
#os.environ["OPENAI_API_KEY"] = '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' 
#from openai import OpenAI
#client = OpenAI(api_key="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")

# *************  CLAVE BUENA DEL PROYECTO OPOSICIONES NIVEL 5 LIMITE 1.000 $
os.environ["OPENAI_API_KEY"] = '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' 
from openai import OpenAI
client = OpenAI(api_key="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")

models = client.models.list()
# Imprimir los nombres de los modelos disponibles
for model in models.data:  # Cambiar 'models['data']' a 'models.data'
    print(model.id)  # Cambiar 'model['id']' a 'model.id'