"""
kyc/pilotage_exports.py
Génération des rapports PDF et PPTX pour le Pilotage KYC.
Utilise ReportLab (PDF) et python-pptx (PPTX).
"""

import io
import os
import math
from datetime import datetime

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

# ─── ReportLab ────────────────────────────────────────────────────────────────
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table,
    TableStyle, KeepTogether, HRFlowable,
)
from reportlab.platypus.flowables import Flowable
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics import renderPDF
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib.utils import ImageReader

# ─── python-pptx ──────────────────────────────────────────────────────────────
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor

# ─── Palette BOA ──────────────────────────────────────────────────────────────
BOA_GREEN       = colors.HexColor("#00965E")   # Vert BOA officiel
BOA_GREEN_LIGHT = colors.HexColor("#E8F5E9")   # Fond vert clair
BOA_GREEN_MED   = colors.HexColor("#81C784")
BOA_DARK        = colors.HexColor("#0f172a")
BOA_BLUE        = colors.HexColor("#1B2A4A")   # Bleu marine BOA
BOA_BLUE_LIGHT  = colors.HexColor("#2563eb")   # Bleu accent
BOA_SLATE       = colors.HexColor("#64748b")
BOA_RED         = colors.HexColor("#ef4444")
BOA_RED_LIGHT   = colors.HexColor("#fee2e2")
BOA_AMBER       = colors.HexColor("#f59e0b")
BOA_AMBER_LIGHT = colors.HexColor("#fef3c7")
BOA_WHITE       = colors.white
BOA_GRAY        = colors.HexColor("#f1f5f9")
BOA_BORDER      = colors.HexColor("#e2e8f0")

# ─── Palette PPTX — Charte BOA officielle ────────────────────────────────────
PPTX_GREEN       = RGBColor(0x00, 0x96, 0x5E)   # Vert BOA        #00965E
PPTX_GREEN_DEEP  = RGBColor(0x00, 0x6B, 0x42)   # Vert sombre     #006B42
PPTX_GREEN_SOFT  = RGBColor(0xE8, 0xF5, 0xEE)   # Vert très pâle  #E8F5EE
PPTX_DARK        = RGBColor(0x1B, 0x2A, 0x4A)   # Marine BOA      #1B2A4A
PPTX_DARK_DEEP   = RGBColor(0x0F, 0x17, 0x2A)   # Marine profond  #0F172A
PPTX_RED         = RGBColor(0xEF, 0x44, 0x44)   # Rouge alerte
PPTX_RED_SOFT    = RGBColor(0xFF, 0xEB, 0xEB)   # Rouge très pâle
PPTX_AMBER       = RGBColor(0xF5, 0x9E, 0x0B)   # Ambre attention
PPTX_AMBER_SOFT  = RGBColor(0xFE, 0xF3, 0xC7)   # Ambre très pâle
PPTX_SLATE       = RGBColor(0x64, 0x74, 0x8B)   # Gris ardoise
PPTX_GRAY        = RGBColor(0xE2, 0xE8, 0xF0)   # Gris clair border
PPTX_GRAY_BG     = RGBColor(0xF8, 0xFA, 0xFC)   # Fond très clair
PPTX_GRAY_TEXT   = RGBColor(0x94, 0xA3, 0xB8)   # Texte secondaire
PPTX_WHITE       = RGBColor(0xFF, 0xFF, 0xFF)
PPTX_GREEN_LIGHT = RGBColor(0xBB, 0xF7, 0xD0)   # Vert clair accent
PPTX_GREEN_PALE  = RGBColor(0xDC, 0xFC, 0xE7)   # Vert pâle décoratif
PPTX_GOLD        = RGBColor(0xF5, 0xC5, 0x18)   # Or accent premium

LOGO_PATH = os.path.join(settings.MEDIA_ROOT, "images", "boa_logo.png")


def _logo_path():
    if os.path.isfile(LOGO_PATH):
        return LOGO_PATH
    return None


def _rate_color(rate, threshold):
    """Retourne la couleur en fonction du taux."""
    if rate is None:
        return BOA_SLATE
    if rate < threshold:
        return BOA_RED
    if rate < threshold + 5:
        return BOA_AMBER
    return BOA_GREEN


def _rate_color_pptx(rate, threshold):
    if rate is None:
        return PPTX_SLATE
    if rate < threshold:
        return PPTX_RED
    if rate < threshold + 5:
        return PPTX_AMBER
    return PPTX_GREEN


# ═══════════════════════════════════════════════════════════════════════════════
#  MINI-BARRE DE PROGRESSION (Flowable ReportLab)
# ═══════════════════════════════════════════════════════════════════════════════

class RateBar(Flowable):
    """Petite barre de progression colorée pour les tableaux."""
    def __init__(self, rate, threshold, width=60, height=8):
        super().__init__()
        self.rate = rate
        self.threshold = threshold
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        rate = self.rate if self.rate is not None else 0
        fill_pct = min(max(rate, 0), 100) / 100
        bar_color = _rate_color(self.rate, self.threshold)

        # Fond gris
        c.setFillColor(BOA_GRAY)
        c.roundRect(0, 0, self.width, self.height, 3, fill=1, stroke=0)
        # Barre colorée
        c.setFillColor(bar_color)
        c.roundRect(0, 0, self.width * fill_pct, self.height, 3, fill=1, stroke=0)

    def wrap(self, available_width, available_height):
        return self.width, self.height


class SetSectionTitle(Flowable):
    """Flowable permettant de changer le titre de la section courante sur le canvas."""
    def __init__(self, title):
        super().__init__()
        self.title = title

    def draw(self):
        self.canv._current_section_title = self.title

    def wrap(self, availWidth, availHeight):
        return 0, 0


# ═══════════════════════════════════════════════════════════════════════════════
#  STYLES COMMUNS
# ═══════════════════════════════════════════════════════════════════════════════

def _build_pdf_styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "title", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=22, textColor=BOA_WHITE,
            leading=26, alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"],
            fontName="Helvetica", fontSize=10, textColor=BOA_GREEN_MED,
            leading=14, alignment=TA_LEFT,
        ),
        "section_title": ParagraphStyle(
            "section_title", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=12, textColor=BOA_WHITE,
            leading=16, alignment=TA_LEFT,
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=7, textColor=BOA_SLATE,
            leading=10, alignment=TA_CENTER, spaceAfter=2,
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=22, textColor=BOA_DARK,
            leading=26, alignment=TA_CENTER,
        ),
        "kpi_value_red": ParagraphStyle(
            "kpi_value_red", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=22, textColor=BOA_RED,
            leading=26, alignment=TA_CENTER,
        ),
        "th": ParagraphStyle(
            "th", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=7, textColor=BOA_WHITE,
            leading=10, alignment=TA_LEFT,
        ),
        "td": ParagraphStyle(
            "td", parent=base["Normal"],
            fontName="Helvetica", fontSize=7, textColor=BOA_DARK,
            leading=10, alignment=TA_LEFT,
        ),
        "td_right": ParagraphStyle(
            "td_right", parent=base["Normal"],
            fontName="Helvetica", fontSize=7, textColor=BOA_DARK,
            leading=10, alignment=TA_RIGHT,
        ),
        "td_bold": ParagraphStyle(
            "td_bold", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=7, textColor=BOA_DARK,
            leading=10, alignment=TA_LEFT,
        ),
        "rate_tag": ParagraphStyle(
            "rate_tag", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=8, textColor=BOA_WHITE,
            leading=11, alignment=TA_CENTER,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["Normal"],
            fontName="Helvetica", fontSize=7, textColor=BOA_SLATE,
            leading=10, alignment=TA_CENTER,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"],
            fontName="Helvetica", fontSize=9, textColor=BOA_DARK,
            leading=13, alignment=TA_LEFT,
        ),
        "chart_title": ParagraphStyle(
            "chart_title", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=9, textColor=BOA_DARK,
            leading=13, alignment=TA_LEFT, spaceAfter=6,
        ),
        "toc_title": ParagraphStyle(
            "toc_title", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=16, textColor=BOA_BLUE,
            leading=22, alignment=TA_LEFT, spaceAfter=12,
        ),
        "toc_entry": ParagraphStyle(
            "toc_entry", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=10, textColor=BOA_DARK,
            leading=16, alignment=TA_LEFT, spaceBefore=4,
        ),
        "toc_sub": ParagraphStyle(
            "toc_sub", parent=base["Normal"],
            fontName="Helvetica", fontSize=9, textColor=BOA_SLATE,
            leading=14, alignment=TA_LEFT, leftIndent=20,
        ),
        "page_tag": ParagraphStyle(
            "page_tag", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=8, textColor=BOA_WHITE,
            leading=11, alignment=TA_RIGHT,
        ),
    }
    return styles


# ═══════════════════════════════════════════════════════════════════════════════
#  GRAPHIQUE BARRES HORIZONTALES (ReportLab)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_completeness_bar_chart(rows, threshold, max_items=15):
    """Construit un HorizontalBarChart ReportLab pour la complétude."""
    if not rows:
        return None

    items = rows[:max_items]
    labels = [f"{r['type']} - {r['field_label'][:22]}" for r in items]
    values = [r["rate"] if r["rate"] is not None else 0 for r in items]
    n = len(items)

    chart_height = max(120, n * 18 + 40)
    chart_width = 480

    drawing = Drawing(chart_width, chart_height)
    bc = HorizontalBarChart()
    bc.x = 160
    bc.y = 20
    bc.width = 260
    bc.height = chart_height - 40
    bc.data = [values]
    bc.categoryAxis.categoryNames = labels
    bc.categoryAxis.labels.fontSize = 7
    bc.categoryAxis.labels.fontName = "Helvetica"
    bc.categoryAxis.labels.dx = -4
    bc.categoryAxis.labels.textAnchor = "end"
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = 100
    bc.valueAxis.valueStep = 20
    bc.valueAxis.labels.fontSize = 7
    bc.valueAxis.labels.fontName = "Helvetica"
    bc.bars[0].strokeColor = None

    # Affichage des taux à côté des barres
    bc.barLabelFormat = '%0.1f%%'
    bc.barLabels.fontName = "Helvetica-Bold"
    bc.barLabels.fontSize = 6
    bc.barLabels.fillColor = BOA_BLUE
    bc.barLabels.boxAnchor = 'w'
    bc.barLabels.textAnchor = 'start'
    bc.barLabels.dx = 4
    bc.barLabels.nudge = 4

    # Colorer chaque barre individuellement selon le seuil
    for i, rate in enumerate(values):
        bc.bars[0, i].fillColor = _rate_color(rate, threshold)

    drawing.add(bc)

    # Ligne de seuil verticale
    seuil_x = bc.x + (threshold / 100) * bc.width
    line = Line(seuil_x, bc.y, seuil_x, bc.y + bc.height,
                strokeColor=BOA_RED, strokeWidth=1, strokeDashArray=[3, 3])
    drawing.add(line)

    return drawing


def _build_quality_bar_chart(rows, threshold, max_items=15):
    """Construit un HorizontalBarChart pour la qualité."""
    if not rows:
        return None

    items = rows[:max_items]
    labels = [f"{r['type']} - {r['rule_name'][:20]}" for r in items]
    values = [r["rate"] if r["rate"] is not None else 0 for r in items]
    n = len(items)

    chart_height = max(120, n * 18 + 40)
    chart_width = 480

    drawing = Drawing(chart_width, chart_height)
    bc = HorizontalBarChart()
    bc.x = 160
    bc.y = 20
    bc.width = 260
    bc.height = chart_height - 40
    bc.data = [values]
    bc.categoryAxis.categoryNames = labels
    bc.categoryAxis.labels.fontSize = 7
    bc.categoryAxis.labels.fontName = "Helvetica"
    bc.categoryAxis.labels.dx = -4
    bc.categoryAxis.labels.textAnchor = "end"
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = 100
    bc.valueAxis.valueStep = 20
    bc.valueAxis.labels.fontSize = 7
    bc.valueAxis.labels.fontName = "Helvetica"
    bc.bars[0].strokeColor = None

    # Affichage des taux à côté des barres
    bc.barLabelFormat = '%0.1f%%'
    bc.barLabels.fontName = "Helvetica-Bold"
    bc.barLabels.fontSize = 6
    bc.barLabels.fillColor = BOA_BLUE
    bc.barLabels.boxAnchor = 'w'
    bc.barLabels.textAnchor = 'start'
    bc.barLabels.dx = 4
    bc.barLabels.nudge = 4

    # Colorer chaque barre individuellement selon le seuil
    for i, rate in enumerate(values):
        bc.bars[0, i].fillColor = _rate_color(rate, threshold)

    drawing.add(bc)

    seuil_x = bc.x + (threshold / 100) * bc.width
    line = Line(seuil_x, bc.y, seuil_x, bc.y + bc.height,
                strokeColor=BOA_RED, strokeWidth=1, strokeDashArray=[3, 3])
    drawing.add(line)

    return drawing


# ═══════════════════════════════════════════════════════════════════════════════
#  EN-TÊTE / PIED DE PAGE PDF
# ═══════════════════════════════════════════════════════════════════════════════

class _HeaderFooterCanvas(pdfcanvas.Canvas):
    """
    Canvas personnalisé qui ajoute sur chaque page :
    - En-tête bleu BOA avec titre de section (haut à droite) + logo (haut à droite)
    - Pied de page marine avec numérotation des pages
    """

    def __init__(self, *args, scope_label="", threshold=90, date_str="",
                 page_titles=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._scope_label = scope_label
        self._threshold = threshold
        self._date_str = date_str
        self._current_section_title = ""
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_header_footer(num_pages)
            pdfcanvas.Canvas.showPage(self)
        pdfcanvas.Canvas.save(self)

    def _draw_header_footer(self, num_pages):
        w, h = A4
        pn = self._pageNumber  # numéro de page courant

        # ═══════════════════════════════════════════
        # EN-TÊTE (à partir de la page 2)
        # ═══════════════════════════════════════════
        if pn > 1:
            self.saveState()
            HEADER_H = 1.3 * cm

            # ── Bandeau gauche vert BOA (titre rapport) ──
            self.setFillColor(BOA_GREEN)
            self.rect(0, h - HEADER_H, w * 0.55, HEADER_H, fill=1, stroke=0)

            # ── Bandeau droite bleu marine BOA (titre de section) ──
            self.setFillColor(BOA_BLUE)
            self.rect(w * 0.55, h - HEADER_H, w * 0.45, HEADER_H, fill=1, stroke=0)

            # ── Logo BOA en haut à droite (dans bandeau bleu) ──
            logo = _logo_path()
            if logo:
                try:
                    logo_h = HEADER_H - 0.15 * cm
                    self.drawImage(
                        logo,
                        w - 3.2 * cm, h - HEADER_H + 0.08 * cm,
                        width=2.8 * cm,
                        height=logo_h,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
                except Exception:
                    pass
            else:
                # Fallback texte si pas de logo
                self.setFillColor(BOA_WHITE)
                self.setFont("Helvetica-Bold", 7)
                self.drawRightString(w - 0.4 * cm, h - HEADER_H + 0.55 * cm, "BOA GROUP")

            # ── Titre rapport (bandeau vert gauche) ──
            self.setFillColor(BOA_WHITE)
            self.setFont("Helvetica-Bold", 8)
            self.drawString(0.5 * cm, h - HEADER_H + 0.70 * cm,
                            "RAPPORT DE PILOTAGE KYC — BOA GROUP")
            self.setFont("Helvetica", 7)
            self.drawString(0.5 * cm, h - HEADER_H + 0.35 * cm,
                            f"Périmètre : {self._scope_label}  |  Seuil : {self._threshold:.1f}%")

            # ── Titre de section (bandeau bleu, haut à droite) ──
            section_title = getattr(self, "_current_section_title", "")
            if section_title:
                self.setFillColor(BOA_WHITE)
                self.setFont("Helvetica-Bold", 8)
                # Centré verticalement et horizontalement dans le bandeau bleu (hors zone logo)
                self.drawCentredString(
                    w * 0.55 + (w * 0.45 - 3.5 * cm) / 2,
                    h - HEADER_H + 0.55 * cm,
                    section_title,
                )

            self.restoreState()

        # ═══════════════════════════════════════════
        # PIED DE PAGE (toutes les pages sauf page 1)
        # ═══════════════════════════════════════════
        if pn > 1:
            self.saveState()
            FOOTER_H = 0.9 * cm

            # Fond marine
            self.setFillColor(BOA_BLUE)
            self.rect(0, 0, w, FOOTER_H, fill=1, stroke=0)

            # Ligne de séparation verte
            self.setStrokeColor(BOA_GREEN)
            self.setLineWidth(1.5)
            self.line(0, FOOTER_H, w, FOOTER_H)

            self.setFillColor(BOA_WHITE)
            self.setFont("Helvetica-Bold", 7)
            self.drawString(0.5 * cm, 0.32 * cm, "BOA Group — Confidentiel")

            self.setFont("Helvetica", 7)
            self.drawCentredString(
                w / 2, 0.32 * cm,
                f"Rapport généré automatiquement le {self._date_str} — Ne pas diffuser sans autorisation"
            )

            # Numéro de page (haut à droite du footer)
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(BOA_GREEN_MED)
            self.drawRightString(w - 0.5 * cm, 0.32 * cm,
                                 f"Page {pn} / {num_pages}")

            self.restoreState()


# ═══════════════════════════════════════════════════════════════════════════════
#  EXPORT PDF
# ═══════════════════════════════════════════════════════════════════════════════

# ── Titres par numéro de page (pour le bandeau haut à droite) ──────────────
_PDF_PAGE_TITLES = {
    2: "SOMMAIRE",
    3: "SYNTHÈSE KPI",
    4: "DÉTAIL COMPLÉTUDE",
    5: "DÉTAIL QUALITÉ",
}


def export_pilotage_pdf(scope_data, summary, completeness_rows, quality_rows):
    """
    Génère un rapport PDF professionnel avec logo BOA, graphiques et tableaux.
    - Logo BOA en haut à droite sur chaque page
    - Sommaire sur la page 2
    - Titre de section (bandeau bleu) en haut à droite
    - Pied de page avec numérotation
    Retourne un HttpResponse avec le PDF en pièce jointe.
    """
    scope = scope_data["scope"]
    selected_filiale = scope_data.get("selected_filiale", "")
    scope_label = "GROUPE" if scope == "groupe" else selected_filiale
    threshold = summary.get("threshold", 90.0)
    date_str = timezone.localtime().strftime("%d/%m/%Y à %H:%M")
    styles = _build_pdf_styles()

    buffer = io.BytesIO()
    w, h = A4

    # ── Document ──
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=2.2 * cm,   # marge haute augmentée pour l'en-tête
        bottomMargin=1.8 * cm,  # marge basse augmentée pour le pied
    )

    frame_normal = Frame(
        doc.leftMargin, doc.bottomMargin,
        w - doc.leftMargin - doc.rightMargin,
        h - doc.topMargin - doc.bottomMargin,
        id="normal",
    )

    # Page de couverture (sans marges)
    frame_cover = Frame(0, 0, w, h, id="cover", leftPadding=0, rightPadding=0,
                        topPadding=0, bottomPadding=0)

    templates = [
        PageTemplate(id="cover", frames=[frame_cover], onPage=lambda c, d: None),
        PageTemplate(id="normal", frames=[frame_normal]),
    ]
    doc.addPageTemplates(templates)

    story = []

    # ═══════════════════════════════════════════════════════
    # PAGE 1 : COUVERTURE
    # ═══════════════════════════════════════════════════════

    class CoverPage(Flowable):
        def draw(self):
            cnv = self.canv
            pw, ph = A4

            # Fond Vert BOA (haut 55%)
            cnv.setFillColor(BOA_GREEN)
            cnv.rect(0, ph * 0.45, pw, ph * 0.55, fill=1, stroke=0)

            # Triangle décoratif (via polygon)
            cnv.setFillColor(colors.HexColor("#166534"))
            path = cnv.beginPath()
            path.moveTo(0, ph * 0.45)
            path.lineTo(pw * 0.6, ph * 0.45)
            path.lineTo(0, ph * 0.30)
            path.close()
            cnv.drawPath(path, fill=1, stroke=0)

            # ── Logo BOA en haut à droite sur la couverture ──
            logo = _logo_path()
            if logo:
                try:
                    logo_h = 2.0 * cm
                    cnv.drawImage(
                        logo, pw - 5.5 * cm, ph - 2.3 * cm,
                        width=4.5 * cm,
                        height=logo_h, preserveAspectRatio=True, mask="auto"
                    )
                except Exception:
                    cnv.setFillColor(BOA_WHITE)
                    cnv.setFont("Helvetica-Bold", 9)
                    cnv.drawRightString(pw - 0.5 * cm, ph - 1.0 * cm, "BOA GROUP")

            # Titre principal
            cnv.setFillColor(BOA_WHITE)
            cnv.setFont("Helvetica-Bold", 28)
            cnv.drawString(1.5 * cm, ph * 0.67, "Rapport de Pilotage")
            cnv.setFont("Helvetica-Bold", 28)
            cnv.drawString(1.5 * cm, ph * 0.62, "KYC")

            # Ligne décorative
            cnv.setStrokeColor(BOA_GREEN_MED)
            cnv.setLineWidth(2)
            cnv.line(1.5 * cm, ph * 0.59, 12 * cm, ph * 0.59)

            # Sous-titre
            cnv.setFont("Helvetica", 12)
            cnv.setFillColor(BOA_GREEN_MED)
            cnv.drawString(1.5 * cm, ph * 0.555,
                         "Analyse de la Completude et de la Qualite des Donnees")

            # Carte blanche avec bordure douce pour les informations
            cnv.setFillColor(BOA_WHITE)
            cnv.setStrokeColor(BOA_BORDER)
            cnv.setLineWidth(1)
            cnv.roundRect(1.5 * cm, ph * 0.18, pw - 3 * cm, ph * 0.16, 8, fill=1, stroke=1)

            # Disposition horizontale moderne en 3 colonnes
            cols = [
                ("Filiale", scope_label, 2.5 * cm),
                ("Seuil d'analyse", f"{threshold:.1f}%", 8.5 * cm),
                ("Date de génération", date_str, 14.2 * cm),
            ]
            for label, value, col_x in cols:
                # Label moderne
                cnv.setFillColor(BOA_SLATE)
                cnv.setFont("Helvetica-Bold", 7)
                cnv.drawString(col_x, ph * 0.27, label.upper())

                # Valeur en bleu BOA
                cnv.setFillColor(BOA_BLUE)
                cnv.setFont("Helvetica-Bold", 11)
                cnv.drawString(col_x, ph * 0.27 - 0.5 * cm, value)

        def wrap(self, *args):
            return A4

    story.append(CoverPage())

    from reportlab.platypus import NextPageTemplate, PageBreak
    story.append(NextPageTemplate("normal"))
    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════
    # PAGE 2 : SOMMAIRE
    # ═══════════════════════════════════════════════════════

    story.append(Spacer(1, 0.5 * cm))
    story.append(SetSectionTitle("SOMMAIRE"))
    story.append(Paragraph("SOMMAIRE", styles["toc_title"]))
    story.append(HRFlowable(width="100%", thickness=2, color=BOA_BLUE, spaceAfter=12))
    story.append(Spacer(1, 0.3 * cm))

    toc_entries = [
        ("01", "Synthèse des Indicateurs Clés",
         "Taux global de complétude, taux de qualité, champs et règles sous seuil", 3),
        ("02", "Détail Complétude",
         "Champs sous le seuil défini avec barres de progression", 4),
        ("03", "Vue d'ensemble Complétude",
         "Tous les champs — tableau complet avec indicateurs", 5),
        ("04", "Détail Qualité",
         "Règles de qualité sous le seuil avec indicateurs visuels", 6),
        ("05", "Vue d'ensemble Qualité",
         "Toutes les règles qualité — tableau complet", 7),
    ]

    for num, titre, desc, page_num in toc_entries:
        # Ligne d'entrée
        entry_data = [[
            Paragraph(
                f'<font color="#1B2A4A"><b>{num}</b></font>',
                ParagraphStyle("toc_num", fontName="Helvetica-Bold",
                               fontSize=14, textColor=BOA_BLUE,
                               leading=18, alignment=TA_CENTER)
            ),
            Table(
                [
                    [Paragraph(titre, styles["toc_entry"])],
                    [Paragraph(desc, styles["toc_sub"])],
                ],
                colWidths=[13 * cm],
            ),
            Paragraph(
                f'<font color="#64748b">p. {page_num}</font>',
                ParagraphStyle("toc_pg", fontName="Helvetica",
                               fontSize=9, textColor=BOA_SLATE,
                               leading=14, alignment=TA_RIGHT)
            ),
        ]]
        entry_t = Table(entry_data, colWidths=[1.2 * cm, 14 * cm, 1.8 * cm])
        entry_t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (0, 0), BOA_BLUE),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, BOA_BORDER),
        ]))
        story.append(entry_t)
        story.append(Spacer(1, 0.25 * cm))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════
    # PAGE 3 : SYNTHÈSE KPI
    # ═══════════════════════════════════════════════════════
    story.append(SetSectionTitle("SYNTHÈSE DES INDICATEURS CLÉS"))

    # Titre section
    story.append(_section_header("📊  Synthèse des Indicateurs Clés", styles))
    story.append(Spacer(1, 0.4 * cm))

    # Tableau 4 KPIs
    comp_rate = summary.get("completeness_rate")
    qual_rate = summary.get("quality_rate")
    low_comp = summary.get("low_completeness_count", 0)
    low_qual = summary.get("low_quality_count", 0)

    def _kpi_cell(label, value, unit="", red=False):
        style_v = styles["kpi_value_red"] if red else styles["kpi_value"]
        val_str = f"{value:.1f}" if isinstance(value, float) else str(value)
        return [
            Paragraph(label, styles["kpi_label"]),
            Paragraph(f"{val_str}{unit}", style_v),
        ]

    def _kpi_bg(rate, threshold, is_count=False):
        if is_count:
            return BOA_RED_LIGHT if rate > 0 else BOA_GREEN_LIGHT
        if rate is None:
            return BOA_GRAY
        if rate < threshold:
            return BOA_RED_LIGHT
        if rate < threshold + 5:
            return BOA_AMBER_LIGHT
        return BOA_GREEN_LIGHT

    kpi_data = [[
        _kpi_cell("TAUX DE COMPLÉTUDE", comp_rate if comp_rate is not None else "—", "%",
                  red=(comp_rate is not None and comp_rate < threshold)),
        _kpi_cell("TAUX DE QUALITÉ", qual_rate if qual_rate is not None else "—", "%",
                  red=(qual_rate is not None and qual_rate < threshold)),
        _kpi_cell("CHAMPS SOUS SEUIL", low_comp, "", red=low_comp > 0),
        _kpi_cell("RÈGLES SOUS SEUIL", low_qual, "", red=low_qual > 0),
    ]]

    kpi_table = Table(kpi_data, colWidths=[4.5 * cm] * 4, rowHeights=None)
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), _kpi_bg(comp_rate, threshold)),
        ("BACKGROUND", (1, 0), (1, 0), _kpi_bg(qual_rate, threshold)),
        ("BACKGROUND", (2, 0), (2, 0), _kpi_bg(low_comp, threshold, is_count=True)),
        ("BACKGROUND", (3, 0), (3, 0), _kpi_bg(low_qual, threshold, is_count=True)),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]),
        ("BOX", (0, 0), (-1, -1), 0, colors.white),
        ("INNERGRID", (0, 0), (-1, -1), 0.5 * mm, colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 0.6 * cm))

    # ─── Graphique complétude ──────────────────────────────
    if completeness_rows:
        story.append(Paragraph("Taux de complétude par champ", styles["chart_title"]))
        chart = _build_completeness_bar_chart(completeness_rows, threshold)
        if chart:
            story.append(chart)
        story.append(Spacer(1, 0.3 * cm))
        # Légende
        legend_data = [["■ Sous le seuil", "■ Proche du seuil", "■ Conforme", "– – Seuil"]]
        leg = Table(legend_data, colWidths=[3.5 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm])
        leg.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("TEXTCOLOR", (0, 0), (0, 0), BOA_RED),
            ("TEXTCOLOR", (1, 0), (1, 0), BOA_AMBER),
            ("TEXTCOLOR", (2, 0), (2, 0), BOA_GREEN),
            ("TEXTCOLOR", (3, 0), (3, 0), BOA_RED),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ]))
        story.append(leg)
        story.append(Spacer(1, 0.6 * cm))

    # ─── Graphique qualité ────────────────────────────────
    if quality_rows:
        story.append(Paragraph("Taux de conformité par règle qualité", styles["chart_title"]))
        chart_q = _build_quality_bar_chart(quality_rows, threshold)
        if chart_q:
            story.append(chart_q)
        story.append(Spacer(1, 0.3 * cm))
        # Légende Qualité
        legend_data = [["■ Sous le seuil", "■ Proche du seuil", "■ Conforme", "– – Seuil"]]
        leg_q = Table(legend_data, colWidths=[3.5 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm])
        leg_q.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("TEXTCOLOR", (0, 0), (0, 0), BOA_RED),
            ("TEXTCOLOR", (1, 0), (1, 0), BOA_AMBER),
            ("TEXTCOLOR", (2, 0), (2, 0), BOA_GREEN),
            ("TEXTCOLOR", (3, 0), (3, 0), BOA_RED),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ]))
        story.append(leg_q)
        story.append(Spacer(1, 0.4 * cm))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════
    # PAGE 4 : TABLEAU COMPLÉTUDE
    # ═══════════════════════════════════════════════════════
    story.append(SetSectionTitle("DÉTAIL COMPLÉTUDE"))

    story.append(_section_header("📋  Détail Complétude — Champs sous seuil", styles))
    story.append(Spacer(1, 0.4 * cm))

    below_comp = [r for r in completeness_rows if r.get("is_below_threshold")]
    if below_comp:
        story.append(_build_completeness_table(below_comp, threshold, styles, scope_label))
    else:
        story.append(Paragraph("✓ Aucun champ n'est sous le seuil défini.", styles["body"]))

    # Tous les champs (résumé complet sur page séparée)
    if completeness_rows:
        story.append(PageBreak())
        story.append(SetSectionTitle("VUE D'ENSEMBLE COMPLÉTUDE"))
        story.append(_section_header("📋  Vue d'ensemble — Tous les champs", styles))
        story.append(Spacer(1, 0.4 * cm))
        story.append(_build_completeness_table(completeness_rows, threshold, styles, scope_label, full=True))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════
    # PAGE 6 : TABLEAU QUALITÉ
    # ═══════════════════════════════════════════════════════
    story.append(SetSectionTitle("DÉTAIL QUALITÉ"))

    story.append(_section_header("🔍  Détail Qualité — Règles sous seuil", styles))
    story.append(Spacer(1, 0.4 * cm))

    below_qual = [r for r in quality_rows if r.get("is_below_threshold")]
    if below_qual:
        story.append(_build_quality_table(below_qual, threshold, styles))
    else:
        story.append(Paragraph("✓ Aucune règle qualité n'est sous le seuil défini.", styles["body"]))

    if quality_rows:
        story.append(PageBreak())
        story.append(SetSectionTitle("VUE D'ENSEMBLE QUALITÉ"))
        story.append(_section_header("🔍  Vue d'ensemble — Toutes les règles", styles))
        story.append(Spacer(1, 0.4 * cm))
        story.append(_build_quality_table(quality_rows, threshold, styles, full=True))

    # ── Build avec canvas personnalisé (en-tête + pied + logo) ──
    def _make_canvas(*args, **kwargs):
        return _HeaderFooterCanvas(
            *args,
            scope_label=scope_label,
            threshold=threshold,
            date_str=date_str,
            **kwargs,
        )

    doc.build(story, canvasmaker=_make_canvas)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    scope_safe = re.sub(r"[^A-Za-z0-9_-]+", "_", scope_label)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    date_file = timezone.localtime().strftime("%Y%m%d")
    response["Content-Disposition"] = (
        f'attachment; filename="rapport_pilotage_kyc_{scope_safe}_{date_file}.pdf"'
    )
    return response


# ─── Helpers pour le PDF ──────────────────────────────────────────────────────

import re

def _section_header(title, styles):
    """Retourne un bloc titre de section avec fond vert."""
    data = [[Paragraph(title, styles["section_title"])]]
    t = Table(data, colWidths=[18 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BOA_BLUE),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    return t


def _rate_badge(rate, threshold, styles):
    """Badge coloré pour afficher le taux."""
    if rate is None:
        return Paragraph("—", styles["td_right"])
    color = _rate_color(rate, threshold)
    color_hex = color.hexval() if hasattr(color, 'hexval') else "#64748b"
    # Utiliser Paragraph avec couleur inline
    rate_str = f"{rate:.1f}%"
    style = ParagraphStyle(
        "badge", fontName="Helvetica-Bold", fontSize=8,
        textColor=color, alignment=TA_RIGHT, leading=10,
    )
    return Paragraph(rate_str, style)


def _build_completeness_table(rows, threshold, styles, scope_label, full=False):
    """Construit le tableau de complétude."""
    headers = ["Type", "Périmètre", "Champ", "Total", "Incomplets", "Taux", ""]
    col_widths = [1.2 * cm, 2.5 * cm, 4 * cm, 1.5 * cm, 1.8 * cm, 1.5 * cm, 3.5 * cm]

    table_data = [[Paragraph(h, styles["th"]) for h in headers]]
    max_rows = 50 if full else len(rows)

    for row in rows[:max_rows]:
        rate = row.get("rate")
        color = _rate_color(rate, threshold)
        rate_str = f"{rate:.1f}%" if rate is not None else "—"
        rate_style = ParagraphStyle(
            "r", fontName="Helvetica-Bold", fontSize=8,
            textColor=color, alignment=TA_RIGHT, leading=10,
        )
        table_data.append([
            Paragraph(row.get("type", ""), styles["td_bold"]),
            Paragraph(row.get("filiale", scope_label), styles["td"]),
            Paragraph(row.get("field_label", ""), styles["td"]),
            Paragraph(str(row.get("total_clients", 0)), styles["td_right"]),
            Paragraph(str(row.get("missing_count", 0)), styles["td_right"]),
            Paragraph(rate_str, rate_style),
            RateBar(rate, threshold, width=65, height=7),
        ])

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        # En-tête
        ("BACKGROUND", (0, 0), (-1, 0), BOA_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), BOA_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        # Corps
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BOA_WHITE, BOA_GRAY]),
        ("GRID", (0, 0), (-1, -1), 0.3, BOA_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN", (3, 0), (5, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ])

    # Colorer les lignes sous seuil
    for i, row in enumerate(rows[:max_rows], start=1):
        if row.get("is_below_threshold"):
            style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fff5f5"))

    t.setStyle(style)
    return t


def _build_quality_table(rows, threshold, styles, full=False):
    """Construit le tableau de qualité."""
    headers = ["Type", "Périmètre", "Règle", "Champ", "Total", "Anomalies", "Taux", ""]
    col_widths = [1.0 * cm, 2.0 * cm, 3.0 * cm, 2.5 * cm, 1.3 * cm, 1.6 * cm, 1.4 * cm, 3.2 * cm]

    table_data = [[Paragraph(h, styles["th"]) for h in headers]]
    max_rows = 50 if full else len(rows)

    for row in rows[:max_rows]:
        rate = row.get("rate")
        color = _rate_color(rate, threshold)
        rate_str = f"{rate:.1f}%" if rate is not None else "—"
        rate_style = ParagraphStyle(
            "r", fontName="Helvetica-Bold", fontSize=8,
            textColor=color, alignment=TA_RIGHT, leading=10,
        )
        table_data.append([
            Paragraph(row.get("type", ""), styles["td_bold"]),
            Paragraph(row.get("scope_label", ""), styles["td"]),
            Paragraph(row.get("rule_name", "")[:30], styles["td"]),
            Paragraph(row.get("field_label", "")[:25], styles["td"]),
            Paragraph(str(row.get("total_clients", 0)), styles["td_right"]),
            Paragraph(str(row.get("fail_count", 0)), styles["td_right"]),
            Paragraph(rate_str, rate_style),
            RateBar(rate, threshold, width=60, height=7),
        ])

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BOA_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), BOA_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BOA_WHITE, BOA_GRAY]),
        ("GRID", (0, 0), (-1, -1), 0.3, BOA_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN", (4, 0), (6, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ])

    for i, row in enumerate(rows[:max_rows], start=1):
        if row.get("is_below_threshold"):
            style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fff5f5"))

    t.setStyle(style)
    return t


# ═══════════════════════════════════════════════════════════════════════════════
#  EXPORT PPTX — Style fidèle au rapport BOA exemple
# ═══════════════════════════════════════════════════════════════════════════════

def export_pilotage_pptx(scope_data, summary, completeness_rows, quality_rows):
    """
    Génère une présentation PowerPoint au style BOA officiel (Calibri, vert #009A56,
    marine #1B2A4A), avec logo en haut à droite, en-tête plein, sections vertes,
    pied de page gris — fidèle au fichier exemple rapport.
    """
    from pptx.util import Cm, Pt, Emu
    from pptx.enum.text import PP_ALIGN
    from pptx.chart.data import ChartData
    from pptx.enum.chart import XL_CHART_TYPE

    scope      = scope_data["scope"]
    fil        = scope_data.get("selected_filiale", "")
    scope_label = "GROUPE" if scope == "groupe" else fil
    threshold   = summary.get("threshold", 90.0)
    date_str    = timezone.localtime().strftime("%d/%m/%Y à %H:%M")

    # ── Dimensions slide (25.4 × 14.29 cm — 16:9) ─────────────────────────────
    prs = Presentation()
    prs.slide_width  = Cm(25.4)
    prs.slide_height = Cm(14.29)

    # ── Slide 1 : Couverture ──────────────────────────────────────────────────
    sld = _boa_blank_slide(prs)
    _boa_cover(sld, prs, scope_label, threshold, date_str)

    # ── Slide 2 : Sommaire ────────────────────────────────────────────────────
    sld_som = _boa_blank_slide(prs)
    _boa_header(sld_som, prs, "SOMMAIRE", scope_label, threshold)
    _boa_footer(sld_som, prs, date_str)
    _boa_sommaire(sld_som, prs)

    # ── Slide 3 : KPIs ────────────────────────────────────────────────────────
    sld2 = _boa_content_slide(prs, "SYNTHÈSE DES INDICATEURS CLÉS", scope_label, threshold, date_str)

    comp_rate = summary.get("completeness_rate")
    qual_rate = summary.get("quality_rate")
    low_comp  = summary.get("low_completeness_count", 0)
    low_qual  = summary.get("low_quality_count", 0)

    kpis = [
        ("TAUX DE COMPLÉTUDE",  f"{comp_rate:.1f}%" if comp_rate is not None else "—",
         _boa_rate_color(comp_rate, threshold)),
        ("TAUX DE QUALITÉ",     f"{qual_rate:.1f}%" if qual_rate is not None else "—",
         _boa_rate_color(qual_rate, threshold)),
        ("CHAMPS SOUS SEUIL",   str(low_comp),
         PPTX_RED if low_comp > 0 else PPTX_GREEN),
        ("RÈGLES SOUS SEUIL",   str(low_qual),
         PPTX_RED if low_qual > 0 else PPTX_GREEN),
    ]
    card_w = Cm(5.5)
    card_h = Cm(5.0)
    card_y = Cm(5.5)
    gap    = Cm(0.4)
    total_w = len(kpis) * card_w + (len(kpis) - 1) * gap
    start_x = (prs.slide_width - total_w) / 2
    for i, (lbl, val, col) in enumerate(kpis):
        cx = start_x + i * (card_w + gap)
        _boa_kpi_card(sld2, cx, card_y, card_w, card_h, lbl, val, col)

    # ── Slide 4 : Graphique Complétude ────────────────────────────────────────
    if completeness_rows:
        sld3 = _boa_content_slide(prs, "COMPLÉTUDE PAR CHAMP", scope_label, threshold, date_str)
        _boa_section_separator(sld3, prs, "TAUX DE COMPLÉTUDE PAR CHAMP", 2.0)
        _boa_bar_chart_native(sld3, prs, completeness_rows, threshold, "rate", "field_label", "type",
                              left_cm=1.5, top_cm=3.2, w_cm=22.4, h_cm=9.5)

    # ── Slide 5 : Tableau Complétude sous seuil ───────────────────────────────
    below_comp = [r for r in completeness_rows if r.get("is_below_threshold")]
    if below_comp:
        sld4 = _boa_content_slide(prs, f"CHAMPS SOUS SEUIL ({threshold:.0f}%) — COMPLÉTUDE", scope_label, threshold, date_str)
        hdrs4 = ["Type", "Filiale", "Champ", "Total", "Incomplets", "Taux"]
        rows4 = [
            [r.get("type",""), r.get("filiale", scope_label), r.get("field_label","")[:28],
              str(r.get("total_clients",0)), str(r.get("missing_count",0)),
              f"{r.get('rate',0):.1f}%" if r.get("rate") is not None else "—"]
            for r in below_comp[:18]
        ]
        col_w4 = [Cm(1.4), Cm(2.8), Cm(7.0), Cm(2.2), Cm(2.8), Cm(2.2)]
        _boa_table(sld4, prs, hdrs4, rows4, col_w4, below_comp, threshold, "rate")

    # ── Slide 6 : Graphique Qualité ───────────────────────────────────────────
    if quality_rows:
        sld5 = _boa_content_slide(prs, "CONFORMITÉ PAR RÈGLE QUALITÉ", scope_label, threshold, date_str)
        _boa_section_separator(sld5, prs, "TAUX DE CONFORMITÉ PAR RÈGLE QUALITÉ", 2.0)
        _boa_bar_chart_native(sld5, prs, quality_rows, threshold, "rate", "rule_name", "type",
                              left_cm=1.5, top_cm=3.2, w_cm=22.4, h_cm=9.5)

    # ── Slide 7 : Tableau Qualité sous seuil ─────────────────────────────────
    below_qual = [r for r in quality_rows if r.get("is_below_threshold")]
    if below_qual:
        sld6 = _boa_content_slide(prs, f"RÈGLES SOUS SEUIL ({threshold:.0f}%) — QUALITÉ", scope_label, threshold, date_str)
        hdrs6 = ["Type", "Filiale", "Règle", "Champ", "Total", "Anomalies", "Taux"]
        rows6 = [
            [r.get("type",""), r.get("scope_label", scope_label), r.get("rule_name","")[:24],
             r.get("field_label","")[:20], str(r.get("total_clients",0)),
             str(r.get("fail_count",0)),
             f"{r.get('rate',0):.1f}%" if r.get("rate") is not None else "—"]
            for r in below_qual[:15]
        ]
        col_w6 = [Cm(1.2), Cm(2.5), Cm(5.8), Cm(4.5), Cm(2.0), Cm(2.5), Cm(2.0)]
        _boa_table(sld6, prs, hdrs6, rows6, col_w6, below_qual, threshold, "rate")

    # ── Slide 8 : Fin de document ─────────────────────────────────────────────
    _boa_end_slide(prs, scope_label, date_str)

    # ── Build ─────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    pptx_bytes = buf.getvalue()
    buf.close()

    scope_safe = re.sub(r"[^A-Za-z0-9_-]+", "_", scope_label)
    date_file  = timezone.localtime().strftime("%Y%m%d")
    response = HttpResponse(
        pptx_bytes,
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="rapport_pilotage_kyc_{scope_safe}_{date_file}.pptx"'
    )
    return response


# ─── Helpers PPTX — style BOA officiel ───────────────────────────────────────

def _boa_blank_slide(prs):
    """Ajoute un slide vierge (layout Blank)."""
    blank = prs.slide_layouts[6]
    return prs.slides.add_slide(blank)


def _boa_rect(slide, left, top, width, height, fill_color, border_color=None):
    """Ajoute un rectangle de remplissage."""
    from pptx.util import Pt
    shape = slide.shapes.add_shape(1, int(left), int(top), int(width), int(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if border_color:
        shape.line.color.rgb = border_color
        shape.line.width = Pt(1)
    else:
        shape.line.fill.background()
    return shape

def _boa_decorative_bg(slide, prs):
    """Motif de fond simple et stylé pour toutes les slides."""
    from pptx.util import Cm
    from pptx.enum.shapes import MSO_SHAPE
    W = prs.slide_width
    H = prs.slide_height
    # Un grand motif géométrique très pâle en bas à droite
    shape = slide.shapes.add_shape(MSO_SHAPE.RIGHT_TRIANGLE, int(W - Cm(6.0)), int(H - Cm(4.0)), int(Cm(6.0)), int(Cm(4.0)))
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor(0xFA, 0xFA, 0xFA)  # très clair
    shape.line.fill.background()

def _boa_logo(slide, prs):
    """Logo est géré directement dans _boa_header et _boa_cover."""
    pass

def _boa_header(slide, prs, title, scope_label, threshold):
    """
    En-tête de page calqué sur le PDF :
    - Bande gauche verte (55%)
    - Bande droite bleue marine (45%)
    """
    from pptx.util import Cm, Pt
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    W = prs.slide_width
    H_HDR = Cm(1.3)
    
    split_x = int(W * 0.55)
    _boa_rect(slide, 0, 0, split_x, H_HDR, PPTX_GREEN)
    _boa_rect(slide, split_x, 0, W - split_x, H_HDR, PPTX_DARK)

    # Titre rapport (bandeau vert gauche)
    tb = slide.shapes.add_textbox(Cm(0.5), 0, split_x - Cm(1.0), H_HDR)
    tf = tb.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.text = f"RAPPORT DE PILOTAGE KYC — BOA GROUP\nPérimètre : {scope_label}  |  Seuil : {threshold:.1f}%"
    p.font.bold = True
    p.font.size = Pt(8)
    p.font.name = "Helvetica"
    p.font.color.rgb = PPTX_WHITE
    p.alignment = PP_ALIGN.LEFT
    
    # Titre de section (bandeau bleu)
    tb2 = slide.shapes.add_textbox(split_x + Cm(0.5), 0, W - split_x - Cm(3.5), H_HDR)
    tf2 = tb2.text_frame
    tf2.vertical_anchor = MSO_ANCHOR.MIDDLE
    p2 = tf2.paragraphs[0]
    p2.text = title
    p2.font.bold = True
    p2.font.size = Pt(8)
    p2.font.name = "Helvetica"
    p2.font.color.rgb = PPTX_WHITE
    p2.alignment = PP_ALIGN.CENTER

    # Logo
    logo = _logo_path()
    if logo:
        try:
            logo_h = H_HDR - Cm(0.15)
            slide.shapes.add_picture(
                logo,
                int(W - Cm(4.0)), int(Cm(0.08)),
                height=int(logo_h),
            )
        except Exception:
            pass

def _boa_footer(slide, prs, date_str):
    """
    Pied de page calqué sur le PDF :
    - Fond marine
    - Ligne séparatrice verte
    """
    from pptx.util import Cm, Pt
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    W = prs.slide_width
    H = prs.slide_height
    FH = Cm(0.9)
    FY = H - FH

    # Fond marine
    _boa_rect(slide, 0, FY, W, FH, PPTX_DARK)
    # Ligne verte
    _boa_rect(slide, 0, FY, W, Cm(0.05), PPTX_GREEN)

    # Texte gauche
    tb = slide.shapes.add_textbox(Cm(0.5), FY, Cm(5.0), FH)
    tf = tb.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.text = "BOA Group — Confidentiel"
    p.font.bold = True
    p.font.size = Pt(7)
    p.font.name = "Helvetica"
    p.font.color.rgb = PPTX_WHITE
    p.alignment = PP_ALIGN.LEFT

    # Texte centre
    tb2 = slide.shapes.add_textbox(Cm(5.5), FY, W - Cm(11.0), FH)
    tf2 = tb2.text_frame
    tf2.vertical_anchor = MSO_ANCHOR.MIDDLE
    p2 = tb2.text_frame.paragraphs[0]
    p2.text = f"Rapport généré automatiquement le {date_str} — Ne pas diffuser sans autorisation"
    p2.font.size = Pt(7)
    p2.font.name = "Helvetica"
    p2.font.color.rgb = PPTX_WHITE
    p2.alignment = PP_ALIGN.CENTER

def _boa_section_separator(slide, prs, subtitle, top_cm):
    """
    Sous-titre de section. (Version simple type PDF)
    """
    from pptx.util import Cm, Pt
    from pptx.enum.text import PP_ALIGN
    W = prs.slide_width

    tb = slide.shapes.add_textbox(0, int(Cm(top_cm)), int(W), int(Cm(0.81)))
    tf = tb.text_frame
    p = tf.paragraphs[0]
    p.text = subtitle
    p.font.bold = True
    p.font.size = Pt(11)
    p.font.name = "Helvetica"
    p.font.color.rgb = PPTX_DARK
    p.alignment = PP_ALIGN.CENTER

def _boa_content_slide(prs, title, scope_label, threshold, date_str):
    slide = _boa_blank_slide(prs)
    _boa_decorative_bg(slide, prs)
    _boa_header(slide, prs, title, scope_label, threshold)
    _boa_footer(slide, prs, date_str)
    return slide

def _boa_cover(slide, prs, scope_label, threshold, date_str):
    """
    Couverture calquée sur le PDF.
    """
    from pptx.util import Cm, Pt
    W = prs.slide_width
    H = prs.slide_height
    
    # Haut 55% vert
    split_h = int(H * 0.55)
    _boa_rect(slide, 0, 0, W, split_h, PPTX_GREEN)

    # Logo
    logo = _logo_path()
    if logo:
        try:
            slide.shapes.add_picture(
                logo,
                int(W - Cm(5.5)), int(Cm(0.3)),
                width=int(Cm(4.5)), height=int(Cm(2.0))
            )
        except Exception:
            pass
            
    # Titre principal (dans la zone verte)
    tb = slide.shapes.add_textbox(Cm(1.5), H * 0.33, W - Cm(3.0), Cm(2.0))
    tf = tb.text_frame
    p1 = tf.paragraphs[0]
    p1.text = "Rapport de Pilotage\nKYC"
    p1.font.bold = True
    p1.font.size = Pt(28)
    p1.font.name = "Helvetica"
    p1.font.color.rgb = PPTX_WHITE



def _boa_end_slide(prs, scope_label, date_str):
    """
    Page de fin simple (style PDF).
    """
    slide = _boa_blank_slide(prs)
    _boa_header(slide, prs, "FIN DU RAPPORT", scope_label, 90.0)
    _boa_footer(slide, prs, date_str)


def _boa_cover(slide, prs, scope_label, threshold, date_str):
    """
    Couverture calquée sur le PDF avec motif élégant.
    """
    from pptx.util import Cm, Pt
    from pptx.enum.shapes import MSO_SHAPE
    W = prs.slide_width
    H = prs.slide_height
    
    # Haut 55% vert
    split_h = int(H * 0.55)
    _boa_rect(slide, 0, 0, W, split_h, PPTX_GREEN)

    # Triangle décoratif
    tri_w = int(W * 0.6)
    tri_h = int(H * 0.15)
    shape = slide.shapes.add_shape(MSO_SHAPE.RIGHT_TRIANGLE, 0, split_h, tri_w, tri_h)
    shape.rotation = 180
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor(0x16, 0x65, 0x34)
    shape.line.fill.background()

    # Logo
    logo = _logo_path()
    if logo:
        try:
            slide.shapes.add_picture(
                logo,
                int(W - Cm(5.0)), int(Cm(0.3)),
                height=int(Cm(1.8))
            )
        except Exception:
            pass
            
    # Titre principal (dans la zone verte)
    tb = slide.shapes.add_textbox(Cm(1.5), H * 0.25, W - Cm(3.0), Cm(2.0))
    tf = tb.text_frame
    p1 = tf.paragraphs[0]
    p1.text = "RAPPORT DE PILOTAGE\nKYC"
    p1.font.bold = True
    p1.font.size = Pt(36)
    p1.font.name = "Helvetica"
    p1.font.color.rgb = PPTX_WHITE

    # Info bas (dans la zone blanche)
    tb_i = slide.shapes.add_textbox(Cm(1.5), split_h + Cm(1.0), W - Cm(3.0), Cm(3.0))
    tf_i = tb_i.text_frame
    p_i = tf_i.paragraphs[0]
    p_i.text = f"Périmètre : {scope_label}\nSeuil de tolérance : {threshold:.1f}%\nDate : {date_str}"
    p_i.font.size = Pt(14)
    p_i.font.name = "Helvetica"
    p_i.font.color.rgb = PPTX_DARK

def _boa_end_slide(prs, scope_label, date_str):
    """
    Page de fin colorée.
    """
    from pptx.util import Cm, Pt
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    slide = _boa_blank_slide(prs)
    W = prs.slide_width
    H = prs.slide_height

    _boa_rect(slide, 0, 0, W, H, PPTX_GREEN)

    logo = _logo_path()
    if logo:
        try:
            slide.shapes.add_picture(logo, int(W - Cm(5.0)), int(Cm(0.3)), height=int(Cm(1.8)))
        except Exception:
            pass

    tb = slide.shapes.add_textbox(0, int(H * 0.4), int(W), int(Cm(2.0)))
    tf = tb.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.text = "FIN DU RAPPORT"
    p.font.bold = True
    p.font.size = Pt(40)
    p.font.name = "Helvetica"
    p.font.color.rgb = PPTX_WHITE
    p.alignment = PP_ALIGN.CENTER

def _boa_sommaire(slide, prs):
    """
    Sommaire designé avec chiffres romains.
    """
    from pptx.util import Cm, Pt
    from pptx.enum.text import PP_ALIGN
    
    W = prs.slide_width
    _boa_decorative_bg(slide, prs)
    
    toc_entries = [
        ("I",   "Synthèse des Indicateurs Clés"),
        ("II",  "Complétude par champ"),
        ("III", "Champs sous seuil — Complétude"),
        ("IV",  "Conformité par règle qualité"),
        ("V",   "Règles sous seuil — Qualité"),
    ]
    
    top = Cm(4.0)
    for num, title in toc_entries:
        _boa_rect(slide, Cm(4.0), top + Cm(0.8), W - Cm(8.0), Cm(0.05), PPTX_GREEN)
        
        tb_n = slide.shapes.add_textbox(Cm(4.0), top, Cm(1.5), Cm(1.0))
        p_n = tb_n.text_frame.paragraphs[0]
        p_n.text = num
        p_n.font.bold = True
        p_n.font.size = Pt(16)
        p_n.font.color.rgb = PPTX_GREEN
        p_n.alignment = PP_ALIGN.LEFT
        
        tb = slide.shapes.add_textbox(Cm(5.5), top, W - Cm(9.5), Cm(1.0))
        p = tb.text_frame.paragraphs[0]
        p.text = title
        p.font.bold = True
        p.font.size = Pt(14)
        p.font.name = "Helvetica"
        p.font.color.rgb = PPTX_DARK
        p.alignment = PP_ALIGN.LEFT
        top += Cm(1.5)


def _boa_rate_color(rate, threshold):
    if rate is None:
        return PPTX_SLATE
    if rate < threshold:
        return PPTX_RED
    if rate < threshold + 5:
        return PPTX_AMBER
    return PPTX_GREEN


def _boa_kpi_card(slide, left, top, width, height, label, value, color):
    """
    Carte KPI — style exemple rapport.
    Fond #F5F5F5, en-tête coloré avec label blanc, valeur grande centrée.
    Dimensions fidèles à l'exemple (Shape 9/10 slide 3).
    """
    from pptx.util import Cm, Pt
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

    # Fond carte gris clair (F5F5F5)
    _boa_rect(slide, int(left), int(top), int(width), int(height),
              RGBColor(0xF5, 0xF5, 0xF5), border_color=PPTX_GRAY)

    # En-tête coloré (0.81 cm de haut — comme Shape 10 de l'exemple)
    header_h = int(Cm(0.81))
    _boa_rect(slide, int(left), int(top), int(width), header_h, color)

    # Label dans l'en-tête
    tb_l = slide.shapes.add_textbox(int(left), int(top), int(width), header_h)
    tf_l = tb_l.text_frame
    tf_l.word_wrap = True
    tf_l.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf_l.margin_top = tf_l.margin_bottom = int(Cm(0.02))
    tf_l.margin_left = tf_l.margin_right = int(Cm(0.1))
    p_l = tf_l.paragraphs[0]
    p_l.text = label
    p_l.font.bold = True
    p_l.font.size = Pt(8)
    p_l.font.name = "Calibri"
    p_l.font.color.rgb = PPTX_WHITE
    p_l.alignment = PP_ALIGN.CENTER

    # Valeur dans le corps
    body_y = int(top) + header_h
    body_h = int(height) - header_h
    tb_v = slide.shapes.add_textbox(int(left), body_y, int(width), body_h)
    tf_v = tb_v.text_frame
    tf_v.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf_v.margin_top = tf_v.margin_bottom = tf_v.margin_left = tf_v.margin_right = 0
    p_v = tf_v.paragraphs[0]
    p_v.text = value
    p_v.font.bold = True
    p_v.font.size = Pt(32)
    p_v.font.name = "Calibri"
    p_v.font.color.rgb = color
    p_v.alignment = PP_ALIGN.CENTER


def _boa_bar_chart_native(slide, prs, rows, threshold, value_key, label_key, type_key,
                          left_cm, top_cm, w_cm, h_cm, max_items=12):
    """
    Graphique à barres horizontales en rendu natif PPTX (rectangles dessinés),
    style identique au rendu PDF ReportLab.
    Compact : barres fines, labels à droite, ligne de seuil rouge pointillée.
    """
    from pptx.util import Cm, Pt, Emu
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

    items = rows[:max_items]
    if not items:
        return

    left   = int(Cm(left_cm))
    top    = int(Cm(top_cm))
    w      = int(Cm(w_cm))
    h      = int(Cm(h_cm))

    n      = len(items)
    bar_h  = int(h / (n + 1))
    bar_h  = max(bar_h, int(Cm(0.32)))
    label_w = int(Cm(4.8))
    rate_w  = int(Cm(1.2))
    bar_area_w = w - label_w - rate_w

    for i, item in enumerate(items):
        rate = item.get(value_key) or 0
        lbl  = f"{str(item.get(type_key, ''))[:3]}  {str(item.get(label_key, ''))[:22]}"
        color = _boa_rate_color(rate, threshold)
        row_top = top + i * bar_h

        # Fond gris de la barre
        _boa_rect(slide, left + label_w, row_top + int(Cm(0.04)),
                  bar_area_w, bar_h - int(Cm(0.08)), RGBColor(0xF1, 0xF5, 0xF9))

        # Barre colorée
        fill_w = int(bar_area_w * min(max(rate, 0), 100) / 100)
        if fill_w > 0:
            _boa_rect(slide, left + label_w, row_top + int(Cm(0.04)),
                      fill_w, bar_h - int(Cm(0.08)), color)

        # Label à gauche
        tb_lbl = slide.shapes.add_textbox(left, row_top, label_w - int(Cm(0.1)), bar_h)
        tf_lbl = tb_lbl.text_frame
        tf_lbl.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf_lbl.margin_top = tf_lbl.margin_bottom = 0
        tf_lbl.margin_left = tf_lbl.margin_right = int(Cm(0.05))
        p_lbl = tf_lbl.paragraphs[0]
        p_lbl.text = lbl
        p_lbl.font.size = Pt(6.5)
        p_lbl.font.name = "Calibri"
        p_lbl.font.color.rgb = PPTX_DARK
        p_lbl.alignment = PP_ALIGN.RIGHT

        # Taux à droite
        rate_x = left + label_w + bar_area_w + int(Cm(0.1))
        tb_rt = slide.shapes.add_textbox(rate_x, row_top, rate_w, bar_h)
        tf_rt = tb_rt.text_frame
        tf_rt.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf_rt.margin_top = tf_rt.margin_bottom = 0
        tf_rt.margin_left = tf_rt.margin_right = 0
        p_rt = tf_rt.paragraphs[0]
        p_rt.text = f"{rate:.1f}%"
        p_rt.font.bold = True
        p_rt.font.size = Pt(7)
        p_rt.font.name = "Calibri"
        p_rt.font.color.rgb = color
        p_rt.alignment = PP_ALIGN.LEFT

    # Ligne de seuil verticale rouge
    seuil_x = left + label_w + int(bar_area_w * threshold / 100)
    _boa_rect(slide, seuil_x, top, int(Cm(0.05)), n * bar_h, PPTX_RED)

    # Légende en bas
    leg_y = top + n * bar_h + int(Cm(0.5))
    
    _boa_rect(slide, left + label_w, leg_y, int(Cm(0.3)), int(Cm(0.3)), PPTX_GREEN)
    tb1 = slide.shapes.add_textbox(left + label_w + int(Cm(0.4)), leg_y - int(Cm(0.1)), int(Cm(4.0)), int(Cm(0.5)))
    tb1.text_frame.paragraphs[0].text = f"Conforme (≥{threshold:.0f}%)"
    tb1.text_frame.paragraphs[0].font.size = Pt(8)
    tb1.text_frame.paragraphs[0].font.color.rgb = PPTX_SLATE
    
    _boa_rect(slide, left + label_w + int(Cm(4.5)), leg_y, int(Cm(0.3)), int(Cm(0.3)), PPTX_AMBER)
    tb2 = slide.shapes.add_textbox(left + label_w + int(Cm(4.9)), leg_y - int(Cm(0.1)), int(Cm(3.0)), int(Cm(0.5)))
    tb2.text_frame.paragraphs[0].text = "Proche du seuil"
    tb2.text_frame.paragraphs[0].font.size = Pt(8)
    tb2.text_frame.paragraphs[0].font.color.rgb = PPTX_SLATE

    _boa_rect(slide, left + label_w + int(Cm(8.0)), leg_y, int(Cm(0.3)), int(Cm(0.3)), PPTX_RED)
    tb3 = slide.shapes.add_textbox(left + label_w + int(Cm(8.4)), leg_y - int(Cm(0.1)), int(Cm(3.0)), int(Cm(0.5)))
    tb3.text_frame.paragraphs[0].text = "Sous le seuil"
    tb3.text_frame.paragraphs[0].font.size = Pt(8)
    tb3.text_frame.paragraphs[0].font.color.rgb = PPTX_SLATE


def _boa_table(slide, prs, headers, rows_data, col_widths, source_rows, threshold, rate_key):
    """Tableau stylisé BOA — en-tête vert BOA #009A56, alternance lignes."""
    from pptx.util import Cm, Pt
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

    H  = prs.slide_height
    FH = Cm(0.71)

    _boa_section_separator(slide, prs, "DÉTAIL DES ÉLÉMENTS", 2.0)

    n_rows = len(rows_data) + 1
    n_cols = len(headers)
    total_w = sum(col_widths)
    left    = (prs.slide_width - total_w) / 2
    top     = Cm(3.2)
    max_h   = H - top - FH - Cm(0.3)
    height  = min(Cm(0.45) * n_rows + Cm(0.3), max_h)

    tbl = slide.shapes.add_table(n_rows, n_cols, int(left), int(top), int(total_w), int(height)).table

    for i, w in enumerate(col_widths):
        tbl.columns[i].width = int(w)

    for i, row in enumerate(tbl.rows):
        row.height = int(Cm(0.55)) if i == 0 else int(Cm(0.45))

    # En-tête vert BOA
    for j, h in enumerate(headers):
        cell = tbl.cell(0, j)
        cell.text = h
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_top = cell.margin_bottom = int(Cm(0.04))
        cell.margin_left = cell.margin_right = int(Cm(0.08))
        cell.fill.solid()
        cell.fill.fore_color.rgb = PPTX_GREEN
        para = cell.text_frame.paragraphs[0]
        para.font.bold = True
        para.font.size = Pt(8)
        para.font.name = "Calibri"
        para.font.color.rgb = PPTX_WHITE
        if j >= len(headers) - 3:
            para.alignment = PP_ALIGN.RIGHT
        elif j == 0:
            para.alignment = PP_ALIGN.CENTER
        else:
            para.alignment = PP_ALIGN.LEFT

    # Lignes de données
    ROW_BG_ALT = RGBColor(0xF5, 0xF5, 0xF5)
    ROW_BG_RED = RGBColor(0xFF, 0xEB, 0xEB)

    for i, row_vals in enumerate(rows_data, start=1):
        src   = source_rows[i-1] if i-1 < len(source_rows) else {}
        rate  = src.get(rate_key)
        below = src.get("is_below_threshold", False)
        bg_col = ROW_BG_RED if below else (ROW_BG_ALT if i % 2 == 0 else PPTX_WHITE)

        for j, val in enumerate(row_vals):
            cell = tbl.cell(i, j)
            cell.text = str(val)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_top = cell.margin_bottom = int(Cm(0.04))
            cell.margin_left = cell.margin_right = int(Cm(0.08))
            cell.fill.solid()
            cell.fill.fore_color.rgb = bg_col
            para = cell.text_frame.paragraphs[0]
            para.font.size = Pt(7.5)
            para.font.name = "Calibri"
            if j == len(row_vals) - 1:
                color = _boa_rate_color(rate, threshold)
                para.font.bold = True
                para.font.color.rgb = color
                para.alignment = PP_ALIGN.RIGHT
            else:
                para.font.color.rgb = PPTX_DARK
                if j >= len(row_vals) - 3:
                    para.alignment = PP_ALIGN.RIGHT
                elif j == 0:
                    para.alignment = PP_ALIGN.CENTER
                else:
                    para.alignment = PP_ALIGN.LEFT


