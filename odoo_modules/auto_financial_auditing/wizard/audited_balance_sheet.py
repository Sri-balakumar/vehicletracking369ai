# -*- coding: utf-8 -*-
"""
wizard/audited_balance_sheet.py
================================
Generates an Audited Balance Sheet that combines:
  - Opening balances from the original Odoo Balance Sheet (unchanged)
  - Movements only from AUDITED transactions (audit.transaction where state='audited')

Logic:
  Assets side:
    - Opening balances (all asset account types) up to date_from - 1 day
    - + Audited receivable credits/debits
    - + Audited cash movements
    - + Other current/fixed asset movements
    - + Direct expense accounts (stock/goods) from audited moves

  Liabilities & Equity side:
    - Opening balances (all liability + equity account types) up to date_from - 1
    - + Audited payable movements
    - + Audited liability movements
    - Equity including Current Year Audited Profit/Loss
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


class AuditedBalanceSheet(models.TransientModel):
    _name = 'audited.balance.sheet'
    _description = 'Audited Balance Sheet'

    name = fields.Char(string='Report Name', default='Audited Balance Sheet')

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

    date_from = fields.Date(
        string='Start Date',
        required=True,
        help='Opening balances are taken as of the day before this date.',
    )
    date_to = fields.Date(
        string='As of Date',
        required=True,
        default=fields.Date.context_today,
    )

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
    show_zero_balance = fields.Boolean(
        string='Show Zero Balance Accounts', default=False)

    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        compute='_compute_currency_id',
    )
    company_names = fields.Char(
        string='Company Names', compute='_compute_company_names')

    # Summary
    total_assets = fields.Monetary(currency_field='currency_id')
    total_liabilities = fields.Monetary(currency_field='currency_id')
    total_equity = fields.Monetary(currency_field='currency_id')
    audited_net_profit = fields.Monetary(
        string='Audited Net Profit/Loss', currency_field='currency_id')

    report_line_ids = fields.One2many(
        'audited.balance.sheet.line', 'report_id', string='Report Lines')

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _company_ids(self):
        """Return list of company IDs to query."""
        self.ensure_one()
        companies = self.company_ids
        for c in self.company_ids:
            companies |= c.child_ids
        return companies.ids

    def _get_opening_balance(self, account_types, opening_date):
        """
        Opening balance = all posted move lines up to (date_from - 1 day)
        for the given account types.  This matches the original Odoo BS logic.
        """
        company_ids = self._company_ids()
        domain = [
            ('company_id', 'in', company_ids),
            ('account_id.account_type', 'in', account_types),
            ('date', '<=', opening_date),
        ]
        if self.target_move == 'posted':
            domain.append(('move_id.state', '=', 'posted'))

        lines = self.env['account.move.line'].search(domain)
        accounts = {}
        for ml in lines:
            aid = ml.account_id.id
            if aid not in accounts:
                accounts[aid] = {
                    'account_id': aid,
                    'code': ml.account_id.code or '',
                    'name': ml.account_id.name,
                    'balance': 0.0,
                    'opening': True,
                }
            accounts[aid]['balance'] += ml.balance
        return accounts

    def _get_audited_move_ids(self):
        """Return all account.move IDs that have been audited (state='audited')."""
        audits = self.env['audit.transaction'].search([
            ('state', '=', 'audited'),
            ('transaction_date', '>=', self.date_from),
            ('transaction_date', '<=', self.date_to),
            ('company_id', 'in', self._company_ids()),
        ])
        return audits.mapped('move_id').ids

    def _get_audited_balance(self, account_types, move_ids):
        """
        Get account balances from ONLY the audited moves within date range.
        """
        if not move_ids:
            return {}

        domain = [
            ('move_id', 'in', move_ids),
            ('account_id.account_type', 'in', account_types),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        lines = self.env['account.move.line'].search(domain)
        accounts = {}
        for ml in lines:
            aid = ml.account_id.id
            if aid not in accounts:
                accounts[aid] = {
                    'account_id': aid,
                    'code': ml.account_id.code or '',
                    'name': ml.account_id.name,
                    'balance': 0.0,
                    'opening': False,
                }
            accounts[aid]['balance'] += ml.balance
        return accounts

    def _merge_accounts(self, opening, audited):
        """
        Merge opening balances with audited period movements.
        Returns combined dict keyed by account_id.
        """
        result = dict(opening)
        for aid, adata in audited.items():
            if aid in result:
                result[aid]['balance'] += adata['balance']
            else:
                result[aid] = dict(adata)
        return result

    def _compute_audited_profit(self, move_ids):
        """
        Audited Net Profit = Audited Revenue - Audited COGS - Audited Indirect Expenses
        Uses ONLY the audited moves.
        """
        if not move_ids:
            return 0.0

        income_types  = ['income', 'income_other']
        expense_types = ['expense', 'expense_depreciation']

        domain_base = [
            ('move_id', 'in', move_ids),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]

        income_lines  = self.env['account.move.line'].search(
            domain_base + [('account_id.account_type', 'in', income_types)])
        expense_lines = self.env['account.move.line'].search(
            domain_base + [('account_id.account_type', 'in', expense_types)])

        income  = sum(income_lines.mapped('balance'))
        expense = sum(expense_lines.mapped('balance'))

        # Income = credit (negative balance), Expense = debit (positive balance)
        net_profit = -(income + expense)
        return net_profit

    # ------------------------------------------------------------------
    # Main report generation
    # ------------------------------------------------------------------
    def action_generate_report(self):
        self.ensure_one()
        self.report_line_ids.unlink()

        opening_date = self.date_from - timedelta(days=1)
        audited_move_ids = self._get_audited_move_ids()

        ASSET_TYPES = [
            'asset_receivable', 'asset_cash',
            'asset_current', 'asset_prepayments',
            'asset_fixed', 'asset_non_current',
        ]
        DIRECT_EXP_TYPES = ['expense_direct_cost']
        LIABILITY_TYPES = [
            'liability_payable', 'liability_current',
            'liability_non_current',
        ]
        EQUITY_TYPES = ['equity', 'equity_unaffected']

        lines_to_create = []
        seq = 0
        total_assets = 0.0
        total_liabilities = 0.0
        total_equity = 0.0

        def _add_line(name, balance, level, line_type):
            nonlocal seq
            seq += 1
            lines_to_create.append({
                'report_id': self.id,
                'name': name,
                'sequence': seq,
                'level': level,
                'line_type': line_type,
                'balance': balance,
            })

        # ================================================================
        # ASSETS
        # ================================================================
        _add_line('═══ ASSETS ═══', 0, 0, 'section_header')

        # --- Current Assets (Opening + Audited movements) ---
        opening_assets  = self._get_opening_balance(ASSET_TYPES, opening_date)
        audited_assets  = self._get_audited_balance(ASSET_TYPES, audited_move_ids)
        combined_assets = self._merge_accounts(opening_assets, audited_assets)

        current_types = ['asset_receivable', 'asset_cash',
                         'asset_current', 'asset_prepayments']
        fixed_types   = ['asset_fixed', 'asset_non_current']

        def _render_section(section_name, filter_types, combined, sign=1):
            nonlocal total_assets
            section_total = 0.0
            details = []
            for aid, adata in combined.items():
                acc = self.env['account.account'].browse(aid)
                if acc.account_type not in filter_types:
                    continue
                bal = adata['balance'] * sign
                if not self.show_zero_balance and abs(bal) < 0.01:
                    continue
                label = f"  {adata['code']} - {adata['name']}" if adata['code'] else f"  {adata['name']}"
                details.append((label, bal, aid))
                section_total += bal
            _add_line(section_name, section_total, 1, 'section')
            for label, bal, aid in details:
                nonlocal seq
                seq += 1
                lines_to_create.append({
                    'report_id': self.id,
                    'name': label,
                    'sequence': seq,
                    'level': 2,
                    'line_type': 'account',
                    'balance': bal,
                    'account_id': aid,
                })
            return section_total

        ca_total = _render_section('Current Assets', current_types, combined_assets)
        total_assets += ca_total

        # --- Direct Expenses / Stock / Goods (Opening + Audited) ---
        opening_de  = self._get_opening_balance(DIRECT_EXP_TYPES, opening_date)
        audited_de  = self._get_audited_balance(DIRECT_EXP_TYPES, audited_move_ids)
        combined_de = self._merge_accounts(opening_de, audited_de)
        de_total    = _render_section(
            'Stock / Goods (Direct Expenses)', DIRECT_EXP_TYPES, combined_de)
        total_assets += de_total

        # --- Fixed Assets ---
        fa_total = _render_section('Fixed Assets', fixed_types, combined_assets)
        total_assets += fa_total

        _add_line('TOTAL ASSETS', total_assets, 0, 'total')

        # ================================================================
        # LIABILITIES & EQUITY
        # ================================================================
        _add_line('═══ LIABILITIES & EQUITY ═══', 0, 0, 'section_header')

        opening_liab  = self._get_opening_balance(LIABILITY_TYPES, opening_date)
        audited_liab  = self._get_audited_balance(LIABILITY_TYPES, audited_move_ids)
        combined_liab = self._merge_accounts(opening_liab, audited_liab)

        # Current Liabilities
        cur_liab_types = ['liability_payable', 'liability_current']
        cl_total = 0.0
        cl_details = []
        for aid, adata in combined_liab.items():
            acc = self.env['account.account'].browse(aid)
            if acc.account_type not in cur_liab_types:
                continue
            bal = -adata['balance']  # liabilities are credit (negative in Odoo)
            if not self.show_zero_balance and abs(bal) < 0.01:
                continue
            label = f"  {adata['code']} - {adata['name']}" if adata['code'] else f"  {adata['name']}"
            cl_details.append((label, bal, aid))
            cl_total += bal
        _add_line('Current Liabilities', cl_total, 1, 'section')
        for label, bal, aid in cl_details:
            seq += 1
            lines_to_create.append({
                'report_id': self.id, 'name': label,
                'sequence': seq, 'level': 2,
                'line_type': 'account', 'balance': bal, 'account_id': aid,
            })
        total_liabilities += cl_total

        # Non-Current Liabilities
        ncl_total = 0.0
        ncl_details = []
        for aid, adata in combined_liab.items():
            acc = self.env['account.account'].browse(aid)
            if acc.account_type != 'liability_non_current':
                continue
            bal = -adata['balance']
            if not self.show_zero_balance and abs(bal) < 0.01:
                continue
            label = f"  {adata['code']} - {adata['name']}" if adata['code'] else f"  {adata['name']}"
            ncl_details.append((label, bal, aid))
            ncl_total += bal
        _add_line('Non-Current Liabilities', ncl_total, 1, 'section')
        for label, bal, aid in ncl_details:
            seq += 1
            lines_to_create.append({
                'report_id': self.id, 'name': label,
                'sequence': seq, 'level': 2,
                'line_type': 'account', 'balance': bal, 'account_id': aid,
            })
        total_liabilities += ncl_total

        # Equity
        opening_eq  = self._get_opening_balance(EQUITY_TYPES, opening_date)
        audited_eq  = self._get_audited_balance(EQUITY_TYPES, audited_move_ids)
        combined_eq = self._merge_accounts(opening_eq, audited_eq)

        eq_total = 0.0
        eq_details = []
        for aid, adata in combined_eq.items():
            bal = -adata['balance']
            if not self.show_zero_balance and abs(bal) < 0.01:
                continue
            label = f"  {adata['code']} - {adata['name']}" if adata['code'] else f"  {adata['name']}"
            eq_details.append((label, bal, aid))
            eq_total += bal
        _add_line('Equity', eq_total, 1, 'section')
        for label, bal, aid in eq_details:
            seq += 1
            lines_to_create.append({
                'report_id': self.id, 'name': label,
                'sequence': seq, 'level': 2,
                'line_type': 'account', 'balance': bal, 'account_id': aid,
            })
        total_equity += eq_total

        # Audited Current Year Profit / Loss
        audited_profit = self._compute_audited_profit(audited_move_ids)
        _add_line('Current Year Audited Profit / Loss', audited_profit, 1, 'profit_loss')
        seq += 1
        lines_to_create.append({
            'report_id': self.id,
            'name': '  Audited Net Profit / Loss',
            'sequence': seq, 'level': 2,
            'line_type': 'profit_loss',
            'balance': audited_profit,
        })
        total_equity += audited_profit

        # Grand total
        _add_line('TOTAL LIABILITIES & EQUITY',
                  total_liabilities + total_equity, 0, 'total')

        # Create all lines
        self.env['audited.balance.sheet.line'].create(lines_to_create)

        self.write({
            'total_assets':      total_assets,
            'total_liabilities': total_liabilities,
            'total_equity':      total_equity,
            'audited_net_profit': audited_profit,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Audited Balance Sheet'),
            'res_model': 'audited.balance.sheet',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'views': [(
                self.env.ref(
                    'auto_financial_auditing.view_audited_balance_sheet_result'
                ).id, 'form'
            )],
        }

    def action_print_pdf(self):
        self.ensure_one()
        if not self.report_line_ids:
            raise UserError(_('Please generate the report first.'))
        return self.env.ref(
            'auto_financial_auditing.action_report_audited_balance_sheet'
        ).report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.report_line_ids:
            raise UserError(_('Please generate the report first.'))
        if not xlsxwriter:
            raise UserError(_('xlsxwriter library is required. Run: pip install xlsxwriter'))

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('Audited Balance Sheet')

        title_fmt   = wb.add_format({'bold': True, 'font_size': 16, 'align': 'center',
                                      'bg_color': '#1B4F72', 'font_color': 'white', 'border': 1})
        header_fmt  = wb.add_format({'bold': True, 'bg_color': '#D5E8D4', 'border': 1})
        section_fmt = wb.add_format({'bold': True, 'bg_color': '#F2F2F2', 'border': 1, 'font_size': 11})
        account_fmt = wb.add_format({'indent': 2, 'border': 1})
        total_fmt   = wb.add_format({'bold': True, 'bg_color': '#1B4F72', 'font_color': 'white',
                                      'border': 2, 'font_size': 12})
        money_fmt   = wb.add_format({'num_format': '#,##0.00', 'border': 1, 'align': 'right'})
        money_bold  = wb.add_format({'num_format': '#,##0.00', 'bold': True, 'border': 1, 'align': 'right', 'bg_color': '#F2F2F2'})
        money_total = wb.add_format({'num_format': '#,##0.00', 'bold': True, 'border': 2, 'align': 'right',
                                      'bg_color': '#1B4F72', 'font_color': 'white'})
        money_pl    = wb.add_format({'num_format': '#,##0.00', 'bold': True, 'border': 1, 'align': 'right', 'bg_color': '#FFF2CC'})
        pl_lbl_fmt  = wb.add_format({'bold': True, 'bg_color': '#FFF2CC', 'border': 1})

        ws.set_column('A:A', 55)
        ws.set_column('B:B', 22)

        ws.merge_range('A1:B1', self.company_names or '', title_fmt)
        ws.merge_range('A2:B2', f'AUDITED BALANCE SHEET as of {self.date_to.strftime("%d/%m/%Y")}',
                       wb.add_format({'bold': True, 'font_size': 12, 'align': 'center', 'border': 1}))
        ws.merge_range('A3:B3',
                       f'Audited Period: {self.date_from.strftime("%d/%m/%Y")} — {self.date_to.strftime("%d/%m/%Y")}',
                       wb.add_format({'align': 'center', 'border': 1, 'italic': True}))
        ws.write(3, 0, 'Particulars', header_fmt)
        ws.write(3, 1, 'Amount', header_fmt)

        row = 4
        for line in self.report_line_ids.sorted('sequence'):
            lt = line.line_type
            if lt == 'section_header':
                ws.write(row, 0, line.name, section_fmt)
                ws.write(row, 1, '', section_fmt)
            elif lt == 'section':
                ws.write(row, 0, line.name, section_fmt)
                ws.write(row, 1, line.balance, money_bold)
            elif lt == 'total':
                ws.write(row, 0, line.name, total_fmt)
                ws.write(row, 1, line.balance, money_total)
            elif lt == 'profit_loss':
                ws.write(row, 0, line.name, pl_lbl_fmt)
                ws.write(row, 1, line.balance, money_pl)
            else:
                ws.write(row, 0, line.name, account_fmt)
                ws.write(row, 1, line.balance, money_fmt)
            row += 1

        wb.close()
        output.seek(0)
        att = self.env['ir.attachment'].create({
            'name': f'Audited_Balance_Sheet_{self.date_to.strftime("%Y%m%d")}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{att.id}?download=true',
            'target': 'new',
        }


class AuditedBalanceSheetLine(models.TransientModel):
    _name = 'audited.balance.sheet.line'
    _description = 'Audited Balance Sheet Line'
    _order = 'sequence'

    report_id  = fields.Many2one('audited.balance.sheet', ondelete='cascade')
    name       = fields.Char(string='Particulars')
    sequence   = fields.Integer(default=10)
    level      = fields.Integer(default=0)
    line_type  = fields.Selection([
        ('section_header', 'Section Header'),
        ('section',        'Section'),
        ('account',        'Account'),
        ('total',          'Total'),
        ('profit_loss',    'Profit/Loss'),
    ], string='Line Type')
    balance    = fields.Float(digits=(16, 2))
    account_id = fields.Many2one('account.account')
    currency_id = fields.Many2one('res.currency', related='report_id.currency_id')
