from odoo import fields, models


class PpaSource(models.Model):
    _name = "ppa.source"
    _description = "PPA Source"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The source code must be unique.")
