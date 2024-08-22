/** @odoo-module */

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { _t } from "@web/core/l10n/translation";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";


export class BookOrderPopup extends AbstractAwaitablePopup {
    static template = "dev_pos.BookOrderPopup";
    static defaultProps = {
        confirmText: _t("Save"),
        cancelText: _t("Discard"),
        title: _t("Book Order"),
    };
    setup() {
        super.setup();
        this.pos = usePos();
        this.orm = useService("orm");
        this.nameField = useRef("nameField");
        this.cardNumberField = useRef("cardNumberField");
    }

    async confirm() {
        const name = this.nameField.el.value;
        const cardNumber = this.cardNumberField.el.value;
    
        const cardData = await this.orm.call("card.number", "search", [[['card_num', '=', cardNumber], ['name', '=', name]]]);
    
        if (cardData.length > 0) {
            const discountPercentage = 10; 
            const totalAmount = this.pos.get_order().get_total_with_tax(); 
            const discountAmount = totalAmount * (discountPercentage / 100);
    
            const order = this.pos.get_order();
            for (let line of order.get_orderlines()) {
                line.set_discount(discountPercentage);
            }
    
            this.cancel();
        } else {
            alert("Nama atau nomor kartu tidak valid. Diskon tidak dapat diterapkan.");
            this.cancel();
        }
    }
}    
