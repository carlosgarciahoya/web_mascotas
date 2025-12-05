@echo off
rem EJECUTA ESTE ARCHIVO COMO ADMINISTRADOR
rem Sustituye los textos entre comillas por tus claves:

setx OPENAI_API_KEY_PERSONAL "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" /M >nul

setx OPENAI_API_KEY_OPOSICION "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" /M >nul
rem Opcional (fallback si falta la personal):

setx OPENAI_API_KEY "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" /M >nul

setx DATABASE_URL "postgresql+psycopg2://mascotas_user:Cmgh2304@localhost:5432/mascotas_db" /M >nul

rem === Credenciales de facebook 

setx ACTIVAR_MESSENGER "false" /M >nul
setx FACEBOOK_APP_ID "1642746476687388" /M >nul
setx FACEBOOK_APP_SECRET "86c13c039cd12094064c97ad26abb98f" /M >nul
setx FACEBOOK_PAGE_ID "905076672682933" /M >nul

rem === setx PAGE_ACCESS_TOKEN "EAAXWEbgy8BwBPZCJ48TgJttsAmb9J1nFHLDT3aCHZAsC6Y2esgXAcyp7kyxdcytwGmvPHfw5fkZCQopdd0pXhRXxwL6SCaDgUCqyWeAZAPbtgrHQYvjECZCbc1YBPjO8Cgg8K3ixmVLZC8hEAPlb2ZCL89erSeRdCV7ehqWKSvdbmPQXyWVQutvy7fxzR8EC4PoZBBwUE7M4" /M >nul
setx PAGE_ACCESS_TOKEN "EAAXWEbgy8BwBQEc2CdSda8ZBJPEZCZBI3vwJY43neK13oNZCAbSfxme2OOlImJGgkdMckk13v9wYGBrD6x80gxFZBbTnypZCiyaJnfHjmwfrd7oShLDFOHZA1ffvtvku59s56Wo454u3UFp1YOPkIfjCAJT7yRZA6TVHPwWDhp3MCbcRUsiH9a0TOC5CGeSKdLlfQQCB" /M >nul

setx PAGE_ACCESS_TOKEN_LAST_REFRESH "2024-01-30T23:40:00" /M >nul
setx PSID_DESTINO "25546787448240611" /M >nul

rem === Credenciales SMTP para el envío de correos ===
setx SMTP_SERVER "smtp.gmail.com" /M >nul
setx SMTP_PORT "587" /M >nul
setx SMTP_USERNAME "encontrar.mi.mascota@gmail.com" /M >nul
setx SMTP_PASSWORD "zmmx umrd xynp tpdn" /M >nul
setx SMTP_TO_EMAIL "encontrar.mi.mascota@gmail.com" /M >nul

rem === setx SMTP_USERNAME "carlos.garciahoya@gmail.com" /M >nul
rem === setx SMTP_PASSWORD "ewox jqkk aqwx kibj" /M >nul
rem === setx SMTP_TO_EMAIL "carlos.garciahoya@gmail.com" /M >nul

echo Variables guardadas a nivel de sistema (para todos los usuarios).
echo Cierra y vuelve a abrir la sesion de cada usuario, o reinicia el equipo, para que esten disponibles.
