#ifndef ACTION_QUEUE_H
#define ACTION_QUEUE_H

#include "FreeRTOS.h"
#include "queue.h"
#include "cmsis_os2.h"
#include "stm32f4xx_hal.h"
#include <stdint.h>
#include <stdint.h>

#define ACTION_QUEUE_LENGTH 16
#define ACTION_MAX_TEXT 48
#define ACTION_MAX_LABEL 24

/* alert severity levels (used by ACT_LCD_ALERT) */
typedef enum {
    ALERT_INFO, /* blue overlay */
    ALERT_WARN, /* orange overlay */
    ALERT_ERROR /* red overlay */
}AlertLevel_t;

/* every action the task can perform */
typedef enum {
    ACT_GPIO_WRITE, /* set a GPIO pin high or low */
    ACT_GPIO_TOGGLE, /* toggle a GPIO pin */
    ACT_GPIO_BLINK, /* link a GPIO pin to a sensor reading (e.g. turn on an LED when PM2.5 > 35) */
    ACT_PWM_SET, /* set a PWM duty cycle (e.g. for a fan) */
    ACT_BUZZER_BEEP, /* beep a buzzer for a specified duration */
    ACT_LCD_PRINT, /* print text to the LCD */
    ACT_LCD_ALERT, /* show an alert on the LCD with a severity level */
    ACT_LCD_BAR, /* display a bar graph on the LCD (e.g. for PM2.5 levels) */
    ACT_LCD_CLEAR, /* clear the LCD */
}ActionType_t;

/* payloads , one per action type */
typedef struct {
    GPIO_TypeDef *port;
    uint16_t pin;
    uint8_t state; /* for ACT_GPIO_WRITE */
    uint8_t count;
    uint16_t period_ms; /* for ACT_GPIO_BLINK */
}GpioPayload_t;

typedef struct {
    TIM_HandleTypeDef *htim;
    uint32_t channel;
    uint16_t duty;
}PwmPayload_t;

typedef struct {
    uint16_t freq_hz;
    uint16_t on_ms;
    uint16_t off_ms;
    uint8_t count;
}BuzzerPayload_t;

typedef struct {
    uint16_t x, y;
    char text[ACTION_MAX_TEXT];
    uint32_t color; /* RGB565 color for text */
    uint8_t font_size; /* font size for text */
}LcdPrintPayload_t;

typedef struct {
    AlertLevel_t level;
    char title[ACTION_MAX_LABEL];
    char message[ACTION_MAX_TEXT];
    uint16_t timeout_ms; /* how long to show the alert before clearing */
}LcdAlertPayload_t;

typedef struct {
    uint16_t x, y, w, h;
    float value; /* value to display (e.g. PM2.5 concentration) */
    char label[ACTION_MAX_LABEL]; /* label to show next to the bar (e.g. "PM2.5") */
    uint32_t color; /* RGB565 color for the bar */
}LcdBarPayload_t;

/* the struct that actually goes into the queue */
typedef struct {
    ActionType_t type;
    union {
        GpioPayload_t gpio;
        PwmPayload_t pwm;
        BuzzerPayload_t buzzer;
        LcdPrintPayload_t lcd_print;
        LcdAlertPayload_t lcd_alert;
        LcdBarPayload_t lcd_bar;
    } u;
}ActionCommand_t;

/* queue handle  (defined in action_queue.c) */
extern osMessageQueueId_t action_queue;

/* public API*/
int action_queue_init(void);

int action_post_gpio_write (GPIO_TypeDef *port, uint16_t pin, uint8_t state);
int action_post_gpio_toggle(GPIO_TypeDef *port, uint16_t pin);
int action_post_gpio_blink (GPIO_TypeDef *port, uint16_t pin,uint8_t count, uint16_t period_ms);

int action_post_pwm_set    (TIM_HandleTypeDef *htim,uint32_t ch, uint16_t duty_permille);

int action_post_buzzer_beep(uint16_t freq_hz, uint16_t on_ms,uint16_t off_ms, uint8_t count);

int action_post_lcd_print  (uint16_t x, uint16_t y, const char *text,uint32_t color, uint8_t font_size);
int action_post_lcd_alert  (AlertLevel_t level, const char *title,const char *msg, uint16_t timeout_ms);
int action_post_lcd_bar    (uint16_t x, uint16_t y, uint16_t w, uint16_t h,float value, const char *label, uint32_t color);
int action_post_lcd_clear  (void);
#endif // ACTION_QUEUE_H
