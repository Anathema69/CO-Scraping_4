import requests
from bs4 import BeautifulSoup
import re


def test_ccb_filter():
    """Prueba diferentes formas de aplicar el filtro de fecha"""

    base_url = "https://bibliotecadigital.ccb.org.co"
    browse_url = f"{base_url}/browse/dateissued"
    scope = "66633b37-c004-4701-9685-446a1d42c06d"

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })

    # Prueba 1: Con startsWith
    print("=== Prueba 1: Con startsWith=2024 ===")
    params1 = {
        'scope': scope,
        'bbm.rpp': 20,
        'bbm.page': 1,
        'sort_by': '2',
        'order': 'ASC',
        'etal': '-1',
        'startsWith': '2024'
    }

    response1 = session.get(browse_url, params=params1)
    soup1 = BeautifulSoup(response1.text, 'html.parser')

    # Contar items
    item_links1 = soup1.find_all('a', href=re.compile(r'/items/([a-f0-9\-]+)'))
    print(f"Items encontrados con startsWith: {len(item_links1)}")

    # Buscar el texto de resultados
    results_text1 = soup1.find(string=re.compile(r'Mostrando \d+ - \d+ de \d+'))
    if results_text1:
        print(f"Texto de resultados: {results_text1}")

    # Prueba 2: Sin startsWith
    print("\n=== Prueba 2: Sin startsWith ===")
    params2 = {
        'scope': scope,
        'bbm.rpp': 20,
        'bbm.page': 1,
        'sort_by': '2',
        'order': 'ASC',
        'etal': '-1'
    }

    response2 = session.get(browse_url, params=params2)
    soup2 = BeautifulSoup(response2.text, 'html.parser')

    item_links2 = soup2.find_all('a', href=re.compile(r'/items/([a-f0-9\-]+)'))
    print(f"Items encontrados sin filtro: {len(item_links2)}")

    # Verificar si los items tienen fecha 2024
    count_2024 = 0
    for link in item_links2[:10]:  # Revisar los primeros 10
        item_text = link.get_text(strip=True)
        if '2024' in item_text:
            count_2024 += 1
            print(f"Item 2024 encontrado: {item_text[:100]}...")

    print(f"\nItems con 2024 en los primeros 10: {count_2024}")

    # Prueba 3: URL directa para año 2024
    print("\n=== Prueba 3: URL directa ===")
    # Algunos sitios usan una URL diferente para filtrar por año
    year_url = f"{browse_url}?scope={scope}&bbm.page=1&bbm.rpp=20&bbm.sd=2024"
    response3 = session.get(year_url)
    soup3 = BeautifulSoup(response3.text, 'html.parser')

    item_links3 = soup3.find_all('a', href=re.compile(r'/items/([a-f0-9\-]+)'))
    print(f"Items encontrados con URL directa: {len(item_links3)}")

    return len(item_links1), len(item_links2), len(item_links3)


if __name__ == "__main__":
    test_ccb_filter()