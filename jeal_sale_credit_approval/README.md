# jeal_sale_credit_approval

Límite de crédito y aprobación de ventas al crédito para **JE-AL** (Odoo 18 Enterprise).

**Autor:** Empiria
**Versión:** 18.0.1.0.0
**Depende de:** `sale`, `account`, `stock`, `mail`

## Qué hace

Impide confirmar una cotización **al crédito** cuando el cliente excede su
línea de crédito o tiene deuda vencida, salvo aprobación del aprobador desde
su correo (botones Aprobar / Rechazar, enlace de un solo uso de 72 h).

## Instalación

1. Copiar la carpeta `jeal_sale_credit_approval/` en el directorio de addons.
2. Actualizar la lista de aplicaciones e instalar el módulo.
3. Ir a **Ventas › Configuración › Ajustes**, bloque *Aprobación de crédito (JE-AL)*:
   - Elegir el **aprobador de crédito** (debe tener correo).
   - Definir la **vigencia del enlace** (72 h por defecto).
   - Activar **exigir aprobación con deuda vencida**.
   - Ajustar la **composición de la deuda total** (borradores, pedidos sin
     facturar, anticipos) según lo que confirme el cliente.
4. Asignar el grupo **Administrador de créditos** a los usuarios designados.
5. Cargar el **límite de crédito** por cliente (pestaña *Crédito* del contacto).

## Flujo

1. En la cotización se marca **Tipo de venta = Crédito**.
2. Al confirmar, si la deuda total + esta cotización excede el límite, o el
   cliente tiene deuda vencida, o el límite es 0, Odoo **bloquea** y pide
   **Enviar solicitud al aprobador**.
3. El aprobador recibe el correo y decide con **Aprobar / Rechazar** (página
   pública con token, segundo clic de confirmación).
4. Aprobado → el vendedor confirma. Rechazado → motivo obligatorio y aviso.
   Vencido (72 h) → el vendedor **Reenvía** con un enlace nuevo recalculado.
5. Si el importe sube por encima de lo aprobado, se pide nueva aprobación.

Toda la trazabilidad queda en el **chatter** del documento.

## Reportes

- **Ventas › Crédito › Reporte línea de crédito** (límite, deuda, vencida,
  disponible, % de uso por cliente).
- **Ventas › Crédito › Solicitudes de aprobación**.

## Nota de alcance

La **composición exacta de la deuda total** es parametrizable en Ajustes
porque el documento funcional no la fijó. Validar con el cliente qué piezas
entran antes de pasar a producción.

> Prototipo de referencia. Requiere pruebas de QA en un entorno de staging
> antes de usarse en producción.
