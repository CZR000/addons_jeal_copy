import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Recalcula los importes de retención de No Domiciliado en los
    comprobantes ya existentes.

    Al pasar Renta Bruta / Renta Neta / Tasa de Retención / Impuesto retenido
    a campos calculados, Odoo no recalcula por sí mismo las filas que ya tenían
    valor almacenado. Se fuerza aquí el recálculo para dejar consistente todo
    el histórico (muchos registros arrastraban valores incorrectos).
    """
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})

    try:
        moves = env['account.move'].search([
            ('move_type', 'in', ['in_invoice', 'in_refund']),
            ('is_nodomicilied', '=', True),
        ])
        if not moves:
            _logger.info('No hay comprobantes No Domiciliados que recalcular.')
            return

        fields_to_recompute = ['hard_rent', 'neto_rent', 'retention_rate', 'tax_withheld']
        for name in fields_to_recompute:
            env.add_to_compute(env['account.move']._fields[name], moves)
        moves.flush_recordset(fields_to_recompute)

        _logger.info('Recalculados %s comprobantes No Domiciliados: %s',
                     len(moves), fields_to_recompute)
    except Exception:
        # Nunca abortar el upgrade del módulo por el recálculo del histórico:
        # los computes dejarán los registros correctos al editarse.
        _logger.exception('No se pudo recalcular el histórico de No Domiciliados.')
