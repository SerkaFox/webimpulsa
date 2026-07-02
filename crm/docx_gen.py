"""Word document (.docx) generation for commercial proposals."""
import io
import logging
from datetime import date

logger = logging.getLogger(__name__)

# Colors (hex without #)
_BLUE   = '1760D6'
_DARK   = '0C1C42'
_MUTED  = '5A6D8C'
_LIGHT  = 'D0E1FA'
_BG     = 'F5F9FF'
_WHITE  = 'FFFFFF'
_GREEN  = '009E73'


def generate_proposal_docx(proposal) -> bytes | None:
    """Generate an editable Word document for the proposal. Returns bytes or None."""
    try:
        from docx import Document
        from docx.shared import Pt, Cm, RGBColor, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
    except ImportError:
        logger.error('python-docx not installed')
        return None

    def _hex(h):
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        return RGBColor(r, g, b)

    def _set_cell_bg(cell, hex_color):
        tc   = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd  = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), hex_color)
        tcPr.append(shd)

    def _set_borders(table, color='D0E1FA'):
        tbl   = table._tbl
        tblPr = tbl.tblPr
        tblBorders = OxmlElement('w:tblBorders')
        for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
            el = OxmlElement(f'w:{side}')
            el.set(qn('w:val'), 'single')
            el.set(qn('w:sz'), '4')
            el.set(qn('w:space'), '0')
            el.set(qn('w:color'), color)
            tblBorders.append(el)
        tblPr.append(tblBorders)

    try:
        doc = Document()

        # Page margins (2 cm)
        for section in doc.sections:
            section.top_margin    = Cm(2)
            section.bottom_margin = Cm(2)
            section.left_margin   = Cm(2.5)
            section.right_margin  = Cm(2.5)

        # Default font
        style = doc.styles['Normal']
        style.font.name = 'Calibri'
        style.font.size = Pt(10)
        style.font.color.rgb = _hex(_DARK)

        c = proposal.company_data or {}
        issued = (proposal.issued_at.strftime('%d/%m/%Y')
                  if hasattr(proposal.issued_at, 'strftime') else str(proposal.issued_at or ''))

        # ── Header ──────────────────────────────────────────────────────────────
        tbl = doc.add_table(rows=1, cols=2)
        tbl.style = 'Table Grid'
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.columns[0].width = Cm(10)
        tbl.columns[1].width = Cm(7)

        row = tbl.rows[0]
        # Left: company name
        lc = row.cells[0]
        _set_cell_bg(lc, _BLUE)
        p = lc.paragraphs[0]
        p.clear()
        run = p.add_run(c.get('trade_name', 'WebImpulsa'))
        run.font.size  = Pt(22)
        run.font.bold  = True
        run.font.color.rgb = _hex(_WHITE)
        lc.paragraphs[0].paragraph_format.space_before = Pt(6)
        lc.paragraphs[0].paragraph_format.space_after  = Pt(2)
        p2 = lc.add_paragraph(c.get('website', 'webimpulsa.es'))
        p2.runs[0].font.color.rgb = RGBColor(0xBF, 0xDB, 0xFE)
        p2.runs[0].font.size = Pt(9)
        p2.paragraph_format.space_after = Pt(6)

        # Right: proposal meta
        rc = row.cells[1]
        _set_cell_bg(rc, _DARK)
        rc.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        for line, bold in [
            ('PROPUESTA COMERCIAL', True),
            (f'Nº {proposal.number}', False),
            (f'Fecha: {issued}', False),
            (f'Válido: {proposal.valid_days} días', False),
        ]:
            p = rc.add_paragraph(line)
            p.runs[0].font.color.rgb = _hex(_WHITE)
            p.runs[0].font.size = Pt(10 if bold else 9)
            p.runs[0].font.bold = bold
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after  = Pt(1)

        # Remove first empty paragraph in right cell
        rc.paragraphs[0].clear()

        doc.add_paragraph()

        # ── Emisor / Cliente ─────────────────────────────────────────────────────
        tbl2 = doc.add_table(rows=1, cols=2)
        tbl2.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_borders(tbl2)

        lc2 = tbl2.rows[0].cells[0]
        rc2 = tbl2.rows[0].cells[1]
        _set_cell_bg(lc2, _BG)
        _set_cell_bg(rc2, _BG)

        def _block(cell, title, lines):
            p = cell.paragraphs[0]
            p.clear()
            r = p.add_run(title)
            r.font.bold = True
            r.font.size = Pt(8)
            r.font.color.rgb = _hex(_BLUE)
            for line in lines:
                if line is None:
                    # Blank fill line
                    pb = cell.add_paragraph('_' * 38)
                    pb.runs[0].font.color.rgb = _hex(_MUTED)
                    pb.runs[0].font.size = Pt(10)
                    pb.paragraph_format.space_after = Pt(3)
                else:
                    pb = cell.add_paragraph(line)
                    pb.runs[0].font.size = Pt(10)
                    pb.runs[0].font.color.rgb = _hex(_DARK)
                    pb.paragraph_format.space_after = Pt(2)

        company_lines = []
        if c.get('legal_name'):  company_lines.append(c['legal_name'])
        if c.get('nif'):         company_lines.append(f"NIF/NIE: {c['nif']}")
        if c.get('address'):     company_lines.append(c['address'])
        if c.get('city'):        company_lines.append(c['city'])
        if c.get('email'):       company_lines.append(c['email'])
        if c.get('phone'):       company_lines.append(c['phone'])
        _block(lc2, 'EMISOR', company_lines)

        client_lines = []
        if proposal.client_name:      client_lines.append(proposal.client_name)
        if proposal.client_email:     client_lines.append(proposal.client_email)
        if proposal.client_phone:     client_lines.append(proposal.client_phone)
        if proposal.client_biz_type:  client_lines.append(proposal.client_biz_type)
        client_lines += ['NIF / CIF (para factura):', None, 'Dirección fiscal:', None]
        _block(rc2, 'PREPARADO PARA', client_lines)

        doc.add_paragraph()

        # ── Project summary ──────────────────────────────────────────────────────
        p = doc.add_paragraph()
        r = p.add_run('Proyecto: ')
        r.font.bold = True
        r.font.color.rgb = _hex(_DARK)
        p.add_run(f"{proposal.project_name or proposal.package or '—'}").font.color.rgb = _hex(_MUTED)
        p2 = doc.add_paragraph()
        r2 = p2.add_run('Plazo estimado: ')
        r2.font.bold = True
        r2.font.color.rgb = _hex(_DARK)
        p2.add_run(proposal.timeline or '—').font.color.rgb = _hex(_MUTED)

        doc.add_paragraph()

        # ── Pricing table ────────────────────────────────────────────────────────
        ph = doc.add_paragraph('DESGLOSE ECONÓMICO')
        ph.runs[0].font.bold  = True
        ph.runs[0].font.size  = Pt(8)
        ph.runs[0].font.color.rgb = _hex(_BLUE)

        price_rows = [('Concepto', 'Importe', True)]
        price_rows.append((proposal.package or 'Paquete base',
                           f'{proposal.package_base_price} €', False))
        for e in (proposal.extras or []):
            price_rows.append((f"  + {e.get('name','')}", f"{e.get('price',0)} €", False))
        if proposal.rush and proposal.rush_amount:
            price_rows.append(('  + Urgencia (×1.25)', f'+{proposal.rush_amount} €', False))

        subtotal = proposal.package_base_price + proposal.extras_price + proposal.rush_amount
        price_rows.append(('Subtotal', f'{subtotal} €', False))
        price_rows.append((f'Descuento {proposal.discount_pct}%',
                           f'−{proposal.discount_amount} €', False))
        price_rows.append(('Base imponible', f'{proposal.taxable_base} €', False))
        price_rows.append(('IVA 21%', f'{proposal.iva_amount} €', False))
        price_rows.append(('TOTAL CON IVA', f'{proposal.total_with_iva} €', True))
        if proposal.maintenance_plan:
            price_rows.append((f'Mantenimiento: {proposal.maintenance_plan}',
                               f'{proposal.maintenance_price} €/mes', False))

        pt = doc.add_table(rows=len(price_rows), cols=2)
        pt.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_borders(pt)
        for i, (label, value, bold) in enumerate(price_rows):
            lc3 = pt.rows[i].cells[0]
            rc3 = pt.rows[i].cells[1]
            if i == 0:
                _set_cell_bg(lc3, _BLUE)
                _set_cell_bg(rc3, _BLUE)
            elif bold:
                _set_cell_bg(lc3, 'EDF4FF')
                _set_cell_bg(rc3, 'EDF4FF')

            for cell, text in [(lc3, label), (rc3, value)]:
                p = cell.paragraphs[0]
                p.clear()
                r = p.add_run(text)
                r.font.bold  = bold
                r.font.size  = Pt(10)
                r.font.color.rgb = _hex(_WHITE if i == 0 else (_BLUE if bold else _DARK))
                if cell is rc3:
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        doc.add_paragraph()

        # ── Alcance / Fuera de alcance ───────────────────────────────────────────
        for title, items in [
            ('ALCANCE DEL PROYECTO', proposal.scope or []),
            ('FUERA DE ALCANCE',     proposal.out_of_scope or []),
        ]:
            ph = doc.add_paragraph(title)
            ph.runs[0].font.bold  = True
            ph.runs[0].font.size  = Pt(8)
            ph.runs[0].font.color.rgb = _hex(_BLUE)
            for item in items:
                pi = doc.add_paragraph(style='List Bullet')
                pi.text = item
                pi.runs[0].font.size = Pt(10)
                pi.runs[0].font.color.rgb = _hex(_DARK if title.startswith('ALCANCE') else _MUTED)
            doc.add_paragraph()

        # ── Condiciones ──────────────────────────────────────────────────────────
        ph = doc.add_paragraph('CONDICIONES GENERALES')
        ph.runs[0].font.bold  = True
        ph.runs[0].font.size  = Pt(8)
        ph.runs[0].font.color.rgb = _hex(_BLUE)
        for i, cond in enumerate(proposal.conditions or [], 1):
            pc = doc.add_paragraph(f'{i}. {cond}')
            pc.runs[0].font.size  = Pt(9)
            pc.runs[0].font.color.rgb = _hex(_MUTED)
            pc.paragraph_format.space_after = Pt(3)

        doc.add_paragraph()

        # ── Signature block ──────────────────────────────────────────────────────
        ph = doc.add_paragraph('ACEPTACIÓN')
        ph.runs[0].font.bold  = True
        ph.runs[0].font.size  = Pt(8)
        ph.runs[0].font.color.rgb = _hex(_BLUE)

        ps = doc.add_paragraph(
            'La firma de este documento implica aceptación del alcance, precio y condiciones indicadas.'
        )
        ps.runs[0].font.size  = Pt(9)
        ps.runs[0].font.color.rgb = _hex(_MUTED)

        sig = doc.add_table(rows=2, cols=4)
        sig.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_borders(sig, 'E2E8F0')
        labels = ['Nombre completo', 'NIF / CIF', 'Fecha', 'Firma']
        for j, label in enumerate(labels):
            top = sig.rows[0].cells[j]
            bot = sig.rows[1].cells[j]
            p = top.paragraphs[0]
            p.clear()
            r = p.add_run(label)
            r.font.size  = Pt(8)
            r.font.color.rgb = _hex(_MUTED)
            r.font.bold  = True
            bot.add_paragraph('')
            bot.add_paragraph('')

        doc.add_paragraph()

        # ── Footer ──────────────────────────────────────────────────────────────
        foot = doc.add_paragraph(
            f"{c.get('trade_name','WebImpulsa')} · {c.get('email','info@webimpulsa.es')}"
            f" · {c.get('phone','')} · {c.get('website','webimpulsa.es')}"
            + (f" · NIF {c['nif']}" if c.get('nif') else '')
        )
        foot.runs[0].font.size  = Pt(8)
        foot.runs[0].font.color.rgb = _hex(_MUTED)
        foot.alignment = WD_ALIGN_PARAGRAPH.CENTER

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        result = buf.read()
        logger.info('DOCX generated for proposal %s (%d bytes)', proposal.number, len(result))
        return result

    except Exception as exc:
        logger.error('DOCX generation failed for proposal %s: %s', proposal.number, exc, exc_info=True)
        return None
