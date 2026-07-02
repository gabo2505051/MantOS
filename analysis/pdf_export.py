import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import pandas as pd
from fpdf import FPDF

COLOR_PRIMARIO = (41, 128, 185)       # Azul ejecutivo
COLOR_SECUNDARIO = (52, 152, 219)     # Azul claro
COLOR_FONDO_TABLA = (236, 240, 241)   # Gris claro
COLOR_TEXTO = (44, 62, 80)            # Gris oscuro
ROW_HEIGHT = 8
PAGE_BOTTOM_MARGIN = 25

class ReportePDF(FPDF):
    """Clase PDF ejecutiva con header/footer corporativos y soporte multi-página."""

    def __init__(self, title="Reporte Ejecutivo MantOS"):
        super().__init__()
        self.report_title = title
        self.alias_nb_pages()

    def header(self) -> None:
        self.set_font('helvetica', 'B', 20)
        self.set_text_color(*COLOR_PRIMARIO)
        self.cell(0, 15, self.report_title, align='C', ln=1)

        self.set_font('helvetica', 'I', 10)
        self.set_text_color(*COLOR_TEXTO)
        fecha_actual = datetime.now().strftime('%d/%m/%Y %H:%M')
        self.cell(0, 10, f'Fecha de generación: {fecha_actual}', align='C', ln=1)

        self.set_draw_color(*COLOR_PRIMARIO)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Página {self.page_no()}/{{nb}}', align='C')

    def _escribir_encabezado_tabla(self, columnas: List[str], anchos: List[int]) -> None:
        self.set_font('helvetica', 'B', 8)
        self.set_fill_color(*COLOR_PRIMARIO)
        self.set_text_color(255, 255, 255)
        for col, ancho in zip(columnas, anchos):
            self.cell(ancho, ROW_HEIGHT, col, border=1, align='C', fill=True)
        self.ln()
        self.set_text_color(*COLOR_TEXTO)
        self.set_font('helvetica', '', 9)

    def tabla_con_paginacion(self, df: pd.DataFrame, anchos: List[int]) -> None:
        columnas = list(df.columns)
        self._escribir_encabezado_tabla(columnas, anchos)

        fill = False
        for _, fila in df.iterrows():
            if self.get_y() + ROW_HEIGHT > self.h - PAGE_BOTTOM_MARGIN:
                self.add_page()
                self._escribir_encabezado_tabla(columnas, anchos)
                fill = False

            if fill:
                self.set_fill_color(*COLOR_FONDO_TABLA)
            else:
                self.set_fill_color(255, 255, 255)

            for valor, ancho in zip(fila, anchos):
                if isinstance(valor, float):
                    str_valor = f"{valor:,.2f}"
                elif isinstance(valor, int):
                    str_valor = f"{valor:,}"
                else:
                    str_valor = str(valor)
                
                # Truncate text if it's too long
                max_chars = int(ancho / 2.5) # approximate chars that fit
                if len(str_valor) > max_chars:
                    str_valor = str_valor[:max_chars-3] + "..."
                    
                self.cell(ancho, ROW_HEIGHT, str_valor, border=1, align='C', fill=fill)
            self.ln()
            fill = not fill

    def add_section_title(self, title: str):
        self.ln(5)
        self.set_font('helvetica', 'B', 14)
        self.set_text_color(*COLOR_TEXTO)
        self.cell(0, 10, title, ln=1)
        self.ln(2)

    def add_key_value(self, key: str, value: str):
        self.set_font('helvetica', 'B', 11)
        self.set_text_color(*COLOR_TEXTO)
        self.cell(60, 7, key, ln=0)
        self.set_font('helvetica', '', 11)
        self.cell(0, 7, value, ln=1)

    def add_bullet_point(self, text: str):
        self.set_font('helvetica', '', 11)
        self.cell(5, 7, "-", ln=0)
        self.multi_cell(0, 7, text)

    def add_image_if_exists(self, img_path: Optional[str]):
        if not img_path or not os.path.exists(img_path):
            return
            
        if self.get_y() + 90 > self.h - PAGE_BOTTOM_MARGIN:
            self.add_page()
            
        ancho_pagina = self.w - 2 * self.l_margin
        ancho_imagen = min(160, ancho_pagina)
        x_imagen = (ancho_pagina - ancho_imagen) / 2 + self.l_margin
        
        try:
            self.image(img_path, x=x_imagen, w=ancho_imagen)
            self.ln(5)
        except Exception as e:
            self.set_font('helvetica', 'I', 10)
            self.cell(0, 10, f'(Error cargando imagen: {e})', align='C', ln=1)
