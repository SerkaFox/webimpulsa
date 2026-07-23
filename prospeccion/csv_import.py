"""
Importación CSV de prospectos — mismo patrón de validación que
crm/services.py (whitelist de extensión + límite de tamaño, errores como
strings), adaptado a `.csv`. Nunca escribe en la BD directamente: solo
valida y devuelve filas listas para pasar a services.create_prospect().
"""
import csv
import io

MAX_CSV_BYTES = 5 * 1024 * 1024  # 5MB de sobra para un CSV de prospectos
ALLOWED_CSV_EXTENSIONS = {'.csv'}

KNOWN_COLUMNS = [
    'name', 'sector', 'address', 'district', 'municipality',
    'lat', 'lng', 'phone', 'email', 'website', 'whatsapp', 'gmaps_url',
]


def validate_csv_file(uploaded_file):
    name = uploaded_file.name or ''
    ext = ('.' + name.rsplit('.', 1)[-1].lower()) if '.' in name else ''
    if ext not in ALLOWED_CSV_EXTENSIONS:
        return 'Solo se admiten ficheros .csv'
    if uploaded_file.size > MAX_CSV_BYTES:
        return f'El fichero supera el límite de {MAX_CSV_BYTES // (1024 * 1024)} MB'
    return None


def parse_csv(uploaded_file):
    """Devuelve (filas_validas, errores). No toca la base de datos."""
    raw = uploaded_file.read()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('latin-1')

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]
    if 'name' not in fieldnames:
        return [], ['El CSV necesita al menos una columna "name"']

    rows, errors = [], []
    for i, raw_row in enumerate(reader, start=2):
        row = {(k or '').strip().lower(): (v or '').strip() for k, v in raw_row.items() if k}
        if not row.get('name'):
            errors.append(f'Fila {i}: falta el nombre, se omite')
            continue

        lat = lng = None
        try:
            if row.get('lat'):
                lat = float(row['lat'])
            if row.get('lng'):
                lng = float(row['lng'])
        except ValueError:
            errors.append(f'Fila {i}: lat/lng no numéricos, se importa sin ubicar')

        rows.append({
            'name': row.get('name', ''),
            'sector': row.get('sector') or 'otro',
            'address': row.get('address', ''),
            'district': row.get('district', ''),
            'municipality': row.get('municipality', ''),
            'lat': lat,
            'lng': lng,
            'phone': row.get('phone', ''),
            'email': row.get('email', ''),
            'website': row.get('website', ''),
            'whatsapp': row.get('whatsapp', ''),
            'gmaps_url': row.get('gmaps_url', ''),
        })
    return rows, errors
