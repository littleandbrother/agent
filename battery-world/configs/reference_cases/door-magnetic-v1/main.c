/* BF pluck reference beacon. Uses Nordic S132 SDK APIs from pinned ViPSN.
 * Engineering derivative, not the paper's exact firmware. Build is not a flash
 * or energy measurement. No persistent event sequence: receiver groups bursts.
 */
#include <stdint.h>
#include <string.h>
#include "nrf.h"
#include "nrf_gpio.h"
#include "ble.h"
#include "ble_advdata.h"
#include "softdevice_handler.h"
#include "app_error.h"

void assert_nrf_callback(uint16_t line, const uint8_t *file) {
    app_error_handler(0xDEADBEEF, line, file);
}

int main(void) {
    /* No external 32 kHz crystal on this module carrier. */
    nrf_clock_lf_cfg_t clock = {NRF_CLOCK_LF_SRC_RC, 16, 2, NRF_CLOCK_LF_XTAL_ACCURACY_500_PPM};
    nrf_gpio_cfg_output(12); nrf_gpio_pin_clear(12);
    nrf_gpio_cfg_input(11, NRF_GPIO_PIN_NOPULL);
    /* PGOOD push-pull from LTC3588-1. Never start RF while output is low. */
    if (!nrf_gpio_pin_read(11)) { nrf_gpio_cfg_sense_input(11, NRF_GPIO_PIN_NOPULL, NRF_GPIO_PIN_SENSE_HIGH); NRF_POWER->SYSTEMOFF = 1; for (;;) { __WFE(); } }
    nrf_gpio_pin_set(12);
    SOFTDEVICE_HANDLER_INIT(&clock, NULL);
    ble_enable_params_t params;
    APP_ERROR_CHECK(softdevice_enable_get_default_config(0, 0, &params));
    APP_ERROR_CHECK(softdevice_enable(&params));

    /* Manufacturer 0xffff = internal prototype, not a production assignment.
     * "BFD2" + device ID, stable across cold starts. Direction is receiver-side.
     */
    uint8_t payload[12] = {'B','F','D','2'};
    uint32_t id[2] = {NRF_FICR->DEVICEID[0], NRF_FICR->DEVICEID[1]};
    memcpy(payload+4, id, sizeof id);
    ble_advdata_manuf_data_t manufacturer = {0};
    manufacturer.company_identifier = 0xffff;
    manufacturer.data.p_data = payload;
    manufacturer.data.size = sizeof payload;
    ble_advdata_t data = {0};
    data.name_type = BLE_ADVDATA_NO_NAME;
    data.flags = BLE_GAP_ADV_FLAG_BR_EDR_NOT_SUPPORTED;
    data.p_manuf_specific_data = &manufacturer;
    APP_ERROR_CHECK(ble_advdata_set(&data, NULL));
    ble_gap_adv_params_t advertising = {0};
    advertising.type = BLE_GAP_ADV_TYPE_ADV_NONCONN_IND;
    advertising.fp = BLE_GAP_ADV_FP_ANY;
    advertising.interval = 160; /* 100 ms / 0.625 ms; plus BLE random delay. */
    advertising.timeout = 0;
    APP_ERROR_CHECK(sd_ble_gap_tx_power_set(0));
    APP_ERROR_CHECK(sd_ble_gap_adv_start(&advertising));
    for (;;) {
        if (!nrf_gpio_pin_read(11)) {
            (void)sd_ble_gap_adv_stop(); nrf_gpio_pin_clear(12);
            nrf_gpio_cfg_sense_input(11, NRF_GPIO_PIN_NOPULL, NRF_GPIO_PIN_SENSE_HIGH);
            (void)sd_power_system_off();
        }
        APP_ERROR_CHECK(sd_app_evt_wait());
    }
}
