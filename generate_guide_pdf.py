import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table,
    TableStyle, PageBreak, Image
)

# ─── Palette BOA ───
BOA_GREEN       = colors.HexColor("#00965E")
BOA_GREEN_LIGHT = colors.HexColor("#E8F5E9")
BOA_DARK        = colors.HexColor("#0f172a")
BOA_BLUE        = colors.HexColor("#1B2A4A")
BOA_SLATE       = colors.HexColor("#64748b")
BOA_WHITE       = colors.white
BOA_BORDER      = colors.HexColor("#e2e8f0")
BOA_GRAY        = colors.HexColor("#f1f5f9")

LOGO_PATH = os.path.join(os.getcwd(), "media", "images", "boa_logo.png")
SCREENSHOTS_DIR = os.path.join(os.getcwd(), "media", "screenshots")

# Create screenshots directory if it doesn't exist
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

def get_styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("title", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=26, textColor=BOA_WHITE, leading=30, alignment=TA_LEFT),
        "heading1": ParagraphStyle("h1", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=18, textColor=BOA_BLUE, leading=22, spaceBefore=20, spaceAfter=10),
        "heading2": ParagraphStyle("h2", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=14, textColor=BOA_GREEN, leading=18, spaceBefore=15, spaceAfter=8),
        "body": ParagraphStyle("body", parent=base["Normal"], fontName="Helvetica", fontSize=10, textColor=BOA_DARK, leading=15, alignment=TA_JUSTIFY, spaceAfter=10),
        "bullet": ParagraphStyle("bullet", parent=base["Normal"], fontName="Helvetica", fontSize=10, textColor=BOA_DARK, leading=15, spaceAfter=5, bulletIndent=10, leftIndent=25),
        "footer": ParagraphStyle("footer", parent=base["Normal"], fontName="Helvetica", fontSize=8, textColor=BOA_SLATE, alignment=TA_CENTER)
    }
    return styles

def get_screenshot_flowable(filename, label="Capture d'écran"):
    """
    Returns an Image if the file exists, otherwise returns a grey Table as a placeholder.
    """
    path = os.path.join(SCREENSHOTS_DIR, filename)
    if os.path.exists(path):
        try:
            # max width for A4 with 1.5cm margins is 18cm. We use 16cm to be safe.
            return Image(path, width=16*cm, height=9*cm, kind='proportional')
        except:
            pass
            
    # Placeholder if image doesn't exist
    data = [[f"[{label} - {filename}]\n\n(Placez l'image dans media/screenshots/{filename})"]]
    t = Table(data, colWidths=[16*cm], rowHeights=[7*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BOA_GRAY),
        ('TEXTCOLOR', (0,0), (-1,-1), BOA_SLATE),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 1, BOA_BORDER),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
    ]))
    return t

def generate_pdf(filename="Guide_Fonctionnel_Plateforme_KYC.pdf"):
    styles = get_styles()
    w, h = A4
    doc = BaseDocTemplate(filename, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=2.5*cm, bottomMargin=2.0*cm)

    def draw_header_footer(canvas, doc):
        canvas.saveState()
        # Footer
        canvas.setFillColor(BOA_BLUE)
        canvas.rect(0, 0, w, 1*cm, fill=1, stroke=0)
        canvas.setStrokeColor(BOA_GREEN)
        canvas.setLineWidth(2)
        canvas.line(0, 1*cm, w, 1*cm)
        canvas.setFillColor(BOA_WHITE)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(1*cm, 0.35*cm, "BOA Group - Confidentiel | Guide d'utilisation KYC")
        canvas.drawRightString(w - 1*cm, 0.35*cm, f"Page {doc.page}")

        # Header (except cover)
        if doc.page > 1:
            canvas.setFillColor(BOA_GREEN)
            canvas.rect(0, h - 1.5*cm, w*0.6, 1.5*cm, fill=1, stroke=0)
            canvas.setFillColor(BOA_BLUE)
            canvas.rect(w*0.6, h - 1.5*cm, w*0.4, 1.5*cm, fill=1, stroke=0)
            
            canvas.setFillColor(BOA_WHITE)
            canvas.setFont("Helvetica-Bold", 10)
            canvas.drawString(1*cm, h - 0.9*cm, "GUIDE D'UTILISATION - PLATEFORME KYC")
            
            if os.path.exists(LOGO_PATH):
                try:
                    canvas.drawImage(LOGO_PATH, w - 4*cm, h - 1.3*cm, width=3*cm, height=1.1*cm, preserveAspectRatio=True, mask="auto")
                except: pass

        canvas.restoreState()

    # Couverture
    def draw_cover(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(BOA_GREEN)
        canvas.rect(0, h*0.5, w, h*0.5, fill=1, stroke=0)

        # Triangle decor
        canvas.setFillColor(colors.HexColor("#007A4A"))
        path = canvas.beginPath()
        path.moveTo(0, h*0.5)
        path.lineTo(w*0.7, h*0.5)
        path.lineTo(0, h*0.35)
        path.close()
        canvas.drawPath(path, fill=1, stroke=0)

        if os.path.exists(LOGO_PATH):
            try:
                canvas.drawImage(LOGO_PATH, w - 6*cm, h - 3*cm, width=5*cm, height=2*cm, preserveAspectRatio=True, mask="auto")
            except: pass

        canvas.setFillColor(BOA_WHITE)
        canvas.setFont("Helvetica-Bold", 32)
        canvas.drawString(1.5*cm, h*0.7, "Guide d'Utilisation")
        canvas.drawString(1.5*cm, h*0.63, "Plateforme Notation KYC")
        
        canvas.setStrokeColor(BOA_WHITE)
        canvas.setLineWidth(3)
        canvas.line(1.5*cm, h*0.59, 10*cm, h*0.59)

        canvas.setFont("Helvetica", 14)
        canvas.drawString(1.5*cm, h*0.54, "Manuel Fonctionnel illustré")

        canvas.setFillColor(BOA_DARK)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(1.5*cm, h*0.4, f"Date de mise à jour : {datetime.now().strftime('%d/%m/%Y')}")
        canvas.drawString(1.5*cm, h*0.35, "Version : 2.0")

        canvas.restoreState()

    frame_cover = Frame(0, 0, w, h, id="cover")
    frame_normal = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame_cover], onPage=draw_cover),
        PageTemplate(id="normal", frames=[frame_normal], onPage=draw_header_footer)
    ])

    story = [Spacer(1, 1)]
    story.append(PageBreak())

    # --- Contenu ---
    story.append(Paragraph("1. Le Tableau de Bord", styles['heading1']))
    story.append(Paragraph("Dès votre connexion, vous arrivez sur le Tableau de Bord (Dashboard). Il vous donne une vision synthétique de la situation KYC de votre périmètre :", styles['body']))
    story.append(Spacer(1, 0.3*cm))
    story.append(get_screenshot_flowable("dashboard.png", "Vue d'ensemble du Tableau de bord"))
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph("2. Gestion des Notations KYC", styles['heading1']))
    story.append(Paragraph("Nouvelle Notation", styles['heading2']))
    story.append(Paragraph("Cet écran vous permet de créer ou mettre à jour le profil KYC d'un client.", styles['body']))
    story.append(Spacer(1, 0.3*cm))
    story.append(get_screenshot_flowable("nouvelle_notation.png", "Écran de saisie d'une Notation"))
    story.append(Spacer(1, 0.5*cm))
    
    story.append(Paragraph("Historique des Notations", styles['heading2']))
    story.append(Paragraph("Permet de consulter toutes les notations passées, avec possibilité de recherche et de filtres.", styles['body']))
    story.append(Spacer(1, 0.3*cm))
    story.append(get_screenshot_flowable("historique.png", "Liste de l'historique des Notations"))
    story.append(PageBreak())

    story.append(Paragraph("3. Suivis et Anomalies", styles['heading1']))
    story.append(Paragraph("Clients en Anomalie", styles['heading2']))
    story.append(Paragraph("Liste détaillée des clients présentant un risque de conformité ou un dossier KYC incomplet. Vous pouvez exporter ces données.", styles['body']))
    story.append(Spacer(1, 0.3*cm))
    story.append(get_screenshot_flowable("clients_anomalie.png", "Écran des clients en anomalie"))
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph("Champs non renseignés", styles['heading2']))
    story.append(Paragraph("Identifiez rapidement les champs manquants dans les profils de vos clients pour organiser vos campagnes de mise à jour.", styles['body']))
    story.append(Spacer(1, 0.3*cm))
    story.append(get_screenshot_flowable("champs_non_renseignes.png", "Écran des champs manquants"))
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph("4. Conformité", styles['heading1']))
    story.append(Paragraph("PPE et Comptes Spécifiques", styles['heading2']))
    story.append(Paragraph("Interfaces dédiées au suivi des Personnes Politiquement Exposées et des comptes à surveillance renforcée (ONG, Ambassades).", styles['body']))
    story.append(Spacer(1, 0.3*cm))
    story.append(get_screenshot_flowable("conformite_ppe.png", "Suivi des PPE"))
    story.append(PageBreak())

    story.append(Paragraph("5. Administration (PASS / DSI)", styles['heading1']))
    story.append(Paragraph("Paramètres Système et Utilisateurs", styles['heading2']))
    story.append(Paragraph("Gestion complète des comptes utilisateurs, des habilitations et du paramétrage général.", styles['body']))
    story.append(Spacer(1, 0.3*cm))
    story.append(get_screenshot_flowable("parametres.png", "Gestion des Paramètres Système"))
    story.append(Spacer(1, 0.5*cm))
    
    story.append(Paragraph("Règles de Qualité", styles['heading2']))
    story.append(Paragraph("Configuration dynamique des règles d'évaluation pour le scoring et les alertes.", styles['body']))
    story.append(Spacer(1, 0.3*cm))
    story.append(get_screenshot_flowable("regles_qualite.png", "Configuration des règles de qualité"))

    doc.build(story)
    print(f"PDF généré avec succès : {filename}")

if __name__ == '__main__':
    generate_pdf()
