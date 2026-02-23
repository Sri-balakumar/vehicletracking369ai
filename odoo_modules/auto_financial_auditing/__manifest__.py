# -*- coding: utf-8 -*-
{
    'name': 'Automatic Financial Auditing',
    'version': '19.0.1.0.0',
    'summary': 'Transaction Auditing, Audited Balance Sheet & Audited P&L',
    'description': """
        Automatic Financial Auditing Module for Odoo 19
        ================================================
        Features:
        - Transaction Auditing Form (with dropdown of all transactions)
        - Audited Balance Sheet (based on audited transactions + opening balances)
        - Audited Profit & Loss Report (only audited entries accepted)
        - Digital signatures for Customer and Cashier
        - PDF/Excel export for all reports
    """,
    'author': 'Your Company',
    'category': 'Accounting/Accounting',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'report/audit_transaction_report_template.xml',
        'report/audit_transaction_report_action.xml',
        'report/audited_balance_sheet_template.xml',
        'report/audited_balance_sheet_action.xml',
        'report/audited_pnl_template.xml',
        'report/audited_pnl_action.xml',
        'wizard/audited_balance_sheet_wizard_views.xml',
        'wizard/audited_pnl_wizard_views.xml',
        'views/audit_transaction_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'auto_financial_auditing/static/src/css/audit.css',
            'auto_financial_auditing/static/src/xml/signature_pad_widget.xml',
            'auto_financial_auditing/static/src/js/signature_pad_widget.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
