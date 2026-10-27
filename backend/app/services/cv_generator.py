import os
import io
from typing import Optional
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from backend.app.config import settings


class CVGeneratorService:
    """
    Generates application-specific PDF CVs with unique embedded profile URLs.
    Supports:
    1. Google Docs API copy-template + replaceAllText + export (when credentials available)
    2. Executive local PDF generator with ReportLab (for offline dev and tests)
    3. pypdf metadata injection (Subject, Keywords, Author)
    """

    def __init__(self):
        self.output_dir = settings.GENERATED_CVS_DIR
        os.makedirs(self.output_dir, exist_ok=True)
        self.template_doc_id = settings.GOOGLE_CV_TEMPLATE_DOC_ID

    def _get_google_services(self):
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            if settings.GOOGLE_SERVICE_ACCOUNT_FILE and os.path.exists(settings.GOOGLE_SERVICE_ACCOUNT_FILE):
                creds = service_account.Credentials.from_service_account_file(
                    settings.GOOGLE_SERVICE_ACCOUNT_FILE,
                    scopes=[
                        'https://www.googleapis.com/auth/drive',
                        'https://www.googleapis.com/auth/documents'
                    ]
                )
                drive = build('drive', 'v3', credentials=creds)
                docs = build('docs', 'v1', credentials=creds)
                return drive, docs
        except Exception as e:
            print(f"Notice: Google Docs API credentials not loaded: {e}")
        return None, None

    def _generate_with_google_docs(self, profile_url: str, company: str, role: str) -> Optional[bytes]:
        """Google Docs API: copy template -> replaceAllText -> export PDF."""
        drive, docs = self._get_google_services()
        if not drive or not docs or not self.template_doc_id or "sample" in self.template_doc_id:
            return None

        try:
            # 1. Copy template document
            copy_body = {'name': f'CV - {settings.CANDIDATE_NAME} - {company} ({role})'}
            copy_res = drive.files().copy(fileId=self.template_doc_id, body=copy_body).execute()
            doc_copy_id = copy_res['id']

            # 2. Replace {{AI_PROFILE_URL}} placeholder
            replace_request = [
                {
                    'replaceAllText': {
                        'containsText': {
                            'text': '{{AI_PROFILE_URL}}',
                            'matchCase': True
                        },
                        'replaceText': profile_url
                    }
                }
            ]
            docs.documents().batchUpdate(documentId=doc_copy_id, body={'requests': replace_request}).execute()

            # 3. Export as PDF
            pdf_bytes = drive.files().export(fileId=doc_copy_id, mimeType='application/pdf').execute()
            return pdf_bytes
        except Exception as e:
            print(f"Google Docs generation failed: {e}. Falling back to local high-fidelity generator.")
            return None

    def _generate_local_cv_pdf(self, profile_url: str, company: str, role: str) -> bytes:
        """Generate a high-quality executive PDF CV for the configured candidate."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40
        )

        styles = getSampleStyleSheet()

        # Custom typography styles
        title_style = ParagraphStyle(
            'CandidateName',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=22,
            leading=26,
            textColor=colors.HexColor('#0f172a')
        )
        headline_style = ParagraphStyle(
            'CandidateHeadline',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=15,
            textColor=colors.HexColor('#0284c7')
        )
        section_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=13,
            leading=17,
            textColor=colors.HexColor('#1e293b'),
            spaceBefore=10,
            spaceAfter=4
        )
        body_style = ParagraphStyle(
            'BodyTextCustom',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9.5,
            leading=13.5,
            textColor=colors.HexColor('#334155')
        )
        role_title_style = ParagraphStyle(
            'RoleTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor('#0f172a')
        )
        bullet_style = ParagraphStyle(
            'BulletCustom',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=13,
            textColor=colors.HexColor('#334155'),
            leftIndent=12
        )
        footer_box_style = ParagraphStyle(
            'FooterBoxText',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#0f172a')
        )
        footer_url_style = ParagraphStyle(
            'FooterBoxURL',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor('#0369a1')
        )

        story = []

        # Header
        story.append(Paragraph(settings.CANDIDATE_NAME, title_style))
        story.append(Spacer(1, 2))
        story.append(Paragraph(settings.CANDIDATE_HEADLINE, headline_style))
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#e2e8f0'), spaceAfter=10))

        # Executive Summary
        story.append(Paragraph("Executive Summary", section_style))
        story.append(Paragraph(
            f"{settings.CANDIDATE_SUMMARY} Prepared specifically for the {role} position at {company}.",
            body_style
        ))
        story.append(Spacer(1, 10))

        story.append(Paragraph("Evidence Notice", section_style))
        story.append(Paragraph(
            "This fallback document contains only the configured candidate summary. "
            "Use a canonical evidence document or an uploaded CV to generate a detailed profile.",
            body_style,
        ))
        story.append(Spacer(1, 14))

        # Visible footer section with exact raw text URL and AI cURL/MCP instruction
        mcp_url = profile_url.replace('/a/', '/mcp/')
        footer_text = (
            f"<b>Extended profile & supporting evidence:</b><br/>"
            f"<font color='#0369a1'>{profile_url}</font><br/>"
            f"<font size='7.5' color='#64748b'>AI & screening discovery: (1) URL GET ({profile_url}/ask?q=...) • (2) REST POST ({profile_url}/ask) • (3) MCP ({mcp_url}) • (4) WebMCP</font>"
        )

        footer_table = Table(
            [[Paragraph(footer_text, footer_box_style)]],
            colWidths=[532]
        )
        footer_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
            ('PADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(footer_table)

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    def _inject_pdf_metadata(self, pdf_bytes: bytes, profile_url: str) -> bytes:
        """Inject Subject, Keywords and Author into PDF metadata using pypdf."""
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        # Add P0/P1 requested PDF metadata
        metadata = {
            "/Author": settings.CANDIDATE_NAME,
            "/Title": f"{settings.CANDIDATE_NAME} — Extended Professional CV",
            "/Subject": f"Extended professional profile: {profile_url}",
            "/Keywords": "DearBot, evidence-linked application profile, curriculum vitae"
        }
        writer.add_metadata(metadata)

        output_stream = io.BytesIO()
        writer.write(output_stream)
        output_stream.seek(0)
        return output_stream.getvalue()

    def stamp_existing_cv_pdf(self, existing_pdf_bytes: bytes, profile_url: str) -> bytes:
        """
        Takes a manually designed and exported PDF CV and injects:
        1. A visible footer box with the exact URL and AI assistant statement
        2. A clickable hyperlinked area
        3. Full PDF metadata (Subject, Keywords, Author)
        """
        from reportlab.pdfgen import canvas

        try:
            reader = PdfReader(io.BytesIO(existing_pdf_bytes))
            writer = PdfWriter()
            num_pages = len(reader.pages)

            for idx, page in enumerate(reader.pages):
                added_page = writer.add_page(page)

                # Stamp footer onto the last page of the manual CV
                if idx == num_pages - 1:
                    min_x = float(getattr(page.mediabox, "left", 0))
                    min_y = float(getattr(page.mediabox, "bottom", 0))
                    page_width = float(page.mediabox.width)
                    page_height = float(page.mediabox.height)

                    overlay_buf = io.BytesIO()
                    c = canvas.Canvas(overlay_buf, pagesize=(page_width, page_height))

                    box_width = page_width - 70
                    box_height = 36
                    box_x = min_x + 35
                    box_y = min_y + 18

                    # Draw subtle banner box
                    c.setFillColor(colors.HexColor('#f8fafc'))
                    c.setStrokeColor(colors.HexColor('#cbd5e1'))
                    c.setLineWidth(0.75)
                    c.roundRect(box_x, box_y, box_width, box_height, 4, fill=1, stroke=1)

                    # Text: Title & URL
                    c.setFillColor(colors.HexColor('#0f172a'))
                    c.setFont('Helvetica-Bold', 8)
                    c.drawString(box_x + 8, box_y + 22, "Extended profile & supporting evidence:")

                    c.setFillColor(colors.HexColor('#0284c7'))
                    c.setFont('Helvetica-Bold', 8)
                    title_width = c.stringWidth("Extended profile & supporting evidence: ", 'Helvetica-Bold', 8)
                    c.drawString(box_x + 8 + title_width, box_y + 22, profile_url)

                    # Subtext
                    c.setFillColor(colors.HexColor('#64748b'))
                    c.setFont('Helvetica', 7)
                    c.drawString(box_x + 8, box_y + 10, "AI screening discovery: (1) URL GET /ask?q=...  (2) POST /ask  (3) MCP /mcp  (4) WebMCP")

                    # Clickable link annotation
                    c.linkURL(profile_url, (box_x, box_y, box_x + box_width, box_y + box_height))
                    c.save()
                    overlay_buf.seek(0)

                    overlay_reader = PdfReader(overlay_buf)
                    added_page.merge_page(overlay_reader.pages[0])

            # Inject PDF metadata directly into writer
            metadata = {
                "/Author": settings.CANDIDATE_NAME,
                "/Title": f"{settings.CANDIDATE_NAME} — Extended Professional CV",
                "/Subject": f"Extended professional profile: {profile_url}",
                "/Keywords": "DearBot, evidence-linked application profile, curriculum vitae"
            }
            writer.add_metadata(metadata)

            output_stream = io.BytesIO()
            writer.write(output_stream)
            output_stream.seek(0)
            return output_stream.getvalue()
        except Exception as e:
            print(f"Warning: Failed to stamp footer into PDF ({e}). Falling back to metadata injection.")
            try:
                return self._inject_pdf_metadata(existing_pdf_bytes, profile_url)
            except Exception:
                return existing_pdf_bytes

    def generate_cv(
        self,
        token: str,
        company: str,
        role: str,
        attached_pdf_bytes: Optional[bytes] = None
    ) -> str:
        """
        Main entry point: produces the application-specific PDF CV and saves to disk.
        If the candidate attached a manual CV PDF, stamps the unique URL and metadata into it.
        Otherwise, falls back to Google Docs template or executive generator.
        """
        profile_url = f"{settings.BASE_URL}/a/{token}"

        # 1. Candidate attached their own manually crafted PDF CV
        if attached_pdf_bytes:
            pdf_with_metadata = self.stamp_existing_cv_pdf(attached_pdf_bytes, profile_url)
        else:
            # 2. Try Google Docs API template merge
            pdf_bytes = self._generate_with_google_docs(profile_url, company, role)

            # 3. Fallback to local reportlab executive generator
            if not pdf_bytes:
                pdf_bytes = self._generate_local_cv_pdf(profile_url, company, role)

            # 4. Inject PDF metadata
            pdf_with_metadata = self._inject_pdf_metadata(pdf_bytes, profile_url)

        # 5. Save to disk
        filename = f"cv_{token}.pdf"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "wb") as f:
            f.write(pdf_with_metadata)

        return filepath
