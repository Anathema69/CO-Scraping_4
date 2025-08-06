import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
import time
import json
import re
from typing import Dict, List, Optional
from datetime import datetime
import logging


logger = logging.getLogger(__name__)


class DIANScraper:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://cijuf.org.co/normatividad/conceptos-y-oficios-dian"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.session.headers.update(self.headers)
        self.processed_urls = set()  # Para evitar duplicados

    def scrape_month(self, year: int, month: int, download_docs: bool = True, max_pages: int = 10) -> List[Dict]:
        """Obtener todos los documentos de un mes específico"""
        documents = []
        month_str = f"{month:02d}"
        base_month_url = f"{self.base_url}/{year}/{month_str}"

        page_num = 0
        consecutive_empty = 0

        logger.info(f"Iniciando scraping de {year}/{month_str}")

        while page_num < max_pages and consecutive_empty < 2:
            url = f"{base_month_url}?page={page_num}"

            logger.info(f"Procesando página {page_num}: {url}")

            try:
                response = self.session.get(url, timeout=30)
                if response.status_code != 200:
                    logger.warning(f"Error HTTP {response.status_code} en página {page_num}")
                    consecutive_empty += 1
                    page_num += 1
                    continue

                # Extraer enlaces de la página
                doc_links = self.extract_document_links_from_listing(response.text)

                if not doc_links:
                    logger.info(f"Página {page_num} vacía")
                    consecutive_empty += 1
                    if page_num >= 3:  # Si página 3+ está vacía, probablemente no hay más
                        break
                else:
                    logger.info(f"Encontrados {len(doc_links)} documentos en página {page_num}")
                    consecutive_empty = 0

                    if download_docs:
                        for i, link_info in enumerate(doc_links, 1):
                            if link_info['url'] in self.processed_urls:
                                logger.debug(f"URL ya procesada: {link_info['url']}")
                                continue

                            try:
                                logger.info(
                                    f"  [{i}/{len(doc_links)}] Procesando: {link_info.get('numero', 'Sin número')}")
                                doc_data = self.process_document(link_info['url'])
                                if doc_data:
                                    doc_data.update(link_info)
                                    documents.append(doc_data)
                                    self.processed_urls.add(link_info['url'])
                                time.sleep(1)
                            except Exception as e:
                                logger.error(f"Error procesando {link_info['url']}: {e}")
                    else:
                        documents.extend(doc_links)

                page_num += 1

            except Exception as e:
                logger.error(f"Error en página {page_num}: {e}")
                consecutive_empty += 1
                page_num += 1

        logger.info(f"Total documentos encontrados en {year}/{month_str}: {len(documents)}")
        return documents

    def extract_document_links_from_listing(self, html_content: str) -> List[Dict]:
        """Extraer enlaces mejorado de la página de listado"""
        documents = []
        soup = BeautifulSoup(html_content, 'html.parser')

        # Buscar todos los enlaces a conceptos y oficios
        for link in soup.find_all('a', href=True):
            href = link['href']

            if '/concepto/' in href or '/oficio/' in href:
                link_text = link.get_text(strip=True)

                # Verificar que sea un enlace válido
                if link_text and (link_text.startswith('Concepto') or
                                  link_text.startswith('Oficio') or
                                  re.match(r'^\d+', link_text)):

                    doc_url = urljoin(self.base_url, href)

                    # Intentar obtener contexto (tema y descriptor)
                    tema = ""
                    descriptor = ""

                    # Buscar hacia atrás en el HTML para encontrar tema y descriptor
                    parent = link.parent
                    while parent and parent.name != 'body':
                        parent_text = parent.get_text()

                        if not tema and 'Tema:' in parent_text:
                            tema_match = re.search(r'Tema:\s*([^\n]+?)(?:Descriptor:|$)', parent_text, re.DOTALL)
                            if tema_match:
                                tema = tema_match.group(1).strip()

                        if not descriptor and 'Descriptor:' in parent_text:
                            desc_match = re.search(r'Descriptor:\s*([^\n]+?)(?:\[|$)', parent_text, re.DOTALL)
                            if desc_match:
                                descriptor = desc_match.group(1).strip()

                        if tema and descriptor:
                            break

                        parent = parent.parent

                    documents.append({
                        'url': doc_url,
                        'numero': link_text,
                        'tipo': 'concepto' if '/concepto/' in href else 'oficio',
                        'tema': tema,
                        'descriptor': descriptor
                    })

        return documents

    def process_document(self, doc_url: str) -> Optional[Dict]:
        """Procesar un documento individual y retornar con el soup completo"""
        try:
            response = self.session.get(doc_url, timeout=30)
            if response.status_code != 200:
                logger.error(f"Error HTTP {response.status_code} al obtener {doc_url}")
                return None

            soup = BeautifulSoup(response.text, 'html.parser')
            doc_info = self.extract_document_info(soup, doc_url)


            doc_info['soup'] = soup

            return doc_info

        except Exception as e:
            logger.error(f"Error procesando documento {doc_url}: {e}")
            return None

    def extract_document_info(self, soup: BeautifulSoup, url: str) -> Dict:
        """Extraer información detallada del documento"""
        info = {
            "url": url,
            "tipo_norma": "",
            "numero": "",
            "fecha": "",
            "tema": "",
            "descriptor": "",
            "archivos": [],
            "content_div": None
        }

        # Buscar por campos con clases específicas
        tipo_field = soup.find('div', class_='field--name-field-tipo-norma')
        if tipo_field:
            tipo_item = tipo_field.find('div', class_='field--item')
            if tipo_item:
                info["tipo_norma"] = tipo_item.get_text(strip=True)

        numero_field = soup.find('div', class_='field--name-field-numero')
        if numero_field:
            numero_item = numero_field.find('div', class_='field--item')
            if numero_item:
                info["numero"] = numero_item.get_text(strip=True)

        fecha_field = soup.find('div', class_='field--name-field-fecha')
        if fecha_field:
            time_elem = fecha_field.find('time')
            if time_elem and time_elem.get('datetime'):
                fecha_str = time_elem['datetime']
                fecha_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', fecha_str)
                if fecha_match:
                    info["fecha"] = fecha_match.group(0)

        titulo_field = soup.find('div', class_='field--name-field-titulo-con-formato')
        if titulo_field:
            titulo_item = titulo_field.find('div', class_='field--item')
            if titulo_item:
                tema_text = titulo_item.get_text(strip=True)
                tema_text = re.sub(r'^Tema:\s*', '', tema_text)
                info["tema"] = tema_text

        subtitulo_field = soup.find('div', class_='field--name-field-norma-subtitulo')
        if subtitulo_field:
            subtitulo_item = subtitulo_field.find('div', class_='field--item')
            if subtitulo_item:
                desc_text = subtitulo_item.get_text(strip=True)
                desc_text = re.sub(r'^Descriptor(es)?:\s*', '', desc_text)
                info["descriptor"] = desc_text

        if not info["numero"]:
            h1 = soup.find('h1', class_='page-header')
            if h1:
                h1_text = h1.get_text(strip=True)
                numero_match = re.search(r'(?:Concepto|Oficio)\s+(\d+(?:\(\d+\))?)', h1_text)
                if numero_match:
                    info["numero"] = numero_match.group(1)

        archivo_field = soup.find('div', class_='field--name-field-archivo')
        if archivo_field:
            for link in archivo_field.find_all('a', href=True):
                href = link['href']
                if href.lower().endswith('.pdf'):
                    pdf_url = urljoin(url, href)
                    pdf_name = link.get_text(strip=True) or os.path.basename(href)
                    info["archivos"].append({
                        "nombre": pdf_name,
                        "url": pdf_url
                    })

        if not info["archivos"]:
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href.lower().endswith('.pdf'):
                    pdf_url = urljoin(url, href)
                    if not any(a['url'] == pdf_url for a in info["archivos"]):
                        pdf_name = link.get_text(strip=True) or os.path.basename(href)
                        info["archivos"].append({
                            "nombre": pdf_name,
                            "url": pdf_url
                        })

        # CORRECCIÓN CRÍTICA: Guardar el contenido completo del div
        content_div = soup.find("div", class_="region region-content")
        if content_div:
            # Limpiar scripts y estilos ANTES de asignar
            for element in content_div.find_all(['script', 'style']):
                element.decompose()
            # Asignar el div completo, NO una copia vacía
            info["content_div"] = content_div

        if not info["tema"]:
            body_field = soup.find('div', class_='field--name-body')
            if body_field:
                for td in body_field.find_all('td'):
                    td_text = td.get_text(strip=True)
                    if td_text == "Tema:":
                        siguiente_td = td.find_next_sibling('td')
                        if siguiente_td:
                            info["tema"] = siguiente_td.get_text(strip=True)
                            break

        return info

    def format_document_name(self, doc_info: Dict, year: int, month: int) -> str:
        """Formatea el nombre del documento según el estándar DIAN"""
        tipo = "Concepto" if "concepto" in doc_info.get("tipo_norma", "").lower() else "Oficio"
        if not doc_info.get("tipo_norma") and doc_info.get("url"):
            tipo = "Concepto" if "/concepto/" in doc_info["url"] else "Oficio"

        numero = doc_info.get("numero", "")
        numero_match = re.search(r'(\d+)', numero)
        if numero_match:
            numero = numero_match.group(1)

        fecha_str = doc_info.get("fecha", "")
        if fecha_str:
            try:
                fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d")
                fecha_formateada = fecha_obj.strftime("%d/%m/%Y")
            except:
                fecha_formateada = f"01/{month:02d}/{year}"
        else:
            fecha_formateada = f"01/{month:02d}/{year}"

        return f"Dirección de Impuestos y Aduanas Nacionales, {tipo} nro. {numero} de {fecha_formateada}"

    def save_document(self, doc_data: Dict, base_folder: str, year: int, month: int):
        """Guardar documento - versión corregida usando el soup original"""
        try:
            tema = doc_data.get('tema', '').strip() or "SIN_CLASIFICAR"
            tema_folder = tema.upper().replace(" ", "_").replace("/", "_")

            year_folder = os.path.join(base_folder, str(year))
            month_folder = os.path.join(year_folder, f"{month:02d}")
            tema_path = os.path.join(month_folder, tema_folder)

            os.makedirs(tema_path, exist_ok=True)

            formatted_name = self.format_document_name(doc_data, year, month)
            safe_filename = formatted_name.replace("/", "-").replace(":", "_")

            html_path = os.path.join(tema_path, f"{safe_filename}.html")

            if os.path.exists(html_path):
                logger.info(f"Archivo ya existe: {safe_filename}")
                return

            # USAR EL SOUP ORIGINAL DEL DOCUMENTO
            soup = doc_data.get('soup')
            if not soup:
                logger.error(f"No hay soup disponible para {doc_data.get('numero')}")
                return

            with open(html_path, 'w', encoding='utf-8') as f:
                f.write("""
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>
                        body { font-family: Arial, sans-serif; margin: 40px; }
                        h1 { color: #2c3e50; }
                        .metadata { background: #f8f9fa; padding: 20px; margin: 20px 0; }
                        .keywords { color: #666; font-style: italic; }
                        .content { margin-top: 30px; }
                        .attachments { margin: 20px 0; }
                        .attachments ul { list-style-type: none; padding-left: 0; }
                        .attachments li { margin: 10px 0; }
                        .attachments a { color: #3498db; text-decoration: none; }
                        .attachments a:hover { text-decoration: underline; }
                    </style>
                </head>
                <body>
                """)

                f.write(f"<h1>{formatted_name}</h1>")

                f.write('<div class="metadata">')
                f.write(f'<p><strong>Fecha:</strong> {doc_data.get("fecha", "")}</p>')
                f.write(f'<p><strong>Tema:</strong> {doc_data.get("tema", "")}</p>')
                f.write(f'<p><strong>Descriptor:</strong> {doc_data.get("descriptor", "")}</p>')

                if doc_data.get("archivos"):
                    f.write('<div class="attachments">')
                    f.write('<p><strong>Archivos adjuntos:</strong></p><ul>')
                    for archivo in doc_data["archivos"]:
                        archivo_nombre = archivo["nombre"]
                        f.write(f'<li><a href="{safe_filename}_{archivo_nombre}">{archivo_nombre}</a></li>')
                    f.write('</ul></div>')
                f.write('</div>')

                # CORRECCIÓN: Usar el div del soup original, igual que el script original
                f.write('<div class="content">')
                content_div = soup.find("div", class_="region region-content")
                if content_div:
                    # Limpiar scripts y estilos
                    for script in content_div.find_all("script"):
                        script.decompose()
                    for style in content_div.find_all("style"):
                        style.decompose()
                    # Escribir el contenido completo
                    f.write(str(content_div))
                f.write('</div>')

                f.write("</body></html>")

            logger.info(f"Guardado: {formatted_name}")

            for archivo in doc_data.get("archivos", []):
                url = archivo.get("url")
                nombre = archivo.get("nombre", "").replace(" ", "_")
                if url:
                    pdf_filename = f"{safe_filename}_{nombre}"
                    success = self.download_pdf(url, tema_path, pdf_filename)
                    if not success:
                        logger.warning(f"No se pudo descargar PDF: {url}")

        except Exception as e:
            logger.error(f"Error guardando documento: {e}")

    def download_pdf(self, pdf_url: str, folder: str, filename: str) -> bool:
        """Descargar PDF"""
        try:
            if not filename.endswith('.pdf'):
                filename = filename + '.pdf'

            filepath = os.path.join(folder, filename)

            if os.path.exists(filepath):
                logger.debug(f"PDF ya existe: {filename}")
                return True

            response = self.session.get(pdf_url, stream=True, timeout=60)
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                logger.info(f"  PDF descargado: {filename}")
                return True
            else:
                logger.warning(f"  Error HTTP {response.status_code} descargando PDF")
                return False

        except Exception as e:
            logger.error(f"  Error descargando PDF: {e}")
            return False


