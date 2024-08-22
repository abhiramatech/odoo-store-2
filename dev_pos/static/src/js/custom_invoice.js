/** @odoo-module **/

import { registry } from "@web/core/registry";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

class CustomPaymentScreen extends PaymentScreen {
    onMounted() {
        super.onMounted();
        this.currentOrder.set_to_invoice(true);
    }
}

registry.category("pos_screens").add("PaymentScreen", CustomPaymentScreen, { force: true });
