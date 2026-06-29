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

def export_pilotage_pptx(scope_data, summary, completeness_rows, quality_rows,
                         notations_list=None, notation_kpis=None):
    """
    Génère une présentation PowerPoint reproduisant fidèlement le thème
    "Conformité BOA Group" (Calibri, vert #009A56, marine #1B2A4A) :
    couverture verte avec cercles décoratifs, en-têtes de section pleins,
    cartes KPI, jauges en anneau, graphiques natifs et tableaux stylés.
    """
    from pptx.util import Inches, Pt, Emu

    scope       = scope_data["scope"]
    fil         = scope_data.get("selected_filiale", "")
    scope_label = "GROUPE" if scope == "groupe" else (fil or "GROUPE")
    threshold   = summary.get("threshold", 90.0)
    _now        = timezone.localtime()
    date_str    = _now.strftime("%d/%m/%Y")
    _MOIS_FR    = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                   "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
    mois_str    = f"{_MOIS_FR[_now.month]} {_now.year}"

    prs = Presentation()
    prs.slide_width  = Inches(10)
    prs.slide_height = Inches(5.625)

    # ── Plan dynamique (sommaire) ─────────────────────────────────────────────
    below_comp = sorted([r for r in completeness_rows if r.get("is_below_threshold")],
                        key=lambda r: r.get("rate", 0))
    below_qual = sorted([r for r in quality_rows if r.get("is_below_threshold")],
                        key=lambda r: r.get("rate", 0))

    toc = [
        ("I",   "Synthèse des indicateurs clés"),
        ("II",  "Complétude des données - Taux par champs"),
    ]
    if below_comp:
        toc.append(("III", "Complétude des données - Champs sous seuil"))
    toc.append((_roman(len(toc) + 1), "Qualité des données - Taux par règles"))
    if below_qual:
        toc.append((_roman(len(toc) + 1), "Qualité des données - Règle sous seuil"))

    # ── Slide 1 : Couverture ──────────────────────────────────────────────────
    _bx_cover(prs, scope_label, mois_str)

    # ── Slide 2 : Sommaire ────────────────────────────────────────────────────
    _bx_sommaire(prs, toc)

    sec = 0
    # ── Slide 3 : Synthèse des indicateurs ────────────────────────────────────
    sec += 1
    s = _bx_section(prs, _roman(sec), "SYNTHÈSE DES INDICATEURS CLÉS")
    _bx_synthese(s, summary, threshold)

    # ── Slide 4 : Complétude par champ (graphique) ────────────────────────────
    sec += 1
    s = _bx_section(prs, _roman(sec), "COMPLÉTUDE DES DONNÉES — TAUX PAR CHAMPS")
    _bx_sublabel(s, "TAUX DE COMPLÉTUDE PAR CHAMP")
    _bx_hbar_chart(s, completeness_rows, threshold, "rate", "field_label", "type",
                   top=1.55, max_items=11)

    # ── Slide 5 : Champs sous seuil (tableau) ─────────────────────────────────
    if below_comp:
        sec += 1
        s = _bx_section(prs, _roman(sec), f"COMPLÉTUDE DES DONNÉES — CHAMPS SOUS SEUIL ({threshold:.0f}%)")
        _bx_sublabel(s, "CHAMPS À FIABILISER EN PRIORITÉ")
        hdrs = ["Type", "Champ", "Total", "Incomplets", "Taux"]
        rows = [[r.get("type", ""), _trunc(r.get("field_label", ""), 40),
                 _fmt_int(r.get("total_clients", 0)), _fmt_int(r.get("missing_count", 0)),
                 f"{r.get('rate', 0):.1f}%"] for r in below_comp[:9]]
        _bx_table(s, hdrs, rows, [0.10, 0.45, 0.15, 0.16, 0.14],
                  below_comp, threshold, "rate")

    # ── Slide 6 : Qualité par règle (graphique) ───────────────────────────────
    sec += 1
    s = _bx_section(prs, _roman(sec), "QUALITÉ DES DONNÉES — TAUX PAR RÈGLES")
    _bx_sublabel(s, "TAUX DE CONFORMITÉ PAR RÈGLE QUALITÉ")
    _bx_hbar_chart(s, quality_rows, threshold, "rate", "rule_name", "type",
                   top=1.55, max_items=11)

    # ── Slide 7 : Règles sous seuil (tableau) ─────────────────────────────────
    if below_qual:
        sec += 1
        s = _bx_section(prs, _roman(sec), f"QUALITÉ DES DONNÉES — RÈGLES SOUS SEUIL ({threshold:.0f}%)")
        _bx_sublabel(s, "RÈGLES NÉCESSITANT UNE ACTION")
        hdrs = ["Type", "Règle", "Champ", "Anomalies", "Taux"]
        rows = [[r.get("type", ""), _trunc(r.get("rule_name", ""), 34),
                 _trunc(r.get("field_label", ""), 24), _fmt_int(r.get("fail_count", 0)),
                 f"{r.get('rate', 0):.1f}%"] for r in below_qual[:9]]
        _bx_table(s, hdrs, rows, [0.10, 0.36, 0.28, 0.14, 0.12],
                  below_qual, threshold, "rate")

    # ── Slide final : Merci ───────────────────────────────────────────────────
    _bx_end(prs, scope_label, mois_str)

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


# ═══════════════════════════════════════════════════════════════════════════════
#  THÈME BOA — palette & primitives
# ═══════════════════════════════════════════════════════════════════════════════

BX_GREEN      = RGBColor(0x00, 0x9A, 0x56)   # Vert BOA principal
BX_GREEN_BRT  = RGBColor(0x00, 0xC0, 0x60)   # Vert vif (cercles couverture)
BX_GREEN_PALE = RGBColor(0xC8, 0xE6, 0xC9)   # Vert pâle décoratif
BX_GREEN_SUB  = RGBColor(0xC8, 0xF0, 0xD8)   # Vert clair sous-titre
BX_NAVY       = RGBColor(0x1B, 0x2A, 0x4A)   # Marine BOA
BX_BODY       = RGBColor(0x33, 0x33, 0x33)   # Corps de texte
BX_MUTED      = RGBColor(0x66, 0x66, 0x66)   # Texte secondaire
BX_FOOT       = RGBColor(0x88, 0x88, 0x88)   # Pied de page
BX_CARD       = RGBColor(0xF5, 0xF5, 0xF5)   # Fond carte
BX_DIVIDER    = RGBColor(0xE0, 0xE0, 0xE0)   # Filets
BX_TRACK      = RGBColor(0xEC, 0xEF, 0xF1)   # Piste de barre/anneau
BX_WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
BX_RED        = RGBColor(0xD3, 0x2F, 0x2F)   # Rouge alerte
BX_AMBER      = RGBColor(0xF5, 0xA6, 0x23)   # Ambre attention
BX_CYAN       = RGBColor(0x29, 0xAB, 0xE2)   # Cyan accent

_FONT = "Calibri"
_FOOTER_TXT = "Conformité BOA Group | Pôle Projet"


def _roman(n):
    return ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"][n] if n < 11 else str(n)


def _trunc(s, n):
    s = str(s or "")
    return s if len(s) <= n else s[: n - 1] + "…"


def _fmt_int(v):
    try:
        return f"{int(v):,}".replace(",", " ")
    except (ValueError, TypeError):
        return str(v)


def _bx_rate_color(rate, threshold):
    """Vert si le taux atteint/dépasse le seuil, orange en deçà. Pas d'autre couleur."""
    if rate is None:
        return BX_MUTED
    return BX_GREEN if rate >= threshold else BX_AMBER


def _bx_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _bx_rect(slide, l, t, w, h, fill, line=None, line_w=1.0):
    """Rectangle plein, sans ombre (Inches)."""
    from pptx.util import Inches, Pt
    from pptx.enum.shapes import MSO_SHAPE
    sp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(l), Inches(t), Inches(w), Inches(h))
    sp.fill.solid()
    sp.fill.fore_color.rgb = fill
    if line is not None:
        sp.line.color.rgb = line
        sp.line.width = Pt(line_w)
    else:
        sp.line.fill.background()
    sp.shadow.inherit = False
    return sp


def _bx_oval(slide, l, t, w, h, fill):
    from pptx.util import Inches
    from pptx.enum.shapes import MSO_SHAPE
    sp = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(l), Inches(t), Inches(w), Inches(h))
    sp.fill.solid()
    sp.fill.fore_color.rgb = fill
    sp.line.fill.background()
    sp.shadow.inherit = False
    return sp


def _bx_ring(slide, l, t, w, h, line_color, line_w=1.5):
    """Cercle décoratif simple : contour seul, sans remplissage."""
    from pptx.util import Inches, Pt
    from pptx.enum.shapes import MSO_SHAPE
    sp = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(l), Inches(t), Inches(w), Inches(h))
    sp.fill.background()
    sp.line.color.rgb = line_color
    sp.line.width = Pt(line_w)
    sp.shadow.inherit = False
    return sp


def _bx_text(slide, l, t, w, h, text, size, color, bold=False, align=None,
             anchor=None, italic=False, wrap=True, font=_FONT, spacing=None):
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    tb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.margin_top = tf.margin_bottom = 0
    tf.margin_left = tf.margin_right = 0
    if anchor is not None:
        tf.vertical_anchor = anchor
    lines = text.split("\n")
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.italic = italic
        p.font.name = font
        p.font.color.rgb = color
        if align is not None:
            p.alignment = align
        if spacing is not None:
            p.line_spacing = spacing
    return tb


def _bx_logo(slide):
    """Boîte logo marine BOA en haut à droite (calquée sur l'exemple)."""
    from pptx.util import Inches
    logo = _logo_path()
    if logo:
        try:
            slide.shapes.add_picture(logo, Inches(7.45), Inches(0.0), width=Inches(2.55))
            return
        except Exception:
            pass
    # Repli : boîte marine dessinée
    _bx_rect(slide, 7.45, 0.0, 2.55, 0.62, BX_NAVY)
    _bx_text(slide, 7.55, 0.06, 2.4, 0.5, "BANK OF AFRICA\nBMCE GROUP", 9, BX_WHITE,
             bold=True, align=None)


def _bx_decor(slide, color):
    """Motif décoratif épuré : deux anneaux fins en haut à droite."""
    _bx_ring(slide, 8.7, -1.1, 3.6, 3.6, color, 1.5)
    _bx_ring(slide, 9.3, 1.4, 2.2, 2.2, color, 1.5)


def _bx_footer(slide):
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    _bx_rect(slide, 0.0, 5.35, 10.0, 0.005, BX_DIVIDER)
    _bx_text(slide, 6.0, 5.37, 3.85, 0.25, _FOOTER_TXT, 8, BX_FOOT,
             align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)


def _bx_section(prs, roman, title):
    """En-tête de section : bande verte pleine + cercles + logo + pied."""
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    s = _bx_slide(prs)
    _bx_decor(s, BX_GREEN_PALE)
    _bx_rect(s, 0.0, 0.0, 10.0, 0.62, BX_GREEN)
    _bx_text(s, 0.4, 0.0, 7.0, 0.62, f"{roman}.  {title}", 18, BX_WHITE,
             bold=True, anchor=MSO_ANCHOR.MIDDLE)
    _bx_logo(s)
    _bx_footer(s)
    return s


def _bx_sublabel(slide, text, top=0.82):
    """Sous-titre vert majuscule + filet vert pleine largeur."""
    from pptx.enum.text import MSO_ANCHOR
    _bx_text(slide, 0.4, top, 9.2, 0.3, text, 11, BX_GREEN, bold=True,
             anchor=MSO_ANCHOR.MIDDLE)
    _bx_rect(slide, 0.4, top + 0.3, 9.2, 0.035, BX_GREEN)


# ═══════════════════════════════════════════════════════════════════════════════
#  THÈME BOA — slides composées
# ═══════════════════════════════════════════════════════════════════════════════

def _bx_cover(prs, scope_label, mois_str):
    from pptx.util import Inches
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    s = _bx_slide(prs)
    _bx_rect(s, 0.0, 0.0, 10.0, 5.625, BX_GREEN)
    _bx_ring(s, 7.9, -1.6, 4.6, 4.6, BX_GREEN_BRT, 2.0)
    _bx_ring(s, 8.9, 2.0, 2.8, 2.8, BX_GREEN_BRT, 2.0)
    _bx_logo(s)

    _bx_text(s, 0.5, 1.35, 7.5, 1.5, "RAPPORT DE PILOTAGE KYC", 46, BX_WHITE,
             bold=True, anchor=MSO_ANCHOR.MIDDLE)
    _bx_text(s, 0.5, 2.9, 7.5, 0.5,
             f"SYNTHÈSE QUALITÉ & COMPLÉTUDE — PÉRIMÈTRE {scope_label.upper()}",
             14, BX_GREEN_SUB, bold=True)
    _bx_rect(s, 0.52, 3.45, 6.0, 0.045, BX_WHITE)
    _bx_text(s, 0.5, 3.65, 7.0, 0.35, mois_str, 11, RGBColor(0xD4, 0xF5, 0xE4))
    _bx_text(s, 0.5, 5.2, 7.0, 0.28, _FOOTER_TXT, 8,
             RGBColor(0xA0, 0xD4, 0xB8), italic=True)


def _bx_sommaire(prs, toc):
    from pptx.enum.text import MSO_ANCHOR
    s = _bx_slide(prs)
    _bx_decor(s, BX_GREEN_PALE)
    _bx_logo(s)
    _bx_footer(s)
    _bx_text(s, 0.5, 0.5, 6.0, 1.1, "SOMMAIRE", 52, BX_GREEN, bold=True,
             anchor=MSO_ANCHOR.MIDDLE)

    n = len(toc)
    top = 1.85
    row_h = min(0.62, (4.9 - top) / max(n, 1))
    for roman, title in toc:
        _bx_rect(s, 0.5, top + 0.04, 0.07, 0.38, BX_GREEN)
        _bx_text(s, 0.68, top, 0.6, 0.42, roman, 12, BX_GREEN, bold=True,
                 anchor=MSO_ANCHOR.MIDDLE)
        _bx_text(s, 1.3, top, 7.0, 0.42, title, 14, BX_NAVY, bold=True,
                 anchor=MSO_ANCHOR.MIDDLE)
        _bx_rect(s, 0.5, top + row_h - 0.12, 7.6, 0.02, BX_DIVIDER)
        top += row_h


def _bx_kpi_card(slide, l, t, w, h, label, value, color, sub=None):
    """Carte KPI : bandeau coloré + corps gris clair + grand chiffre."""
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    _bx_rect(slide, l, t, w, h, BX_CARD)
    _bx_rect(slide, l, t, w, 0.34, color)
    _bx_text(slide, l + 0.05, t, w - 0.1, 0.34, label, 8.5, BX_WHITE, bold=True,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    val_h = (h - 0.34) if not sub else (h - 0.34 - 0.3)
    _bx_text(slide, l, t + 0.34, w, val_h, value, 33, color, bold=True,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    if sub:
        _bx_text(slide, l, t + h - 0.32, w, 0.28, sub, 8.5, BX_MUTED,
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def _bx_donut(slide, l, t, sz, rate, threshold, title):
    """Jauge en anneau native + grand pourcentage centré + titre dessous."""
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE

    color = _bx_rate_color(rate, threshold)
    r = max(0.0, min(float(rate or 0), 100.0))
    cd = CategoryChartData()
    cd.categories = ["ok", "reste"]
    cd.add_series("s", (r, 100.0 - r))
    gf = slide.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, Inches(l), Inches(t),
                                Inches(sz), Inches(sz), cd)
    chart = gf.chart
    chart.has_legend = False
    chart.has_title = False
    plot = chart.plots[0]
    plot.has_data_labels = False
    try:
        from pptx.oxml.ns import qn
        plot._element.find(qn("c:firstSliceAng"))
        hole = plot._element.find(qn("c:holeSize"))
        if hole is not None:
            hole.set("val", "68")
    except Exception:
        pass
    pts = plot.series[0].points
    pts[0].format.fill.solid()
    pts[0].format.fill.fore_color.rgb = color
    pts[1].format.fill.solid()
    pts[1].format.fill.fore_color.rgb = BX_TRACK
    for pt in pts:
        pt.format.line.fill.background()

    # Pourcentage centré + titre sous l'anneau
    _bx_text(slide, l, t + sz / 2 - 0.32, sz, 0.6,
             f"{r:.1f}%", 26, color, bold=True,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    _bx_text(slide, l - 0.4, t + sz + 0.05, sz + 0.8, 0.3, title, 11, BX_NAVY,
             bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def _bx_synthese(slide, summary, threshold):
    """Slide synthèse : 2 jauges (complétude/qualité) + 2 cartes alertes + mini PP/PM."""
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    _bx_sublabel(slide, "VUE D'ENSEMBLE DU PÉRIMÈTRE")

    comp = summary.get("completeness_rate")
    qual = summary.get("quality_rate")
    comp_pp = summary.get("completeness_rate_pp")
    comp_pm = summary.get("completeness_rate_pm")
    qual_pp = summary.get("quality_rate_pp")
    qual_pm = summary.get("quality_rate_pm")
    low_c = summary.get("low_completeness_count", 0)
    low_q = summary.get("low_quality_count", 0)

    # Deux jauges
    _bx_donut(slide, 0.7, 1.65, 2.1, comp, threshold, "COMPLÉTUDE GLOBALE")
    _bx_donut(slide, 3.3, 1.65, 2.1, qual, threshold, "QUALITÉ GLOBALE")

    # Mini PP/PM sous chaque jauge
    _bx_text(slide, 0.3, 4.45, 2.9, 0.3,
             f"PP {comp_pp:.0f}%    ·    PM {comp_pm:.0f}%" if comp_pp is not None else "",
             10, BX_MUTED, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    _bx_text(slide, 2.9, 4.45, 2.9, 0.3,
             f"PP {qual_pp:.0f}%    ·    PM {qual_pm:.0f}%" if qual_pp is not None else "",
             10, BX_MUTED, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

    # Deux cartes alertes à droite
    cx = 6.05
    cw = 3.55
    _bx_kpi_card(slide, cx, 1.65, cw, 1.35, "CHAMPS SOUS LE SEUIL",
                 str(low_c), BX_AMBER if low_c else BX_GREEN,
                 sub="champs de complétude à fiabiliser")
    _bx_kpi_card(slide, cx, 3.2, cw, 1.35, "RÈGLES SOUS LE SEUIL",
                 str(low_q), BX_AMBER if low_q else BX_GREEN,
                 sub="règles qualité nécessitant une action")


def _bx_hbar_chart(slide, rows, threshold, value_key, label_key, type_key,
                   top=1.55, max_items=11):
    """Graphique à barres horizontales natif, points colorés selon le seuil."""
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION

    items = list(rows)[:max_items]
    if not items:
        _bx_text(slide, 0.4, 2.6, 9.2, 0.5, "Aucune donnée disponible pour ce périmètre.",
                 12, BX_MUTED, align=PP_ALIGN.CENTER)
        return

    cats, vals, colors = [], [], []
    for it in items:
        rate = it.get(value_key) or 0
        typ = str(it.get(type_key, "")).strip()
        lab = _trunc(it.get(label_key, ""), 34)
        cats.append(f"{typ}  {lab}" if typ else lab)
        vals.append(round(float(rate), 1))
        colors.append(_bx_rate_color(rate, threshold))

    cats.reverse(); vals.reverse(); colors.reverse()  # 1er en haut

    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("Taux", vals)
    chart_h = min(3.55, 0.31 * len(items) + 0.6)
    gf = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED,
                                Inches(0.4), Inches(top + 0.05),
                                Inches(9.2), Inches(chart_h), cd)
    chart = gf.chart
    chart.has_legend = False
    chart.has_title = False

    plot = chart.plots[0]
    plot.gap_width = 60
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format = '0.0"%"'
    dl.number_format_is_linked = False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    dl.font.size = Pt(8.5)
    dl.font.bold = True
    dl.font.name = _FONT
    dl.font.color.rgb = BX_BODY

    series = plot.series[0]
    for idx, pt in enumerate(series.points):
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = colors[idx]
        pt.format.line.fill.background()

    va = chart.value_axis
    va.minimum_scale = 0
    va.maximum_scale = 100
    va.has_major_gridlines = False
    va.visible = False
    ca = chart.category_axis
    ca.tick_labels.font.size = Pt(8.5)
    ca.tick_labels.font.name = _FONT
    ca.tick_labels.font.color.rgb = BX_BODY
    ca.format.line.color.rgb = BX_DIVIDER

    # Légende seuil
    ly = top + chart_h + 0.12
    _bx_legend(slide, ly, threshold)


def _bx_legend(slide, y, threshold):
    from pptx.enum.text import MSO_ANCHOR
    items = [(BX_GREEN, f"Conforme (≥ {threshold:.0f}%)"),
             (BX_AMBER, f"Sous le seuil (< {threshold:.0f}%)")]
    x = 0.4
    for col, lab in items:
        _bx_rect(slide, x, y + 0.04, 0.22, 0.22, col)
        _bx_text(slide, x + 0.3, y, 2.6, 0.3, lab, 9, BX_MUTED,
                 anchor=MSO_ANCHOR.MIDDLE)
        x += 0.32 + 0.022 * len(lab) * 8 / 8 + 1.7


def _bx_table(slide, headers, rows_data, col_fracs, source_rows, threshold, rate_key,
              top=1.5):
    """Tableau stylé : en-tête vert, alternance de lignes, taux coloré."""
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

    n_rows = len(rows_data) + 1
    n_cols = len(headers)
    total_w = 9.2
    left = 0.4
    col_w = [f * total_w for f in col_fracs]
    head_h = 0.42
    row_h = min(0.4, (3.6 - head_h) / max(len(rows_data), 1))
    height = head_h + row_h * len(rows_data)

    tbl = slide.shapes.add_table(n_rows, n_cols, Inches(left), Inches(top),
                                 Inches(total_w), Inches(height)).table
    tbl.first_row = False
    tbl.horz_banding = False
    for i, w in enumerate(col_w):
        tbl.columns[i].width = Inches(w)
    tbl.rows[0].height = Inches(head_h)
    for i in range(1, n_rows):
        tbl.rows[i].height = Inches(row_h)

    right_cols = {n_cols - 1, n_cols - 2}
    # En-tête
    for j, h in enumerate(headers):
        c = tbl.cell(0, j)
        c.text = h
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        c.margin_top = c.margin_bottom = Inches(0.02)
        c.margin_left = c.margin_right = Inches(0.07)
        c.fill.solid(); c.fill.fore_color.rgb = BX_GREEN
        p = c.text_frame.paragraphs[0]
        p.font.bold = True; p.font.size = Pt(9); p.font.name = _FONT
        p.font.color.rgb = BX_WHITE
        p.alignment = PP_ALIGN.CENTER if j == 0 else (PP_ALIGN.RIGHT if j in right_cols else PP_ALIGN.LEFT)

    for i, vals in enumerate(rows_data, start=1):
        src = source_rows[i - 1] if i - 1 < len(source_rows) else {}
        bg = BX_WHITE if i % 2 else RGBColor(0xF2, 0xF6, 0xFA)
        for j, val in enumerate(vals):
            c = tbl.cell(i, j)
            c.text = str(val)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            c.margin_top = c.margin_bottom = Inches(0.01)
            c.margin_left = c.margin_right = Inches(0.07)
            c.fill.solid(); c.fill.fore_color.rgb = bg
            p = c.text_frame.paragraphs[0]
            p.font.size = Pt(8.5); p.font.name = _FONT
            if j == n_cols - 1:
                p.font.bold = True
                p.font.color.rgb = _bx_rate_color(src.get(rate_key), threshold)
                p.alignment = PP_ALIGN.RIGHT
            else:
                p.font.color.rgb = BX_BODY
                p.alignment = PP_ALIGN.CENTER if j == 0 else (PP_ALIGN.RIGHT if j in right_cols else PP_ALIGN.LEFT)


def _bx_end(prs, scope_label, mois_str):
    from pptx.enum.text import MSO_ANCHOR
    s = _bx_slide(prs)
    _bx_rect(s, 0.0, 0.0, 10.0, 5.625, BX_GREEN)
    _bx_ring(s, 7.9, -1.6, 4.6, 4.6, BX_GREEN_BRT, 2.0)
    _bx_ring(s, 8.9, 2.0, 2.8, 2.8, BX_GREEN_BRT, 2.0)
    _bx_logo(s)
    _bx_text(s, 0.5, 1.7, 7.5, 1.2, "FIN DU DOCUMENT", 44, BX_WHITE, bold=True,
             anchor=MSO_ANCHOR.MIDDLE)
    _bx_rect(s, 0.52, 3.05, 6.0, 0.045, BX_WHITE)
    _bx_text(s, 0.5, 3.25, 7.5, 0.4,
             f"RAPPORT DE PILOTAGE KYC — {_FOOTER_TXT}", 13, BX_WHITE, bold=True)
    _bx_text(s, 0.5, 3.85, 7.0, 0.35, mois_str, 11,
             RGBColor(0xD4, 0xF5, 0xE4), italic=True)
