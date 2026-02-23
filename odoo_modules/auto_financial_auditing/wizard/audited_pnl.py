# -*- coding: utf-8 -*-
"""
wizard/audited_pnl.py
======================
Generates an Audited Profit & Loss Report that ONLY includes entries
from transactions that have been audited (audit.transaction state='audited').

Structure mirrors the advanced net profit report:
  Revenue (from audited sales invoices)
  - COGS (from audited invoice lines × product cost)
  = Gross Profit
  + Other Income (audited)
  - Indirect Expenses (audited)
  - Depreciation (audited)
  = Audited Net Profit
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta, date
import calendar
import io
import base64

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class AuditedPnl(models.TransientModel):
    _name = 'audited.pnl'
    _description = 'Audited Profit & Loss Report'

    name = fields.Char(string='Report Name', default='Audited P&L Report')

    # ── Period preset ──────────────────────────────────────────────────────
    period_preset = fields.Selection([
        ('this_month',   'This Month'),
        ('last_month',   'Last Month'),
        ('this_quarter', 'This Quarter'),
        ('last_quarter', 'Last Quarter'),
        ('this_year',    'This Year'),
        ('last_year',    'Last Year'),
        ('today',        'Today'),
        ('yesterday',    'Yesterday'),
        ('this_week',    'This Week'),
        ('last_week',    'Last Week'),
        ('custom',       'Custom Range'),
    ], string='Period', default='this_month')

    date_from = fields.Date(string='Start Date', required=True)
    date_to   = fields.Date(string='End Date',   required=True,
                             default=fields.Date.context_today)

    # ── Company scope ──────────────────────────────────────────────────────
    company_scope = fields.Selection([
        ('all',      'All Active Companies'),
        ('selected', 'Selected Companies'),
    ], string='Company Scope', default='all', required=True)

    company_ids = fields.Many2many(
        'res.company', string='Companies',
        default=lambda self: self.env.companies,
    )
    target_move = fields.Selection([
        ('posted', 'All Posted Entries'),
        ('all',    'All Entries'),
    ], string='Target Moves', default='posted', required=True)

    currency_id = fields.Many2one(
        'res.currency', compute='_compute_currency_id')
    company_names = fields.Char(compute='_compute_company_names')

    # Computed totals
    revenue_total           = fields.Monetary(currency_field='currency_id', readonly=True)
    cogs_total              = fields.Monetary(currency_field='currency_id', readonly=True)
    gross_profit            = fields.Monetary(currency_field='currency_id', readonly=True)
    other_income_total      = fields.Monetary(currency_field='currency_id', readonly=True)
    indirect_expense_total  = fields.Monetary(currency_field='currency_id', readonly=True)
    depreciation_total      = fields.Monetary(currency_field='currency_id', readonly=True)
    net_profit              = fields.Monetary(currency_field='currency_id', readonly=True)

    line_ids = fields.One2many(
        'audited.pnl.line', 'report_id', string='Report Lines')

    @api.onchange('period_preset')
    def _onchange_period_preset(self):
        if self.period_preset == 'custom':
            return
        today = fields.Date.context_today(self)
        y, m = today.year, today.month

        if self.period_preset == 'today':
            self.date_from = self.date_to = today
        elif self.period_preset == 'yesterday':
            d = today - timedelta(days=1)
            self.date_from = self.date_to = d
        elif self.period_preset == 'this_week':
            self.date_from = today - timedelta(days=today.weekday())
            self.date_to   = self.date_from + timedelta(days=6)
        elif self.period_preset == 'last_week':
            start = today - timedelta(days=today.weekday()) - timedelta(weeks=1)
            self.date_from = start
            self.date_to   = start + timedelta(days=6)
        elif self.period_preset == 'this_month':
            self.date_from = today.replace(day=1)
            self.date_to   = today.replace(day=calendar.monthrange(y, m)[1])
        elif self.period_preset == 'last_month':
            last = today.replace(day=1) - timedelta(days=1)
            self.date_from = last.replace(day=1)
            self.date_to   = last
        elif self.period_preset == 'this_quarter':
            q_start = ((m - 1) // 3) * 3 + 1
            q_end   = q_start + 2
            self.date_from = date(y, q_start, 1)
            self.date_to   = date(y, q_end, calendar.monthrange(y, q_end)[1])
        elif self.period_preset == 'last_quarter':
            q_start = ((m - 1) // 3) * 3 + 1
            if q_start == 1:
                self.date_from = date(y - 1, 10, 1)
                self.date_to   = date(y - 1, 12, 31)
            else:
                lq_start = q_start - 3
                lq_end   = lq_start + 2
                self.date_from = date(y, lq_start, 1)
                self.date_to   = date(y, lq_end, calendar.monthrange(y, lq_end)[1])
        elif self.period_preset == 'this_year':
            self.date_from = date(y, 1, 1)
            self.date_to   = date(y, 12, 31)
        elif self.period_preset == 'last_year':
            self.date_from = date(y - 1, 1, 1)
            self.date_to   = date(y - 1, 12, 31)

    @api.onchange('company_scope')
    def _onchange_company_scope(self):
        if self.company_scope == 'all':
            self.company_ids = self.env.companies

    @api.depends('company_ids')
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = (
                rec.company_ids[0].currency_id
                if rec.company_ids else self.env.company.currency_id
            )

    @api.depends('company_ids')
    def _compute_company_names(self):
        for rec in self:
            rec.company_names = ', '.join(rec.company_ids.mapped('name')) or ''

    def _company_ids(self):
        companies = self.company_ids
        for c in self.company_ids:
            companies |= c.child_ids
        return companies.ids

    def _get_audited_move_ids(self):
        audits = self.env['audit.transaction'].search([
            ('state', '=', 'audited'),
            ('transaction_date', '>=', self.date_from),
            ('transaction_date', '<=', self.date_to),
            ('company_id', 'in', self._company_ids()),
        ])
        return audits.mapped('move_id').ids

    def _get_audited_account_balances(self, move_ids, account_types):
        """Return list of {account_id, account_code, account_name, balance}."""
        if not move_ids:
            return []

        domain = [
            ('move_id', 'in', move_ids),
            ('account_id.account_type', 'in', account_types),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        lines = self.env['account.move.line'].search(domain)
        acc_data = {}
        for ml in lines:
            aid = ml.account_id.id
            if aid not in acc_data:
                acc_data[aid] = {
                    'account_id':   aid,
                    'account_code': ml.account_id.code or '',
                    'account_name': ml.account_id.name,
                    'balance':      0.0,
                }
            acc_data[aid]['balance'] += ml.balance
        return list(acc_data.values())

    def _get_audited_cogs(self, move_ids):
        """COGS from audited out_invoice lines: product cost × quantity."""
        if not move_ids:
            return []

        domain = [
            ('id', 'in', move_ids),
            ('move_type', 'in', ['out_invoice', 'out_refund']),
        ]
        invoices = self.env['account.move'].search(domain)
        acc_data = {}
        for inv in invoices:
            sign = 1 if inv.move_type == 'out_invoice' else -1
            for line in inv.invoice_line_ids.filtered(
                    lambda l: l.product_id and l.display_type == 'product'):
                cost = line.product_id.standard_price or 0.0
                cogs_amount = cost * line.quantity * sign
                acc = (line.product_id.property_account_expense_id
                       or line.product_id.categ_id.property_account_expense_categ_id)
                if not acc:
                    continue
                if acc.id not in acc_data:
                    acc_data[acc.id] = {
                        'account_id':   acc.id,
                        'account_code': acc.code or '',
                        'account_name': acc.name,
                        'balance':      0.0,
                    }
                acc_data[acc.id]['balance'] += cogs_amount
        return list(acc_data.values())

    def action_compute(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('Start Date must be before End Date.'))

        # Clear existing lines
        self.line_ids.unlink()

        move_ids = self._get_audited_move_ids()

        SECTION_MAP = {
            'revenue':          (['income'], False),
            'cogs':             ([], True),   # True = use COGS logic
            'other_income':     (['income_other'], False),
            'indirect_expense': (['expense'], False),
            'depreciation':     (['expense_depreciation'], False),
        }

        totals = {}
        line_vals = []

        for section, (acc_types, is_cogs) in SECTION_MAP.items():
            if is_cogs:
                balances = self._get_audited_cogs(move_ids)
            else:
                balances = self._get_audited_account_balances(move_ids, acc_types)

            # Sign conventions
            section_total = 0.0
            for b in balances:
                amount = b['balance']
                if section in ('revenue', 'other_income'):
                    amount = -amount  # income accounts are credit (negative)
                section_total += amount
                line_vals.append({
                    'report_id':    self.id,
                    'section':      section,
                    'account_id':   b['account_id'],
                    'account_code': b['account_code'],
                    'account_name': b['account_name'],
                    'amount':       amount,
                })
            totals[section] = section_total

        gross_profit = totals.get('revenue', 0) - totals.get('cogs', 0)
        net_profit   = (
            gross_profit
            + totals.get('other_income', 0)
            - totals.get('indirect_expense', 0)
            - totals.get('depreciation', 0)
        )

        self.write({
            'revenue_total':          totals.get('revenue', 0),
            'cogs_total':             totals.get('cogs', 0),
            'gross_profit':           gross_profit,
            'other_income_total':     totals.get('other_income', 0),
            'indirect_expense_total': totals.get('indirect_expense', 0),
            'depreciation_total':     totals.get('depreciation', 0),
            'net_profit':             net_profit,
        })

        for lv in line_vals:
            self.env['audited.pnl.line'].create(lv)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Audited P&L Report'),
            'res_model': 'audited.pnl',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'views': [(
                self.env.ref(
                    'auto_financial_auditing.view_audited_pnl_result'
                ).id, 'form'
            )],
        }

    def action_print_pdf(self):
        self.ensure_one()
        if not self.line_ids and not self.revenue_total:
            raise UserError(_('Please compute the report first.'))
        return self.env.ref(
            'auto_financial_auditing.action_report_audited_pnl'
        ).report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError(_('xlsxwriter library is required. Run: pip install xlsxwriter'))

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('Audited P&L')

        title_fmt   = wb.add_format({'bold': True, 'font_size': 16, 'align': 'center',
                                      'bg_color': '#1B4F72', 'font_color': 'white'})
        hdr_fmt     = wb.add_format({'bold': True, 'bg_color': '#1a237e',
                                      'font_color': 'white', 'border': 1})
        sec_fmt     = wb.add_format({'bold': True, 'bg_color': '#e8eaf6', 'border': 1})
        acct_fmt    = wb.add_format({'border': 1})
        money_fmt   = wb.add_format({'num_format': '#,##0.00', 'border': 1, 'align': 'right'})
        money_sec   = wb.add_format({'num_format': '#,##0.00', 'bold': True, 'border': 1,
                                      'align': 'right', 'bg_color': '#e8eaf6'})
        profit_fmt  = wb.add_format({'num_format': '#,##0.00', 'bold': True, 'border': 2,
                                      'align': 'right', 'bg_color': '#c8e6c9', 'font_size': 12})
        loss_fmt    = wb.add_format({'num_format': '#,##0.00', 'bold': True, 'border': 2,
                                      'align': 'right', 'bg_color': '#ffcdd2', 'font_size': 12})

        ws.set_column(0, 0, 15)
        ws.set_column(1, 1, 42)
        ws.set_column(2, 2, 22)

        ws.merge_range('A1:C1', 'AUDITED PROFIT & LOSS REPORT', title_fmt)
        ws.write(1, 0, 'Company:')
        ws.write(1, 1, self.company_names or '')
        ws.write(2, 0, 'Period:')
        ws.write(2, 1, f'{self.date_from} to {self.date_to}')
        ws.write(3, 0, 'NOTE:', wb.add_format({'bold': True, 'font_color': '#c0392b'}))
        ws.write(3, 1, 'Only transactions verified through the Audit form are included.',
                 wb.add_format({'italic': True, 'font_color': '#c0392b'}))

        row = 5
        ws.write(row, 0, 'Code', hdr_fmt)
        ws.write(row, 1, 'Account', hdr_fmt)
        ws.write(row, 2, 'Amount', hdr_fmt)
        row += 1

        sections_order = [
            ('revenue',         'REVENUE (Audited Direct Income)',    self.revenue_total,          self.line_ids.filtered(lambda l: l.section == 'revenue')),
            ('cogs',            'COST OF REVENUE (COGS)',              self.cogs_total,             self.line_ids.filtered(lambda l: l.section == 'cogs')),
            ('gross_profit',    'GROSS PROFIT',                        self.gross_profit,           None),
            ('other_income',    'OTHER INCOME (Audited)',              self.other_income_total,     self.line_ids.filtered(lambda l: l.section == 'other_income')),
            ('indirect_expense','INDIRECT EXPENSES (Audited)',         self.indirect_expense_total, self.line_ids.filtered(lambda l: l.section == 'indirect_expense')),
            ('depreciation',    'DEPRECIATION & AMORTIZATION (Audited)', self.depreciation_total,  self.line_ids.filtered(lambda l: l.section == 'depreciation')),
            ('net_profit',      'AUDITED NET PROFIT',                  self.net_profit,             None),
        ]

        for sec_key, label, total, lines in sections_order:
            ws.write(row, 0, '', sec_fmt)
            ws.write(row, 1, label, sec_fmt)
            ws.write(row, 2, '', sec_fmt)
            row += 1
            if lines:
                for line in lines:
                    ws.write(row, 0, line.account_code or '', acct_fmt)
                    ws.write(row, 1, line.account_name or '', acct_fmt)
                    ws.write(row, 2, line.amount, money_fmt)
                    row += 1
            if sec_key in ('gross_profit', 'net_profit'):
                fmt = profit_fmt if total >= 0 else loss_fmt
                ws.write(row, 0, '', fmt)
                ws.write(row, 1, label, fmt)
                ws.write(row, 2, total, fmt)
            else:
                ws.write(row, 0, '', money_sec)
                ws.write(row, 1, f'Total {label}', sec_fmt)
                ws.write(row, 2, total, money_sec)
            row += 2

        wb.close()
        att = self.env['ir.attachment'].create({
            'name': f'Audited_PnL_{self.date_from}_{self.date_to}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.getvalue()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{att.id}?download=true',
            'target': 'new',
        }


class AuditedPnlLine(models.TransientModel):
    _name = 'audited.pnl.line'
    _description = 'Audited P&L Line'
    _order = 'section, account_code'

    report_id    = fields.Many2one('audited.pnl', ondelete='cascade')
    section      = fields.Selection([
        ('revenue',          'Revenue'),
        ('cogs',             'Cost of Revenue'),
        ('other_income',     'Other Income'),
        ('indirect_expense', 'Indirect Expenses'),
        ('depreciation',     'Depreciation'),
    ], string='Section')
    account_id   = fields.Many2one('account.account')
    account_code = fields.Char(string='Code')
    account_name = fields.Char(string='Account Name')
    amount       = fields.Float(digits=(16, 2))
    currency_id  = fields.Many2one('res.currency', related='report_id.currency_id')
