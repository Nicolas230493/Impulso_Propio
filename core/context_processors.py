from .fechas import hoy, mes_a_texto, mes_de_request


def mes(request):
    """El mes filtrado viaja por ?mes=AAAA-MM; todas las pantallas lo ven."""
    return {"mes": mes_a_texto(mes_de_request(request)), "mes_actual": mes_a_texto(hoy())}
