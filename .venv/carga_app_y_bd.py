from web import create_app
from web.models import db, Mascota, FotoMascotaDesaparecida

app = create_app()
app.app_context().push()
