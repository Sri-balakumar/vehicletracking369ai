# -*- coding: utf-8 -*-
"""
auto_financial_auditing/models/audit_transaction.py
====================================================
Core model for the Transaction Auditing Form.

Every financial transaction in Odoo (invoice, payment, purchase, journal
entry …) can be selected from a dropdown, its data is pulled automatically
from the database, and the auditor just needs to collect both signatures.
"""

import io
import base64

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

try:
    import barcode as _barcode
    from barcode.writer import ImageWriter as _ImageWriter
    HAS_BARCODE = True
except ImportError:
    HAS_BARCODE = False

_STATE_LABELS = {'draft': 'Draft', 'audited': 'Audited', 'rejected': 'Rejected'}


# ---------------------------------------------------------------------------
# Helper: map move_type → human-readable audit account type
# ---------------------------------------------------------------------------
MOVE_TYPE_LABEL = {
    'out_invoice':   'Sales Invoice',
    'out_refund':    'Sales Credit Note',
    'in_invoice':    'Purchase Invoice / Bill',
    'in_refund':     'Purchase Credit Note',
    'out_receipt':   'Sales Receipt',
    'in_receipt':    'Purchase Receipt',
    'entry':         'Journal Entry',
}

PAYMENT_TYPE_LABEL = {
    'inbound':  'Customer Payment (Receipt)',
    'outbound': 'Vendor Payment',
}


class AuditTransaction(models.Model):
    """
    One record per audited transaction.

    The user selects the move (or payment) from a dropdown; all financial
    data is fetched automatically from the original document.
    """
    _name = 'audit.transaction'
    _description = 'Audited Transaction'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'transaction_date desc, id desc'
    _rec_name = 'display_name'

    # ------------------------------------------------------------------
    # 1. TRANSACTION REFERENCE (dropdown of all posted moves / payments)
    # ------------------------------------------------------------------
    move_id = fields.Many2one(
        'account.move',
        string='Transaction Reference',
        required=True,
        domain="['|', ('move_type', '!=', 'entry'), ('journal_id.type', 'not in', ['cash', 'bank'])]",
        tracking=True,
        help='Select the journal entry / invoice / bill from the dropdown. '
             'All other fields are filled automatically.',
    )

    # 2. AUDIT ACCOUNT TYPE
    audit_account_type = fields.Selection([
        ('Sales Invoice',              'Sales / Invoice'),
        ('Sales Credit Note',          'Sales Credit Note'),
        ('Purchase Invoice / Bill',    'Purchase / Bill'),
        ('Purchase Credit Note',       'Purchase Credit Note'),
        ('Customer Payment (Receipt)', 'Customer Payment (Receipt)'),
        ('Vendor Payment',             'Vendor Payment'),
        ('Journal Entry',              'Journal Entry'),
    ], string='Audit Account Type', tracking=True, readonly=True)

    # 3. PARTNER
    partner_id = fields.Many2one(
        'res.partner', string='Partner', readonly=True, tracking=True)

    # 4. AMOUNT (subtotal before tax)
    amount_untaxed = fields.Monetary(
        string='Amount (before Tax)',
        currency_field='currency_id',
        readonly=True,
    )

    # 5. TAX AMOUNT (only shown when there is tax)
    has_tax = fields.Boolean(string='Has Tax', readonly=True)
    amount_tax = fields.Monetary(
        string='Tax Amount',
        currency_field='currency_id',
        readonly=True,
    )

    # 6. TOTAL
    amount_total = fields.Monetary(
        string='Total Amount',
        currency_field='currency_id',
        readonly=True,
    )

    # 7. SALESPERSON / CREATOR
    salesperson_id = fields.Many2one(
        'res.users', string='Salesperson / Creator', readonly=True)
    created_by = fields.Many2one(
        'res.users', string='Created By', readonly=True)

    # 7b. PAYMENT METHOD (auto-filled from journal/payment)
    payment_method = fields.Char(
        string='Payment Method', readonly=True)

    # 8. PARTNER SIGNATURE
    customer_signature = fields.Binary(
        string='Partner Signature',
        attachment=True,
    )
    customer_signed_by = fields.Char(
        string='Partner Name (Signed)',
        tracking=True,
    )
    customer_signed_date = fields.Datetime(
        string='Partner Signed Date',
        tracking=True,
    )

    # Courier delivery fields (alternative to partner signature)
    is_courier = fields.Boolean(
        string='Courier Delivery',
        default=False,
        help='Check if goods were delivered via courier.',
    )
    courier_proof = fields.Binary(
        string='Courier Proof',
        attachment=True,
        help='Upload courier delivery proof (photo, receipt, etc.).',
    )
    courier_proof_filename = fields.Char(string='Courier Proof Filename')

    # 9. CASHIER SIGNATURE
    cashier_signature = fields.Binary(
        string='Cashier Signature',
        attachment=True,
    )
    cashier_signed_by = fields.Char(
        string='Cashier Name (Signed)',
        tracking=True,
    )
    cashier_signed_date = fields.Datetime(
        string='Cashier Signed Date',
        tracking=True,
    )

    # ------------------------------------------------------------------
    # Additional auto-filled fields (metadata from original move)
    # ------------------------------------------------------------------
    transaction_date = fields.Date(
        string='Transaction Date', readonly=True)
    transaction_ref = fields.Char(
        string='Transaction Number / Ref', readonly=True)
    journal_id = fields.Many2one(
        'account.journal', string='Journal', readonly=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency', readonly=True,
        default=lambda self: self.env.company.currency_id,
    )
    company_id = fields.Many2one(
        'res.company', string='Company', readonly=True,
        default=lambda self: self.env.company,
    )

    # Audit Status
    state = fields.Selection([
        ('draft',    'Draft'),
        ('audited',  'Audited'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', tracking=True)

    # Computed display name
    display_name = fields.Char(
        string='Name', compute='_compute_display_name', store=True)

    # Link to the voucher/invoice attachment from original move
    source_attachment_ids = fields.Many2many(
        'ir.attachment',
        string='Source Voucher / Invoice Attachments',
        compute='_compute_source_attachments',
    )

    # ------------------------------------------------------------------
    # Line details pulled from the original move (read-only)
    # ------------------------------------------------------------------
    audit_line_ids = fields.One2many(
        'audit.transaction.line', 'audit_id',
        string='Transaction Line Details',
    )

    # QR Code (auto-generated from transaction data)
    qr_code_img = fields.Binary(
        string='QR Code',
        compute='_compute_qr_code',
        store=True,
        help='Scan to verify all transaction details.',
    )

    # Barcode (Code 128 of the invoice reference)
    barcode_img = fields.Binary(
        string='Barcode',
        compute='_compute_barcode_img',
        help='Code 128 barcode of the transaction reference number.',
    )

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    _sql_constraints = [
        ('unique_move_audit',
         'UNIQUE(move_id)',
         'This transaction has already been audited. '
         'Each transaction can only be audited once.'),
    ]

    # ------------------------------------------------------------------
    # Compute / Onchange
    # ------------------------------------------------------------------
    @api.depends('transaction_ref', 'transaction_date', 'partner_id',
                 'amount_total', 'state', 'currency_id', 'company_id',
                 'audit_account_type', 'journal_id')
    def _compute_qr_code(self):
        for rec in self:
            if not rec.transaction_ref or not HAS_QRCODE:
                rec.qr_code_img = False
                continue
            qr_data = '\n'.join([
                f"Ref: {rec.transaction_ref}",
                f"Date: {rec.transaction_date or ''}",
                f"Type: {rec.audit_account_type or ''}",
                f"Partner: {rec.partner_id.name if rec.partner_id else ''}",
                f"Amount: {rec.amount_total:.2f} {rec.currency_id.name if rec.currency_id else ''}",
                f"Status: {_STATE_LABELS.get(rec.state, rec.state)}",
                f"Company: {rec.company_id.name if rec.company_id else ''}",
                f"Journal: {rec.journal_id.name if rec.journal_id else ''}",
            ])
            try:
                qr = qrcode.QRCode(
                    version=None,
                    error_correction=qrcode.constants.ERROR_CORRECT_M,
                    box_size=6,
                    border=2,
                )
                qr.add_data(qr_data)
                qr.make(fit=True)
                img = qr.make_image(fill_color='black', back_color='white')
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                rec.qr_code_img = base64.b64encode(buf.getvalue())
            except Exception:
                rec.qr_code_img = False

    @api.depends('transaction_ref')
    def _compute_barcode_img(self):
        for rec in self:
            if not rec.transaction_ref:
                rec.barcode_img = False
                continue
            try:
                # reportlab is always available in Odoo (used for PDF generation)
                from reportlab.graphics.barcode import createBarcodeDrawing
                from reportlab.graphics import renderPM
                drawing = createBarcodeDrawing(
                    'Code128',
                    value=rec.transaction_ref,
                    barHeight=40,
                    width=340,
                    height=60,
                )
                buf = io.BytesIO()
                renderPM.drawToFile(drawing, buf, fmt='PNG')
                rec.barcode_img = base64.b64encode(buf.getvalue())
            except Exception:
                rec.barcode_img = False

    @api.depends('transaction_ref', 'audit_account_type', 'partner_id')
    def _compute_display_name(self):
        for rec in self:
            parts = [rec.transaction_ref or '(New)']
            if rec.audit_account_type:
                parts.append(rec.audit_account_type)
            if rec.partner_id:
                parts.append(rec.partner_id.name)
            rec.display_name = ' | '.join(parts)

    @api.depends('move_id')
    def _compute_source_attachments(self):
        """Fetch attachments linked to the original move document."""
        Attachment = self.env['ir.attachment']
        for rec in self:
            if not rec.move_id:
                rec.source_attachment_ids = False
                continue
            rec.source_attachment_ids = Attachment.search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', rec.move_id.id),
            ])

    @api.onchange('move_id')
    def _onchange_move_id(self):
        """
        When a transaction is selected from the dropdown, pull ALL relevant
        data automatically from the original record in the database.
        This guarantees financial accuracy — no manual re-entry.
        """
        if self.move_id:
            existing = self.env['audit.transaction'].search([
                ('move_id', '=', self.move_id.id),
                ('id', '!=', self._origin.id or 0),
            ], limit=1)
            if existing:
                move_name = self.move_id.name
                self.move_id = False
                return {
                    'warning': {
                        'title': _('Duplicate Transaction Reference'),
                        'message': _(
                            'Transaction "%s" has already been audited.\n\n'
                            'Audit record: %s\n\n'
                            'Each transaction can only be audited once.'
                        ) % (move_name, existing.display_name),
                    }
                }
        self._fill_from_move()

    def _fill_from_move(self):
        """Fill all fields from the selected account.move."""
        for rec in self:
            move = rec.move_id
            if not move:
                rec._clear_fields()
                continue

            # Determine audit type label
            audit_type = MOVE_TYPE_LABEL.get(move.move_type, 'Journal Entry')

            # Partner: invoice partner or first line partner
            partner = move.partner_id

            # Amounts
            amount_untaxed = move.amount_untaxed
            amount_tax     = move.amount_tax
            amount_total   = move.amount_total

            # For inbound/outbound moves negate if credit note
            if move.move_type in ('out_refund', 'in_refund'):
                amount_untaxed = -abs(amount_untaxed)
                amount_tax     = -abs(amount_tax)
                amount_total   = -abs(amount_total)

            # Salesperson
            salesperson = (
                move.invoice_user_id
                or move.user_id
                or move.create_uid
            )

            # Payment method: most specific → least specific
            # Priority: payment method line name → journal type label → journal name
            _JOURNAL_TYPE_LABEL = {
                'cash':     'Cash',
                'bank':     'Bank Transfer',
                'sale':     'Customer Account',
                'purchase': 'Supplier Account',
                'general':  'General',
            }
            payment_method_name = False

            # 1. Check payment method line (Odoo 16+ account.payment)
            payment = getattr(move, 'payment_id', None)
            if payment:
                method_line = getattr(payment, 'payment_method_line_id', None)
                if method_line and method_line.name:
                    payment_method_name = method_line.name
                elif getattr(payment, 'payment_method_id', None) and payment.payment_method_id.name:
                    payment_method_name = payment.payment_method_id.name

            # 2. Fall back to journal type → human-readable label
            if not payment_method_name and move.journal_id:
                payment_method_name = _JOURNAL_TYPE_LABEL.get(
                    move.journal_id.type, move.journal_id.type.capitalize())

            rec.audit_account_type  = audit_type
            rec.partner_id          = partner.id if partner else False
            rec.amount_untaxed      = amount_untaxed
            rec.amount_tax          = amount_tax
            rec.has_tax             = bool(amount_tax)
            rec.amount_total        = amount_total
            rec.salesperson_id      = salesperson.id if salesperson else False
            rec.created_by          = move.create_uid.id
            rec.transaction_date    = move.date
            rec.transaction_ref     = move.name
            rec.journal_id          = move.journal_id.id
            rec.currency_id         = move.currency_id.id
            rec.company_id          = move.company_id.id
            rec.payment_method      = payment_method_name
            # Auto-fill partner name in signature tab
            rec.customer_signed_by  = partner.name if partner else False
            rec.customer_signed_date = rec.customer_signed_date or fields.Datetime.now()
            # Auto-fill cashier name from current user (only if not already set)
            rec.cashier_signed_by   = rec.cashier_signed_by or self.env.user.name
            rec.cashier_signed_date = rec.cashier_signed_date or fields.Datetime.now()

            # Pull detail lines
            rec.audit_line_ids = [(5, 0, 0)]  # clear existing
            lines = []
            for ml in move.invoice_line_ids.filtered(
                    lambda l: l.display_type == 'product'):
                lines.append((0, 0, {
                    'product_id':   ml.product_id.id,
                    'name':         ml.name,
                    'quantity':     ml.quantity,
                    'price_unit':   ml.price_unit,
                    'tax_amount':   sum(
                        ml.tax_ids.compute_all(
                            ml.price_unit, quantity=ml.quantity,
                            partner=ml.partner_id,
                        ).get('taxes', [{}])[0].get('amount', 0)
                        for _ in [1]
                    ) if ml.tax_ids else 0.0,
                    'subtotal':     ml.price_subtotal,
                    'account_id':   ml.account_id.id,
                }))
            if lines:
                rec.audit_line_ids = lines

    def _clear_fields(self):
        self.audit_account_type = False
        self.partner_id = False
        self.amount_untaxed = 0.0
        self.amount_tax = 0.0
        self.has_tax = False
        self.amount_total = 0.0
        self.salesperson_id = False
        self.created_by = False
        self.transaction_date = False
        self.transaction_ref = False
        self.journal_id = False
        self.currency_id = self.env.company.currency_id
        self.payment_method = False
        self.customer_signed_by = False
        self.audit_line_ids = [(5, 0, 0)]

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------
    def action_mark_audited(self):
        for rec in self:
            # Cashier signature is always mandatory
            if not rec.cashier_signature:
                raise ValidationError(
                    _('Cashier Signature is required before marking as Audited.'))

            # Partner signature is mandatory only for Sales Invoices
            # (customer account receivable / credit transactions).
            # Exception: if courier delivery is checked AND courier proof
            # is uploaded, either courier proof OR signature is sufficient.
            if rec.audit_account_type == 'Sales Invoice':
                has_courier_proof = rec.is_courier and rec.courier_proof
                if not rec.customer_signature and not has_courier_proof:
                    raise ValidationError(
                        _('For Sales Invoice transactions, either a Partner '
                          'Signature or a Courier Proof (with courier checked) '
                          'is required before marking as Audited.'))

            rec.state = 'audited'

    def action_reset_draft(self):
        for rec in self:
            rec.state = 'draft'

    def action_reject(self):
        for rec in self:
            rec.state = 'rejected'

    def action_print_voucher(self):
        """Print the transaction audit voucher PDF."""
        return self.env.ref(
            'auto_financial_auditing.action_report_audit_transaction'
        ).report_action(self)

    # ------------------------------------------------------------------
    # Create override: re-fill from move on create (in case onchange
    # was not triggered, e.g. programmatic creation)
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.move_id and not rec.transaction_ref:
                rec._fill_from_move()
        return records


class AuditTransactionLine(models.Model):
    """Detail lines pulled from the original move's invoice lines."""
    _name = 'audit.transaction.line'
    _description = 'Audit Transaction Line'
    _order = 'id'

    audit_id = fields.Many2one(
        'audit.transaction', string='Audit Record',
        ondelete='cascade', required=True)
    product_id = fields.Many2one(
        'product.product', string='Product', readonly=True)
    name = fields.Char(string='Description', readonly=True)
    quantity = fields.Float(
        string='Quantity', digits='Product Unit of Measure', readonly=True)
    price_unit = fields.Float(
        string='Unit Price', digits='Product Price', readonly=True)
    tax_amount = fields.Float(
        string='Tax Amount', digits=(16, 2), readonly=True)
    subtotal = fields.Float(
        string='Subtotal', digits=(16, 2), readonly=True)
    account_id = fields.Many2one(
        'account.account', string='Account', readonly=True)
    currency_id = fields.Many2one(
        'res.currency', related='audit_id.currency_id')
