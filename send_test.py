from messenger_client import MessengerClient

def main():
    # Sustituye este valor por el PSID del usuario que escribió a la página
    recipient_psid = "1234567890"

    # Mensaje de prueba
    text = "Hola, esto es una prueba desde mi web 🚀"

    client = MessengerClient()
    response = client.send_text_message(recipient_psid, text)
    print("Respuesta de Facebook:", response)

if __name__ == "__main__":
    main()