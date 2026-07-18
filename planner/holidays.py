"""Festivos de Bizkaia / Barakaldo (con festivos móviles calculados por año) y
una breve reseña de cada uno, para mostrarlos en el calendario con un icono "?".
Fuente de los festivos fijos: calendario laboral oficial de Bizkaia/Barakaldo 2026
(euskadi.eus / ayuntamientos)."""

from datetime import date, timedelta

FIXED_HOLIDAYS = {
    '01-01': ('Año Nuevo', 'Primer día del año en el calendario gregoriano, festivo en toda España.'),
    '01-06': ('Día de Reyes', 'Epifanía del Señor: la tradición cristiana que recuerda la visita de los Reyes Magos a Belén; en España es también el día en que los niños reciben sus regalos.'),
    '03-19': ('San José', 'Festividad católica del padre adoptivo de Jesús, mantenida como festivo en Euskadi.'),
    '05-01': ('Día del Trabajador', 'Jornada internacional en memoria de las luchas obreras por la jornada de 8 horas, iniciadas en Chicago en 1886.'),
    '07-16': ('Virgen del Carmen (fiestas de Barakaldo)', 'Festivo local de Barakaldo en honor a su patrona, la Virgen del Carmen. Da inicio a las fiestas patronales de la ciudad, celebradas del 11 al 19 de julio.'),
    '07-31': ('San Ignacio de Loyola', 'Festivo territorial de Bizkaia y Gipuzkoa en honor al fundador de la Compañía de Jesús (los jesuitas), nacido en Azpeitia (Gipuzkoa) en 1491.'),
    '08-15': ('Asunción de la Virgen', 'Festividad católica que celebra la subida de la Virgen María al cielo en cuerpo y alma.'),
    '10-12': ('Fiesta Nacional de España', 'Conmemora la llegada de Cristóbal Colón a América en 1492.'),
    '11-01': ('Todos los Santos', 'Día en el que la tradición católica recuerda a todos los santos y, popularmente, a los difuntos.'),
    '12-06': ('Día de la Constitución', 'Conmemora la ratificación en referéndum de la Constitución Española de 1978.'),
    '12-08': ('La Inmaculada Concepción', 'Festividad católica dedicada a la concepción de la Virgen María libre de pecado original.'),
    '12-25': ('Navidad', 'Celebración cristiana del nacimiento de Jesús.'),
}


def _easter_sunday(year):
    """Domingo de Resurrección para un año dado (algoritmo de Gauss/Meeus)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def holidays_for_year(year):
    """Dict 'MM-DD' -> (nombre, descripción), incluyendo los festivos móviles de Semana Santa
    calculados para ese año concreto."""
    result = dict(FIXED_HOLIDAYS)
    easter = _easter_sunday(year)
    jueves_santo = easter - timedelta(days=3)
    viernes_santo = easter - timedelta(days=2)
    lunes_pascua = easter + timedelta(days=1)

    result[jueves_santo.strftime('%m-%d')] = (
        'Jueves Santo',
        'Festivo cristiano que recuerda la Última Cena de Jesús con sus discípulos, la noche antes de su Pasión.',
    )
    result[viernes_santo.strftime('%m-%d')] = (
        'Viernes Santo',
        'Festivo cristiano que conmemora la crucifixión y muerte de Jesús.',
    )
    result[easter.strftime('%m-%d')] = (
        'Aberri Eguna (Día de la Patria Vasca)',
        'Día nacional vasco impulsado por Sabino Arana en 1902 para reivindicar la identidad y los '
        'derechos históricos del pueblo vasco. Se celebra cada Domingo de Resurrección con actos y '
        'manifestaciones, especialmente en Bilbao. No es festivo laboral (coincide con domingo), pero '
        'es una fecha muy señalada en Euskadi.',
    )
    result[lunes_pascua.strftime('%m-%d')] = (
        'Lunes de Pascua',
        'Festivo que prolonga la celebración de la Resurrección de Jesús, mantenido como día no laborable en Euskadi.',
    )
    return result
