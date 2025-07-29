# utils/form_helpers.py
# Funciones para procesar formularios web

def build_search_params(form):
    """
    Convierte los datos del formulario web a los parámetros exactos
    que necesita el scraper judicial
    """

    # 1) Salas: vienen de <select name="salas[]" multiple>
    selected = form.getlist('salas[]')
    scivil = [v for v in selected if 'CASACIÓN CIVIL' in v]
    # CORREGIDO: incluir tanto DESCONGESTIÓN como CASACIÓN LABORAL
    slaboral = [v for v in selected if 'LABORAL' in v]
    spenal = [v for v in selected if 'Sala Especial' in v or 'Casación Penal' in v]
    splena = [v for v in selected if v == 'SALA PLENA']

    # 2) Fechas (DD/MM/YYYY)
    fecha_ini = form.get('start_date', '')
    fecha_fin = form.get('end_date', '')

    # 3) Radio buttons
    asunto_value = form.get('asunto', 'TODO')
    publicacion_value = form.get('publicacion', '')

    # 4) Tipo de providencia
    providencia_value = form.get('providencia', 'SENTENCIA')

    # 5) Ámbito temático (checkboxes)
    ambito_values = form.getlist('ambito[]')

    # 6) Tema libre (cuando se implemente)
    tema_value = form.get('tema', '')

    # Mapeos para los valores - CORREGIDOS
    ASUNTO_MAP = {
        'ASUNTOS DE SALA': 'ASUNTOS DE SALA',
        'TUTELA': 'TUTELA',
        'TODO': 'TODO'
    }

    PUBLICACION_MAP = {
        'RELEVANTE': 'RELEVANTE',
        'PUBLICADA': 'PUBLICADA',
        '': ''  # CORREGIDO: Todas (valor vacío) mapea a cadena vacía
    }

    # ViewState placeholder (se obtendrá dinámicamente en el scraper)
    viewstate = 'PLACEHOLDER_VIEWSTATE'

    # Parámetros en el formato exacto que necesita el scraper
    params = {
        # JSF/AJAX base
        'javax.faces.partial.ajax': 'true',
        'javax.faces.source': 'searchForm:searchButton',
        'javax.faces.partial.execute': '@all',
        'javax.faces.partial.render': 'resultForm:jurisTable resultForm:pagText2 resultForm:selectAllButton',
        'searchForm:searchButton': 'searchForm:searchButton',
        'searchForm': 'searchForm',

        # Campos de tema y focus
        # Tema con formato especial (ya formateado)
        'searchForm:temaInput': f'"{tema_value}"' if tema_value else '',
        'searchForm:scivil_focus': '',
        'searchForm:slaboral_focus': '',
        'searchForm:spenal_focus': '',
        'searchForm:splena_focus': '',

        # Radio buttons
        'searchForm:relevanteselect': PUBLICACION_MAP[publicacion_value],
        'searchForm:tutelaselect': ASUNTO_MAP[asunto_value],

        # Otros campos base
        'searchForm:options1': '0',
        'searchForm:fulltxtInput': '',
        'searchForm:set-fulltxt_collapsed': 'true',
        'searchForm:ponenteInput': '',
        'searchForm:set-ponente_collapsed': 'true',
        'searchForm:set-fecha_collapsed': 'false',
        'searchForm:radicadoInput': '',
        'searchForm:set-radicado_collapsed': 'true',
        'searchForm:providenciaInput': '',
        'searchForm:set-providencia_collapsed': 'true',
        'searchForm:idInput': '',
        'searchForm:set-id_collapsed': 'true',
        'searchForm:set-tipo_collapsed': 'false',
        'searchForm:claseInput': '',
        'searchForm:set-clase_collapsed': 'true',
        'searchForm:fuenteInput': '',
        'searchForm:set-fuente_collapsed': 'true',
        'searchForm:jurisInput': '',
        'searchForm:set-juris_collapsed': 'true',
        'searchForm:procedenciaInput': '',
        'searchForm:set-procedencia_collapsed': 'true',
        'searchForm:delitosInput': '',
        'searchForm:set-delitos_collapsed': 'true',
        'searchForm:sujetosInput': '',
        'searchForm:set-sujetos_collapsed': 'true',
        'searchForm:servidorInput': '',
        'searchForm:set-servidor_collapsed': 'true',
        'searchForm:categoriaInput': '',
        'searchForm:set-categoria_collapsed': 'true',
        'javax.faces.ViewState': viewstate,

        # OPCIONES CONFIGURABLES DESDE EL FORMULARIO
        # Tipo de providencia con formato especial (ya formateado)
        'searchForm:tipoInput': f'"{providencia_value}"' if providencia_value else '',
        

        # Fechas
        'searchForm:fechaIniCal': fecha_ini,
        'searchForm:fechaFinCal': fecha_fin,
        # Ámbito temático
        'searchForm:j_idt187': ambito_values,
        # Salas
        'searchForm:scivil': scivil,
        'searchForm:slaboral': slaboral,
        'searchForm:spenal': spenal,
        'searchForm:splena': splena,
    }

    return params