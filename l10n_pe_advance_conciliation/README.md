# Anticipos y Revolventes (`l10n_pe_advance_conciliation`)

Módulo Odoo 18 para el control de anticipos de clientes/proveedores y
revolventes mediante documentos con saldo propio (ANTC / REV), con creación,
aplicación y conciliación automáticas.

**Autor:** Empiria · **Versión:** 18.0.1.0.0 · **Cliente:** JEAL

## Qué hace

- Al publicar una factura con un producto de rol *Origen*, crea el documento
  de anticipo (ANTC) con su saldo.
- Un depósito al haber de la cuenta de control del revolvente crea el documento
  REV.
- Wizard **Aplicar anticipos** (facturas en borrador): inserta la línea negativa
  y concilia la cuenta de control al publicar.
- Wizard **Aplicar revolvente** (facturas publicadas): reparte por FIFO y genera
  el asiento de compensación automático.
- Wizard **Cerrar saldo residual** por tolerancia de redondeo.
- Reportes: saldos por documento (lista/pivote/gráfico), estado de cuenta (PDF)
  y cuadre del módulo contra el mayor.

## Instalación

1. Copiar la carpeta a `addons/`.
2. Actualizar lista de aplicaciones e instalar **Anticipos y Revolventes**.
3. Configurar en *Anticipos y Revolventes → Configuración*.

Ver la guía de configuración y los casos de prueba entregados por separado.

## Pendientes de decisión (ver documento de diseño, sección 10)

1. **Tipo de cambio entre monedas.** Por defecto el módulo usa el TC de la
   factura/fecha del movimiento (`currency._convert`). Está marcado en el código
   como el punto a confirmar con contabilidad.
2. **Disparador del revolvente.** Acotado por `revolving_journal_ids` en la
   configuración: solo los diarios listados crean revolvente. Si se deja vacío,
   cualquier haber a la cuenta lo dispara.
3. **Facturación electrónica (SUNAT).** Las líneas negativas van dentro de la
   factura; validar la emisión con el módulo de e-invoicing en uso.
4. **Migración de saldos iniciales.** Wizard preliminar incluido; dimensionar y
   validar contra el cuadre.

## Nota

Este módulo requiere pruebas en una instancia Odoo 18 real. La lógica de
conciliación, el cálculo de IGV incluido en las líneas de aplicación y el
tratamiento multimoneda del depósito son los puntos a verificar primero.
