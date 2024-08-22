/** @odoo-module **/
import { _t } from "@web/core/l10n/translation";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { BookOrderPopup } from "./pop_up_card"; // Import BookOrderPopup
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";

class BookedOrdersButton extends Component {
    static template = 'dev_pos.BookedOrdersButton';
    
    setup() {
        this.pos = usePos();
        this.popup = useService("popup");
    }
    async onClick() {
        var order=this.pos.selectedOrder
        var order_lines = order.orderlines;
        var partner = order.partner
        if (partner == null) {
            this.pos.popup.add(ErrorPopup, {
                    title: _t("Please Select the Customer"),
                    body: _t(
                        "You need to select a customer for using this option"
                    ),
                });
        } else if (order_lines.length == 0) {
            this.pos.popup.add(ErrorPopup, {
                    title: _t("Order line is empty"),
                    body: _t(
                        "Please select at least one product"
                    ),
                });
        } else {
          await this.pos.popup.add(BookOrderPopup, {
            title: _t("Card Member"),
        });
        }
    }
}

ProductScreen.addControlButton({
    component: BookedOrdersButton,
    condition: () => true
});
