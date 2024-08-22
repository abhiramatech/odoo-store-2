# -*- coding: utf-8 -*-
from odoo import fields, models, api
from datetime import datetime, time
from pytz import UTC

class EndShiftSession(models.Model):
    _name = 'end.shift'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "End Shift Session per Cashier"

    doc_num = fields.Char(string='Shift Number', tracking=True, readonly=True)
    cashier_id = fields.Many2one('hr.employee', string='Cashier', tracking=True, required=True)
    session_id = fields.Many2one('pos.session', string='Session', tracking=True, required=True)
    start_date = fields.Datetime(string='Start Date', tracking=True)
    end_date = fields.Datetime(string='End Date', tracking=True)
    state = fields.Selection([
        ('opened', 'Opened'),
        ('in_progress', 'In Progress'),
        ('closed', 'Closed'),
        ('finished', 'Finished')
    ], string='Status', default='opened', required=True, readonly=True, copy=False, tracking=True)

    line_ids = fields.One2many('end.shift.line', 'end_shift_id', string='Shift Lines', context={'parent_state': 'state'})

    pos_order_count = fields.Integer(string='POS Orders', compute='_compute_pos_order_count')

    @api.depends('cashier_id', 'session_id')
    def _compute_pos_order_count(self):
        for record in self:
            # Mendapatkan tanggal hari ini dalam waktu lokal server
            start_date_str = fields.Datetime.to_string(self.start_date)
            end_date_str = fields.Datetime.to_string(self.end_date)

            record.pos_order_count = self.env['pos.order'].search_count([
                ('session_id', '=', record.session_id.id),
                ('employee_id', '=', record.cashier_id.id),
                ('state', '=', 'invoiced'),
                ('create_date', '>=', start_date_str),
                ('create_date', '<=', end_date_str)
            ])

    def action_view_pos_orders(self):
        self.ensure_one()
        
        # Menggunakan start_date dan end_date dari record end.shift
        start_date_str = fields.Datetime.to_string(self.start_date)
        end_date_str = fields.Datetime.to_string(self.end_date)

        domain = [
            ('session_id', '=', self.session_id.id),
            ('employee_id', '=', self.cashier_id.id),
            ('state', '=', 'invoiced'),
            ('create_date', '>=', start_date_str),
            ('create_date', '<=', end_date_str)
        ]

        # Untuk debugging
        orders = self.env['pos.order'].search(domain)
        print(f"Jumlah pesanan yang ditemukan: {len(orders)}")
        for order in orders:
            print(f"Order ID: {order.id}, Create Date: {order.create_date}")

        return {
            'name': 'POS Orders',
            'type': 'ir.actions.act_window',
            'res_model': 'pos.order',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {'create': False}
        }

    @api.model
    def create(self, vals):
        vals['state'] = 'opened'
        return super(EndShiftSession, self).create(vals)

    def action_start_progress(self):
        for record in self:
            record.state = 'in_progress'
            record.line_ids.write({'state': 'in_progress'})

    def action_close(self):
        for record in self:
            # Update end_date to current time
            current_time = fields.Datetime.now()
            record.write({
                'end_date': current_time,
                'state': 'closed'
            })

            # Mencari pos.order yang sesuai
            pos_orders = self.env['pos.order'].search([
                ('session_id', '=', record.session_id.id),
                ('state', '=', 'invoiced'),
                ('create_date', '>=', record.start_date),
                ('create_date', '<=', record.end_date)
            ])

            payment_data = {}
            for order in pos_orders:
                payments = order.payment_ids
                for payment in payments:
                    method_id = payment.payment_method_id.id
                    amount = payment.amount
                    payment_date = payment.payment_date

                    if method_id in payment_data:
                        payment_data[method_id]['expected_amount'] += amount
                        if payment_date > payment_data[method_id]['payment_date']:
                            payment_data[method_id]['payment_date'] = payment_date
                    else:
                        payment_data[method_id] = {
                            'payment_method_id': method_id,
                            'expected_amount': amount,
                            'payment_date': payment_date,
                        }

            # Hapus line_ids yang ada dan buat yang baru
            record.line_ids.unlink()
            for line_data in payment_data.values():
                self.env['end.shift.line'].create({
                    'end_shift_id': record.id,
                    'payment_method_id': line_data['payment_method_id'],
                    'expected_amount': line_data['expected_amount'],
                    'payment_date': line_data['payment_date'],
                    'state': 'closed',
                })

    def action_finish(self):
        for record in self:
            record.state = 'finished'
            record.line_ids.write({'state': 'finished'})
            
            cashier_logs = self.env['pos.cashier.log'].search([
                ('employee_id', '=', record.cashier_id.id),
                ('session_id', '=', record.session_id.id),
                ('state', '!=', 'closed')
            ])
            if cashier_logs:
                cashier_logs.write({'state': 'closed'})

    # def action_reset(self):
    #     for record in self:
    #         record.state = 'opened'
    #         record.line_ids.write({'state': 'opened'})

class EndShiftSessionLine(models.Model):
    _name = 'end.shift.line'
    _description = "End Shift Line Session per Cashier"

    end_shift_id = fields.Many2one('end.shift', string='End Shift Session', required=True, ondelete='cascade')
    payment_date = fields.Datetime(string='Date', tracking=True)
    payment_method_id = fields.Many2one('pos.payment.method', string="Payment Method", tracking=True, required=True)
    amount = fields.Float(string="Amount", tracking=True)
    expected_amount = fields.Float(string="Expected Amount", tracking=True)
    amount_difference = fields.Float(string="Amount Difference", compute='_compute_amount_difference', store=True, tracking=True)
    state = fields.Selection([
        ('opened', 'Opened'),
        ('in_progress', 'In Progress'),
        ('closed', 'Closed'),
        ('finished', 'Finished')
    ], string='Status', default='opened', required=True, readonly=True, copy=False, tracking=True)
            
    @api.depends('amount', 'expected_amount')
    def _compute_amount_difference(self):
        for record in self:
            record.amount_difference = record.amount - record.expected_amount

    @api.model
    def create(self, vals):
        res = super(EndShiftSessionLine, self).create(vals)
        res._compute_amount_difference()
        return res

    def write(self, vals):
        res = super(EndShiftSessionLine, self).write(vals)
        if 'amount' in vals or 'expected_amount' in vals:
            self._compute_amount_difference()
        return res