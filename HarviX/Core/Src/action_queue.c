#include "action_queue.h"
#include <string.h>
#include "FreeRTOS.h"
#include "cmsis_os2.h"
#include "task.h"
osMessageQueueId_t action_queue;




/* internal shortcut */
static int post(ActionCommand_t *cmd){
    return osMessageQueuePut(action_queue, cmd, 0,0) == pdTRUE;
}

/* GPIO*/
volatile ActionCommand_t cmd_dbg;
int action_post_gpio_write(GPIO_TypeDef *port, uint16_t pin , uint8_t state)
{

    ActionCommand_t cmd = {.type = ACT_GPIO_WRITE};
    cmd.u.gpio.port = port;
    cmd.u.gpio.pin = pin;
    cmd.u.gpio.state = state;
    cmd_dbg=cmd;
    return post(&cmd);
}

int action_post_gpio_toggle(GPIO_TypeDef *port, uint16_t pin)
{
    ActionCommand_t cmd = {.type = ACT_GPIO_TOGGLE};
    cmd.u.gpio.port = port;
    cmd.u.gpio.pin = pin;
    return post(&cmd);
}

int action_post_gpio_blink(GPIO_TypeDef *port, uint16_t pin, uint8_t count, uint16_t period_ms)
{
    ActionCommand_t cmd = {.type = ACT_GPIO_BLINK};
    cmd.u.gpio.port = port;
    cmd.u.gpio.pin = pin;
    cmd.u.gpio.count = count;
    cmd.u.gpio.period_ms = period_ms;
    return post(&cmd);
}

/* PWM */
int action_post_pwm_set(TIM_HandleTypeDef *htim, uint32_t channel, uint16_t duty)
{
    ActionCommand_t cmd = {.type = ACT_PWM_SET};
    cmd.u.pwm.htim = htim;
    cmd.u.pwm.channel = channel;
    cmd.u.pwm.duty = duty;
    return post(&cmd);
}

/* Buzzer */
int action_post_buzzer_beep(uint16_t freq_hz, uint16_t on_ms, uint16_t off_ms, uint8_t count)
{
    ActionCommand_t cmd = {.type = ACT_BUZZER_BEEP};
    cmd.u.buzzer.freq_hz = freq_hz;
    cmd.u.buzzer.on_ms = on_ms;
    cmd.u.buzzer.off_ms = off_ms;
    cmd.u.buzzer.count = count;
    return post(&cmd);
}

/* LCD */
int action_post_lcd_print(uint16_t x, uint16_t y, const char *text, uint32_t color, uint8_t font_size)
{
    ActionCommand_t cmd = {.type = ACT_LCD_PRINT};
    cmd.u.lcd_print.x = x;
    cmd.u.lcd_print.y = y;
    cmd.u.lcd_print.color = color;
    cmd.u.lcd_print.font_size = font_size;
    strncpy(cmd.u.lcd_print.text, text, ACTION_MAX_TEXT - 1);
    return post(&cmd);
}

int action_post_lcd_alert(AlertLevel_t level, const char *title, const char *msg, uint16_t timeout_ms)
{
    ActionCommand_t cmd = {.type = ACT_LCD_ALERT};
    cmd.u.lcd_alert.level = level;
    cmd.u.lcd_alert.timeout_ms = timeout_ms;
    strncpy(cmd.u.lcd_alert.title, title, ACTION_MAX_LABEL - 1);
    strncpy(cmd.u.lcd_alert.message, msg, ACTION_MAX_TEXT - 1);
    return post(&cmd);
}

int action_post_lcd_bar(uint16_t x, uint16_t y, uint16_t w, uint16_t h, float value, const char *label, uint32_t color)
{
    ActionCommand_t cmd = {.type = ACT_LCD_BAR};
    cmd.u.lcd_bar.x = x;
    cmd.u.lcd_bar.y = y;
    cmd.u.lcd_bar.w = w;
    cmd.u.lcd_bar.h = h;
    cmd.u.lcd_bar.value = value;
    cmd.u.lcd_bar.color = color;
    strncpy(cmd.u.lcd_bar.label, label, ACTION_MAX_LABEL - 1);
    return post(&cmd);
}

int action_post_lcd_clear(void)
{
    ActionCommand_t cmd = {.type = ACT_LCD_CLEAR};
    return post(&cmd);
}
