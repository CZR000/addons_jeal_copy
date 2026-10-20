from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """One-time backfill: assign the 7-digit PLE correlative (account.asset.ple_code)
    to every existing asset that doesn't already have one, in acquisition/creation
    order. Runs exactly once, tied to this module version. New assets created after
    this get their code from AccountAsset.create() instead."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['account.asset']._assign_ple_asset_codes()
